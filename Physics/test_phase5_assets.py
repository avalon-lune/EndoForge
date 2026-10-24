"""Fail-closed anatomy asset validation before starting a simulation service."""
import argparse, copy, hashlib, json, pathlib, subprocess
BASE=pathlib.Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--phase',type=int,choices=(5,6),default=5);ap.add_argument('--output',type=pathlib.Path);args=ap.parse_args()
OUT=(args.output or BASE.parent/'tmp/phase5-physics-v2/asset-validation').resolve()
OUT.mkdir(parents=True,exist_ok=True)
EXE=BASE/'runtime/LapPhysics.exe'
SOURCE=BASE.parent/f'Assets/Phase{args.phase}/physics-mesh.json'
original=json.loads(SOURCE.read_text())
cases=[]
def case(name,change):
    item=copy.deepcopy(original);change(item);cases.append((name,item))
case('wrong_units',lambda d:d.update(units='mm'))
case('invalid_model_version',lambda d:d.update(version=0))
case('open_gallbladder_surface',lambda d:d['triangles'].pop())
case('invalid_face_index',lambda d:d['triangles'][0].__setitem__(0,999999))
case('zero_normal',lambda d:d['normals'].__setitem__(0,[0,0,0]))
case('out_of_bounds_wall_thickness',lambda d:d.update(thickness_m=.00001))
case('unbound_bed_anchor',lambda d:d['attachment_anchor_positions_m'].pop())
case('invalid_fixed_node',lambda d:d['fixed_vertex_ids'].append(-1))
case('invalid_liver_face',lambda d:d['static_liver']['triangles'][0].__setitem__(0,999999))
case('missing_anchor_surface_bindings',lambda d:d.pop('attachment_anchor_bindings'))
case('floating_anchor',lambda d:d['attachment_anchor_positions_m'][0].__setitem__(2,d['attachment_anchor_positions_m'][0][2]+.001))
case('invalid_anchor_triangle',lambda d:d['attachment_anchor_bindings'][0].update(triangle_id=999999))
case('invalid_anchor_weights',lambda d:d['attachment_anchor_bindings'][0].update(barycentric=[.5,.5,.5]))
if args.phase==6:
    case('initial_tool_inside_liver',lambda d:d['home_tips_m'].__setitem__(0,[.01,.052,-.015]))
    case('open_liver_surface',lambda d:d['static_liver']['triangles'].pop())
    case('missing_ready_recipes',lambda d:d.pop('phase6_interaction'))
    case('unknown_ready_path',lambda d:d['phase6_interaction']['recipes'][1]['approach_waypoints'][0].update(kind='teleport'))
    case('out_of_bounds_ready_path',lambda d:d['phase6_interaction']['recipes'][1]['approach_waypoints'][0].update(distance_m=.5))
checks={};details={}
for name,asset in cases:
    path=OUT/(name+'.json');path.write_text(json.dumps(asset))
    try:
        result=subprocess.run([str(EXE),f'--phase{args.phase}','--mesh',str(path),'--port','47339'],capture_output=True,text=True,errors='replace',timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
        passed=result.returncode!=0 and 'FATAL' in result.stderr+result.stdout
        details[name]={'returncode':result.returncode,'message':(result.stderr+result.stdout).splitlines()[-1]}
    except subprocess.TimeoutExpired:
        passed=False;details[name]={'error':'Invalid asset was accepted and service remained running'}
    checks[name]=passed
result=subprocess.run([str(EXE),f'--phase{args.phase}','--config',str(BASE/'configs/flat.json')],capture_output=True,text=True,errors='replace',timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
checks['reject_unbound_legacy_config']=result.returncode!=0 and 'immutable anatomy asset' in result.stderr+result.stdout
report={'phase':args.phase,'kind':'asset_validation','checks':checks,'details':details,'passed':all(checks.values()),'asset_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'executable_sha256':hashlib.sha256(EXE.read_bytes()).hexdigest()}
(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['passed'] else 2)
