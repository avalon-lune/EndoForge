"""Finish an interrupted frozen native suite without repeating passed cases.

Only the final legacy protocol-4 socket test may be missing. Its test logic is
unchanged; the service port and output files are isolated from older deliveries.
Every previously completed report and the native binary must still match their
checkpoint hashes before the missing test is run or the suite is sealed.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from native_long_hold import expected_long_hold_cases, validate_long_hold


ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def base_expected_cases():
    return (['interaction', 'dual-reference'] +
            [f'matrix-a{angle}-s{speed}-{path}' for angle in (75, 90, 105)
             for speed, path in ((6, 'straight'), (12, 'lateral'), (18, 'forward'))] +
            ['replay', 'network', 'fresh-process-replays', 'endurance',
             'asset-validation', 'legacy-phase3', 'legacy-phase3-network',
             'legacy-phase4', 'legacy-phase4-network'])


def expected_cases():
    return base_expected_cases() + ['long-hold-'+name for name in expected_long_hold_cases()]


def append_long_hold_cases(out, checkpoint, workers=2):
    """Extend the unchanged twenty cases with all fifteen required hold cases."""
    frozen = checkpoint['native_sha256']
    binary = ROOT/'Physics/runtime/LapPhysics.exe'
    assert sha(binary) == frozen, 'Native binary changed before long-hold validation'
    existing = [item['name'] for item in checkpoint['completed']]
    assert existing in (base_expected_cases(), expected_cases()), 'Long holds require complete base regression'
    folder = out/'long-hold'; summary = folder/'long-hold-report.json'
    if not folder.exists():
        checkpoint.update(status='running', current='long-hold-15')
        (out/'checkpoint.json').write_text(json.dumps(checkpoint, indent=2)+'\n', encoding='utf-8')
        with (out/'long-hold.log').open('x', encoding='utf-8') as log:
            result = subprocess.run([sys.executable, str(ROOT/'Physics/run_phase6_long_hold.py'),
                                     '--output', str(folder), '--workers', str(workers)], cwd=ROOT,
                                    stdout=log, stderr=subprocess.STDOUT,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0, 'Long-hold validation failed; raw evidence is preserved'
    assert sha(binary) == frozen, 'Native binary changed during long-hold validation'
    validated = validate_long_hold(ROOT, summary, frozen)
    additions = [{'name': name, 'report': item['path'], 'sha256': item['sha256'],
                  'binary_identity_source': str(summary)} for name, item in validated['evidence'].items()]
    if existing == expected_cases():
        assert checkpoint['completed'][len(base_expected_cases()):] == additions, 'Completed long-hold evidence changed'
    else:
        checkpoint['completed'].extend(additions)
    checkpoint['long_hold_summary'] = {'path': str(summary), 'sha256': sha(summary)}
    return checkpoint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--latency', type=Path, required=True)
    parser.add_argument('--port', type=int, default=47336)
    parser.add_argument('--long-hold-workers', type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT / 'tmp/phase6'):
        raise ValueError('Resume evidence must remain under tmp/phase6')
    checkpoint_path = out / 'checkpoint.json'
    checkpoint = read(checkpoint_path)
    binary = ROOT / 'Physics/runtime/LapPhysics.exe'
    frozen = sha(binary)
    assert frozen == checkpoint['native_sha256'], 'Frozen binary changed'
    completed = checkpoint['completed']
    names = [item['name'] for item in completed]
    expected = base_expected_cases()
    assert names in (expected, expected[:-1], expected_cases()), 'Unexpected incomplete case list'
    for item in completed:
        path = Path(item['report'])
        report = read(path)
        assert sha(path) == item['sha256'], 'Previously completed report changed: ' + str(path)
        assert report.get('passed') is True and all(v is True for v in report.get('checks', {}).values())
        if not item['name'].startswith('long-hold-'):
            assert report['executable_sha256'] == frozen
    if names == expected[:-1]:
        assert checkpoint['status'] == 'paused_at_case_boundary'
        isolated = out / 'legacy-phase4-network-isolated'
        isolated.mkdir(exist_ok=False)
        script = ROOT / 'Physics/test_phase4_network.py'
        source = script.read_text(encoding='utf-8-sig')
        replacements = {
            'PORT=47326': f'PORT={args.port}',
            "SESSION=RUNTIME/'phase4-network-session'": f'SESSION=pathlib.Path({str(isolated / "sessions")!r})',
            "REPORT=RUNTIME/'phase4-network-test-results.json'": f'REPORT=pathlib.Path({str(isolated / "report.json")!r})',
            "log=(RUNTIME/'phase4-network-test.log').open": f'log=pathlib.Path({str(isolated / "service.log")!r}).open',
            "(RUNTIME/'phase4-network-states.json').write_text": f'pathlib.Path({str(isolated / "states.json")!r}).write_text',
        }
        for before, after in replacements.items():
            assert source.count(before) == 1, 'Network test isolation anchor changed: ' + before
            source = source.replace(before, after)
        adapted = isolated / 'isolated-test.py'
        adapted.write_text('__file__ = ' + repr(str(script)) + '\n' + source, encoding='utf-8')
        manifest = {'original_test': str(script), 'original_test_sha256': sha(script),
                    'adapted_test_sha256': sha(adapted), 'overrides': replacements,
                    'scope': 'Only service port and output locations differ. Native executable, socket test logic, checks and thresholds are unchanged.'}
        (isolated / 'isolation.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        started = time.time()
        with (out / 'legacy-phase4-network.log').open('x', encoding='utf-8') as log:
            result = subprocess.run([sys.executable, str(adapted)], cwd=ROOT,
                                    stdout=log, stderr=subprocess.STDOUT,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
        assert sha(binary) == frozen, 'Native binary changed during missing test'
        assert sha(script) == manifest['original_test_sha256'], 'Original test changed during execution'
        document = read(isolated / 'report.json')
        assert result.returncode == 0 and document.get('passed') is True, 'Missing network case failed; diagnostic evidence is preserved'
        assert document['executable_sha256'] == frozen
        document.update(native_exit_code=result.returncode,
                        tested_at_utc=datetime.datetime.fromtimestamp(started, datetime.timezone.utc).isoformat(),
                        test_isolation=manifest)
        report_path = out / 'legacy-phase4-network.json'
        with report_path.open('x', encoding='utf-8') as stream:
            json.dump(document, stream, indent=2)
            stream.write('\n')
        completed.append({'name': 'legacy-phase4-network', 'report': str(report_path),
                          'sha256': sha(report_path), 'wall_seconds': time.time() - started})
    checkpoint = append_long_hold_cases(out, checkpoint, args.long_hold_workers)
    completed = checkpoint['completed']
    checkpoint.update(status='complete', current=None, completed=completed,
                      resumed_by='Scripts/Phase6/complete_native_suite.py',
                      completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2) + '\n', encoding='utf-8')
    result = subprocess.run([sys.executable, str(ROOT / 'Physics/summarize_phase6_tests.py'),
                             '--output', str(out), '--latency', str(args.latency.resolve())],
                            cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
