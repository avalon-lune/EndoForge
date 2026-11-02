"""Run the unchanged mandatory all-state hold validator on sealed final02 inputs."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / 'tmp/phase9/native-qualification-final02'
OUTPUT = RUN / 'long-hold-raw-state-audit.json'
DRIVERS = RUN / '_drivers'
sys.path.insert(0, str(DRIVERS))
from native_long_hold import expected_long_hold_cases, validate_long_hold


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    if OUTPUT.exists():
        raise FileExistsError('Never overwrite a raw-state audit result')
    started = time.monotonic()
    source_paths = [DRIVERS / 'native_long_hold.py', DRIVERS / 'common.py',
                    DRIVERS / 'acceptance-spec.json', RUN / 'qualification.json',
                    RUN / 'checkpoint.json', RUN / 'long-hold/long-hold-report.json',
                    RUN / 'dual-reference.json', Path(__file__).resolve()]
    before = {str(path): sha(path) for path in source_paths}
    qualification = json.loads((RUN / 'qualification.json').read_text())
    reference = json.loads((RUN / 'dual-reference.json').read_text())
    index = RUN / 'long-hold/long-hold-report.json'
    report = {'schema': 'endoforge.phase9.long-hold-raw-state-audit.v1',
              'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'passed': False, 'native_processes_launched': 0,
              'validator_call': 'validate_long_hold(ROOT, final02 long-hold index, qualified native hash, model_config=dual-reference.config, inspect_states=True)',
              'sources_and_input_documents_sha256': before,
              'qualification': {'path': str(RUN / 'qualification.json'),
                                'sha256': before[str(RUN / 'qualification.json')]},
              'scope': 'Unchanged every-recorded-state native_long_hold validator on all15 holds. Native35 execution and independent contact/liver geometry remain separately sealed requirements.'}
    try:
        if qualification['passed'] is not True or qualification['case_count'] != 35:
            raise ValueError('Full native35 execution must already pass')
        result = validate_long_hold(ROOT, index, qualification['native_binary']['sha256'],
                                    model_config=reference['config'], inspect_states=True)
        report['validation'] = result
        raw = result['raw_state_audits']
        checks = {'all_15_expected_cases_audited': set(raw) == set(expected_long_hold_cases()),
                  'every_raw_state_case_passed': bool(raw) and all(case['passed'] is True for case in raw.values()),
                  'validator_sources_and_documents_unchanged': all(sha(path) == digest for path, digest in before.items()),
                  'qualified_binary_unchanged': sha(qualification['native_binary']['path']) == qualification['native_binary']['sha256'],
                  'qualified_mesh_unchanged': sha(qualification['mesh']['path']) == qualification['mesh']['sha256']}
        report['checks'] = checks
        report['passed'] = all(checks.values())
        report['total_recorded_states_tested'] = sum(case['states'] for case in raw.values())
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        report['traceback'] = traceback.format_exc()
    report['elapsed_seconds'] = time.monotonic() - started
    with OUTPUT.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(report, handle, indent=2)
        handle.write('\n')
    print(json.dumps({key: report.get(key) for key in ('schema', 'passed', 'checks', 'error',
                      'total_recorded_states_tested', 'elapsed_seconds')}, indent=2), flush=True)
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
