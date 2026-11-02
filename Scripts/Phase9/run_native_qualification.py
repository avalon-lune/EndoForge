"""Run all 35 existing native regression cases against explicit Phase9 inputs.

The Phase6 test bodies, case options and acceptance thresholds are retained.
Small generated driver copies change paths and provenance only; original files
and the selected runtime are read only. This creates fresh execution evidence,
never an inherited pass. --plan-only performs no writes or native execution.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def expected_cases():
    base = (['interaction', 'dual-reference'] +
            [f'matrix-a{angle}-s{speed}-{path}' for angle in (75, 90, 105)
             for speed, path in ((6, 'straight'), (12, 'lateral'), (18, 'forward'))] +
            ['replay', 'network', 'fresh-process-replays', 'endurance',
             'asset-validation', 'legacy-phase3', 'legacy-phase3-network',
             'legacy-phase4', 'legacy-phase4-network'])
    holds = ['tool0-nominal', 'tool1-nominal', 'dual-2mm'] + [
        f'tool{tool}-{axis}-{direction}' for tool in (0, 1)
        for axis in 'xyz' for direction in ('minus', 'plus')]
    return base + ['long-hold-' + name for name in holds]


def fresh_output(value):
    path = Path(os.path.abspath(value))
    for ancestor in reversed((path, *path.parents)):
        if ancestor.exists() or ancestor.is_symlink():
            info = ancestor.stat(follow_symlinks=False)
            require(not stat.S_ISLNK(info.st_mode)
                    and not getattr(info, 'st_file_attributes', 0) & REPARSE,
                    'Output must not contain links or reparse points: ' + str(ancestor))
    allowed = (ROOT / 'tmp/phase9', ROOT / 'output/Phase9')
    require(any(path.is_relative_to(folder) and path != folder for folder in allowed),
            'Output must be a fresh child of tmp/phase9 or output/Phase9')
    require(not path.exists(), 'Use a completely fresh qualification output directory')
    return path


def driver_sources(mesh, executable, output):
    """Return adapted text and exact replacement records without writing files."""
    drivers = output / '_drivers'
    physics = ROOT / 'Physics'
    runtime = executable.parent
    old3 = output / 'legacy-phase3-network-isolated'
    old4 = output / 'legacy-phase4-network-isolated'
    path = lambda value: 'pathlib.Path(' + repr(str(value)) + ')'
    ppath = lambda value: 'Path(' + repr(str(value)) + ')'
    adapted = {}
    records = []

    def add(relative, replacements=()):
        original = ROOT / relative
        data = original.read_bytes()
        text = data.decode('utf-8-sig')
        changes = []
        for before, after, count in replacements:
            require(text.count(before) == count,
                    f'Path adaptation anchor changed in {relative}: {before!r}')
            text = text.replace(before, after)
            changes.append({'before': before, 'after': after, 'count': count})
        ast.parse(text, filename=str(drivers / original.name))
        adapted[original.name] = text
        records.append({'source': relative, 'source_sha256': hashlib.sha256(data).hexdigest(),
                        'generated': str(drivers / original.name),
                        'generated_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                        'replacements': changes})

    add('Physics/run_phase6_regression.py', [
        ('ROOT = pathlib.Path(__file__).resolve().parent.parent', 'ROOT = ' + path(ROOT), 1),
        ("EXE = BASE / 'runtime/LapPhysics.exe'", 'EXE = ' + path(executable), 1),
        ("sys.path.insert(0, str(ROOT/'Scripts/Phase6'))", f'sys.path.insert(0, {str(drivers)!r})', 1),
        ('out.mkdir(parents=True, exist_ok=False)', 'out.mkdir(parents=True, exist_ok=True)', 1),
        ("'schema': 'endoforge.phase6.native-run.v1'", "'schema': 'endoforge.phase9.native-run.v1', 'qualification_phase': 9, 'native_test_mode_phase': 6, 'inherited_results': False", 1),
        ("cmd = [EXE] + arguments + ['--report', report]", f"cmd = [EXE] + arguments + ['--mesh', {path(mesh)}, '--report', report]", 1),
        ("BASE / 'test_phase5_network.py'", path(drivers / 'test_phase5_network.py'), 1),
        ("BASE / 'test_phase5_replay_fixture.py'", path(drivers / 'test_phase5_replay_fixture.py'), 1),
        ("BASE / 'test_phase5_assets.py'", path(drivers / 'test_phase5_assets.py'), 1),
        ("BASE / f'test_phase{phase}_network.py'", path(drivers) + " / f'test_phase{phase}_network.py'", 1),
        ("runtime_report = BASE / f'runtime/phase{phase}-network-test-results.json'", "runtime_report = out / f'legacy-phase{phase}-network-isolated/report.json'", 1),
    ])
    add('Physics/test_phase5_network.py', [
        ('BASE = pathlib.Path(__file__).resolve().parent', 'BASE = ' + path(physics), 1),
        ("EXE = BASE / 'runtime/LapPhysics.exe'", 'EXE = ' + path(executable), 1),
        ("MODEL = json.loads((BASE/f'runtime/assets/phase{args.phase}.json').read_text())", f'MODEL = json.loads({path(mesh)}.read_text())', 1),
        ("[str(EXE), f'--phase{args.phase}', '--port'", f"[str(EXE), f'--phase{{args.phase}}', '--mesh', {str(mesh)!r}, '--port'", 1),
    ])
    add('Physics/test_phase5_replay_fixture.py', [
        ("exe=pathlib.Path(__file__).parent/'runtime/LapPhysics.exe'", 'exe=' + path(executable), 1),
        ("[str(exe.resolve()),f'--phase{args.phase}','--port'", f"[str(exe.resolve()),f'--phase{{args.phase}}','--mesh',{str(mesh)!r},'--port'", 1),
    ])
    add('Physics/test_phase5_assets.py', [
        ('BASE=pathlib.Path(__file__).resolve().parent', 'BASE=' + path(physics), 1),
        ("EXE=BASE/'runtime/LapPhysics.exe'", 'EXE=' + path(executable), 1),
        ("SOURCE=BASE.parent/f'Assets/Phase{args.phase}/physics-mesh.json'", 'SOURCE=' + path(mesh), 1),
        ("[str(EXE),f'--phase{args.phase}','--config'", f"[str(EXE),f'--phase{{args.phase}}','--mesh',{str(mesh)!r},'--config'", 1),
    ])
    add('Physics/test_phase3_network.py', [
        ('BASE = pathlib.Path(__file__).resolve().parent', 'BASE = ' + path(physics), 1),
        ("RUNTIME = BASE / 'runtime'", 'RUNTIME = ' + path(runtime), 1),
        ("(RUNTIME / 'phase3-network-test.log')", path(old3 / 'service.log'), 1),
        ("(RUNTIME / 'phase3-network-test-results.json')", path(old3 / 'report.json'), 1),
    ])
    add('Physics/test_phase4_network.py', [
        ('BASE=pathlib.Path(__file__).resolve().parent', 'BASE=' + path(physics), 1),
        ("RUNTIME=BASE/'runtime'", 'RUNTIME=' + path(runtime), 1),
        ("SESSION=RUNTIME/'phase4-network-session'", 'SESSION=' + path(old4 / 'sessions'), 1),
        ("REPORT=RUNTIME/'phase4-network-test-results.json'", 'REPORT=' + path(old4 / 'report.json'), 1),
        ("(RUNTIME/'phase4-network-test.log')", path(old4 / 'service.log'), 1),
        ("(RUNTIME/'phase4-network-states.json')", path(old4 / 'states.json'), 1),
    ])
    add('Physics/run_phase6_long_hold.py', [
        ('ROOT = Path(__file__).resolve().parents[1]', 'ROOT = ' + ppath(ROOT), 1),
        ('EXE = ROOT / "Physics/runtime/LapPhysics.exe"', 'EXE = ' + ppath(executable), 1),
        ('ROOT/"Assets/Phase6/physics-mesh.json"', ppath(mesh), 1),
        ('[str(EXE), "--phase6", "--self-test-phase5"', f'[str(EXE), "--phase6", "--mesh", {str(mesh)!r}, "--self-test-phase5"', 1),
        ('"Assets/Phase6/physics-mesh.json phase6_interaction; material-bound shared public preset recipe, sampled at each approach"', repr(str(mesh) + ' phase6_interaction; material-bound shared public preset recipe, sampled at each approach'), 1),
    ])
    add('Scripts/Phase6/complete_native_suite.py', [
        ('ROOT = Path(__file__).resolve().parents[2]', 'ROOT = ' + ppath(ROOT), 1),
        ("ROOT/'Physics/runtime/LapPhysics.exe'", ppath(executable), 1),
        ("ROOT/'Physics/run_phase6_long_hold.py'", ppath(drivers / 'run_phase6_long_hold.py'), 1),
    ])
    add('Scripts/Phase6/native_long_hold.py', [
        ("root/'Physics/run_phase6_long_hold.py'", ppath(drivers / 'run_phase6_long_hold.py'), 1),
    ])
    add('Scripts/Phase6/common.py')
    spec = ROOT / 'Scripts/Phase6/acceptance-spec.json'
    adapted[spec.name] = spec.read_text(encoding='utf-8-sig')
    records.append({'source': spec.relative_to(ROOT).as_posix(), 'source_sha256': sha(spec),
                    'generated': str(drivers / spec.name),
                    'generated_sha256': hashlib.sha256(adapted[spec.name].encode('utf-8')).hexdigest(),
                    'replacements': []})
    return adapted, records


def write_new(path, data):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesh', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True,
                        help='Read-only runtime directory, or its LapPhysics.exe')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--long-hold-workers', type=int, choices=(1, 2), default=2)
    parser.add_argument('--plan-only', action='store_true', help='Print the exact adaptation plan; write nothing and launch no native process')
    args = parser.parse_args()
    require(sys.flags.optimize == 0, 'Python optimization disables inherited assertion gates; run without -O')
    mesh, selected_runtime = args.mesh.resolve(), args.runtime.resolve()
    executable = selected_runtime / 'LapPhysics.exe' if selected_runtime.is_dir() else selected_runtime
    require(mesh.is_file(), 'Explicit mesh must be an existing file')
    require(executable.is_file() and executable.name.casefold() == 'lapphysics.exe',
            'Runtime must contain LapPhysics.exe, with its existing dependencies')
    output = fresh_output(args.output)
    spec = json.loads((ROOT / 'Scripts/Phase6/acceptance-spec.json').read_text(encoding='utf-8-sig'))
    model = json.loads(mesh.read_text(encoding='utf-8-sig'))
    tips = [recipe['rest_ready_tip_m'] for recipe in model['phase6_interaction']['recipes']]
    require(tips == spec['physics']['long_hold']['nominal_rest_ready_tips_m'],
            'Selected mesh authored ready tips differ from the frozen Phase6 pose gate; review this explicit contract change before qualification')
    texts, adaptations = driver_sources(mesh, executable, output)
    names = expected_cases()
    require(len(names) == len(set(names)) == 35, 'Expected all twenty base and fifteen long-hold cases')
    command = [sys.executable, '-B', str(output / '_drivers/run_phase6_regression.py'),
               '--output', str(output), '--long-hold-workers', str(args.long_hold_workers)]
    plan = {'schema': 'endoforge.phase9.native-qualification-plan.v1', 'qualification_phase': 9,
            'native_test_mode_phase': 6, 'plan_only': args.plan_only,
            'native_execution_started': False, 'inherited_results': False,
            'mesh': {'path': str(mesh), 'sha256': sha(mesh)},
            'native_binary': {'path': str(executable), 'sha256': sha(executable)},
            'output': str(output), 'expected_cases': names, 'case_count': len(names),
            'adaptations': adaptations, 'command': command,
            'scope': 'Fresh execution of unchanged native case bodies/options/thresholds against the explicit selected mesh/runtime. Path and metadata adaptations only. No inherited test results. Independent geometry/data audits, UE integration, performance, source/build provenance and delivery acceptance remain separate gates.'}
    if args.plan_only:
        print(json.dumps(plan, indent=2))
        return 0
    output.mkdir(parents=True, exist_ok=False)
    drivers = output / '_drivers'
    drivers.mkdir()
    for name, text in texts.items():
        with (drivers / name).open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
    for phase in (3, 4):
        (output / f'legacy-phase{phase}-network-isolated').mkdir()
    write_new(output / 'adaptation-plan.json', plan)
    started = utc_now()
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    with (output / 'suite.log').open('x', encoding='utf-8') as log:
        result = subprocess.run(command, cwd=ROOT, env=environment, stdout=log,
                                stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    checks = {'suite_exit_zero': result.returncode == 0,
              'native_binary_unchanged': sha(executable) == plan['native_binary']['sha256'],
              'selected_mesh_unchanged': sha(mesh) == plan['mesh']['sha256'],
              'original_drivers_and_spec_unchanged': all(sha(ROOT / item['source']) == item['source_sha256'] for item in adaptations),
              'generated_drivers_and_spec_unchanged': all(sha(item['generated']) == item['generated_sha256'] for item in adaptations)}
    checkpoint_path = output / 'checkpoint.json'
    checkpoint = json.loads(checkpoint_path.read_text(encoding='utf-8')) if checkpoint_path.exists() else {}
    completed = checkpoint.get('completed', [])
    checks['all_35_cases_completed_in_order'] = checkpoint.get('status') == 'complete' and [item['name'] for item in completed] == names
    checks['all_current_reports_pass_and_match_hashes'] = checks['all_35_cases_completed_in_order'] and all(
        Path(item['report']).resolve().is_relative_to(output)
        and sha(item['report']) == item['sha256']
        and json.loads(Path(item['report']).read_text(encoding='utf-8-sig')).get('passed') is True
        for item in completed)
    report = {'schema': 'endoforge.phase9.native-qualification.v1', 'phase': 9,
              'native_test_mode_phase': 6, 'started_utc': started, 'completed_utc': utc_now(),
              'native_execution_started': True, 'inherited_results': False,
              'native_exit_code': result.returncode, 'passed': all(checks.values()),
              'checks': checks, 'mesh': plan['mesh'], 'native_binary': plan['native_binary'],
              'case_count': len(completed), 'expected_case_count': len(names),
              'adaptation_plan_sha256': sha(output / 'adaptation-plan.json'),
              'checkpoint_sha256': sha(checkpoint_path) if checkpoint_path.exists() else None,
              'completed': completed, 'scope': plan['scope']}
    write_new(output / 'qualification.json', report)
    print(json.dumps(report))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
