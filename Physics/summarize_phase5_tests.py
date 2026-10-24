"""Bind completed native acceptance reports to the exact executable and inputs."""
import argparse, datetime, hashlib, json, pathlib, shutil
BASE=pathlib.Path(__file__).resolve().parent
ROOT=BASE.parent
parser=argparse.ArgumentParser();parser.add_argument('--output',type=pathlib.Path,default=ROOT/'tmp/phase5-resume-physics');parser.add_argument('--baseline',type=pathlib.Path,default=ROOT/'tmp/phase5-physics-v2');args=parser.parse_args()
OUT=args.output.resolve();OLD=args.baseline.resolve();OUT.mkdir(parents=True,exist_ok=True)
EXE=BASE/'runtime/LapPhysics.exe'
ASSET=ROOT/'Assets/Phase5/physics-mesh.json'
def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def evidence(path):
    return {'path':str(path.resolve()),'relative_path':path.relative_to(ROOT).as_posix(),'sha256':digest(path),'bytes':path.stat().st_size}
for phase in (3,4):
    shutil.copy2(BASE/f'runtime/phase{phase}-network-test-results.json',OUT/f'legacy-phase{phase}-network.json')
names=[f'matrix-a{angle}-s{speed}-{path}' for angle in (75,90,105) for speed,path in ((6,'straight'),(12,'lateral'),(18,'forward'))]
reports={name:OLD/'matrix-2mm'/f'{name}.json' for name in names}
reports.update({name:OLD/f'{name}.json' for name in ['replay','legacy-phase3','legacy-phase4']})
reports.update({name:OUT/f'{name}.json' for name in ['endurance','legacy-phase3-network','legacy-phase4-network']})
reports.update(network=OUT/'network/report.json',asset_validation=OLD/'asset-validation/report.json')
reports['isolated_profile']=OLD/'final-isolated-profile.json'
reports['fresh_process_replays']=OUT/'fixture-final-five/report.json'
checks={};items={};documents={}
exe_hash=digest(EXE)
fingerprint=14695981039346656037
for byte in ASSET.read_bytes():fingerprint=((fingerprint^byte)*1099511628211)&0xffffffffffffffff
fingerprint=f'fnv1a64:{fingerprint:016x}'
for name,path in reports.items():
    document=json.loads(path.read_text(encoding='utf-8-sig'));documents[name]=document
    checks[name]=document.get('passed') is True and all(v is True for v in document.get('checks',{}).values())
    items[name]=evidence(path);items[name]['checks']=document.get('checks',{})
    if 'options' in document:items[name]['options']=document['options']
    if 'metrics' in document:items[name]['metrics']=document['metrics']
    if 'executable_sha256' in document:checks[name+'_tested_same_executable']=document['executable_sha256']==exe_hash
    if name in names+['endurance','replay','isolated_profile']:
        trace=path.with_name(path.stem+'-states.jsonl');items[name]['trajectory']=evidence(trace)
        checks[name+'_after_current_build']=path.stat().st_mtime>=EXE.stat().st_mtime
        checks[name+'_bound_same_asset']=document['config']['asset_fingerprint']==fingerprint
checks['staged_asset_matches_source']=digest(ASSET)==digest(BASE/'runtime/assets/phase5.json')
source_names=['main.cpp','Phase2Model.h','Phase3Model.h','Phase4Session.h','Phase4Tests.h','Phase4CollisionTests.h','AnatomyAsset.h','Phase5Intersection.h','Phase5Tests.h','CMakeLists.txt','test_network.py','test_phase3_network.py','test_phase4_network.py','test_phase5_network.py','test_phase5_replay_fixture.py','test_phase5_assets.py','summarize_phase5_tests.py','RunPhase3Regression.ps1','RunPhase4Regression.ps1','build.ps1','stage-runtime.ps1','configs/flat.json','configs/curved.json','../Assets/Phase5/physics-mesh.json']
sources={name:digest(BASE/name) for name in source_names}
for name in ['main.cpp','Phase2Model.h','Phase3Model.h','Phase4Session.h','Phase4Tests.h','Phase4CollisionTests.h','AnatomyAsset.h','Phase5Intersection.h','Phase5Tests.h']:
    checks['compiled_current_'+name]=(BASE/name).stat().st_mtime<=EXE.stat().st_mtime
baseline=documents['replay'];endurance=documents['endurance']
stress={}
for name in names:
    path=OLD/f'{name}.json';document=json.loads(path.read_text());stress[name]=evidence(path)
    stress[name].update(passed=document['passed'],checks=document['checks'],options=document['options'],metrics=document['metrics'],trajectory=evidence(path.with_name(path.stem+'-states.jsonl')))
    checks[name+'_operating_lift_2mm']=documents[name]['options'].get('lift_m')==.002
