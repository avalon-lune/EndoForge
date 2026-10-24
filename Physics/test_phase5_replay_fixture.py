"""Replay one persisted recording in fresh native processes, preserving diagnostics."""
import argparse, datetime, hashlib, json, math, pathlib, shutil, socket, subprocess, time

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--actions',type=pathlib.Path,required=True);ap.add_argument('--output',type=pathlib.Path,required=True);ap.add_argument('--repeats',type=int,default=3);ap.add_argument('--port',type=int,default=47329);ap.add_argument('--phase',type=int,choices=(5,6),default=5);args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    exe=pathlib.Path(__file__).parent/'runtime/LapPhysics.exe'
    doc=json.loads(args.actions.read_text());states=args.actions.with_name(args.actions.name.replace('-actions.json','-states.jsonl'))
    expected=[json.loads(s) for s in states.read_text().splitlines()]
    report={'schema':f'endoforge.phase{args.phase}.fresh_fixture.v1','executable_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'actions_sha256':hashlib.sha256(args.actions.read_bytes()).hexdigest(),'states_sha256':hashlib.sha256(states.read_bytes()).hexdigest(),'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'repeats':[]}
    for repeat in range(args.repeats):
        run=args.output/f'run-{repeat+1}';run.mkdir();(run/'last-session.json').write_text(json.dumps(doc))
        proc=None;sock=None;buf=b'';seen=set();summary={'repeat':repeat+1,'max_node_rms_m':0.,'max_single_node_m':0.,'max_force_difference_n':0.,'event_mismatches':[],'first_nonzero':None,'first_over_1e_10':None,'identity_and_topology_match':True}
        with (run/'service.log').open('w') as log,(run/'replayed-states.jsonl').open('w') as trace:
            try:
                proc=subprocess.Popen([str(exe.resolve()),f'--phase{args.phase}','--port',str(args.port),'--session-dir',str(run.resolve()),'--exit-after-client'],cwd=exe.parent,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
                for _ in range(150):
                    try:sock=socket.create_connection(('127.0.0.1',args.port),timeout=.2);break
                    except OSError:time.sleep(.1)
                assert sock;sock.settimeout(.1);sent=False;done=False;deadline=time.monotonic()+max(90,len(doc['steps'])*.8)
                while time.monotonic()<deadline and not done:
                    try:
                        b=sock.recv(524288)
                        if not b:raise RuntimeError('Disconnected before completion')
                        buf+=b
                    except socket.timeout:continue
                    while b'\n' in buf:
                        line,buf=buf.split(b'\n',1);s=json.loads(line)
                        if s['type']=='hello' and not sent:
                            command={'type':'command','reset_id':1,'paused':False,'active_tool':0,'specimen':'gallbladder','tools':[{'tip_m':p,'roll_deg':90,'closed':0} for p in s['home_tips_m']],'session_action':'replay_last','action_id':1}
                            sock.sendall((json.dumps(command)+'\n').encode());sent=True
                        if s['type']!='state' or s['session']['mode'] not in ('replaying','replay_complete'):continue
                        idx=s['session']['step_index']
                        if idx in seen:continue
                        seen.add(idx);trace.write(json.dumps(s,separators=(',',':'))+'\n');ref=expected[idx]
                        assert len(s['vertices'])==len(ref['vertices'])
                        summary['identity_and_topology_match'] &= all(s[key]==ref[key] for key in ['asset_fingerprint','model_id','model_version','config','node_ids','triangles','component_count','cut_count'])
                        ds=[math.dist(x,y) for x,y in zip(s['vertices'],ref['vertices'])];rms=math.sqrt(sum(d*d for d in ds)/len(ds))
                        summary['max_node_rms_m']=max(summary['max_node_rms_m'],rms);summary['max_single_node_m']=max(summary['max_single_node_m'],max(ds))
                        if rms and summary['first_nonzero'] is None:summary['first_nonzero']={'step':idx,'rms_m':rms,'max_m':max(ds),'actual_tools':s['tools'],'expected_tools':ref['tools']}
                        if rms>=1e-10 and summary['first_over_1e_10'] is None:summary['first_over_1e_10']={'step':idx,'rms_m':rms,'max_m':max(ds)}
                        def event(q):return [[t['grasping'],t['grip_state']] for t in q['tools']]
                        if event(s)!=event(ref):summary['event_mismatches'].append({'step':idx,'actual':event(s),'expected':event(ref)})
                        summary['max_force_difference_n']=max(summary['max_force_difference_n'],*(abs(a['force_n']-b['force_n']) for a,b in zip(s['tools'],ref['tools'])))
                        assert s['healthy'] and s['safety_stops']==0
                        done=s['session']['mode']=='replay_complete'
                assert done,'Replay timeout';sock.close();sock=None;proc.wait(timeout=20);assert proc.returncode==0
                summary.update(completed=True,received_steps=len(seen),expected_steps=len(doc['steps']),contiguous_steps=seen==set(range(1,len(doc['steps'])+1)),events_identical=not summary['event_mismatches'])
            finally:
                if sock:sock.close()
                if proc and proc.poll() is None:proc.terminate();proc.wait(timeout=20)
        report['repeats'].append(summary);(args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:v for k,v in summary.items() if k not in ('first_nonzero','event_mismatches')},indent=2),flush=True)
    report['acceptance']={'rms_node_tolerance_m':.0005,'events':'identical','source':'Scripts/Phase5/acceptance-spec.json required.repeatability','bitwise_reproducibility_claimed':False}
    report['passed']=all(r['completed'] and r['contiguous_steps'] and r['events_identical'] and r['identity_and_topology_match'] and r['max_node_rms_m']<=.0005 for r in report['repeats'])
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return 0 if report['passed'] else 2

if __name__=='__main__':raise SystemExit(main())
