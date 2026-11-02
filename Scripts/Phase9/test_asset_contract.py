"""Probe Phase9 asset rejection before graph creation, using an explicit runtime.

Only malformed assets are launched. No socket is opened by this driver and no
commands are sent to any service. Each hidden child is owned through its Popen
handle, has a bounded timeout, and is reaped before the next case. Positive
absent/null/empty-tag compatibility and physical behavior are outside this
launcher; the unchanged native35 suite retains its legacy Phase3/4 coverage.
--plan-only writes nothing and launches nothing.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import sys
import time


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
OUTPUT_SCHEMA = 'endoforge.phase9-physics-output.v1'
REPORT_SCHEMA = 'endoforge.phase9.asset-contract-rejection.v1'
REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
NONFINITE_MARKER = '__PHASE9_ASSET_CONTRACT_NONFINITE_NUMBER__'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_path(value, existing_file=False):
    path = Path(os.path.abspath(value))
    for ancestor in reversed((path, *path.parents)):
        if ancestor.exists() or ancestor.is_symlink():
            info = ancestor.stat(follow_symlinks=False)
            require(not stat.S_ISLNK(info.st_mode) and
                    not getattr(info, 'st_file_attributes', 0) & REPARSE,
                    'Links/reparse points are not permitted: ' + str(ancestor))
    if existing_file:
        require(path.is_file(), 'Missing explicit input file: ' + str(path))
    return path


def fresh_output(value):
    path = checked_path(value)
    require(any(path.is_relative_to(base) and path != base
                for base in (ROOT/'tmp/phase9', ROOT/'output/Phase9')),
            'Output must be a fresh child of tmp/phase9 or output/Phase9')
    require(not path.exists(), 'Use a completely fresh output directory')
    return path


def write_new(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def rejection_cases(original):
    """Mutate one contract property; retain the other authored mesh values."""
    require(original.get('phase9_physics_output') == {'schema': OUTPUT_SCHEMA},
            'Use a known-good source asset carrying the exact Phase9 output tag')
    require('phase9_linear_solver' not in original,
            'The source must not already request an experimental linear solver')
    ids = original.get('attachment_vertex_ids')
    require(isinstance(ids, list) and ids, 'Source attachment IDs are missing')
    weights = original.get('attachment_vertex_weights', [1.0]*len(ids))
    require(isinstance(weights, list) and len(weights) == len(ids) and
            all(type(weight) in (int, float) and math.isfinite(weight) and weight > 0
                for weight in weights), 'Source weights must be positive finite aligned values')
    cases = []

    def add(name, mutate, expected, raw_number=None):
        asset = copy.deepcopy(original)
        asset.setdefault('attachment_vertex_weights', list(weights))
        mutate(asset)
        text = json.dumps(asset, ensure_ascii=True, allow_nan=False, separators=(',', ':'))+'\n'
        if raw_number is not None:
            token = json.dumps(NONFINITE_MARKER)
            require(text.count(token) == 1, 'Nonfinite-number mutation is not unique')
            text = text.replace(token, raw_number, 1)
        cases.append({'name': name, 'expected_fatal_fragment': expected,
                      'rejection_layer': 'JSON numeric-overflow parser' if raw_number else 'AnatomyAsset loader',
                      'payload': text.encode('utf-8')})

    tag_error = 'Unsupported Phase9 physics output schema'
    add('unsupported_output_schema', lambda a: a.update(phase9_physics_output={'schema': OUTPUT_SCHEMA+'.unsupported'}), tag_error)
    add('nonempty_output_tag_wrong_type', lambda a: a.update(phase9_physics_output='phase9'), tag_error)
    add('output_tag_extra_member', lambda a: a['phase9_physics_output'].update(unexpected=True), tag_error)
    count_error = 'Attachment vertex weights must match attachment vertex IDs'
    add('weight_count_short', lambda a: a['attachment_vertex_weights'].pop(), count_error)
    add('weight_count_long', lambda a: a['attachment_vertex_weights'].append(1.0), count_error)
    add('weights_not_array', lambda a: a.update(attachment_vertex_weights={'0': 1.0}), count_error)
    positive_error = 'Attachment vertex weight must be positive and finite'
    add('zero_weight', lambda a: a['attachment_vertex_weights'].__setitem__(0, 0.0), positive_error)
    add('negative_weight', lambda a: a['attachment_vertex_weights'].__setitem__(0, -1.0), positive_error)
    numeric_error = 'Attachment vertex weight must be numeric'
    add('string_weight', lambda a: a['attachment_vertex_weights'].__setitem__(0, '1.0'), numeric_error)
    add('boolean_weight', lambda a: a['attachment_vertex_weights'].__setitem__(0, True), numeric_error)
    add('null_weight', lambda a: a['attachment_vertex_weights'].__setitem__(0, None), numeric_error)
    # JSON has no NaN/Infinity values. Legal numeric tokens beyond binary64's
    # range are rejected by nlohmann's parser before the loader finite check.
    # These cases establish rejection, not execution of that unreachable branch.
    for name, token in (('positive_nonfinite_numeric_overflow', '1e309'),
                        ('negative_nonfinite_numeric_overflow', '-1e309')):
        add(name, lambda a: a['attachment_vertex_weights'].__setitem__(0, NONFINITE_MARKER),
            'number overflow parsing', raw_number=token)
    disabled_error = 'Attachment vertex weights require the Phase9 physics output tag'
    add('weights_with_absent_output_tag', lambda a: a.pop('phase9_physics_output'), disabled_error)
    add('weights_with_null_output_tag', lambda a: a.update(phase9_physics_output=None), disabled_error)
    add('weights_with_empty_output_tag', lambda a: a.update(phase9_physics_output={}), disabled_error)
    solver_error = 'Experimental linear solver assets are not accepted by this runtime'
    add('experimental_eigen_solver_field', lambda a: a.update(phase9_linear_solver='EigenSimplicialLDLT'), solver_error)
    add('unknown_solver_field', lambda a: a.update(phase9_linear_solver='unsupported'), solver_error)
    add('null_solver_field', lambda a: a.update(phase9_linear_solver=None), solver_error)
    return cases


def stop_owned(process, actions):
    """Use only the handle from our Popen; never enumerate/reopen another PID."""
    for action, timeout in (('terminate', 2), ('kill', 5)):
        if process.poll() is not None:
            return True
        actions.append(action+'_owned_popen_handle')
        try:
            getattr(process, action)()
        except OSError as error:
            # The child may have exited between poll and termination. Its
            # original handle remains the sole ownership authority.
            actions.append(action+'_error: '+str(error))
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            continue
    return process.poll() is not None


def run_case(case, executable, folder, timeout, port):
    directory = folder/case['name']
    directory.mkdir()
    asset = directory/'asset.json'
    with asset.open('xb') as stream:
        stream.write(case['payload'])
    stdout, stderr = directory/'stdout.log', directory/'stderr.log'
    command = [str(executable), '--phase6', '--mesh', str(asset), '--port', str(port)]
    process = None
    timed_out = False
    launch_error = None
    cleanup = []
    started, clock = now(), time.monotonic()
    reaped = True
    with stdout.open('xb') as out, stderr.open('xb') as err:
        try:
            process = subprocess.Popen(command, cwd=executable.parent,
                                       stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
        except Exception as error:
            launch_error = str(error)
        finally:
            if process is not None:
                reaped = stop_owned(process, cleanup)
    output = stdout.read_text(encoding='utf-8-sig', errors='replace')
    errors = stderr.read_text(encoding='utf-8-sig', errors='replace')
    combined = output+'\n'+errors
    checks = {
        'exited_with_expected_fatal_status': process is not None and process.returncode == 1,
        'expected_contract_reason': 'FATAL ' in combined and case['expected_fatal_fragment'] in combined,
        'rejected_without_timeout': not timed_out and launch_error is None,
        'no_graph_or_service_started': not any(marker in combined for marker in
                                               ('Phase3 initializing graph', 'Phase3 graph ready', 'READY SOFA')),
        'owned_child_reaped': reaped,
    }
    result = {'name': case['name'], 'passed': all(checks.values()), 'checks': checks,
              'expected_fatal_fragment': case['expected_fatal_fragment'],
              'rejection_layer': case['rejection_layer'], 'command': command,
              'owned_pid': process.pid if process is not None else None,
              'ownership': 'Only the child created by this Popen handle can be stopped',
              'started_utc': started, 'completed_utc': now(),
              'elapsed_wall_s': time.monotonic()-clock,
              'exit_code': process.returncode if process is not None else None,
              'timeout_seconds': timeout, 'timed_out': timed_out,
              'launch_error': launch_error, 'cleanup_actions': cleanup,
              'socket_connections_or_commands_sent': False,
              'asset': {'path': str(asset), 'sha256': sha(asset)},
              'stdout': {'path': str(stdout), 'sha256': sha(stdout)},
              'stderr': {'path': str(stderr), 'sha256': sha(stderr)},
              'fatal_lines': [line for line in combined.splitlines() if 'FATAL ' in line]}
    write_new(directory/'result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesh', type=Path, required=True)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout-seconds', type=float, default=5.0)
    parser.add_argument('--port', type=int, default=47489,
                        help='Used only if a malformed asset is unexpectedly accepted; this driver never connects')
    parser.add_argument('--plan-only', action='store_true')
    args = parser.parse_args()
    require(math.isfinite(args.timeout_seconds) and 1 <= args.timeout_seconds <= 15,
            'Timeout must be between 1 and 15 seconds')
    require(1025 <= args.port <= 65535, 'Invalid isolated service port')
    mesh, executable = checked_path(args.mesh, True), checked_path(args.exe, True)
    require(executable.name.casefold() == 'lapphysics.exe', 'Select the explicit LapPhysics.exe')
    folder = fresh_output(args.output)
    original = json.loads(mesh.read_text(encoding='utf-8-sig'))
    cases = rejection_cases(original)
    identity = {'source_mesh': {'path': str(mesh), 'sha256': sha(mesh)},
                'native_binary': {'path': str(executable), 'sha256': sha(executable)},
                'launcher': {'path': str(Path(__file__).resolve()), 'sha256': sha(__file__)}}
    loader = ROOT/'Physics/AnatomyAsset.h'
    if loader.is_file():
        identity['reviewed_loader_source'] = {'path': str(loader), 'sha256': sha(loader),
                                             'scope': 'Reviewed source rules; binary/source binding belongs to the build receipt'}
    scope = ('Focused negative asset contract only. All expected rejections must occur before graph creation. '
             'Numeric-overflow cases are parser rejections, not finite-check branch coverage. '
             'Positive absent/null/empty-tag compatibility and physical/clinical behavior are excluded. '
             'Unchanged native35 legacy Phase3/4 cases remain separate required coverage.')
    plan = {'schema': REPORT_SCHEMA, 'phase': 9, 'plan_only': args.plan_only,
            'native_execution_started': False, 'scope': scope, 'identity': identity,
            'output': str(folder), 'expected_case_count': len(cases),
            'cases': [{key: value for key, value in case.items() if key != 'payload'} for case in cases]}
    if args.plan_only:
        print(json.dumps(plan, indent=2))
        return 0
    folder.mkdir(parents=True, exist_ok=False)
    write_new(folder/'plan.json', plan)
    started = now()
    results = []
    runner_error = None
    try:
        for case in cases:
            require(sha(mesh) == identity['source_mesh']['sha256'] and
                    sha(executable) == identity['native_binary']['sha256'],
                    'Explicit input identity changed; no next process was launched')
            result = run_case(case, executable, folder, args.timeout_seconds, args.port)
            results.append(result)
            print(json.dumps({'case': result['name'], 'passed': result['passed'],
                              'exit_code': result['exit_code'], 'timed_out': result['timed_out']}), flush=True)
            require(result['checks']['owned_child_reaped'],
                    'Owned child could not be reaped; no next process was launched')
    except Exception as error:
        runner_error = str(error)
    checks = {'all_expected_cases_completed': len(results) == len(cases),
              'every_contract_rejection_passed': bool(results) and all(row['passed'] for row in results),
              'source_mesh_unchanged': sha(mesh) == identity['source_mesh']['sha256'],
              'native_binary_unchanged': sha(executable) == identity['native_binary']['sha256'],
              'launcher_unchanged': sha(__file__) == identity['launcher']['sha256'],
              'no_runner_error': runner_error is None}
    report = {**plan, 'plan_only': False, 'native_execution_started': any(row['owned_pid'] is not None for row in results),
              'started_utc': started, 'completed_utc': now(), 'case_count': len(results),
              'passed': all(checks.values()), 'checks': checks, 'runner_error': runner_error,
              'cases': results, 'not_covered': ['Positive absent/null/empty output tags with weights absent',
                                             'Physical grasp/traction/replay/stability',
                                             'Clinical material or force calibration']}
    write_new(folder/'report.json', report)
    print(json.dumps({'passed': report['passed'], 'case_count': len(results),
                      'report': str(folder/'report.json')}))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