fresh=documents['fresh_process_replays'];fresh_runs=fresh['repeats']
checks['five_fresh_process_replays']=len(fresh_runs)==5 and all(r['completed'] and r['contiguous_steps'] and r['identity_and_topology_match'] and r['events_identical'] and r['max_node_rms_m']<=.0005 for r in fresh_runs)
for number in range(1,6):items[f'fresh_fixture_run_{number}']=evidence(OUT/f'fixture-final-five/run-{number}/replayed-states.jsonl')
items['fresh_fixture_original_actions']=evidence(OLD/'network/sessions/session-1792650614093992-38316-actions.json')
items['fresh_fixture_original_states']=evidence(OLD/'network/sessions/session-1792650614093992-38316-states.jsonl')
items['replay_source_review']=evidence(OUT/'replay-source-review.json')
items['replay_numerical_analysis']=evidence(OUT/'replay-numerical-analysis.json')
checks['fresh_fixture_matches_original_actions']=fresh['actions_sha256']==items['fresh_fixture_original_actions']['sha256']
checks['fresh_fixture_matches_original_states']=fresh['states_sha256']==items['fresh_fixture_original_states']['sha256']
report={'schema':'endoforge.phase5.native-suite.v1','phase':5,'passed':all(checks.values()),'checks':checks,
    'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'native_binary':evidence(EXE),'anatomy_asset':evidence(ASSET),
    'sources_sha256':sources,'evidence':items,'model_config':baseline['config'],'stress_exploration_4mm':stress,
    'metrics':{'matrix_cases':len(names),'continuous_simulation_seconds':endurance['metrics']['duration_s'],'continuous_cycles':endurance['metrics']['completed_cycles'],
        'isolated_native_step_p95_ms':documents['isolated_profile']['metrics']['step_p95_ms'],
        'replay_repeats':len(baseline['replays']),'maximum_replay_frame_node_rms_m':max(x['max_frame_node_rms_m'] for x in baseline['replays']),
        'same_process_replay_repeats':len(baseline['replays']),'same_process_maximum_node_rms_m':max(x['max_frame_node_rms_m'] for x in baseline['replays']),
        'fresh_process_replay_repeats':len(fresh_runs),'fresh_process_maximum_node_rms_m':max(x['max_node_rms_m'] for x in fresh_runs),
        'fresh_process_maximum_single_node_difference_m':max(x['max_single_node_m'] for x in fresh_runs),
        'fresh_process_maximum_force_difference_n':max(x['max_force_difference_n'] for x in fresh_runs),'fresh_process_events_identical':all(x['events_identical'] for x in fresh_runs),
        'minimum_tet_volume_ratio':min(documents[n]['metrics']['min_tet_volume_ratio'] for n in names+['endurance','replay']),
        'minimum_triangle_area_ratio':min(documents[n]['metrics']['min_triangle_area_ratio'] for n in names+['endurance','replay']),
        'minimum_lumen_volume_ratio':min(documents[n]['metrics']['min_lumen_volume_ratio'] for n in names+['endurance','replay']),
        'maximum_lumen_volume_ratio':max(documents[n]['metrics']['max_lumen_volume_ratio'] for n in names+['endurance','replay']),
        'peak_node_penetration_m':max(documents[n]['metrics']['peak_node_depth_m'] for n in names+['endurance','replay'])},
    'scope':{'contact_validation':'Native checks sample physical node depth only; independent whole-triangle/interpolated/organ audits are separate required evidence.',
        'timing':'Suite jobs ran concurrently. The separately identified isolated_profile is an idle-desktop headless measurement; it does not certify full UE real-time performance.',
        'clinical_material_validated':False,'fluid_pressure_model':False,'self_collision':False,
        'replay_numerics':'Acceptance is the original 0.5 mm per-frame node RMS limit plus identical grip events. Five same-process and five fresh-process runs are reported separately. Bitwise replay is not claimed. Tiny differences begin at first contact and can grow during friction iterations, including a one-update (0.6 degree) load-responsive jaw closure difference. SOFA source contains address-ordered force-field matrix accumulation, but that candidate initial cause has not been experimentally isolated. The original stricter failure is retained.',
        'instrument_liver_and_instrument_instrument_response':'Kinematic instruments are not dynamically constrained against one another or liver; the accepted trajectories are independently screened for geometric intersection.',
        'differential_traction':'Longer or asymmetric pulls can lose frictional hold. The accepted nine-case matrix lifts 2 mm per tool; selected-tool input alternates two 1 mm increments per tool. The 90-degree endurance and replay tests lift 4 mm simultaneously. The separate 75-degree/6 mm/s/4 mm straight stress case loses left hold and fails its grasp criteria, although it releases safely; all original stress evidence is retained.'}}
(OUT/'native-suite-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
if report['passed']:
    info_path=BASE/'runtime/build-info.json';info=json.loads(info_path.read_text(encoding='utf-8-sig'));info['source_files_sha256']=sources
    info['source_sha256']=sources['main.cpp'];info['tested_protocol']=5;info['tested_protocols']=[3,4,5]
    info['verification_status']='Native Phase5 matrix/endurance/replay/socket/asset validation and legacy Phase3/4 core/socket checks passed; independent geometry/UE evidence is separate.'
    info['native_suite_sha256']=digest(OUT/'native-suite-report.json');info['tested_at_utc']=report['created_at_utc']
    info['phase5_delivery_ready']='native checks passed; independent anatomy/contact and packaged UE acceptance remain required'
    info_path.write_text(json.dumps(info,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':report['passed'],'checks':checks,'metrics':report['metrics']},indent=2))
raise SystemExit(0 if report['passed'] else 2)
