"""Seal actual successful package capture audits without changing prior records."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SMALL = ROOT / 'tmp/phase9/audits-package-final01'
GEOMETRY = ROOT / 'tmp/phase9/presented-geometry-package-final01'
OUTPUT = SMALL / 'complete-audit-index.json'
sys.path.insert(0, str(ROOT / 'Scripts/Phase7'))
from audit_identity import verify_geometry_report


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def identity(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}


def all_checks(value):
    return isinstance(value, dict) and bool(value) and all(type(v) is bool and v for v in value.values())


def main():
    require(not OUTPUT.exists(), 'Never overwrite the complete index')
    small_path = SMALL / 'audit-run.json'
    small_before = sha(small_path)
    small = read(small_path)
    require(small['independent_small_audits_passed'] is True and small['inputs_unchanged'] is True,
            'All original small audits and selected input stability must pass')
    require(small['overall_acceptance_passed'] is False, 'Preserve the original small index scope')
    selected = read(small['selected_input_inventory']['path'])
    require(sha(small['selected_input_inventory']['path']) == small['selected_input_inventory']['sha256'],
            'Selected inventory changed')
    capture = Path(small['capture'])
    package = Path(small['package'])
    receipt_path = capture / 'package-run.json'
    receipt = read(receipt_path)
    require(receipt['integration_capture_completed'] is True
            and receipt['game_exit_code'] == receipt['native_exit_code'] == 0
            and receipt['native_graceful_exit'] is True and receipt['error'] is None,
            'Actual owned game/native receipts must be successful')
    require(receipt['inputs_sha256'] == receipt['inputs_after_sha256'], 'Actual capture inputs changed')
    actual_inputs = {'physics_exe_sha256': sha(package / 'Physics/LapPhysics.exe'),
                     'physics_mesh_sha256': sha(Path(small['assets']) / 'physics-mesh.json'),
                     'game_exe_sha256': sha(package / 'LapTrainer/Binaries/Win64/LapTrainer.exe')}
    require(actual_inputs == small['inputs'], 'Small-index selected executable/mesh/game inputs changed')
    require(receipt['inputs_sha256']['native_executable'] == actual_inputs['physics_exe_sha256']
            and receipt['inputs_sha256']['physics_mesh'] == actual_inputs['physics_mesh_sha256']
            and receipt['inputs_sha256']['game_executable'] == actual_inputs['game_exe_sha256'],
            'Actual package receipt input binding differs')
    for path, item in selected['files'].items():
        require(Path(path).stat().st_size == item['bytes'] and sha(path) == item['sha256'],
                'Previously selected package/capture/reference/source input changed: ' + path)
    extraction_path = SMALL / 'extract.json'
    extraction = read(extraction_path)
    require(extraction['passed'] is True and extraction['exit_code'] == 0
            and sha(extraction_path) == small['extraction_report']['sha256'], 'Extraction evidence changed')
    trace = Path(extraction['summary']['path'])
    trace_sha = sha(trace)
    require(trace_sha == extraction['summary']['sha256'], 'Extracted trace changed')
    reference_path = Path(small['reference']['actual_case_report'])
    reference_trace = Path(small['reference']['trace'])
    reference = read(reference_path)
    require(reference['passed'] is True and reference['native_exit_code'] == 0
            and reference['executable_sha256'] == actual_inputs['physics_exe_sha256']
            and sha(reference_path) == small['reference']['case_report_sha256']
            and sha(reference_trace) == small['reference']['trace_sha256'], 'Actual native reference identity differs')
    config = reference['config']
    config_sha = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':'),
                                           allow_nan=False).encode('utf-8')).hexdigest()
    resets = []
    count = 0
    previous = None
    with trace.open(encoding='utf-8-sig') as handle:
        header = json.loads(next(handle))
        for raw in handle:
            state = json.loads(raw)
            require(state['config'] == config and state['asset_fingerprint'] == config['asset_fingerprint'],
                    'Presented native state configuration differs from actual native reference')
            if previous is not None and (state.get('simulation_id') != previous.get('simulation_id')
                                        or state.get('frame', 0) < previous.get('frame', 0)):
                resets.append({'before_original_state': count - 1, 'after_original_state': count,
                               'simulation_id_before': previous.get('simulation_id'),
                               'simulation_id_after': state.get('simulation_id')})
            previous = state
            count += 1
    require(count == extraction['summary']['states'] == 1538, 'Original presented state membership differs')
    provenance = header['provenance']
    require(provenance['native_reference_sha256'] == small['reference']['trace_sha256']
            and provenance['physics_mesh_sha256'] == actual_inputs['physics_mesh_sha256']
            and provenance['presented_sha256'] == sha(capture / 'phase5-presented-states.jsonl'),
            'Actual extracted trace provenance differs')
    execution = read(GEOMETRY / 'execution.json')
    require(execution['passed'] is True and execution['native_processes_launched'] == 0,
            'Both offline audit invocations must complete successfully')
    reports = {}
    for name, item in small['reports'].items():
        report_path = Path(item['path'])
        report = read(report_path)
        invocation = read(item['invocation_record']['path'])
        require(item['passed'] is True and item['exit_code'] == invocation['exit_code'] == 0
                and invocation['passed'] is True and report.get('passed') is True
                and sha(report_path) == item['sha256']
                and sha(item['invocation_record']['path']) == item['invocation_record']['sha256'],
                'Small actual audit/exit/hash evidence failed: ' + name)
        if 'checks' in report:
            require(all_checks(report['checks']), 'Small auditor checks failed: ' + name)
        reports[name] = {**identity(report_path), 'passed': True, 'exit_code': 0,
                         'schema': report['schema'],
                         'invocation_record': item['invocation_record']}
        if 'checks' in report:
            reports[name]['checks'] = report['checks']
    require(set(reports) == {'appearance', 'runtime', 'geometry', 'snapshot', 'dataset', 'context'},
            'Exactly the six original actual small audits are required')
    verified_identities = {}
    full_reports = {}
    for kind in ('contact', 'liver'):
        path = GEOMETRY / ('presented-' + kind + '.json')
        report = read(path)
        invocation_path = GEOMETRY / (kind + '.invocation.json')
        invocation = read(invocation_path)
        require(report.get('passed') is True and all_checks(report['checks'])
                and invocation['passed'] is True and invocation['exit_code'] == 0
                and execution['records'][kind] == invocation
                and invocation['report']['sha256'] == sha(path), 'Full actual geometry report/exit/checks failed')
        original = report['original_trace']
        require(original['sha256'] == trace_sha and original['original_state_count'] == count
                and original['exact_state_bytes_and_membership_verified'] is True
                and report['workers'] == 1 and report['chunk_states_target'] == 500,
                'Full original state coverage or worker policy differs')
        require(report['metrics']['states_audited_including_overlap'] == count + original['duplicated_overlap_count'],
                'Full auditor state membership does not cover originals and declared overlaps')
        for case in report['cases']:
            require(case['audit_completed'] is True and case['chunk_geometric_passed'] is True
                    and all_checks(case['chunk_geometric_checks']), 'A chunk has failed geometry/health checks')
        if kind == 'contact':
            require(report['metrics']['reset_boundaries_not_interpolated'] == len(resets)
                    and report['metrics']['interpolated_samples'] == 3 * (count - 1 - len(resets)),
                    'Every non-reset interpolation edge must be covered exactly once')
        verified_identities[kind] = {'workspace': verify_geometry_report(report, ROOT, kind, 7),
                                     'packaged_source': verify_geometry_report(report, package / 'Source', kind, 7)}
        manifest = GEOMETRY / (kind + '-work/manifest.json')
        require(sha(manifest) == report['work_manifest_sha256'], 'Full auditor work manifest changed')
        reports['presented_' + kind] = {**identity(path), 'passed': True, 'exit_code': 0,
                                       'schema': report['schema'], 'checks': report['checks'],
                                       'metrics': report['metrics'],
                                       'invocation_record': identity(invocation_path),
                                       'work_manifest': identity(manifest)}
        full_reports[kind] = report
    observation_path = ROOT / 'tmp/phase9/package-launch-observation-final01.json'
    observation = read(observation_path)
    require(observation['outer_exec_exit_code'] == 1
            and observation['exact_last_exitcode_value_was_not_captured'] is True
            and observation['actual_integration_capture_completed'] is True
            and observation['actual_game_exit_code'] == observation['actual_native_exit_code'] == 0,
            'Preserve the actual outer-wrapper diagnostic facts separately')
    require(sha(small_path) == small_before and sha(trace) == trace_sha, 'Small index or trace changed during sealing')
    checks = {name: True for name in (
        'all_six_actual_small_audits_passed', 'full_presented_contact_passed', 'full_presented_liver_passed',
        'all_report_exit_codes_zero_and_checks_true', 'all_original_presented_states_audited',
        'all_non_reset_interpolation_edges_audited', 'exact_trace_bytes_and_membership_preserved',
        'every_chunk_geometry_and_health_checks_passed', 'auditors_match_workspace_and_frozen_packaged_sources',
        'actual_package_capture_completed_game_and_native_zero', 'actual_selected_executable_mesh_game_hashes_match',
        'all_previously_selected_inputs_unchanged', 'extraction_and_actual_reference_bound',
        'every_presented_native_config_matches_actual_reference', 'outer_exit_one_observation_preserved_separately',
        'original_small_audit_index_unchanged')}
    document = {'schema': 'endoforge.phase9.complete-audit-index.v1', 'phase': 9,
                'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'passed': True, 'checks': checks, 'inputs': small['inputs'], 'reports': reports,
                'capture': str(capture), 'package': str(package),
                'small_audit_index': identity(small_path),
                'selected_input_inventory': small['selected_input_inventory'],
                'extraction_report': identity(extraction_path), 'presented_trace': identity(trace),
                'actual_package_run_receipt': identity(receipt_path),
                'actual_game_exit_code': receipt['game_exit_code'], 'actual_native_exit_code': receipt['native_exit_code'],
                'outer_wrapper_observation': {**identity(observation_path), 'diagnostic_only': True,
                                              'facts': observation},
                'native_reference': {'case_report': identity(reference_path), 'trace': identity(reference_trace),
                                     'config': config, 'config_canonical_json_sha256': config_sha,
                                     'config_hash_encoding': 'UTF-8 JSON with sorted keys, compact separators, finite numbers',
                                     'asset_fingerprint': config['asset_fingerprint']},
                'trace_provenance': provenance,
                'coverage': {'original_states': count, 'adjacent_original_pairs': count - 1,
                             'reset_boundaries': resets, 'non_reset_edges': count - 1 - len(resets),
                             'interpolated_samples': full_reports['contact']['metrics']['interpolated_samples'],
                             'contact_policy': full_reports['contact']['coverage_policy'],
                             'liver_distance_sampling_policy': full_reports['liver']['distance_sampling_policy']},
                'verified_geometry_auditor_identities': verified_identities,
                'geometry_execution': identity(GEOMETRY / 'execution.json'),
                'sealer': identity(Path(__file__)),
                'human_visual_approval_claim': False, 'final_delivery_claim': False,
                'scope': 'All six existing small audits plus unchanged full presented contact and closed-liver audits of this actual package capture. Original small index and outer wrapper failure record are preserved. Native35/raw-hold qualification, broader endurance/nominal geometry, human visual approval and final delivery receipt remain separate requirements.'}
    with OUTPUT.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(document, handle, indent=2)
        handle.write('\n')
    print(json.dumps({'path': str(OUTPUT), 'sha256': sha(OUTPUT), 'passed': document['passed'],
                      'reports': len(reports), 'coverage': document['coverage']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
