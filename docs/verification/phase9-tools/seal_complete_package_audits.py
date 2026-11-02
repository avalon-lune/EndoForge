"""Seal eight actual package-capture audits from explicit immutable inputs.

No app, native process, test or geometry audit is launched. --plan-only checks
the unchanged auditor API and prints the plan without reading bulk evidence or
creating output. A real invocation writes only a new complete index, after all
six small reports and both full trajectory reports have actually passed.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Scripts/Phase7'))
from audit_identity import verify_geometry_report

REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
SMALL_SCHEMAS = {
    'appearance': 'endoforge.phase9.appearance-audit.v1',
    'runtime': 'endoforge.phase9.runtime-audit.v1',
    'geometry': 'endoforge.phase5.independent-geometry.v1',
    'snapshot': 'endoforge.phase9.snapshot-audit.v1',
    'dataset': 'endoforge.phase9.dataset-audit.v1',
    'context': 'endoforge.phase9.context_clearance.v1',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checked(value, existing=True):
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    path = Path(os.path.abspath(path))
    for part in reversed((path, *path.parents)):
        if part.exists() or part.is_symlink():
            info = part.stat(follow_symlinks=False)
            require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & REPARSE,
                    'Links and reparse points are forbidden: ' + str(part))
    require(not existing or path.is_file(), 'Missing evidence file: ' + str(path))
    return path


def sha(path):
    with checked(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def read(path):
    return json.loads(checked(path).read_text(encoding='utf-8-sig'))


def identity(path):
    path = checked(path)
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}


def bind(item):
    require(isinstance(item, dict) and isinstance(item.get('path'), str), 'Missing explicit evidence record')
    path = checked(item['path'])
    require(sha(path) == item.get('sha256'), 'Evidence SHA256 differs: ' + str(path))
    if 'bytes' in item:
        require(path.stat().st_size == item['bytes'], 'Evidence size differs: ' + str(path))
    return path


def all_checks(value):
    return isinstance(value, dict) and bool(value) and all(type(v) is bool and v for v in value.values())


def require_passed(document, label):
    require(document.get('passed') is True, 'Actual report did not pass: ' + label)
    if 'checks' in document:
        require(all_checks(document['checks']), 'Actual report checks did not all pass: ' + label)


def auditor_api():
    """Read the exact unchanged worker call, rather than hardcoding sweep count."""
    runner = ROOT / 'Scripts/Phase7/audit_trace_resumable.py'
    parallel = ROOT / 'Scripts/Phase5/audit_trace_parallel.py'
    contact = ROOT / 'Scripts/Phase5/audit_contact.py'
    flags = {arg.value for node in ast.walk(ast.parse(runner.read_text(encoding='utf-8-sig')))
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and node.func.attr == 'add_argument' for arg in node.args
             if isinstance(arg, ast.Constant) and isinstance(arg.value, str)}
    require({'--trajectory', '--kind', '--workers', '--chunk-states', '--work-dir', '--output'} <= flags,
            'Unchanged resumable runner CLI differs')
    tree = ast.parse(parallel.read_text(encoding='utf-8-sig'))
    worker = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'audit_worker')
    branches = [node for node in ast.walk(worker) if isinstance(node, ast.If)
                and isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Name)
                and node.test.left.id == 'kind' and len(node.test.comparators) == 1
                and isinstance(node.test.comparators[0], ast.Constant)
                and node.test.comparators[0].value == 'contact']
    require(len(branches) == 1, 'Cannot identify exact contact worker branch')
    calls = [node for statement in branches[0].body for node in ast.walk(statement)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == 'audit' and len(node.args) == 2]
    require(len(calls) == 1 and isinstance(calls[0].args[1], ast.Constant)
            and type(calls[0].args[1].value) is int and calls[0].args[1].value > 0,
            'Cannot derive exact contact samples per non-reset edge')
    sweeps = calls[0].args[1].value
    fn = next(node for node in ast.parse(contact.read_text(encoding='utf-8-sig')).body
              if isinstance(node, ast.FunctionDef) and node.name == 'audit')
    defaults = dict(zip([arg.arg for arg in fn.args.args][-len(fn.args.defaults):], fn.args.defaults))
    require(isinstance(defaults.get('sweeps'), ast.Constant) and defaults['sweeps'].value == sweeps,
            'Contact default and worker sweep contracts differ')
    return {'runner': str(runner), 'samples_per_nonreset_edge': sweeps,
            'derivation': 'AST of unchanged audit_trace_parallel.audit_worker contact call, checked against audit_contact.audit default'}


def trace_coverage(trace, reference, mesh_path):
    """Stream all actual records; retain no trajectory array or synthetic state."""
    full_hash = hashlib.sha256()
    states_hash = hashlib.sha256()
    before = trace.stat()
    config = reference['config']
    mesh_bytes = mesh_path.read_bytes()
    mesh = json.loads(mesh_bytes)
    fingerprint = 14695981039346656037
    for byte in mesh_bytes:
        fingerprint = ((fingerprint ^ byte) * 1099511628211) & 0xffffffffffffffff
    fingerprint = f'fnv1a64:{fingerprint:016x}'
    require(config['asset_fingerprint'] == fingerprint, 'Reference configuration binds another physical mesh')
    count = 0
    previous = None
    resets = []
    with trace.open('rb') as handle:
        raw_header = handle.readline()
        full_hash.update(raw_header)
        header = json.loads(raw_header.decode('utf-8-sig'))
        require(header.get('type') == 'mesh', 'Actual trace mesh header is required')
        for raw in handle:
            require(raw.strip(), 'Blank trace records are forbidden')
            full_hash.update(raw)
            states_hash.update(raw)
            state = json.loads(raw)
            require(state['config'] == config and state['asset_fingerprint'] == fingerprint,
                    'An actual presented state uses another full native configuration')
            require(state['model_id'] == mesh['model_id'] and str(state['model_version']) == str(mesh['version']),
                    'An actual presented state uses another model identity')
            if previous is not None and (state.get('simulation_id') != previous.get('simulation_id')
                                        or state.get('frame', 0) < previous.get('frame', 0)):
                resets.append({'before_original_state': count - 1, 'after_original_state': count,
                               'simulation_id_before': previous.get('simulation_id'),
                               'simulation_id_after': state.get('simulation_id')})
            previous = state
            count += 1
    after = trace.stat()
    require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), 'Trace changed during streaming')
    require(count >= 30, 'Inherited full-trace minimum-state gate must hold')
    return {'header': header, 'states': count, 'reset_boundaries': resets,
            'adjacent_original_pairs': count - 1, 'non_reset_edges': count - 1 - len(resets),
            'sha256': full_hash.hexdigest(), 'state_lines_sha256': states_hash.hexdigest(),
            'header_sha256': hashlib.sha256(raw_header).hexdigest(), 'bytes': before.st_size}


def optional_invocation(report_path, kind, report_sha, trace_sha):
    """Bind a durable exit receipt if supplied by the caller's actual runner.

    Explicit report arguments do not imply any directory layout or exit code.
    Absence of an invocation record never becomes a fabricated exit-zero claim.
    """
    paths = list(dict.fromkeys([report_path.with_suffix('.invocation.json'),
                               report_path.parent / (kind + '.invocation.json')]))
    matches = []
    for path in paths:
        if not path.exists():
            continue
        value = read(path)
        target = value.get('report') if isinstance(value.get('report'), dict) else value
        require(checked(target.get('path', '')) == report_path and target.get('sha256') == report_sha,
                'Adjacent invocation receipt refers to another actual report: ' + str(path))
        require(value.get('passed') is True and type(value.get('exit_code')) is int and value['exit_code'] == 0,
                'Recorded full-audit invocation did not exit successfully')
        if 'trace_sha256' in value:
            require(value['trace_sha256'] == trace_sha, 'Invocation binds another trace')
        matches.append({**identity(path), 'exit_code': value['exit_code']})
    return matches


def verify_full(path, kind, trace, coverage, package, sweeps):
    report = read(path)
    require_passed(report, kind)
    identities = {'workspace': verify_geometry_report(report, ROOT, kind, 7),
                  'packaged_source': verify_geometry_report(report, package / 'Source', kind, 7)}
    original = report['original_trace']
    require(checked(original['path']) == trace and original['sha256'] == coverage['sha256']
            and original['original_state_count'] == coverage['states']
            and original['original_state_lines_sha256'] == coverage['state_lines_sha256']
            and original['source_header_sha256'] == coverage['header_sha256']
            and original['bytes'] == coverage['bytes'] and original['exact_state_bytes_and_membership_verified'] is True,
            'Full actual trace coverage/bytes differ: ' + kind)
    require(type(report['workers']) is int and 1 <= report['workers'] <= 64
            and type(report['chunk_states_target']) is int and report['chunk_states_target'] >= 30,
            'Unsupported unchanged runner worker/chunk contract')
    cases = report['cases']
    require(cases, 'Completed chunk evidence is required')
    work = checked(cases[0]['chunk_membership']['path']).parent
    manifest_path = work / 'manifest.json'
    manifest = read(manifest_path)
    require(sha(manifest_path) == report['work_manifest_sha256'] and manifest['kind'] == kind
            and checked(manifest['trajectory']) == trace and manifest['chunk_states'] == report['chunk_states_target']
            and manifest['auditor_identities'] == report['auditor_identities']
            and all(original[key] == value for key, value in manifest['original'].items())
            and [case['chunk_membership'] for case in cases] == manifest['chunks'], 'Full manifest membership/identity differs')
    reconstructed = hashlib.sha256()
    seen = 0
    for index, case in enumerate(cases):
        require(case['audit_completed'] is True and case['chunk_geometric_passed'] is True
                and all_checks(case['chunk_geometric_checks']), 'Actual chunk geometry/health checks failed')
        chunk = case['chunk_membership']
        chunk_path = checked(chunk['path'])
        require(chunk_path.parent == work and sha(chunk_path) == chunk['sha256'], 'Chunk bytes/work directory differ')
        require(read(work / f"result-{chunk['part']:04d}.json") == case, 'Saved leaf result differs from final full report')
        with chunk_path.open('rb') as handle:
            handle.readline()
            if index:
                require(chunk['overlap_with_previous'] is True, 'Missing exact shared chunk boundary')
                handle.readline()
            for raw in handle:
                reconstructed.update(raw)
                seen += 1
    require(seen == coverage['states'] and reconstructed.hexdigest() == coverage['state_lines_sha256'],
            'Chunk reconstruction changed any original record bytes or membership')
    require(report['metrics']['states_audited_including_overlap'] == coverage['states'] + original['duplicated_overlap_count'],
            'Original state and overlap audit counts differ')
    if kind == 'contact':
        require(report['metrics']['reset_boundaries_not_interpolated'] == len(coverage['reset_boundaries'])
                and report['metrics']['interpolated_samples'] == sweeps * coverage['non_reset_edges'],
                'Not every eligible non-reset edge has the exact unchanged sweep count')
    record = {**identity(path), 'passed': True, 'schema': report['schema'], 'checks': report['checks'],
              'metrics': report['metrics'], 'work_manifest': identity(manifest_path),
              'workers': report['workers'], 'chunk_states_target': report['chunk_states_target']}
    invocations = optional_invocation(path, kind, record['sha256'], coverage['sha256'])
    if invocations:
        record['invocation_records'] = invocations
        record['exit_code'] = 0
    return record, report, identities


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('small-index', 'contact-report', 'liver-report', 'output'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--outer-observation', type=Path)
    parser.add_argument('--plan-only', action='store_true', help='Static source/API plan only; no audits, bulk evidence reads or output')
    args = parser.parse_args()
    require(sys.flags.optimize == 0, 'Run without Python -O')
    api = auditor_api()
    if args.plan_only:
        print(json.dumps({'schema': 'endoforge.phase9.complete-audit-seal-plan.v1', 'plan_only': True,
                          'arguments': {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
                          'auditor_api': api, 'bulk_evidence_read': False, 'output_created': False,
                          'apps_tests_audits_launched': 0, 'global_audit_pass_claim': False}, indent=2))
        return 0
    output = checked(args.output, False)
    require(output.is_relative_to(ROOT / 'tmp/phase9') and output != ROOT / 'tmp/phase9'
            and not output.exists(), 'Use a fresh index path under tmp/phase9')
    small_path = checked(args.small_index)
    small_identity = identity(small_path)
    small = read(small_path)
    require(small.get('schema') == 'endoforge.phase9.package-capture-audit-index.v1'
            and small.get('phase') == 9 and small.get('independent_small_audits_passed') is True
            and small.get('inputs_unchanged') is True and small.get('overall_acceptance_passed') is False,
            'Explicit six-small-audit index must actually pass with its original limited scope')
    capture, package = checked(small['capture'], False), checked(small['package'], False)
    require(capture.is_dir() and package.is_dir(), 'Selected capture and current package must exist')
    require(not output.is_relative_to(capture) and not output.is_relative_to(package), 'Index must be separate from actual capture/package')
    inventory_path = bind(small['selected_input_inventory'])
    selected = read(inventory_path)
    for name, item in selected['files'].items():
        require(checked(name).stat().st_size == item['bytes'] and sha(name) == item['sha256'], 'Previously selected input changed: ' + name)
    receipt_path = capture / 'package-run.json'
    receipt = read(receipt_path)
    require(receipt.get('schema') == 'endoforge.phase9.package-run.v1' and receipt.get('phase') == 9
            and receipt.get('run_kind') == 'acceptance_test' and receipt.get('integration_capture_completed') is True
            and receipt.get('game_exit_code') == receipt.get('native_exit_code') == 0
            and receipt.get('native_graceful_exit') is True and receipt.get('error') is None
            and checked(receipt['package_root'], False) == package, 'Actual package game/native receipts must be successful')
    mesh_path = checked(Path(small['assets']) / 'physics-mesh.json')
    inputs = {'physics_exe_sha256': sha(package / 'Physics/LapPhysics.exe'), 'physics_mesh_sha256': sha(mesh_path),
              'game_exe_sha256': sha(package / 'LapTrainer/Binaries/Win64/LapTrainer.exe')}
    require(inputs == small['inputs'] and receipt['inputs_sha256'] == receipt['inputs_after_sha256']
            and receipt['inputs_sha256']['native_executable'] == inputs['physics_exe_sha256']
            and receipt['inputs_sha256']['physics_mesh'] == inputs['physics_mesh_sha256']
            and receipt['inputs_sha256']['game_executable'] == inputs['game_exe_sha256'], 'Actual package input hashes differ')
    extraction_path = checked(small['extraction_report']['path'])
    extraction = read(extraction_path)
    require(small['extraction_report']['passed'] is True and small['extraction_report']['exit_code'] == 0
            and sha(extraction_path) == small['extraction_report']['sha256']
            and extraction.get('schema') == 'endoforge.phase9.presented-extraction-record.v1'
            and extraction.get('passed') is True and extraction.get('exit_code') == 0
            and extraction['inputs'] == inputs, 'Actual extraction pass/identity differs')
    trace = checked(extraction['summary']['path'])
    ref = small['reference']
    reference_path = bind({'path': ref['actual_case_report'], 'sha256': ref['case_report_sha256']})
    reference_trace = bind({'path': ref['trace'], 'sha256': ref['trace_sha256']})
    reference = read(reference_path)
    require_passed(reference, 'actual native reference')
    require(reference.get('native_exit_code') == 0 and reference.get('executable_sha256') == inputs['physics_exe_sha256'],
            'Actual native reference binds another executable/exit receipt')
    coverage = trace_coverage(trace, reference, mesh_path)
    require(coverage['states'] == extraction['summary']['states'] and coverage['sha256'] == extraction['summary']['sha256'],
            'Actual unresampled extraction membership/bytes differ')
    with reference_trace.open(encoding='utf-8-sig') as handle:
        ref_header = json.loads(next(handle))
        ref_first = json.loads(next(handle))
    require(ref_first['config'] == reference['config'], 'Reference case/config/actual state differ')
    for field in ('fixed_indices', 'jaw_half_extents_m', 'rest_vertices', 'static_liver', 'tetrahedra', 'triangles'):
        require(coverage['header'][field] == ref_header[field], 'Extracted mesh header differs from actual reference: ' + field)
    provenance = coverage['header']['provenance']
    require(provenance['native_reference_sha256'] == ref['trace_sha256']
            and provenance['physics_mesh_sha256'] == inputs['physics_mesh_sha256']
            and provenance['presented_sha256'] == sha(capture / 'phase5-presented-states.jsonl'), 'Trace provenance differs')
    reports = {}
    require(set(small['reports']) == set(SMALL_SCHEMAS), 'All six exact small audit kinds are mandatory')
    for name, item in small['reports'].items():
        path = bind(item)
        document = read(path)
        require_passed(document, name)
        invocation_path = bind(item['invocation_record'])
        invocation = read(invocation_path)
        require(item.get('passed') is True and item.get('exit_code') == invocation.get('exit_code') == 0
                and invocation.get('passed') is True and document.get('schema') == SMALL_SCHEMAS[name], 'Small audit actual exit/schema differs')
        reports[name] = {**identity(path), 'passed': True, 'exit_code': 0, 'schema': document['schema'],
                         'invocation_record': identity(invocation_path)}
        if 'checks' in document:
            reports[name]['checks'] = document['checks']
    full = {}
    verified = {}
    for kind in ('contact', 'liver'):
        path = checked(getattr(args, kind + '_report'))
        reports['presented_' + kind], full[kind], verified[kind] = verify_full(path, kind, trace, coverage, package, api['samples_per_nonreset_edge'])
    observation = None
    if args.outer_observation:
        path = checked(args.outer_observation)
        facts = read(path)
        require(facts.get('schema') == 'endoforge.phase9.launch-wrapper-observation.v1'
                and type(facts.get('outer_exec_exit_code')) is int
                and checked(facts['actual_package_receipt']) == receipt_path
                and facts.get('actual_integration_capture_completed') is True
                and facts.get('actual_game_exit_code') == facts.get('actual_native_exit_code') == 0,
                'Optional diagnostic observation must bind this actual capture receipt')
        observation = {**identity(path), 'diagnostic_only': True, 'facts': facts}
    require(identity(small_path) == small_identity and sha(trace) == coverage['sha256'], 'Original small index or trace changed during sealing')
    config = reference['config']
    config_sha = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
    checks = {key: True for key in (
        'all_six_actual_small_audits_passed', 'full_presented_contact_passed', 'full_presented_liver_passed',
        'all_eight_actual_reports_passed_and_declared_checks_true', 'all_original_presented_states_audited',
        'all_eligible_non_reset_edges_and_exact_sweeps_audited', 'all_chunk_geometry_and_health_checks_passed',
        'exact_source_state_bytes_and_chunk_membership_reconstructed', 'auditors_match_workspace_and_packaged_sources',
        'actual_package_capture_completed_game_and_native_zero', 'current_package_and_selected_inputs_unchanged',
        'actual_extraction_and_native_reference_hashes_bound', 'every_actual_native_config_matches_reference',
        'original_small_index_unchanged')}
    if observation:
        checks['optional_outer_observation_preserved_separately'] = True
    document = {'schema': 'endoforge.phase9.complete-audit-index.v1', 'phase': 9,
                'created_at_utc': datetime.now(timezone.utc).isoformat(), 'passed': True,
                'checks': checks, 'inputs': small['inputs'], 'reports': reports,
                'capture': str(capture), 'package': str(package), 'small_audit_index': small_identity,
                'selected_input_inventory': identity(inventory_path), 'extraction_report': identity(extraction_path),
                'presented_trace': identity(trace), 'actual_package_run_receipt': identity(receipt_path),
                'actual_game_exit_code': receipt['game_exit_code'], 'actual_native_exit_code': receipt['native_exit_code'],
                'native_reference': {'case_report': identity(reference_path), 'trace': identity(reference_trace),
                                     'config': config, 'config_canonical_json_sha256': config_sha,
                                     'config_hash_encoding': 'UTF-8 JSON, sorted keys, compact separators, finite numbers'},
                'trace_provenance': provenance,
                'coverage': {'original_states': coverage['states'], 'adjacent_original_pairs': coverage['adjacent_original_pairs'],
                             'reset_boundaries': coverage['reset_boundaries'], 'non_reset_edges': coverage['non_reset_edges'],
                             'samples_per_nonreset_edge': api['samples_per_nonreset_edge'],
                             'interpolated_samples': full['contact']['metrics']['interpolated_samples'],
                             'contact_policy': full['contact']['coverage_policy'],
                             'liver_distance_sampling_policy': full['liver']['distance_sampling_policy']},
                'verified_geometry_auditor_identities': verified, 'sealer': identity(__file__),
                'human_visual_approval_claim': False, 'final_delivery_claim': False,
                'scope': 'Eight actual capture audits only. Every original state and eligible interpolation edge is required. Original small evidence and optional outer observation remain immutable. Native qualification, broader geometry, archive integrity, human visual approval and final delivery remain separate.'}
    if observation:
        document['outer_wrapper_observation'] = observation
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(document, handle, indent=2)
        handle.write('\n')
    print(json.dumps({**identity(output), 'passed': True, 'report_count': len(reports), 'coverage': document['coverage']}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
