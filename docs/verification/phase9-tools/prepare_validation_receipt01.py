"""Bind explicit completed Phase9 evidence for the review-candidate assembler.
No build or test is executed by this helper. Never infers visual approval.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json
ROOT=Path(__file__).resolve().parents[2]
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def record(p):
    p=Path(p).resolve()
    with p.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':str(p),'sha256':digest,'bytes':p.stat().st_size}
def passed(p):
    data=read(p)
    assert data.get('passed') is True, str(p)
    checks=data.get('checks')
    if checks is not None: assert checks and all(type(v) is bool and v for v in checks.values()), str(p)
    return data
p=argparse.ArgumentParser()
p.add_argument('--output',type=Path,required=True)
p.add_argument('--build-receipt',type=Path,required=True)
p.add_argument('--endurance-audit-index',type=Path,required=True)
p.add_argument('--package-audit-index',type=Path)
args=p.parse_args()
out=args.output.resolve()
assert out.is_relative_to(ROOT/'tmp/phase9') and not out.exists()
native=ROOT/'tmp/phase9/native-qualification-final02/qualification.json'
raw_holds=ROOT/'tmp/phase9/native-qualification-final02/long-hold-raw-state-audit.json'
geometry=ROOT/'tmp/phase9/native-geometry-final02/final-coverage-index.json'
assets=ROOT/'tmp/phase9/asset-contract22/report.json'
preserve=ROOT/'tmp/phase9/delivery-preflight01/preservation-check.json'
nd=passed(native); gd=passed(geometry); passed(assets); passed(preserve)
rh=passed(raw_holds)
assert rh['qualification']['sha256']==record(native)['sha256']
assert 'inspect_states=True' in rh['validator_call'] and rh['native_processes_launched']==0
ed=passed(args.endurance_audit_index)
assert set(ed['reports'])=={'contact','liver'}
endurance_completion=ROOT/'tmp/phase9/endurance-geometry-final02/completion-state01.json'
ec=passed(endurance_completion)
assert ec['index']['sha256']==record(args.endurance_audit_index)['sha256']
assert all(v['final_exit_code']==0 and v['final_controller_and_workers_reaped'] is True for v in ec['jobs'].values())
assert nd['case_count']==nd['expected_case_count']==35
assert gd['expected_audit_count']==26 and len(gd['results'])==26
assert all(v['status']=='passed' for v in gd['results'])
build=read(args.build_receipt)
assert build['build_succeeded'] and build['source_snapshot_unchanged']
assert build['native_runtime_files_sha256']['LapPhysics.exe']==nd['native_binary']['sha256']
assert build['asset_files_sha256']['physics-mesh.json']==nd['mesh']['sha256']
prestage=ROOT/'tmp/phase9/delivery-preflight01/native-runtime-prestage.json'
runtime_before={v['path']:v['sha256'] for v in read(prestage)['files']}
runtime_after={k:v for k,v in build['native_runtime_files_sha256'].items() if Path(k).suffix.lower() in ('.exe','.dll')}
assert runtime_before==runtime_after, 'Staging changed qualified runtime dependency bytes'
ev={'native_qualification':record(native),'build_receipt':record(args.build_receipt),
    'all_15_raw_hold_states':record(raw_holds),
    'native_geometry_coverage':record(geometry),'asset_contract':record(assets),
    'earlier_phase_preservation':record(preserve),
    'visual_observations':record(ROOT/'tmp/phase9/visual-review-main01.json'),
    'native_runtime_prestage':record(prestage),
    'endurance_geometry_coverage':record(args.endurance_audit_index),
    'endurance_actual_completion':record(endurance_completion)}
for name,filename in (
 ('archive_integrity_tool','archive_phase9.py'),
 ('packaged_audit_tool','run_package_audits.py')):
    ev[name]=record(ROOT/'tmp/phase9/delivery-preflight01'/filename)
ev['candidate_validation_tool']=record(__file__)
for kind,value in ed['reports'].items():
    r=record(value['path']); assert r['sha256']==value['sha256']
    report=passed(r['path'])
    assert report['original_trace']['sha256']=='8f7a3a1578e534e28f1ada7865ef47ebf4f874a03ebbc79b67ae7a6cb6a0aeef'
    ev['endurance_geometry_'+kind]=r
for i,item in enumerate(gd['results']):
    r=record(item['report']); assert r['sha256']==item['sha256']
    passed(r['path'])
    ev[f'geometry_{i:02d}_{item["kind"]}']=r
gallery_map=ROOT/'tmp/phase9/visual-gallery02-evidence-map.json'
gallery=read(gallery_map)
ev['gallery_evidence_map']=record(gallery_map)
ev['actual_packaged_gallery_recipe']=record(ROOT/'tmp/phase9/visual-gallery02-execution.json')
ev['actual_packaged_gallery_wrapper']=record(ROOT/'tmp/phase9/create_packaged_gallery02.py')
for name,value in gallery.items():
    r=record(ROOT/value['path']); assert r['sha256']==value['sha256'] and r['bytes']==value['bytes']
    ev[name]=r
checks={'fresh_native_35':True,'all_15_raw_hold_states':True,'fresh_native_geometry_26':True,'fresh_full_endurance_geometry':True,'negative_asset_contract':True,
        'successful_frozen_build':True,'runtime_dependencies_unchanged_by_staging':True,
        'earlier_phases_unchanged':True,'actual_review_views_supplied':True}
scope='Candidate assembly prerequisites passed. Actual packaged runtime/performance, extracted-archive checks and human visual approval are separate; no final delivery acceptance is implied.'
if args.package_audit_index:
    index=passed(args.package_audit_index)
    assert index['schema']=='endoforge.phase9.complete-audit-index.v1'
    assert set(index['reports'])=={'appearance','runtime','geometry','snapshot','dataset','context','presented_contact','presented_liver'}
    ev['packaged_audits']=record(args.package_audit_index)
    assert index['inputs']['physics_exe_sha256']==nd['native_binary']['sha256']
    assert index['inputs']['physics_mesh_sha256']==nd['mesh']['sha256']
    assert index['inputs']['game_exe_sha256']==build['ue_package_files_sha256']['LapTrainer/Binaries/Win64/LapTrainer.exe']
    for name,value in index['reports'].items():
        r=record(value['path']); assert r['sha256']==value['sha256']; passed(r['path'])
        ev['packaged_'+name]=r
    checks['actual_packaged_integration_and_independent_audits']=True
    scope='Native, build and actual packaged checks bind the same executable/mesh/game bytes. A fresh archive extraction check and human visual approval remain separate.'
data={'schema':'endoforge.phase9.validation.v1','phase':9,'passed':True,
      'created_utc':datetime.now(timezone.utc).isoformat(),'diagnostic_only':False,
      'inherited_results':False,'human_visual_approval':'pending','delivery_accepted':False,
      'checks':checks,'inputs':{'physics_exe_sha256':nd['native_binary']['sha256'],
       'physics_mesh_sha256':nd['mesh']['sha256'],
       'game_exe_sha256':build['ue_package_files_sha256']['LapTrainer/Binaries/Win64/LapTrainer.exe']},
      'evidence':ev,'scope':scope,'helper':record(__file__)}
with out.open('x',encoding='utf-8') as f: json.dump(data,f,indent=2); f.write('\n')
print(json.dumps(record(out)))
