"""Run existing independent audits of one completed actual Phase9 package capture.

This temporary orchestrator never edits frozen sources or runs UE/native code.
--plan-only checks the static CLI/API plan and writes/runs nothing. Actual mode
requires a completed TestPhase9Package package-run.json and a fresh tmp/phase9
output. Presented contact/liver audits are deliberately separate; this runner
never declares overall/final acceptance passed.
"""
import argparse
import ast
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
ROOT = Path(__file__).resolve().parents[3]
REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
SCRIPTS = {
    'appearance': 'Scripts/Phase9/audit_appearance.py',
    'runtime': 'Scripts/Phase9/audit_runtime.py',
    'geometry': 'Scripts/Phase5/audit_geometry.py',
    'snapshot': 'Scripts/Phase9/audit_snapshot.py',
    'dataset': 'Scripts/Phase9/audit_dataset.py',
    'context': 'Scripts/Phase9/audit_context.py',
    'extract': 'Scripts/Phase9/extract_presented_trace.py',
}
EXTRA_DEPENDENCIES = [
    'Scripts/Phase9/common.py', 'Scripts/Phase9/audit_uv.py',
    'Scripts/Phase9/audit_attachment.py', 'Scripts/Phase9/acceptance-spec.json',
    'Scripts/Phase5/audit_contact.py', 'Scripts/Phase5/audit_liver_contact.py',
    'Scripts/Phase5/audit_trace_parallel.py', 'Scripts/audit_phase4_collision_geometry.py',
    'Scripts/Phase7/audit_trace_resumable.py',
]
REQUIRED_FLAGS = {
    'appearance': {'--manifest', '--assets', '--output'},
    'runtime': {'--capture', '--physics-mesh', '--spec', '--unreal-log', '--output'},
    'geometry': {'--mesh', '--output'},
    'snapshot': {'--physics-mesh', '--assets', '--phase', '--output'},
    'dataset': {'--dataset', '--physics-mesh', '--output'},
    'context': {'--presented', '--scene', '--native-reference', '--output'},
    'extract': {'--presented', '--native-reference', '--physics-mesh', '--output'},
}
SCHEMAS = {
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


def checked(value, *, existing=True, directory=False):
    path = Path(os.path.abspath(value))
    for part in reversed((path, *path.parents)):
        if part.exists() or part.is_symlink():
            info = part.stat(follow_symlinks=False)
            require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & REPARSE,
                    'Links/reparse points are forbidden: '+str(part))
    if existing:
        require(path.is_dir() if directory else path.is_file(), 'Missing selected input: '+str(path))
    return path


def sha(path):
    with checked(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(checked(path).read_text(encoding='utf-8-sig'))


def metadata(path):
    info = checked(path).stat()
    return (info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_dev, info.st_ino)


def walk(folder, excluded=()):
    result = []
    for item in sorted(checked(folder, directory=True).iterdir()):
        checked(item, directory=item.is_dir())
        if item.is_dir():
            if item.name.casefold() not in excluded:
                result.extend(walk(item, excluded))
        elif item.is_file():
            result.append(item)
    return result


def source_contract():
    hashes = {}
    for name, relative in SCRIPTS.items():
        path = checked(ROOT/relative)
        tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
        flags = {arg.value for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == 'add_argument'
                 for arg in node.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str)}
        require(REQUIRED_FLAGS[name].issubset(flags), 'Frozen auditor CLI changed: '+relative)
        hashes[relative] = sha(path)
    for relative in EXTRA_DEPENDENCIES:
        hashes[relative] = sha(ROOT/relative)
    return hashes


def jobs(paths, snapshots):
    capture, assets, output = (paths[key] for key in ('capture', 'assets', 'output'))
    mesh = assets/'physics-mesh.json'
    common = {
        'appearance': ['--manifest', capture/'dataset/visual-manifest.json', '--assets', assets],
        'runtime': ['--capture', capture, '--physics-mesh', mesh, '--spec', ROOT/'Scripts/Phase9/acceptance-spec.json', '--unreal-log', capture/'ue.log'],
        'geometry': ['--mesh', mesh],
        'snapshot': [*snapshots, '--phase', '9', '--physics-mesh', mesh, '--assets', assets],
        'dataset': ['--dataset', capture/'dataset', '--physics-mesh', mesh],
        'context': ['--presented', capture/'phase5-presented-states.jsonl', '--scene', assets/'scene.json', '--native-reference', paths['native_reference']],
        'extract': ['--presented', capture/'phase5-presented-states.jsonl', '--native-reference', paths['native_reference'], '--physics-mesh', mesh],
    }
    result = []
    for name, relative in SCRIPTS.items():
        report = output/(name+'.json')
        target = output/'presented-native-trace.jsonl' if name == 'extract' else report
        command = [str(paths['python']), '-B', str(ROOT/relative), *map(str, common[name]), '--output', str(target)]
        result.append({'name': name, 'script': str(ROOT/relative), 'command': command,
                       'report': str(report), 'target': str(target)})
    return result


