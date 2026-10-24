"""Read-only old-release reproduction via saved-input replay; never writes its cwd."""
import argparse, hashlib, json, math, pathlib, socket, subprocess, time

def audit_saved(out):
    import audit_phase4_collision_geometry as audit
    path=out/'baseline-received-states.jsonl';node=surface=0.;max_node_step=None;max_surface=None;indices=[];healthy=True
    for line in path.open(encoding='utf-8-sig'):
        state=json.loads(line)
        if not audit.finite_tree(state):raise ValueError('Nonfinite baseline raw state')
        index=state['session']['step_index'];indices.append(index)
        if len(indices)>1 and index<=indices[-2]:raise ValueError('Out-of-order baseline state')
        healthy &= state['healthy'] and state['safety_stops']==0
        n,depth,witness=audit.geometry_depth(state['vertices'],state['triangles'],state['tools'],[.00725,.00125,.0007])
        if n>node:node=n;max_node_step=index
        if depth>surface:surface=depth;max_surface={'step_index':index,'witness':witness}
    reproduction=json.loads((out/'baseline-reproduction.json').read_text(encoding='utf-8-sig'))
    result={'kind':'independent_old_release_geometry','expected_failure':True,'raw_file':path.name,'raw_sha256':audit.sha(path),'audit_script_sha256':audit.sha(audit.__file__),'driver_script_sha256':audit.sha(__file__),'executable_sha256':reproduction['executable_sha256'],'actions_sha256':audit.sha(out/'baseline-sessions/baseline-actions.json'),'received_frames':len(indices),'missing_steps':[i for i in range(1,331) if i not in indices],'max_node_depth_m':node,'max_surface_depth_m':surface,'node_peak_step':max_node_step,'surface_peak':max_surface,'regression_reproduced':node>.00015 and surface>.00015,'all_received_states_healthy':bool(healthy),'scope':'Received accepted output states only; one or more missing states are explicitly listed; not proof of all old-run substeps.'}
    (out/'baseline-independent-geometry.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--exe',type=pathlib.Path);ap.add_argument('--audit-only',action='store_true');ap.add_argument('--outdir',required=True,type=pathlib.Path);ap.add_argument('--port',type=int,default=47331);a=ap.parse_args()
    out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=True)
    if a.audit_only:
        result=audit_saved(out);raise SystemExit(0 if result['regression_reproduced'] else 2)
    if a.exe is None:ap.error('--exe is required unless --audit-only')
    session=out/'baseline-sessions';session.mkdir(exist_ok=True)
    command={'type':'command','reset_id':501,'paused':False,'active_tool':0,'tools':[{'tip_m':[-.022,-.047,.006],'closed':0,'roll_deg':90},{'tip_m':[.022,-.047,.006],'closed':0,'roll_deg':90}]}
    steps=[]
    for i in range(330):
        y=-.015
        if i<90:y=-.034 if i<45 else -.034+.019*min(1,(i-45)/35)
        v=[-.022,y,.0045+.012*math.sin(math.pi*(y+.04)/.08)]
        if 150<=i<180:v[2]+=.004
        if i>=210:v=[-.022,-.047,.006]
        j=json.loads(json.dumps(command));j['tools'][0]['tip_m']=v;j['tools'][0]['closed']=int(90<=i<180);steps.append(j)
    recording={'schema':'endoforge.actions.v1','config':{'name':'curved'},'dt_s':1/30,'steps':steps,'actions_file':'baseline-actions.json'}
    for name in ['last-session.json','baseline-actions.json']:(session/name).write_text(json.dumps(recording),encoding='utf-8')
    frames={};log=(out/'baseline.log').open('w',encoding='utf-8');proc=None;sock=None;buf=b''
    try:
        proc=subprocess.Popen([str(a.exe.resolve()),'--port',str(a.port),'--session-dir',str(session),'--exit-after-client'],cwd=a.exe.resolve().parent,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(200):
            try:sock=socket.create_connection(('127.0.0.1',a.port),timeout=.3);break
            except OSError:time.sleep(.1)
        if sock is None:raise RuntimeError('No connection')
        sock.settimeout(.08);packet=dict(command,session_action='replay_last',action_id=1);deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            sock.sendall((json.dumps(packet)+'\n').encode())
            try:chunk=sock.recv(2**20)
            except socket.timeout:continue
            if not chunk:raise RuntimeError('Disconnected')
            buf+=chunk
            while b'\n' in buf:
                line,buf=buf.split(b'\n',1);state=json.loads(line)
                if state.get('type')!='state' or state.get('session',{}).get('action_id')!=1:continue
                idx=state['session']['step_index'];frames[idx]=state
            if 330 in frames:break
        if 330 not in frames:raise RuntimeError('Incomplete baseline replay')
        sock.close();sock=None;proc.wait(timeout=20)
        (out/'baseline-received-states.jsonl').write_text(''.join(json.dumps(frames[i],separators=(',',':'))+'\n' for i in sorted(frames)),encoding='utf-8')
        maximum=max(t['penetration_m'] for f in frames.values() for t in f['tools']);steps_over=[i for i,f in frames.items() if max(t['penetration_m'] for t in f['tools'])>.00015]
        report={'kind':'old_release_straight_withdrawal_reproduction','executable':str(a.exe.resolve()),'executable_sha256':hashlib.sha256(a.exe.read_bytes()).hexdigest(),'received_steps':sorted(frames),'missing_steps':[i for i in range(1,331) if i not in frames],'max_node_depth_m':maximum,'steps_over_0_15mm':steps_over,'regression_reproduced':maximum>.00015,'all_healthy':all(f['healthy'] and f['safety_stops']==0 for f in frames.values()),'returncode':proc.returncode,'script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()}
        (out/'baseline-reproduction.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k not in ['received_steps','steps_over_0_15mm']}),flush=True)
    finally:
        if sock:sock.close()
        if proc and proc.poll() is None:
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        log.close()
if __name__=='__main__':main()
