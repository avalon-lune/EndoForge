"""Audit one completed Phase8 capture with explicit inputs and a fresh report dir.

Adapted from tmp/phase7/run_capture_audits.py and its accepted evidence bindings.
No UE/native process is launched. Native inheritance is a separate identity
receipt, never a new native regression or a substitute for these capture audits.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time


EXPECTED_FRAMES = {'left_traction': 3, 'bimanual_traction': 1}
DEPENDENCIES = [
    'Scripts/Phase8/run_capture_audits.py', 'Scripts/Phase8/common.py',
    'Scripts/Phase8/audit_appearance.py', 'Scripts/Phase8/audit_runtime.py',
    'Scripts/Phase8/audit_dataset.py', 'Scripts/Phase8/audit_snapshot.py',
    'Scripts/Phase8/audit_context.py', 'Scripts/Phase8/audit_uv.py',
    'Scripts/Phase8/audit_attachment.py', 'Scripts/Phase8/extract_presented_trace.py',
    'Scripts/Phase8/inherit_native.py', 'Scripts/Phase8/preservation.py',
    'Scripts/Phase7/audit_trace_resumable.py', 'Scripts/Phase7/audit_identity.py',
    'Scripts/Phase7/acceptance-spec.json', 'Scripts/Phase5/audit_geometry.py',
    'Scripts/Phase5/audit_contact.py', 'Scripts/Phase5/audit_liver_contact.py',
    'Scripts/Phase5/audit_trace_parallel.py', 'Scripts/audit_phase4_collision_geometry.py',
]
PERFORMANCE_KEYS = ('width', 'height', 'display_mean_fps_minimum', 'display_target_fps',
                    'simulation_to_wall_ratio_minimum', 'display_p95_frame_ms_maximum',
                    'exclude_capture_freeze_seconds', 'no_concurrent_acceptance_workloads')
INTERACTION_KEYS = ('response_p95_ms_maximum', 'target_lead_mm_maximum',
                    'stop_residual_travel_mm_maximum', 'collision_maximum_depth_mm')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def safe_path(value):
    path = Path(os.path.abspath(value))
    for item in reversed((path, *path.parents)):
        try:
            info = item.stat(follow_symlinks=False)
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'Link or Windows reparse point is forbidden: ' + str(item))
    return path


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def fingerprint(path):
    info = path.stat(follow_symlinks=False)
    return (info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_dev, info.st_ino)


def descriptor(path):
    before = fingerprint(path)
    digest = sha(path)
    require(before == fingerprint(path), 'Input changed while hashing: ' + str(path))
    return {'path': str(path), 'bytes': before[0], 'sha256': digest}


def tree_metadata(directory):
    result = {}
    pending = [directory]
    while pending:
        current = pending.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                path = safe_path(entry.path)
                info = path.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    pending.append(path)
                else:
                    require(stat.S_ISREG(info.st_mode), 'Unexpected input-tree member: ' + str(path))
                    result[path.relative_to(directory).as_posix()] = fingerprint(path)
    return result


def child(directory, relative):
    path = safe_path(directory / relative)
    require(path.is_relative_to(directory), 'Audited payload path escapes its directory: ' + str(relative))
    return path


def publish(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def validate_pass(name, report):
    require(report.get('passed') is True, 'Missing/failed report: ' + name)
    for key, value in report.get('checks', {}).items():
        if isinstance(value, bool):
            require(value is True, 'Failed check: ' + name + '.' + key)


def jobs_for(paths, snapshots, workers, chunk_states):
    source, capture, output = (paths[key] for key in ('source_root', 'capture', 'output'))
    phase8 = source / 'Scripts/Phase8'
    trace = output / 'presented-native-trace.jsonl'

    def job(name, script, arguments, report=True):
        return {'name': name, 'script': script, 'arguments': list(map(str, arguments)),
                'report': output / (name + '.json') if report else None}

    sequential = [
        job('appearance', phase8 / 'audit_appearance.py', ['--manifest', paths['dataset'] / 'visual-manifest.json',
            '--assets', paths['assets'], '--output', output / 'appearance.json']),
        job('runtime', phase8 / 'audit_runtime.py', ['--capture', capture, '--spec', paths['spec'],
            '--unreal-log', paths['unreal_log'], '--output', output / 'runtime.json']),
        job('geometry', source / 'Scripts/Phase5/audit_geometry.py', ['--mesh', paths['physics_mesh'],
            '--output', output / 'geometry.json']),
        job('extract', phase8 / 'extract_presented_trace.py', ['--presented', capture / 'phase5-presented-states.jsonl',
            '--native-reference', paths['native_reference'], '--output', trace], False),
    ]
    parallel = [
        job('dataset', phase8 / 'audit_dataset.py', ['--dataset', paths['dataset'], '--physics-mesh', paths['physics_mesh'],
            '--output', output / 'dataset.json']),
        job('snapshot', phase8 / 'audit_snapshot.py', [*snapshots, '--phase', '8', '--output', output / 'snapshot.json']),
        job('context', phase8 / 'audit_context.py', ['--presented', capture / 'phase5-presented-states.jsonl',
            '--scene', paths['scene'], '--native-reference', paths['native_reference'], '--output', output / 'context.json']),
    ]
    geometry = [job('presented-' + kind, source / 'Scripts/Phase7/audit_trace_resumable.py',
        ['--trajectory', trace, '--kind', kind, '--workers', str(workers), '--chunk-states', str(chunk_states),
         '--work-dir', output / ('presented-' + kind + '-chunks'), '--output', output / ('presented-' + kind + '.json')])
        for kind in ('contact', 'liver')]
    return (sequential, parallel, geometry), trace


def preflight(paths, snapshots):
    require(not paths['output'].exists(), 'Use a completely fresh report directory')
    for protected in ('capture', 'assets', 'dataset'):
        require(not paths['output'].is_relative_to(paths[protected]), 'Reports must be outside the input ' + protected)
    require(paths['scene'] == paths['assets'] / 'scene.json', 'Scene must be the explicit assets/scene.json')
    require(paths['physics_mesh'] == paths['assets'] / 'physics-mesh.json', 'Physical mesh must be assets/physics-mesh.json')
    require(paths['dataset'] == paths['capture'] / 'dataset',
            'Current adapters require the explicit dataset directory to be capture/dataset')
    require(paths['unreal_log'].is_relative_to(paths['capture']), 'Selected UE log must belong to this capture directory')
    require(snapshots, 'Missing actual snapshot; a completed capture is required')
    require(Path(__file__).resolve() == paths['source_root'] / 'Scripts/Phase8/run_capture_audits.py',
            'Invoke the runner from the selected source-root tree')
    dependencies = {name: descriptor(safe_path(paths['source_root'] / name)) for name in DEPENDENCIES}
    files = {name: paths[name] for name in ('scene', 'physics_mesh', 'native_reference', 'native_inheritance',
                                          'native_executable', 'accepted_native_suite', 'spec')}
    files.update(runtime=paths['capture'] / 'phase6-runtime.json',
                 interaction=paths['capture'] / 'phase6-interaction-test.json',
                 input=paths['capture'] / 'phase5-input-test.json',
                 log=paths['unreal_log'], presented=paths['capture'] / 'phase5-presented-states.jsonl',
                 manifest=paths['dataset'] / 'visual-manifest.json')
    files.update({'snapshot_' + str(index): path for index, path in enumerate(snapshots)})
    frames = sorted(paths['dataset'].glob('*/*/frame.json'))
    require(len(frames) == 4, 'Exactly four internal alignment frames are required')
    files.update({'frame_' + str(index): path for index, path in enumerate(frames)})
    inputs = {name: descriptor(safe_path(path)) for name, path in files.items()}
    scene, runtime, interaction, capture_input, manifest, inheritance, suite, spec = [read(files[name])
        for name in ('scene', 'runtime', 'interaction', 'input', 'manifest', 'native_inheritance', 'accepted_native_suite', 'spec')]
    require(scene.get('phase') == 8 and manifest.get('phase') == 8, 'Wrong captured/current scene milestone')
    require(runtime.get('schema') == 'endoforge.phase8.runtime.v1' and runtime.get('phase') == 8
            and runtime.get('run_kind') == 'acceptance_test', 'A completed Phase8 acceptance capture is required')
    require(interaction.get('schema') == 'endoforge.phase8.interaction.v1' and interaction.get('phase') == 8,
            'Wrong interaction capture identity')
    require(capture_input.get('phase') == 8 and capture_input.get('mechanics_phase') == 6
            and capture_input.get('stereo_frames') == 4, 'Input report must identify four Phase8 internal alignment frames')
    validate_pass('captured input', capture_input)
    validate_pass('captured interaction', interaction)
    manifest_sha1 = hashlib.sha1(files['manifest'].read_bytes()).hexdigest()
    require(runtime.get('visual_manifest_sha1') == capture_input.get('visual_manifest_sha1') == manifest_sha1,
            'Input/runtime reports are not bound to this captured visual manifest')
    require(manifest['asset_file_hashes']['scene.json'].lower() == hashlib.sha1(files['scene'].read_bytes()).hexdigest(),
            'Selected scene is not the captured scene')
    require(spec.get('phase') == 8 and spec.get('schema') == 'endoforge.phase8.acceptance.v1',
            '--spec must explicitly identify the Phase8 acceptance specification')
    old_spec = read(paths['source_root'] / 'Scripts/Phase7/acceptance-spec.json')
    for group, keys in (('performance', PERFORMANCE_KEYS), ('interaction', INTERACTION_KEYS)):
        for key in keys:
            require(spec[group][key] == old_spec[group][key], 'Inherited acceptance threshold changed: ' + group + '.' + key)
    require(inheritance.get('schema') == 'endoforge.phase8.native-inheritance.v1' and inheritance.get('phase') == 8,
            'Wrong native inheritance receipt')
    validate_pass('native identity inheritance', inheritance)
    require(inheritance.get('execution_phase') == 7 and inheritance.get('native_suite_reexecuted') is False
            and inheritance.get('new_native_35_execution') is False
            and inheritance.get('phase6_acceptance_inherited') is False
            and inheritance.get('integration_tests_still_required') is True,
            'Native identity receipt must explicitly retain its inherited Phase7 execution scope')
    require(inputs['native_executable']['sha256'] == inheritance['native_binary_sha256'] == suite['native_binary']['sha256'],
            'Actual selected native executable differs from inherited qualified identity')
    require(inputs['physics_mesh']['sha256'] == inheritance['physical_asset_sha256'] == suite['anatomy_asset']['sha256'],
            'Explicit selected physical mesh differs from inherited qualified identity')
    require(inputs['accepted_native_suite']['sha256'] == inheritance['accepted_phase7_native_execution']['suite']['sha256'],
            'Accepted native suite differs from the inherited receipt')
    validate_pass('accepted Phase7 native suite', suite)
    require(inputs['native_reference']['sha256'] == suite['evidence']['dual-reference']['trajectory']['sha256'],
            'Native reference is not the accepted Phase7 dual-reference trajectory')
    require(dependencies['Scripts/Phase8/inherit_native.py']['sha256'] == inheritance['helper_sha256'],
            'Inherited receipt was produced by a different helper version')
    return dependencies, inputs, files, frames, inheritance


def bind_reports(paths, snapshots, reports, trace, inputs, dependencies):
    require(reports['dataset'].get('frame_count') == 4 and reports['dataset'].get('sequences') == EXPECTED_FRAMES,
            'Dataset audit did not cover the exact four internal frames')
    for frame in reports['dataset']['frames']:
        for kind in ('dynamic_uv', 'attachment_geometry'):
            validate_pass('dataset ' + kind, frame[kind])
        require(frame['sequence'] in EXPECTED_FRAMES and type(frame['frame']) is int and frame['frame'] >= 0,
                'Invalid reported alignment-frame identity')
        frame_path = paths['dataset'] / frame['sequence'] / f"{frame['frame']:04d}" / 'frame.json'
        require(sha(frame_path) == frame['frame_json_sha256'], 'Audited frame JSON changed')
        for relative, digest in frame['audited_payload_sha256'].items():
            require(sha(child(frame_path.parent, relative)) == digest, 'Audited alignment payload changed: ' + relative)
    require(len(reports['snapshot']['snapshots']) == len(snapshots), 'Snapshot report membership differs')
    require({row['file'] for row in reports['snapshot']['snapshots']} == {path.name for path in snapshots},
            'Snapshot report filenames differ from this capture')
    for snapshot in reports['snapshot']['snapshots']:
        for kind in ('dynamic_uv', 'attachment_geometry'):
            validate_pass('snapshot ' + kind, snapshot[kind])
        require(sha(child(paths['capture'], snapshot['file'])) == snapshot['snapshot_sha256'], 'Audited snapshot changed')
        screenshot = snapshot.get('screenshot')
        require(isinstance(screenshot, dict), 'A completed snapshot must include its actual PNG capture')
        require(sha(child(paths['capture'], screenshot['file'])) == screenshot['sha256'], 'Audited snapshot PNG changed')
    require(reports['dataset']['physics_mesh_sha256'] == reports['geometry']['asset_sha256'] == inputs['physics_mesh']['sha256'],
            'Geometry/data reports use another physical mesh')
    require(reports['dataset']['scene_sha256'] == reports['context']['scene_sha256'] == inputs['scene']['sha256'],
            'Data/context reports use another scene')
    require(reports['dataset']['visual_manifest_sha256'] == reports['appearance']['metrics']['manifest_sha256'] == inputs['manifest']['sha256'],
            'Appearance/data reports use another captured manifest')
    for report_key, input_key in (('runtime_sha256', 'runtime'), ('interaction_sha256', 'interaction'), ('unreal_log_sha256', 'log')):
        require(reports['runtime'][report_key] == inputs[input_key]['sha256'], 'Runtime audit input binding differs: ' + input_key)
    require(reports['runtime']['acceptance_spec_sha256'] == inputs['spec']['sha256'], 'Runtime used another acceptance spec')
    for image in reports['runtime']['images']:
        require(sha(child(paths['capture'], image['file'])) == image['sha256'], 'Audited render comparison changed')
    require(reports['context']['presented_sha256'] == inputs['presented']['sha256']
            and reports['context']['native_reference_sha256'] == inputs['native_reference']['sha256'], 'Context trace/reference binding differs')
    for name in ('appearance', 'runtime', 'dataset', 'snapshot', 'context'):
        require(reports[name]['audit_script_sha256'] == dependencies['Scripts/Phase8/audit_' + name + '.py']['sha256'],
                'Audit source binding differs: ' + name)
    for name in ('dataset', 'snapshot'):
        for helper in ('uv', 'attachment'):
            require(reports[name][helper + '_audit_script_sha256'] == dependencies['Scripts/Phase8/audit_' + helper + '.py']['sha256'],
                    'UV/attachment helper binding differs: ' + name)
    require(reports['appearance']['metrics']['asset_bytes_verified'] is True,
            'Appearance audit did not verify actual authored asset bytes')
    with trace.open(encoding='utf-8-sig') as stream:
        header = json.loads(next(stream))
    require(header['provenance']['presented_sha256'] == inputs['presented']['sha256']
            and header['provenance']['native_reference_sha256'] == inputs['native_reference']['sha256']
            and header['provenance']['extractor_sha256'] == dependencies['Scripts/Phase8/extract_presented_trace.py']['sha256'],
            'Extracted geometry trace provenance differs')
    # Reuse the accepted identity validator; the unchanged geometry runner keeps
    # its historical Phase7 schema even though the presented records are Phase8.
    import runpy
    identities = runpy.run_path(str(paths['source_root'] / 'Scripts/Phase7/audit_identity.py'))
    geometry_identities = {'geometry': identities['verify_geometry_report'](reports['geometry'], paths['source_root'], 'geometry')}
    digest = sha(trace)
    for kind in ('contact', 'liver'):
        name = 'presented-' + kind
        require(reports[name]['original_trace']['sha256'] == digest, 'Geometry report covers another presented trace')
        geometry_identities[name] = identities['verify_geometry_report'](reports[name], paths['source_root'], kind, 7)
    return geometry_identities


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root', 'capture', 'assets', 'native-reference', 'native-inheritance',
                 'native-executable', 'accepted-native-suite', 'spec', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--scene', type=Path, help='Explicit scene path; must be assets/scene.json')
    parser.add_argument('--dataset', type=Path, help='Explicit data path; must be capture/dataset')
    parser.add_argument('--unreal-log', type=Path, help='Explicit UE log within capture; otherwise exactly one unreal.log/ue.log')
    parser.add_argument('--geometry-workers', type=int, default=3)
    parser.add_argument('--chunk-states', type=int, default=1000)
    parser.add_argument('--plan-only', action='store_true', help='Print commands only; write nothing and execute no auditor')
    args = parser.parse_args()
    require(1 <= args.geometry_workers <= 64 and args.chunk_states >= 30, 'Invalid geometry worker count or chunk size')
    paths = {name: safe_path(value) for name, value in vars(args).items() if isinstance(value, Path)}
    paths.setdefault('scene', paths['assets'] / 'scene.json')
    paths.setdefault('dataset', paths['capture'] / 'dataset')
    if 'unreal_log' not in paths:
        candidates = [paths['capture'] / name for name in ('unreal.log', 'ue.log')
                      if (paths['capture'] / name).is_file()]
        require(len(candidates) == 1 or (args.plan_only and not candidates),
                'Select --unreal-log explicitly unless exactly one capture/unreal.log or capture/ue.log exists')
        paths['unreal_log'] = safe_path(candidates[0]) if candidates else paths['capture'] / 'unreal.log'
    paths['physics_mesh'] = paths['assets'] / 'physics-mesh.json'
    snapshots = sorted(safe_path(path) for path in paths['capture'].glob('*snapshot-*.json'))
    stages, trace = jobs_for(paths, snapshots, args.geometry_workers, args.chunk_states)
    if args.plan_only:
        print(json.dumps({'executed': False, 'passed': None, 'scope': 'Command plan only; no acceptance evidence produced',
            'paths': {key: str(value) for key, value in paths.items()}, 'expected_internal_frames': EXPECTED_FRAMES,
            'stages': [[{'name': job['name'], 'command': [sys.executable, '-B', '-X', 'utf8', str(job['script']), *job['arguments']]}
                        for job in stage] for stage in stages]}, indent=2))
        return 0

    # Disable bytecode writes in both this process and all legacy auditor imports.
    sys.dont_write_bytecode = True
    dependencies, inputs, files, frames, inheritance = preflight(paths, snapshots)
    watched = {Path(row['path']): fingerprint(Path(row['path'])) for row in [*dependencies.values(), *inputs.values()]}
    capture_tree, asset_tree = tree_metadata(paths['capture']), tree_metadata(paths['assets'])
    paths['output'].mkdir(parents=True, exist_ok=False)
    summary_path = paths['output'] / 'audit-run.json'
    summary = {'schema': 'endoforge.phase8.capture-audits.v1', 'phase': 8, 'passed': False, 'status': 'running',
        'started_utc': utc_now(), 'paths': {key: str(value) for key, value in paths.items()},
        'expected_internal_alignment_frames': EXPECTED_FRAMES, 'inputs': inputs, 'dependencies': dependencies,
        'native_inheritance': {'receipt': inputs['native_inheritance'], 'accepted_native_execution_phase': 7,
            'new_native_35_execution': False, 'scope': 'Separate accepted Phase7 identity inheritance only. It does not count as a fresh Phase8 capture, native regression, or delivery acceptance.'},
        'delivery_accepted': False, 'visual_review_still_required': True, 'jobs': []}
    publish(summary_path, summary)
    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        env[key] = '1'

    def run(job):
        name = job['name']
        command = [sys.executable, '-B', '-X', 'utf8', str(job['script']), *job['arguments']]
        log_path = paths['output'] / (name + '.log')
        started, clock_start = utc_now(), time.monotonic()
        print(json.dumps({'starting': name, 'utc': started}), flush=True)
        with log_path.open('x', encoding='utf-8') as log:
            result = subprocess.run(command, cwd=paths['source_root'], env=env, stdout=log,
                stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        require(result.returncode == 0, name + ' failed (exit ' + str(result.returncode) + '); see ' + str(log_path))
        report = read(job['report']) if job['report'] is not None else None
        if report is not None:
            validate_pass(name, report)
        record = {'name': name, 'command': command, 'started_utc': started, 'completed_utc': utc_now(),
                  'elapsed_seconds': time.monotonic() - clock_start, 'exit_code': result.returncode,
                  'log': descriptor(log_path), 'report': descriptor(job['report']) if report is not None else None}
        print(json.dumps({'completed': name, 'seconds': record['elapsed_seconds']}), flush=True)
        return name, report, record

    reports = {}
    try:
        for stage_index, stage in enumerate(stages):
            if stage_index == 0:
                completed = [run(job) for job in stage]
            else:
                with ThreadPoolExecutor(max_workers=len(stage)) as pool:
                    completed = [future.result() for future in as_completed([pool.submit(run, job) for job in stage])]
            for name, report, record in completed:
                summary['jobs'].append(record)
                if report is not None:
                    reports[name] = report
            publish(summary_path, summary)
        identities = bind_reports(paths, snapshots, reports, trace, inputs, dependencies)
        for path, before in watched.items():
            require(before == fingerprint(path), 'Audited input/dependency changed during orchestration: ' + str(path))
        require(tree_metadata(paths['capture']) == capture_tree, 'Capture membership or metadata changed during audits')
        require(tree_metadata(paths['assets']) == asset_tree, 'Asset membership or metadata changed during audits')
        require(sorted(paths['capture'].glob('*snapshot-*.json')) == snapshots, 'Snapshot membership changed')
        require(sorted(paths['dataset'].glob('*/*/frame.json')) == frames, 'Alignment-frame membership changed')
        receipt_copy = paths['output'] / 'native-inheritance.json'
        with paths['native_inheritance'].open('rb') as source, receipt_copy.open('xb') as target:
            shutil.copyfileobj(source, target)
        require(sha(receipt_copy) == inputs['native_inheritance']['sha256'], 'Copied inherited receipt changed')
        summary.update(passed=True, status='capture_audits_passed', geometry_auditor_identity=identities,
            native_inheritance_copy=descriptor(receipt_copy), extracted_trace=descriptor(trace),
            dynamic_uv_and_attachment={'dataset_frames_checked': 4, 'snapshots_checked': len(snapshots),
                'schema_policy': 'Unchanged historical Phase7 UV/attachment/progression algorithms; all per-frame thresholds retained'},
            scope='Automated audits of this completed Phase8 capture only. Four internal alignment frames are not research sequence delivery. Visual review, preservation, package/source identity, build provenance, fresh extraction and final delivery acceptance are separate gates. No new native 35-case execution.')
    except Exception as error:
        summary.update(passed=False, status='failed', error_type=type(error).__name__, error=str(error))
    summary['completed_utc'] = utc_now()
    publish(summary_path, summary)
    print(json.dumps({'passed': summary['passed'], 'status': summary['status'], 'report': str(summary_path),
        'sha256': sha(summary_path), 'delivery_accepted': False, 'new_native_35_execution': False,
        'visual_review_still_required': True, 'error': summary.get('error')}), flush=True)
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
