"""Protocol 4 acceptance over actual loopback sockets. Owns only its service PID."""
import datetime,hashlib,json,math,pathlib,socket,subprocess,time,traceback
BASE=pathlib.Path(__file__).resolve().parent
RUNTIME=BASE/'runtime';PORT=47326
SESSION=RUNTIME/'phase4-network-session';SESSION.mkdir(exist_ok=True)
REPORT=RUNTIME/'phase4-network-test-results.json'
report={'phase':4,'kind':'tcp_session','passed':False,'checks':{},'metrics':{},'tested_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'executable_sha256':hashlib.sha256((RUNTIME/'LapPhysics.exe').read_bytes()).hexdigest()}
log=(RUNTIME/'phase4-network-test.log').open('w',encoding='utf-8');sock=None;proc=None;buf=b'';latest=None;hello=None;states=[];aid=0;rid=0;seq=0
command={'type':'command','reset_id':0,'paused':False,'active_tool':0,'tools':[{'tip_m':[-.022,-.047,.006],'closed':0,'roll_deg':90},{'tip_m':[.022,-.047,.006],'closed':0,'roll_deg':90}]}
def check(name,ok):
    report['checks'][name]=bool(ok)
    print(name,ok,flush=True)
    assert ok,name

def send(packet=None):
    global seq
    seq+=1;packet=dict(command if packet is None else packet);packet['seq']=seq
    sock.sendall((json.dumps(packet)+'\n').encode())

def receive():
    global buf,latest,hello
    try:
        chunk=sock.recv(524288)
        if not chunk:raise ConnectionError('service disconnected')
        buf+=chunk
    except socket.timeout:pass
    while b'\n' in buf:
        line,buf=buf.split(b'\n',1);j=json.loads(line)
        if j['type']=='hello':hello=j
        elif j['type']=='state':
            latest=j;states.append({k:j[k] for k in ('state_id','simulation_id','reset_id','time','healthy','safety_stops','topology_revision','cut_count','component_count')})
            assert j['protocol']==4 and j['healthy'] and j['safety_stops']==0
            assert len(j['node_ids'])==len(j['vertices'])==len(j['material_node_ids'])
            assert len(set(j['node_ids']))==len(j['node_ids'])
            assert all(math.isfinite(n) for v in j['vertices'] for n in v)

def until(predicate,timeout=30,packet=None):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        send(packet);receive()
        if latest and predicate(latest):return latest
    raise AssertionError('state wait timed out')

def action(name,new_reset=False,specimen=None):
    global aid,rid
    aid+=1
    if new_reset:rid+=1;command['reset_id']=rid
    if specimen:command['specimen']=specimen
    packet=dict(command,action_id=aid,session_action=name)
    j=until(lambda s:s['session']['action_id']==aid and (not new_reset or s['reset_id']==rid),packet=packet)
    return j

def run_steps(n):
    start=latest['session']['step_index'];return until(lambda s:s['session']['step_index']>=start+n,timeout=max(30,n*.4))

try:
    probe=socket.socket();probe.bind(('127.0.0.1',PORT));probe.close()
    proc=subprocess.Popen([str(RUNTIME/'LapPhysics.exe'),'--port',str(PORT),'--session-dir',str(SESSION),'--exit-after-client'],cwd=RUNTIME,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(100):
        try:sock=socket.create_connection(('127.0.0.1',PORT),timeout=.2);break
        except OSError:time.sleep(.1)
    assert sock;sock.settimeout(.03);until(lambda s:True)
    check('protocol4_hello_and_identity',hello['protocol']==4 and len(hello['node_ids'])==850 and latest['specimen']=='flat')
    # Validate the whole command before a reset mutates any model/config.
    before=latest;bad=dict(command,reset_id=100,specimen='curved');bad['tools']=json.loads(json.dumps(command['tools']));bad['tools'][1]['tip_m']=[1e308,1e308,1e308]
    until(lambda s:s['state_id']>before['state_id']+2,packet=bad)
    check('malformed_reset_atomic',latest['reset_id']==0 and latest['simulation_id']==before['simulation_id'] and latest['specimen']=='flat')
    action('record_start',True,'curved');sim=latest['simulation_id'];idx=latest['session']['step_index']
    packet=dict(command,action_id=aid,session_action='record_start');until(lambda s:s['session']['step_index']>idx+3,packet=packet)
    check('repeated_action_deduplicated',latest['simulation_id']==sim)
    stale=dict(command,reset_id=999,action_id=aid,session_action='record_start',specimen='flat');idx=latest['state_id'];until(lambda s:s['state_id']>idx+3,packet=stale)
    check('stale_action_cannot_reset_or_change_specimen',latest['simulation_id']==sim and latest['specimen']=='curved' and latest['reset_id']==rid)
    target=[-.022,-.034,.006+.012*math.sin(math.pi*.006/.08)-.0015]
    command['tools'][0]['tip_m']=target;run_steps(45)
    command['tools'][0]['closed']=1;run_steps(55)
    check('curved_tcp_bilateral_grip',latest['tools'][0]['grasping'])
    command['tools'][0]['tip_m']=target[:2]+[target[2]+.004];run_steps(40)
    check('curved_tcp_grip_transfers_traction',latest['tools'][0]['grasping'] and latest['max_displacement_m']>.002)
    command['tools'][0]['closed']=0;run_steps(35)
    command['tools'][0]['tip_m']=[-.022,-.047,.006];run_steps(100)
    action('record_stop');length=latest['session']['recorded_steps'];record_file=SESSION/latest['session']['file'];action_doc=json.loads(record_file.read_text(encoding='utf-8'))
    check('recording_written_with_every_step',length==len(action_doc['steps']) and length>250)
    stem=record_file.name.removesuffix('-actions.json');snapshots=[json.loads(line) for line in (SESSION/(stem+'-states.jsonl')).read_text(encoding='utf-8').splitlines()]
    check('physics_snapshots_contiguous',len(snapshots)==length+1 and [s['session']['step_index'] for s in snapshots]==list(range(length+1)))
    check('snapshot_geometry_velocity_provenance',all(len(s['vertices'])==len(s['velocities_m_s'])==len(s['node_ids']) for s in snapshots) and all('tetrahedra' in s and 'config' in s and 'parent_node_ids' in s for s in snapshots))
    final=snapshots[-1]['vertices'];action('replay_last',True)
    until(lambda s:s['session']['mode']=='replay_complete',timeout=length*.5)
    squared=sum((a-b)**2 for va,vb in zip(final,latest['vertices']) for a,b in zip(va,vb));rms=math.sqrt(squared/len(final))
    check('saved_input_replay_reproduces_geometry',rms<=.0005 and latest['session']['step_index']==length)
    complete=latest;command['tools'][0]['tip_m']=[.05,.05,.05];until(lambda s:s['state_id']>complete['state_id']+5)
    check('replay_complete_ignores_live_input',latest['vertices']==complete['vertices'])
    action('replay_stop');check('replay_stop_releases_tools',all(not t['grasping'] for t in latest['tools']))
    rid+=1;command['reset_id']=rid;command['specimen']='flat';until(lambda s:s['reset_id']==rid)
    check('specimen_reset_restores_flat',latest['specimen']=='flat' and latest['cut_count']==0 and latest['session']['mode']=='idle')
    # No heartbeat: healthy watchdog explicitly releases both tools.
    end=time.monotonic()+1.2
    while time.monotonic()<end:receive()
    check('watchdog_releases_both_tools',all(not t['grasping'] for t in latest['tools']) and 'timeout' in latest['message'].lower())
    check('state_ids_monotonic',all(a['state_id']<b['state_id'] for a,b in zip(states,states[1:])))
    # A window close drops the socket while recording; the service must flush
    # a complete session, which a new process can replay from its directory.
    action('record_start',True,'flat');command['tools'][0]['tip_m']=[-.022,-.034,.0045];command['tools'][0]['closed']=0;run_steps(45);command['tools'][0]['closed']=1;run_steps(50);command['tools'][0]['tip_m']=[-.022,-.034,.0085];run_steps(35)
    disconnected_file=SESSION/latest['session']['file'];disconnected_stem=disconnected_file.name.removesuffix('-actions.json');disconnected_meta=SESSION/(disconnected_stem+'-metadata.json')
    sock.close();sock=None
    deadline=time.monotonic()+10
    while time.monotonic()<deadline and not disconnected_meta.exists():time.sleep(.05)
    check('disconnect_recording_flushed',disconnected_meta.exists() and disconnected_file.exists())
    disk_actions=json.loads(disconnected_file.read_text(encoding='utf-8'));disk_states=[json.loads(line) for line in (SESSION/(disconnected_stem+'-states.jsonl')).read_text(encoding='utf-8').splitlines()]
    check('disconnect_recording_state_count',len(disk_states)==len(disk_actions['steps'])+1 and len(disk_actions['steps'])>=130)
    proc.wait(timeout=15);check('disconnect_flush_then_clean_exit',proc.returncode==0)
    proc=subprocess.Popen([str(RUNTIME/'LapPhysics.exe'),'--port',str(PORT),'--session-dir',str(SESSION),'--exit-after-client'],cwd=RUNTIME,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    buf=b'';latest=None;hello=None
    for _ in range(100):
        try:sock=socket.create_connection(('127.0.0.1',PORT),timeout=.2);break
        except OSError:time.sleep(.1)
    assert sock;sock.settimeout(.03);until(lambda s:True);action('replay_last',True)
    disk_max_rms=0.;matched_steps=set();end=time.monotonic()+max(40,len(disk_actions['steps'])*.4)
    while time.monotonic()<end:
        send();receive();step=latest['session']['step_index']
        if step<=len(disk_actions['steps']):
            expected=disk_states[step]['vertices'];actual=latest['vertices'];rms_step=math.sqrt(sum((a-b)**2 for va,vb in zip(actual,expected) for a,b in zip(va,vb))/len(expected));disk_max_rms=max(disk_max_rms,rms_step);matched_steps.add(step)
        if latest['session']['mode']=='replay_complete':break
    check('fresh_process_disk_replay_completed',latest['session']['mode']=='replay_complete' and latest['session']['step_index']==len(disk_actions['steps']))
    check('fresh_process_disk_trajectory_matches',disk_max_rms<=.0005 and len(matched_steps)>20)
    report['persisted_replay']={'steps':len(disk_actions['steps']),'matched_received_steps':len(matched_steps),'max_received_frame_node_rms_m':disk_max_rms,'actions_file':str(disconnected_file),'states_file':str(SESSION/(disconnected_stem+'-states.jsonl'))}

    report['metrics']={'received_states':len(states),'recorded_steps':length,'replay_final_rms_m':rms,'session_directory':str(SESSION),'actions_file':str(record_file),'snapshot_file':str(SESSION/(stem+'-states.jsonl')),'safety_stops':max(s['safety_stops'] for s in states)}
    report['passed']=all(report['checks'].values())
except Exception as exc:report['error']=str(exc);report['traceback']=traceback.format_exc()
finally:
    if sock:sock.close()
    if proc:
        proc.terminate()
        try:proc.wait(timeout=15)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
    log.close();REPORT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (RUNTIME/'phase4-network-states.json').write_text(json.dumps(states,separators=(',',':')),encoding='utf-8')
raise SystemExit(0 if report['passed'] else 2)
