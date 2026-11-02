"""Seal completed native nominal children for early independent geometry only."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / 'tmp/phase9/native-qualification-final02'
OUT = RUN / 'early-case-seals'
NAMES = ('tool0-nominal', 'tool1-nominal', 'dual-2mm')
EXE_SHA = '2ab82f5b9d74419ae4507f698d4dcb5b071e43d3cbae5ef188d41be8a3a2f3a0'
MESH_SHA = 'bb78f5c1950d14c6656d476d199f6f5f03743ebe886c47d1030ca570ee8085ec'


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fingerprint(path):
    before = path.stat()
    digest = sha(path)
    after = path.stat()
    require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
            'Artifact changed while hashing: ' + str(path))
    return {'path': str(path.resolve()), 'bytes': after.st_size, 'mtime_ns': after.st_mtime_ns,
            'sha256': digest}


def main():
    require(not OUT.exists(), 'Use fresh seals; never overwrite previous evidence')
    plan_path = RUN / 'adaptation-plan.json'
    plan = read(plan_path)
    binary = Path(plan['native_binary']['path'])
    mesh = Path(plan['mesh']['path'])
    require(plan['native_binary']['sha256'] == sha(binary) == EXE_SHA, 'Wrong native identity')
    require(plan['mesh']['sha256'] == sha(mesh) == MESH_SHA, 'Wrong mesh identity')
    adaptation = next(a for a in plan['adaptations'] if a['source'] == 'Physics/run_phase6_long_hold.py')
    driver = Path(adaptation['generated'])
    require(sha(driver) == adaptation['generated_sha256'], 'Generated driver identity changed')
    require(sha(ROOT / adaptation['source']) == adaptation['source_sha256'], 'Original driver identity changed')
    driver_lines = driver.read_text(encoding='utf-8').splitlines()
    required = ('result = subprocess.run(',
                'ok = result.returncode == 0 and value.get("passed") is True',
                'name, result = future.result()',
                'print(json.dumps({"case": name, "passed": result["passed"]')
    evidence_lines = []
    for fragment in required:
        matches = [(n + 1, line.strip()) for n, line in enumerate(driver_lines) if fragment in line]
        require(len(matches) == 1, 'Completion control-flow anchor changed: ' + fragment)
        evidence_lines.append({'line': matches[0][0], 'text': matches[0][1]})
    spec = importlib.util.spec_from_file_location('phase9_executed_hold_driver', driver)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected = dict(module.cases())  # Pure option generation; no child process is launched.
    completion_log = RUN / 'long-hold.log'
    prefix = completion_log.read_bytes()
    events = {}
    offset = 0
    for raw in prefix.splitlines(keepends=True):
        require(raw.endswith(b'\n'), 'Completion log ends with a partial event')
        event = json.loads(raw)
        if event.get('case') in NAMES:
            require(event['case'] not in events and event.get('passed') is True,
                    'Missing unique successful completion event')
            events[event['case']] = {'event': event, 'byte_offset': offset,
                                    'event_line': raw.decode('utf-8').rstrip('\r\n'),
                                    'event_line_sha256': hashlib.sha256(raw).hexdigest()}
        offset += len(raw)
    require(set(events) == set(NAMES), 'All nominal child-completion events are required')
    reference = read(RUN / 'dual-reference.json')
    checkpoint = read(RUN / 'checkpoint.json')
    require(checkpoint['native_sha256'] == EXE_SHA and len(checkpoint['completed']) >= 20,
            'Base native suite identity/completion unavailable')
    first_pass = {}
    reports = {}
    for name in NAMES:
        report_path = RUN / 'long-hold' / (name + '.json')
        value = read(report_path)
        require(value.get('passed') is True and value.get('milestone') == 9 and value.get('phase') == 6,
                'Report must pass as a tagged Phase9 native test: ' + name)
        require(value['checks'] and all(v is True for v in value['checks'].values()), 'Report check failed')
        require(value['config'] == reference['config'], 'Nominal full physics config differs from sealed reference')
        require(value['config']['asset_fingerprint'] == 'fnv1a64:a401268b7d86193d', 'Wrong asset fingerprint')
        require(value['options'] == expected[name], 'Nominal case options differ from executed driver')
        option_path = report_path.with_name(name + '-options.json')
        require(read(option_path) == expected[name], 'Options file changed')
        trace = Path(value['trace']).resolve()
        require(trace == (report_path.parent / (name + '-states.jsonl')).resolve(), 'Wrong trace path')
        audit = value['phase9_output_audit']
        require(audit['all_audits_passed'] is True and audit['failed_samples'] == 0
                and audit['nonzero_contact_reference_exercised'] is True, 'Native output audit did not pass')
        output_audit = Path(audit['trace']).resolve()
        paths = {'report': report_path, 'trace': trace, 'options': option_path,
                 'native_log': report_path.with_suffix('.log'), 'phase9_output_audit_trace': output_audit}
        first_pass[name] = {kind: fingerprint(path) for kind, path in paths.items()}
        reports[name] = value
    # Second full hash pass verifies every artifact, including complete trace bytes.
    for name, artifacts in first_pass.items():
        for kind, item in artifacts.items():
            require(fingerprint(Path(item['path'])) == item, 'Artifact failed stable second hash: ' + name + '/' + kind)
    require(sha(binary) == EXE_SHA and sha(mesh) == MESH_SHA, 'Input identity changed while sealing')
    with completion_log.open('rb') as handle:
        require(handle.read(len(prefix)) == prefix, 'Completion log prefix changed while sealing')
    OUT.mkdir()
    index = {'schema': 'endoforge.phase9.native-early-long-hold-case-seal-index.v1',
             'created_at_utc': datetime.now(timezone.utc).isoformat(), 'cases': {},
             'scope': 'Early independent geometry dispatch only. Does not replace all15 raw-state audits, final long-hold index, outer checkpoint, or native35 qualification.'}
    for name in NAMES:
        value = reports[name]
        seal = {'schema': 'endoforge.phase9.native-early-long-hold-case-seal.v1',
                'case': name, 'sealed_at_utc': index['created_at_utc'],
                'native_child_completion': {'exit_code': 0, 'report_passed': True,
                    'evidence_kind': 'executed-driver-post-subprocess-wait-passed-event',
                    'exit_code_observation': 'Exit0 is a necessary condition of the emitted passed:true event in this exact executed driver; numeric exit code is not separately logged and no already-reaped process is queried.',
                    'completion_event': events[name],
                    'completion_log_prefix': {'path': str(completion_log.resolve()), 'bytes': len(prefix),
                                              'sha256': hashlib.sha256(prefix).hexdigest()},
                    'executed_driver': {'path': str(driver.resolve()), 'sha256': sha(driver),
                                        'control_flow_lines': evidence_lines},
                    'adaptation_plan': {'path': str(plan_path.resolve()), 'sha256': sha(plan_path)}},
                'native_binary': {'path': str(binary.resolve()), 'sha256': EXE_SHA},
                'mesh': {'path': str(mesh.resolve()), 'sha256': MESH_SHA,
                         'asset_fingerprint': value['config']['asset_fingerprint']},
                'config': value['config'], 'options': value['options'],
                'artifacts': first_pass[name], 'stable_full_hash_passes': 2,
                'native_report_checks': value['checks'],
                'native_report_metrics': value['metrics'],
                'native_output_audit': value['phase9_output_audit'],
                'seal_script': {'path': str(Path(__file__).resolve()), 'sha256': sha(__file__)},
                'qualification_claim': False, 'scope': index['scope']}
        path = OUT / (name + '.json')
        with path.open('x', encoding='utf-8', newline='\n') as handle:
            json.dump(seal, handle, indent=2)
            handle.write('\n')
        index['cases'][name] = {'path': str(path.resolve()), 'sha256': sha(path)}
    with (OUT / 'index.json').open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(index, handle, indent=2)
        handle.write('\n')
    print(json.dumps(index, indent=2), flush=True)


if __name__ == '__main__':
    main()
