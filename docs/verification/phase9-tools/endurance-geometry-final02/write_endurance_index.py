"""Bind both full unchanged endurance results; optionally wait and mirror pause.

This reads completed evidence only. It never modifies a kernel, kills a process,
or claims operating-matrix/native-suite/clinical acceptance. Root PAUSE_REQUEST
is copied into both actual resumable work directories once their manifests exist.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[2]
JOBS = {
    'contact': {'report':'contact.json','work':'contact-chunks','workers':2,'session_id':38662,
                'controller_pid':44000,'started_utc':'2026-11-02T11:04:50.301059+00:00','python':'E:/python/python.exe'},
    'liver': {'report':'liver-corrected03.json','work':'liver-corrected03-chunks','workers':4,'session_id':99322,
              'controller_pid':41076,'started_utc':'2026-11-02T11:06:46.357925+00:00',
              'python':'C:/Users/Avalon/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'},
}

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def require(condition,message):
    if not condition:
        raise ValueError(message)

def write_new(path,data):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(data,stream,indent=2);stream.write('\n')

def mirror_pause():
    if not (HERE/'PAUSE_REQUEST').exists():
        return
    for kind,job in JOBS.items():
        work=HERE/job['work'];marker=work/'PAUSE_REQUEST'
        if (work/'manifest.json').exists() and not marker.exists():
            try:
                with marker.open('x',encoding='utf-8') as stream:
                    stream.write('Propagated shared root PAUSE_REQUEST at '+datetime.now(timezone.utc).isoformat()+'\n')
                print(json.dumps({'kind':kind,'pause_propagated':True}),flush=True)
            except FileExistsError:
                pass

def finish():
    start=read(HERE/'start-bindings.json')
    expected=start['inputs'];reports={};documents={};errors=[]
    for kind,job in JOBS.items():
        path=HERE/job['report'];data=read(path);documents[kind]=data
        try:
            require(data.get('schema')=='endoforge.phase7.parallel-'+kind+'.v1' and data.get('kind')==kind,'Wrong unchanged auditor identity')
            require(data.get('passed') is True and data.get('checks') and all(value is True for value in data['checks'].values()),'Full auditor checks did not all pass')
            original=data['original_trace']
            require(original['sha256']==expected['trace_sha256'] and original['original_state_count']==21865
                    and original['exact_state_bytes_and_membership_verified'] is True,'Wrong original trace/state coverage')
            require(data['workers']==job['workers'] and data['chunk_states_target']==500,'Unexpected authorized worker/chunk settings')
            require(data['auditor_identities'] and all(start['auditor_identities'].get(name)==digest
                    and sha(Path(name))==digest for name,digest in data['auditor_identities'].items()),'Auditor/kernel identity changed')
            passed=True
        except Exception as error:
            passed=False;errors.append(kind+': '+str(error))
        reports[kind]={'path':str(path),'sha256':sha(path),'passed':passed,'workers':job['workers'],
                       'python':job['python'],'session_id':job['session_id'],'controller_pid':job['controller_pid'],
                       'started_utc':job['started_utc'],'original_state_count':data.get('original_trace',{}).get('original_state_count'),
                       'original_adjacent_edge_count':data.get('original_trace',{}).get('original_state_count',0)-1,
                       'checks':data.get('checks',{}),'metrics':data.get('metrics',{})}
    trace=Path(start['original_trace']['path'])
    unchanged={
        'original_trace_unchanged':sha(trace)==expected['trace_sha256'],
        'native_executable_unchanged':sha(WORKSPACE/'Physics/runtime/LapPhysics.exe')==expected['physics_exe_sha256'],
        'physical_mesh_unchanged':sha(WORKSPACE/'Assets/Phase9/physics-mesh.json')==expected['physics_mesh_sha256'],
        'native_endurance_report_unchanged':sha(Path(start['endurance_case']['path']))==expected['endurance_report_sha256'],
        'bound_checkpoint_snapshot_unchanged':sha(Path(start['checkpoint_snapshot']))==expected['checkpoint_sha256'],
        'all_bound_auditors_unchanged':all(sha(Path(name))==digest for name,digest in start['auditor_identities'].items()),
    }
    contact=documents['contact'];count=contact['original_trace']['original_state_count']
    resets=contact.get('metrics',{}).get('reset_boundaries_not_interpolated')
    interpolated=contact.get('metrics',{}).get('interpolated_samples')
    final={'schema':'endoforge.phase9.endurance-geometry-index.v1','phase':9,
           'created_utc':datetime.now(timezone.utc).isoformat(),'inputs':expected,
           'start_bindings':{'path':str(HERE/'start-bindings.json'),'sha256':sha(HERE/'start-bindings.json')},
           'reports':reports,'checks':unchanged,'passed':all(unchanged.values()) and all(record['passed'] for record in reports.values()),
           'original_trace':{'path':str(trace),'sha256':expected['trace_sha256'],'original_state_count':count,
                             'original_adjacent_edge_count':count-1,'bytes':start['original_trace']['bytes']},
           'contact_interpolation':{'samples':interpolated,'samples_per_nonreset_edge':3,
                                    'reset_boundaries_not_interpolated':resets,
                                    'nonreset_edges_audited':interpolated//3 if type(interpolated) is int else None},
           'failed_initial_liver_attempt':{'path':str(HERE/'liver.json'),'sha256':sha(HERE/'liver.json'),
                 'passed':False,'reason':'E:/python lacked NumPy. Complete corrected liver run is bound above; no failed result was reused.'},
           'errors':errors,'offline_correctness_only':True,'scope':'Full original endurance trace only, without deduplication or sample/edge reduction. Contact retains all nonreset three-sample interpolation edges; liver retains every original state and its unchanged sampled-distance policy, not a CCD claim. This index supplies no operating-matrix, full native-suite, visual, clinical or final delivery acceptance.'}
    write_new(HERE/'audit-run.json',final)
    print(json.dumps({'index':str(HERE/'audit-run.json'),'passed':final['passed'],'original_states':count,'original_edges':count-1}),flush=True)
    return 0 if final['passed'] else 2

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--watch',action='store_true');args=parser.parse_args()
    require(not (HERE/'audit-run.json').exists(),'Final endurance index is immutable')
    while True:
        mirror_pause()
        if all((HERE/job['report']).is_file() for job in JOBS.values()):
            return finish()
        if not args.watch:
            print(json.dumps({'status':'pending','passed':False,'reports_present':{kind:(HERE/job['report']).exists() for kind,job in JOBS.items()}}))
            return 3
        time.sleep(2)

if __name__=='__main__':
    raise SystemExit(main())
