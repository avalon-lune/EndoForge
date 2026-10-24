"""Run the frozen native Phase6 regression sequentially; retain all raw evidence."""
import argparse
import datetime
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import time


ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = ROOT / 'Physics'
EXE = BASE / 'runtime/LapPhysics.exe'
sys.path.insert(0, str(ROOT/'Scripts/Phase6'))
from complete_native_suite import append_long_hold_cases


def digest(path):
    with pathlib.Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=pathlib.Path, default=ROOT / 'tmp/phase6/physics/regression')
    parser.add_argument('--long-hold-workers', type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    frozen = digest(EXE)
    checkpoint = {'schema': 'endoforge.phase6.native-run.v1', 'native_sha256': frozen,
                  'started_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'completed': []}
    jobs = []
    def run(name, cmd, report):
        assert digest(EXE) == frozen, 'Native executable changed during regression'
        while (out / 'PAUSE_REQUEST').exists():
            checkpoint['status'] = 'paused_at_case_boundary'
            (out / 'checkpoint.json').write_text(json.dumps(checkpoint, indent=2))
            time.sleep(1)
        checkpoint['status'] = 'running'
        checkpoint['current'] = name
        (out / 'checkpoint.json').write_text(json.dumps(checkpoint, indent=2))
        started = time.time()
        with (out / f'{name}.log').open('w', encoding='utf-8') as log:
            result = subprocess.run([str(x) for x in cmd], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
        assert digest(EXE) == frozen, 'Native executable changed during test'
        document = json.loads(report.read_text(encoding='utf-8-sig'))
        assert result.returncode == 0 and document.get('passed') is True, f'{name} failed; see {report}'
        document.update(executable_sha256=frozen, native_exit_code=result.returncode,
                        tested_at_utc=datetime.datetime.fromtimestamp(started, datetime.timezone.utc).isoformat())
        report.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
        jobs.append({'name': name, 'report': str(report), 'sha256': digest(report), 'wall_seconds': time.time() - started})
        checkpoint['completed'] = jobs
        (out / 'checkpoint.json').write_text(json.dumps(checkpoint, indent=2))
        print(name, 'passed', round(time.time() - started, 2), flush=True)
    def native(name, arguments, options=None):
        report = out / f'{name}.json'
        cmd = [EXE] + arguments + ['--report', report]
        if options is not None:
            p = out / f'{name}-options.json';p.write_text(json.dumps(options))
            cmd += ['--probe-options', p]
        run(name, cmd, report)
    native('interaction', ['--self-test-phase6'])
    native('dual-reference', ['--phase6', '--self-test-phase5'], {'dual': True, 'lift_m': .002, 'assembly_compare': True})
    for angle in (75, 90, 105):
        for speed, path in ((6, 'straight'), (12, 'lateral'), (18, 'forward')):
            native(f'matrix-a{angle}-s{speed}-{path}', ['--phase6', '--self-test-phase5'],
                   {'dual': True, 'lift_m': .002, 'roll': angle, 'speed_m_s': speed / 1000, 'path': path})
    native('replay', ['--phase6', '--self-test-phase5'], {'dual': True, 'lift_m': .002, 'replay': True})
    run('network', [sys.executable, BASE / 'test_phase5_network.py', '--phase', '6', '--port', '47332', '--output', out / 'network'], out / 'network/report.json')
    actions = sorted((out / 'network/sessions').glob('*-actions.json'))
    assert len(actions) == 1
    run('fresh-process-replays', [sys.executable, BASE / 'test_phase5_replay_fixture.py', '--phase', '6', '--actions', actions[0], '--output', out / 'fixture-final-five', '--port', '47332', '--repeats', '5'], out / 'fixture-final-five/report.json')
    native('endurance', ['--phase6', '--self-test-phase5'], {'dual': True, 'lift_m': .002, 'cycles': 50})
    run('asset-validation', [sys.executable, BASE / 'test_phase5_assets.py', '--phase', '6', '--output', out / 'asset-validation'], out / 'asset-validation/report.json')
    for phase in (3, 4):
        report = out / f'legacy-phase{phase}.json'
        run(f'legacy-phase{phase}', [EXE, f'--self-test-phase{phase}', report], report)
        runtime_report = BASE / f'runtime/phase{phase}-network-test-results.json'
        run(f'legacy-phase{phase}-network', [sys.executable, BASE / f'test_phase{phase}_network.py'], runtime_report)
        copied = out / f'legacy-phase{phase}-network.json';shutil.copy2(runtime_report, copied)
        jobs[-1]['report'] = str(copied);jobs[-1]['sha256'] = digest(copied)
    checkpoint['completed'] = jobs
    checkpoint = append_long_hold_cases(out, checkpoint, args.long_hold_workers)
    checkpoint.update(status='complete', current=None)
    (out / 'checkpoint.json').write_text(json.dumps(checkpoint, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
