"""Seal native Phase6 evidence against one exact executable and anatomy asset."""
import argparse
import datetime
import hashlib
import json
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = ROOT / 'Physics'
sys.path.insert(0, str(ROOT/'Scripts/Phase6'))
from complete_native_suite import expected_cases
from native_long_hold import validate_long_hold


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def evidence(path):
    path = path.resolve()
    return {'path': str(path), 'relative_path': path.relative_to(ROOT).as_posix(),
            'sha256': sha(path), 'bytes': path.stat().st_size}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=pathlib.Path, required=True)
    parser.add_argument('--latency', type=pathlib.Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    run = read(out / 'checkpoint.json')
    exe = BASE / 'runtime/LapPhysics.exe'
    asset = ROOT / 'Assets/Phase6/physics-mesh.json'
    binary_hash = sha(exe)
    checks = {'run_complete': run['status'] == 'complete', 'frozen_executable': run['native_sha256'] == binary_hash,
              'staged_asset_matches_source': sha(asset) == sha(BASE / 'runtime/assets/phase6.json')}
    checks['thirty_five_native_cases'] = [job['name'] for job in run['completed']] == expected_cases()
    assert checks['thirty_five_native_cases'], 'All twenty regression and fifteen long-hold cases are mandatory'
    hold_path = out/'long-hold/long-hold-report.json'
    assert run['long_hold_summary'] == {'path': str(hold_path), 'sha256': sha(hold_path)}
    long_hold = validate_long_hold(ROOT, hold_path, binary_hash, read(out/'replay.json')['config'], inspect_states=True)
    checks['fifteen_long_hold_cases_and_all_raw_states'] = len(long_hold['raw_state_audits']) == 15 and all(
        item['passed'] is True for item in long_hold['raw_state_audits'].values())
    items, documents = {}, {}
    for job in run['completed']:
        path = pathlib.Path(job['report'])
        doc = read(path)
        name = job['name'].replace('-', '_') if job['name'] in ('asset-validation', 'fresh-process-replays') else job['name']
        documents[name] = doc
        checks[name] = doc.get('passed') is True and all(v is True for v in doc.get('checks', {}).values())
        checks[name + '_same_binary'] = (long_hold['evidence'][name]['sha256'] == sha(path)
                                       if name.startswith('long-hold-') else doc['executable_sha256'] == binary_hash)
        checks[name + '_sealed_report'] = sha(path) == job['sha256']
        item = evidence(path)
        for key in ('checks', 'options', 'metrics'):
            if key in doc:
                item[key] = doc[key]
        trace = path.with_name(path.stem + '-states.jsonl')
        if trace.exists():
            item['trajectory'] = evidence(trace)
        items[name] = item
    items['long_hold_summary'] = long_hold['summary']
    latency = read(args.latency)
    documents['native_socket_latency'] = latency
    items['native_socket_latency'] = evidence(args.latency)
    items['native_socket_latency']['trajectory'] = evidence(args.latency.parent / 'responses.jsonl')
    checks['native_socket_latency'] = latency.get('passed') is True and all(latency['checks'].values())
    checks['native_socket_latency_same_binary'] = latency['executable_sha256'] == binary_hash
    matrix_names = [k for k in documents if k.startswith('matrix-')]
    checks['nine_operating_matrix_cases'] = len(matrix_names) == 9
    checks['operating_matrix_lift_2mm'] = all(documents[k]['options']['lift_m'] == .002 for k in matrix_names)
    endurance, replay = documents['endurance'], documents['replay']
    fresh = documents['fresh_process_replays']
    checks['endurance_600s_30cycles'] = endurance['metrics']['duration_s'] >= 600 and endurance['metrics']['completed_cycles'] >= 30
    checks['five_fresh_process_replays'] = len(fresh['repeats']) == 5 and all(
        r['completed'] and r['contiguous_steps'] and r['identity_and_topology_match'] and r['events_identical'] and r['max_node_rms_m'] <= .0005 for r in fresh['repeats'])
    for number in range(1, 6):
        items[f'fresh_fixture_run_{number}'] = evidence(out / f'fixture-final-five/run-{number}/replayed-states.jsonl')
    actions = list((out / 'network/sessions').glob('*-actions.json'))
    assert len(actions) == 1
    states = actions[0].with_name(actions[0].name.replace('-actions.json', '-states.jsonl'))
    items['fresh_fixture_original_actions'] = evidence(actions[0])
    items['fresh_fixture_original_states'] = evidence(states)
    checks['fresh_fixture_actions_bound'] = fresh['actions_sha256'] == sha(actions[0])
    checks['fresh_fixture_states_bound'] = fresh['states_sha256'] == sha(states)
    compiled = ('main.cpp', 'Phase2Model.h', 'Phase3Model.h', 'Phase4Session.h', 'Phase4Tests.h',
                'Phase4CollisionTests.h', 'AnatomyAsset.h', 'Phase5Intersection.h', 'Phase5Tests.h', 'Phase6FEM.h', 'Phase6ReadyRecipes.h', 'Phase6ToolCollision.h', 'Phase6Tests.h')
    sources = list(compiled) + ['CMakeLists.txt', 'stage-runtime.ps1', 'build.ps1', 'test_phase3_network.py',
                               'test_phase4_network.py', 'test_phase5_network.py', 'test_phase5_replay_fixture.py',
                               'test_phase5_assets.py', 'test_phase6_latency.py', 'run_phase6_regression.py',
                               'summarize_phase6_tests.py', 'run_phase6_long_hold.py',
                               '../Scripts/Phase6/native_long_hold.py', '../Scripts/Phase6/complete_native_suite.py',
                               '../Scripts/Phase6/acceptance-spec.json', '../Assets/Phase6/physics-mesh.json']
    source_hashes = {name: sha(BASE / name) for name in sources}
    for name in compiled:
        checks['compiled_current_' + name] = (BASE / name).stat().st_mtime <= exe.stat().st_mtime
    same_config_names = matrix_names + ['interaction', 'dual-reference', 'endurance', 'replay'] + list(long_hold['evidence'])
    checks['same_physics_configuration'] = all(documents[k]['config'] == replay['config'] for k in same_config_names)
    references = documents['dual-reference']['stages']
    checks['equivalent_stiffness_in_rest_and_deformation'] = all(s['assembly_reference_max_relative'] < 1e-12 for s in references)
    physics_cases = [documents[k]['metrics'] for k in matrix_names + ['endurance', 'replay']]
    report = {'schema': 'endoforge.phase6.native-suite.v1', 'phase': 6, 'passed': all(checks.values()),
              'created_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'checks': checks, 'native_binary': evidence(exe), 'anatomy_asset': evidence(asset),
              'sources_sha256': source_hashes, 'evidence': items, 'model_config': replay['config'],
              'long_hold_validation': long_hold,
              'metrics': {'matrix_cases': len(matrix_names), 'continuous_simulation_seconds': endurance['metrics']['duration_s'],
                          'continuous_cycles': endurance['metrics']['completed_cycles'],
                          'same_process_replay_repeats': len(replay['replays']),
                          'same_process_maximum_node_rms_m': max(r['max_frame_node_rms_m'] for r in replay['replays']),
                          'fresh_process_replay_repeats': len(fresh['repeats']),
                          'fresh_process_maximum_node_rms_m': max(r['max_node_rms_m'] for r in fresh['repeats']),
                          'fresh_process_maximum_single_node_difference_m': max(r['max_single_node_m'] for r in fresh['repeats']),
                          'fresh_process_maximum_force_difference_n': max(r['max_force_difference_n'] for r in fresh['repeats']),
                          'fresh_process_events_identical': all(r['events_identical'] for r in fresh['repeats']),
                          'minimum_tet_volume_ratio': min(m['min_tet_volume_ratio'] for m in physics_cases),
                          'minimum_triangle_area_ratio': min(m['min_triangle_area_ratio'] for m in physics_cases),
                          'peak_node_penetration_m': max(m['peak_node_depth_m'] for m in physics_cases),
                          'maximum_reference_element_stiffness_difference_n_m': max(s['assembly_reference_max_absolute_n_m'] for s in references),
                          'native_tcp': latency['metrics'],
                          'native_case_count': len(run['completed']), 'long_hold_cases': long_hold['case_count'],
                          'long_hold_seconds_per_case': long_hold['hold_seconds_per_case']},
              'scope': {'numerics': 'The equivalent 3x3 block assembly keeps the SOFA corotational force law, current strain/rotation matrices, all element couplings, direct solver, contact constraints, time step and adaptive safeguards. Every element stiffness entry is independently compared with the inherited SOFA dense assembly at rest, approach, grasp, traction, release, withdrawal and settle.',
                        'timing': 'Native TCP latency is local transport/accepted-state timing only. The UI event to displayed accepted state and full rendering/physics performance require the separate packaged UE run. Regression runs are correctness evidence, not isolated CPU benchmarks.',
                        'contact': 'Node-depth native checks do not replace independent whole-face/interpolated contact and closed-organ audits. Claims are limited to the recorded paths.',
                        'clinical_material_validated': False, 'fluid_pressure_model': False, 'self_collision': False,
                        'instrument_liver_and_instrument_instrument_response': 'Phase6 jaw motion is continuously limited against the static liver by an oriented-box geometric guard. It has no measured reaction-force output. Full-shaft and instrument-instrument response are not implemented. Geometric audits and operating bounds are reported separately.',
                        'repeatability': 'Acceptance is 0.5 mm frame node RMS and identical grip events over five fresh processes; no bitwise reproducibility or calibrated-force claim.',
                        'phase_scope': 'Common foundation only. No suturing or Project 1/2 specialized dataset implementation.'}}
    (out / 'native-suite-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if report['passed']:
        info_path = BASE / 'runtime/build-info.json';info = read(info_path)
        info.update(phase=6, source_files_sha256=source_hashes, source_sha256=source_hashes['main.cpp'],
                    executable_sha256=binary_hash, tested_protocol=5, tested_protocols=[3, 4, 5],
                    tested_execution_modes=['phase3', 'phase4', 'phase6'], native_suite_sha256=sha(out / 'native-suite-report.json'),
                    verification_status='Phase6 twenty regression cases plus fifteen sustained grasp/traction/retraction cases and all raw-state checks passed, with native socket latency. Independent whole-surface geometry and packaged UE checks remain separate.')
        info_path.write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'checks': checks, 'metrics': report['metrics']}, indent=2))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