def prepare(paths, dependencies):
    capture, package, reference = (paths[key] for key in ('capture', 'package', 'native_reference'))
    assets = paths['assets']
    mesh_path, scene_path = assets/'physics-mesh.json', assets/'scene.json'
    run_path = checked(capture/'package-run.json')
    run = read(run_path)
    require(run.get('schema') == 'endoforge.phase9.package-run.v1' and run.get('phase') == 9
            and run.get('run_kind') == 'acceptance_test' and run.get('integration_capture_completed') is True
            and run.get('game_exit_code') == run.get('native_exit_code') == 0
            and run.get('native_graceful_exit') is True and not run.get('error'),
            'A completed actual TestPhase9Package capture is required')
    require(checked(run['package_root'], directory=True) == package, 'Capture executed against another package')
    require(run.get('stereo_frames') == 4, 'Exactly four internal validation frames are required')
    manifest_path = checked(package/'assembly-manifest.json')
    require(sha(manifest_path) == run.get('assembly_manifest_sha256'), 'Capture assembly manifest changed')
    candidate_path = checked(package/'review-candidate.json')
    candidate = read(candidate_path)
    require(candidate.get('schema') == 'endoforge.phase9.review-candidate.v1' and candidate.get('phase') == 9,
            'Wrong selected package receipt')
    input_paths = {'scene': scene_path, 'physics_mesh': mesh_path,
                   'native_executable': package/'Physics/LapPhysics.exe',
                   'game_executable': package/'LapTrainer/Binaries/Win64/LapTrainer.exe',
                   'candidate_receipt': candidate_path, 'assembly_manifest': manifest_path}
    hashes = {name: sha(path) for name, path in input_paths.items()}
    require(run.get('inputs_sha256') == run.get('inputs_after_sha256') == hashes,
            'Captured before/after selected input hashes differ from this package')
    for name in ('phase5-input-test.json', 'phase6-interaction-test.json', 'phase6-runtime.json'):
        require(sha(capture/name) == run.get('reports_sha256', {}).get(name), 'Capture raw report changed: '+name)
        data = read(capture/name)
        require(data.get('phase') == 9 and data.get('mechanics_phase') == 6, 'Wrong raw capture identity: '+name)
    runtime = read(capture/'phase6-runtime.json')
    require(runtime.get('schema') == 'endoforge.phase9.runtime.v1' and runtime.get('run_kind') == 'acceptance_test'
            and runtime.get('appearance', {}).get('diagnostic_neutral_grey') is False,
            'Diagnostic/grey capture cannot replace actual package acceptance capture')
    rows = read(manifest_path)
    require(isinstance(rows, list) and rows, 'Missing sealed assembly members')
    members = {}
    for row in rows:
        name = row['path']
        require(isinstance(name, str) and name and '\\' not in name and ':' not in name
                and not Path(name).is_absolute() and all(part not in ('', '.', '..') for part in name.split('/')),
                'Invalid assembly member')
        require(name.casefold() not in {key.casefold() for key in members}, 'Duplicate assembly member')
        path = checked(package/name)
        require(path.is_relative_to(package) and path.stat().st_size == row['bytes'] and sha(path) == row['sha256'],
                'Sealed package member changed: '+name)
        members[name] = path
    actual_package = {path.relative_to(package).as_posix() for path in walk(package, {'saved','logs','sessions','__pycache__'})}
    require(actual_package == set(members) | {'assembly-manifest.json'}, 'Selected package contains unexpected immutable members')
    for relative, digest in dependencies.items():
        shipped = 'Source/'+relative
        require(shipped in members and sha(members[shipped]) == digest,
                'Workspace auditor differs from this package frozen source: '+relative)
    ref_case_path = checked(reference.with_name('dual-reference.json'))
    ref_case = read(ref_case_path)
    require(ref_case.get('passed') is True and ref_case.get('native_exit_code') == 0
            and ref_case.get('executable_sha256') == hashes['native_executable']
            and checked(ref_case['trace']) == reference, 'Explicit native reference case/executable identity mismatch')
    require(ref_case.get('checks') and all(value is True for value in ref_case['checks'].values()),
            'Explicit native reference case has missing/failed checks')
    with reference.open(encoding='utf-8-sig') as stream:
        header, ref_state = json.loads(next(stream)), json.loads(next(stream))
    require(header.get('type') == 'mesh' and ref_state.get('type') == 'state' and ref_state.get('protocol') == 5,
            'Selected native reference must contain its actual mesh/state')
    require(ref_state['config'] == ref_case['config'], 'Native reference case configuration changed')
    mesh = read(mesh_path)
    fingerprint = 14695981039346656037
    for byte in mesh_path.read_bytes():
        fingerprint = ((fingerprint ^ byte)*1099511628211) & 0xffffffffffffffff
    fingerprint = f'fnv1a64:{fingerprint:016x}'
    require(ref_state.get('asset_fingerprint') == fingerprint and ref_state.get('model_id') == mesh['model_id']
            and str(ref_state.get('model_version')) == str(mesh['version']), 'Reference does not use the selected package mesh')
    visual = read(capture/'dataset/visual-manifest.json')
    require(visual.get('phase') == 9 and visual.get('mechanics_phase') == 6
            and visual.get('physics_fingerprint') == fingerprint, 'Captured visual manifest binds another physical source')
    snapshots = sorted(capture.glob('*snapshot-*.json'))
    require(snapshots, 'At least one actual frozen snapshot JSON is required')
    duration = run.get('duration_s')
    require(type(duration) in (int, float) and math.isfinite(duration) and duration > 0, 'Missing actual capture duration')
    inferred_start = run_path.stat().st_mtime-duration
    selected_capture = walk(capture, {'native-session', 'native-sessions', 'sessions', '__pycache__'})
    for path in selected_capture:
        require(path.stat().st_mtime >= inferred_start, 'Potential stale file in capture directory: '+str(path))
    selected = sorted(set([manifest_path, ref_case_path, reference, *members.values(), *selected_capture,
                           *(ROOT/relative for relative in dependencies)]))
    before = {str(path): metadata(path) for path in selected}
    inventory = {str(path): {'bytes': before[str(path)][0], 'sha256': sha(path)} for path in selected}
    require(all(metadata(path) == before[str(path)] for path in selected), 'An input changed during initial inventory')
    return {'snapshots': snapshots, 'input_paths': input_paths, 'input_hashes': hashes,
            'selected_paths': selected, 'metadata': before, 'inventory': inventory,
            'capture_members': [str(path) for path in selected_capture], 'package_members': sorted(members),
            'reference_case': ref_case_path, 'reference_state': ref_state,
            'fingerprint': fingerprint, 'capture_inferred_start_utc': datetime.fromtimestamp(inferred_start,timezone.utc).isoformat()}


def write_new(path, data):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, indent=2); stream.write('\n')


def validate_report(name, document, paths, selected, deps):
    require(document.get('schema') == SCHEMAS[name] and document.get('passed') is True, 'Missing/failed current auditor result')
    require(document.get('audit_script_sha256') == deps[SCRIPTS[name]], 'Auditor result source identity differs')
    if 'checks' in document:
        require(document['checks'] and all(type(value) is bool and value for value in document['checks'].values()), 'Incomplete auditor checks')
    mesh_sha = selected['input_hashes']['physics_mesh']
    capture = paths['capture']
    if name == 'runtime':
        for field, source in (('runtime_sha256',capture/'phase6-runtime.json'),('interaction_sha256',capture/'phase6-interaction-test.json'),('unreal_log_sha256',capture/'ue.log')):
            require(document.get(field) == selected['inventory'][str(source)]['sha256'], 'Runtime report selected-input mismatch: '+field)
        require(document.get('physical_source', {}).get('sha256') == mesh_sha, 'Runtime report mesh differs')
    elif name == 'geometry':
        require(document.get('asset_sha256') == mesh_sha, 'Geometry report mesh differs')
    elif name == 'snapshot':
        require(len(document.get('snapshots', [])) == len(selected['snapshots']), 'Snapshot report membership differs')
        for result, path in zip(document['snapshots'], selected['snapshots']):
            require(result.get('snapshot_sha256') == selected['inventory'][str(path)]['sha256']
                    and result.get('physical_source', {}).get('sha256') == mesh_sha, 'Snapshot report selected input differs')
    elif name == 'dataset':
        require(document.get('physics_mesh_sha256') == mesh_sha
                and document.get('scene_sha256') == selected['input_hashes']['scene']
                and document.get('visual_manifest_sha256') == selected['inventory'][str(capture/'dataset/visual-manifest.json')]['sha256'], 'Dataset report selected inputs differ')
    elif name == 'context':
        for field, source in (('native_reference_sha256',paths['native_reference']),('presented_sha256',capture/'phase5-presented-states.jsonl')):
            require(document.get(field) == selected['inventory'][str(source)]['sha256'], 'Context report selected input differs: '+field)
        require(document.get('scene_sha256') == selected['input_hashes']['scene']
                and document.get('physics_mesh_sha256') == mesh_sha, 'Context report package inputs differ')
    elif name == 'appearance':
        require(document.get('metrics', {}).get('manifest_sha256') == selected['inventory'][str(capture/'dataset/visual-manifest.json')]['sha256']
                and document.get('metrics', {}).get('asset_bytes_verified') is True, 'Appearance report does not bind actual package assets')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('capture', 'package', 'native-reference', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--python', type=Path, default=Path('C:/Users/Avalon/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'),
                        help='NumPy/Pillow-enabled audit interpreter; all child audits use this exact executable')
    parser.add_argument('--plan-only', action='store_true', help='Static source/API/command plan only; no audits, bulk hashing or writes')
    args = parser.parse_args()
    require(sys.flags.optimize == 0, 'Run without Python -O; inherited assertions are mandatory')
    paths = {name: checked(value, existing=not args.plan_only, directory=name in ('capture','package'))
             for name,value in vars(args).items() if isinstance(value,Path) and name != 'output'}
    paths['output'] = checked(args.output, existing=False)
    paths['assets'] = paths['package']/'Assets/Phase9'
    output = paths['output']
    require(output.is_relative_to(ROOT/'tmp/phase9') and output != ROOT/'tmp/phase9' and not output.exists(), 'Use a fresh audit child under tmp/phase9')
    for source in (paths['capture'],paths['package'],paths['native_reference'].parent):
        require(not output.is_relative_to(source) and not source.is_relative_to(output), 'Output must be separate from selected input trees')
    deps = source_contract()
    if args.plan_only:
        planned = jobs(paths, [paths['capture']/'<actual-snapshot-JSON-selected-during-preflight>'])
        print(json.dumps({'schema':'endoforge.phase9.package-audit-plan.v1','plan_only':True,'inputs':{key:str(value) for key,value in paths.items()},'dependencies':deps,'jobs':planned,'audits_launched':False,'bulk_input_hashing_performed':False,'overall_acceptance_passed':False,'separate_required':['presented-contact','presented-liver']},indent=2))
        return 0
    orchestrator = {'path':str(Path(__file__).resolve()),'sha256':sha(Path(__file__))}
    selected = prepare(paths, deps)
    planned = jobs(paths, selected['snapshots'])
    output.mkdir(parents=True,exist_ok=False)
    inputs = {'physics_exe_sha256':selected['input_hashes']['native_executable'],
              'physics_mesh_sha256':selected['input_hashes']['physics_mesh'],
              'game_exe_sha256':selected['input_hashes']['game_executable']}
    inventory_path = output/'selected-inputs.json'
    write_new(inventory_path, {'schema':'endoforge.phase9.selected-audit-inputs.v1','inputs':inputs,'paths':{key:str(value) for key,value in paths.items()},'files':selected['inventory'],'dependencies':deps,'capture_inferred_start_utc':selected['capture_inferred_start_utc']})
    inventory_sha = sha(inventory_path)
    write_new(output/'audit-plan.json', {'schema':'endoforge.phase9.package-audit-plan.v1','inputs':inputs,'jobs':planned,'selected_input_inventory_sha256':inventory_sha,'overall_acceptance_passed':False})
    records = {}
    environment = dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONOPTIMIZE='0',
                       OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    started = datetime.now(timezone.utc).isoformat()
    for job in planned:
        name = job['name']; report = Path(job['report'])
        record = {'path':str(report),'sha256':None,'passed':False,'exit_code':None,'inputs':inputs,
                  'selected_input_inventory_sha256':inventory_sha,'command':job['command'],
                  'audit_script_sha256':deps[SCRIPTS[name]],'orchestrator':orchestrator,
                  'started_utc':datetime.now(timezone.utc).isoformat()}
        clock = time.monotonic(); wall = time.time()
        stdout,stderr = output/(name+'.stdout.log'),output/(name+'.stderr.log')
        try:
            require(not report.exists() and not Path(job['target']).exists(), 'Use fresh per-auditor report/trace targets')
            with stdout.open('x',encoding='utf-8') as out,stderr.open('x',encoding='utf-8') as error:
                process = subprocess.run(job['command'],cwd=ROOT,env=environment,stdout=out,stderr=error,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            record['exit_code'] = process.returncode
            require(process.returncode == 0, 'Auditor exited nonzero; see fresh stdout/stderr logs')
            if name == 'extract':
                summary = json.loads(stdout.read_text(encoding='utf-8-sig'))
                trace = checked(job['target'])
                require(trace.stat().st_mtime >= wall and summary.get('sha256') == sha(trace)
                        and summary.get('physics_mesh_sha256') == inputs['physics_mesh_sha256']
                        and summary.get('phase') == 9 and summary.get('states',0) >= 30, 'Fresh trace extraction evidence differs')
                with trace.open(encoding='utf-8-sig') as stream: header = json.loads(next(stream))
                provenance = header['provenance']
                require(provenance['native_reference_sha256'] == selected['inventory'][str(paths['native_reference'])]['sha256']
                        and provenance['physics_mesh_sha256'] == inputs['physics_mesh_sha256']
                        and provenance['presented_sha256'] == selected['inventory'][str(paths['capture']/'phase5-presented-states.jsonl')]['sha256'], 'Extracted trace input bindings differ')
                document = {'schema':'endoforge.phase9.presented-extraction-record.v1','phase':9,'passed':True,'exit_code':process.returncode,'inputs':inputs,'summary':summary,'selected_input_inventory_sha256':inventory_sha,'native_reference_sha256':provenance['native_reference_sha256'],'scope':'Trace preparation only; presented contact/liver audits remain separate.'}
                write_new(report,document)
            else:
                require(report.is_file() and report.stat().st_mtime >= wall, 'Fresh auditor report was not created')
                validate_report(name,read(report),paths,selected,deps)
            record.update(passed=True,sha256=sha(report))
        except Exception as error:
            record.update(error_type=type(error).__name__,error=str(error),sha256=sha(report) if report.is_file() else None)
        record.update(completed_utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=round(time.monotonic()-clock,3),stdout_path=str(stdout),stderr_path=str(stderr))
        invocation = output/(name+'.invocation.json')
        write_new(invocation,record)
        record['invocation_record'] = {'path':str(invocation),'sha256':sha(invocation)}
        records[name] = record
        print(json.dumps({'audit':name,'passed':record['passed'],'exit_code':record['exit_code'],'elapsed_seconds':record['elapsed_seconds']}),flush=True)
    stability_error = None
    try:
        unchanged = (source_contract() == deps and sha(Path(__file__)) == orchestrator['sha256']
            and all(metadata(path) == selected['metadata'][str(path)] and sha(path) == selected['inventory'][str(path)]['sha256'] for path in selected['selected_paths'])
            and [str(path) for path in walk(paths['capture'],{'native-session','native-sessions','sessions','__pycache__'})] == selected['capture_members']
            and {path.relative_to(paths['package']).as_posix() for path in walk(paths['package'],{'saved','logs','sessions','__pycache__'})} == set(selected['package_members']) | {'assembly-manifest.json'})
    except Exception as error:
        unchanged = False
        stability_error = str(error)
    small_passed = unchanged and all(record['passed'] for record in records.values())
    index = {'schema':'endoforge.phase9.package-capture-audit-index.v1','phase':9,'started_utc':started,'created_utc':datetime.now(timezone.utc).isoformat(),
             'capture':str(paths['capture']),'package':str(paths['package']),'assets':str(paths['assets']),
             'inputs':inputs,'orchestrator':orchestrator,'selected_input_inventory':{'path':str(inventory_path),'sha256':inventory_sha},
             'reports':{name:record for name,record in records.items() if name!='extract'},'extraction_report':records['extract'],
             'reference':{'trace':str(paths['native_reference']),'trace_sha256':selected['inventory'][str(paths['native_reference'])]['sha256'],'actual_case_report':str(selected['reference_case']),'case_report_sha256':selected['inventory'][str(selected['reference_case'])]['sha256'],'config_matches_capture_required':True},
             'inputs_unchanged':unchanged,'input_stability_error':stability_error,'independent_small_audits_passed':small_passed,'overall_acceptance_passed':False,
             'required_separate_audits':{'presented-contact':{'executed_by_this_runner':False,'passed':None},'presented-liver':{'executed_by_this_runner':False,'passed':None}},
             'scope':'Six existing independent actual-package capture/source audits plus actual-reference-bound unresampled trace extraction. All report records bind selected executable/mesh/game hashes, source identity and explicit exit codes. Large presented contact/liver trajectory audits, complete native qualification, human visual approval and final delivery acceptance remain separate.'}
    write_new(output/'audit-run.json',index)
    print(json.dumps({'index':str(output/'audit-run.json'),'independent_small_audits_passed':small_passed,'overall_acceptance_passed':False}))
    return 0 if small_passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
