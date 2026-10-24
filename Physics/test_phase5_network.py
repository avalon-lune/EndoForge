"""Protocol 5 over real sockets: effective UI input, disk replay and identity."""
import argparse, datetime, hashlib, json, math, pathlib, socket, subprocess, time, traceback
BASE = pathlib.Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--output',type=pathlib.Path,default=BASE.parent/'tmp/phase5-resume-physics/network');parser.add_argument('--phase',type=int,choices=(5,6),default=5);parser.add_argument('--port',type=int,default=47329);args=parser.parse_args()
OUT = args.output.resolve()
OUT.mkdir(parents=True, exist_ok=False)
EXE = BASE / 'runtime/LapPhysics.exe'
MODEL = json.loads((BASE/f'runtime/assets/phase{args.phase}.json').read_text())
PORT = args.port
REPORT = {'phase': args.phase, 'passed': False, 'checks': {}, 'tested_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'executable_sha256': hashlib.sha256(EXE.read_bytes()).hexdigest()}
log = (OUT / 'service.log').open('w', encoding='utf-8')
proc = sock = None
buf = b''
latest = hello = None
rid = aid = seq = 0
command = {}
def check(name, passed):
    REPORT['checks'][name] = bool(passed)
    print(name, passed, flush=True)
    assert passed, name
def send(packet=None):
    global seq
    seq += 1
    packet = dict(command if packet is None else packet, seq=seq)
    sock.sendall((json.dumps(packet)+'\n').encode())
def receive():
    global buf, latest, hello
    try:
        chunk = sock.recv(524288)
        if not chunk: raise ConnectionError('service disconnected')
        buf += chunk
    except socket.timeout: pass
    while b'\n' in buf:
        line, buf = buf.split(b'\n', 1)
        state = json.loads(line)
        if state['type'] == 'hello': hello = state
        elif state['type'] == 'state':
            latest = state
            assert state['protocol'] == 5 and state['healthy'] and state['safety_stops'] == 0
            assert len(state['vertices']) == len(state['node_ids']) == len(set(state['node_ids']))
            assert all(math.isfinite(x) for p in state['vertices'] for x in p)
def until(predicate, timeout=30, packet=None):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        if command: send(packet)
        receive()
        if latest and predicate(latest): return latest
    raise AssertionError('state wait timeout')
def start():
    global proc, sock, buf, latest, hello, command
    buf = b''; latest = hello = None; command = {}
    proc = subprocess.Popen([str(EXE), f'--phase{args.phase}', '--port', str(PORT), '--session-dir', str(OUT/'sessions'), '--exit-after-client'], cwd=EXE.parent, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(100):
        try: sock = socket.create_connection(('127.0.0.1', PORT), timeout=.2); break
        except OSError: time.sleep(.1)
    assert sock
    sock.settimeout(.03); until(lambda s: True)
    command = {'type':'command','reset_id':0,'paused':False,'active_tool':0,'specimen':'gallbladder', 'tools':[{'tip_m':p,'roll_deg':90,'closed':0} for p in hello['home_tips_m']]}
def action(name, reset=False):
    global aid, rid
    aid += 1
    if reset: rid += 1; command['reset_id'] = rid
    packet = dict(command, session_action=name, action_id=aid)
    return until(lambda s: s['session']['action_id']==aid and (not reset or s['reset_id']==rid), packet=packet)
def steps(n):
    first = latest['session']['step_index']
    return until(lambda s:s['session']['step_index']>=first+n, timeout=max(30,n*.4))
def close():
    global sock, proc
    if sock: sock.close(); sock=None
    if proc: proc.wait(timeout=20); check('service_clean_exit',proc.returncode==0);proc=None
try:
    start()
    check('immutable_anatomy_hello',hello['model_id']==MODEL['model_id'] and hello['model_version']==MODEL['version'] and hello['asset_fingerprint'].startswith('fnv1a64:') and hello['tool_roles']==['grasper','grasper'] and not hello['cutting_enabled'])
    initial = latest
    bad = json.loads(json.dumps(command));bad['reset_id']=999;bad['specimen']='flat'
    until(lambda s:s['state_id']>initial['state_id']+3,packet=bad)
    check('invalid_specimen_reset_atomic',latest['simulation_id']==initial['simulation_id'] and latest['reset_id']==initial['reset_id'])
    action('record_start',True)
    targets=hello['grasp_targets_m']
    for k in (0,1):
        command['active_tool']=k
        if args.phase==6:
            recipe=hello['phase6_ready_recipes']['recipes'][k];binding=recipe['material_binding']
            target=[binding['tip_offset_m'][a]+sum(latest['vertices'][n][a]*w for n,w in zip(binding['node_ids'],binding['barycentric'])) for a in range(3)]
            cursor=latest['tools'][k]['tip_m'][:];points=[]
            for waypoint in recipe['approach_waypoints']:
                if waypoint['kind']=='current_xy_at_z':cursor=[cursor[0],cursor[1],waypoint['z_m']]
                elif waypoint['kind']=='toward_pivot_from_frozen_ready':
                    delta=[a-b for a,b in zip(latest['tools'][k]['pivot_m'],target)];length=math.sqrt(sum(x*x for x in delta))
                    cursor=[a+x*waypoint['distance_m']/length for a,x in zip(target,delta)]
                else:raise ValueError('Unknown authored ready waypoint')
                points.append(cursor[:])
            points.append(target)
            REPORT.setdefault('ready_recipe_samples',[]).append({'tool':k,'recipe':recipe,'sampled_state_id':latest['state_id'],'frozen_target_m':target,'resolved_waypoints_m':points})
            command['tools'][k]['roll_deg']=recipe['roll_deg']
            for point in points:
                command['tools'][k]['tip_m']=point
                until(lambda s:math.dist(s['tools'][k]['tip_m'],point)<1e-8 and abs(s['tools'][k]['roll_deg']-recipe['roll_deg'])<1e-8)
        else:
            command['tools'][k]['tip_m']=targets[k][:];steps(90)
        command['tools'][k]['closed']=1;steps(60)
        check(f'actual_selected_tool_{k}_grips',latest['tools'][k]['grasping'])
        if args.phase==6 and k==0:
            command['tools'][0]['tip_m'][2]+=.001;steps(15)
            check('left_grip_retained_during_handoff_lift',latest['tools'][0]['grasping'])
    check('inactive_grasper_retains_real_hold',all(t['grasping'] for t in latest['tools']))
    grasp_vertices=latest['vertices']
    # Alternating short movements keep two frictional contacts balanced. A
    # sudden 3 mm differential pull legitimately slips the opposite thin wall.
    for _ in range(2):
        for k in (0,1):
            command['active_tool']=k;command['tools'][k]['tip_m'][2]+=.001;steps(15)
    pull_displacement=max(math.dist(p,q) for p,q in zip(grasp_vertices,latest['vertices']))
    check('sequential_two_tool_traction',all(t['grasping'] for t in latest['tools']) and pull_displacement>=.0015 and latest['attachment_max_extension_m']>1e-6)
    REPORT['selected_tool_traction']={'increment_per_tool_m':.001,'increments_per_tool':2,'total_lift_per_tool_m':.002,'max_node_motion_from_grasp_m':pull_displacement}
    for tool in command['tools']:tool['closed']=0
    steps(45);check('release_both_via_input',all(not t['grasping'] for t in latest['tools']))
    for k in (0,1):
        command['active_tool']=k;command['tools'][k]['tip_m']=hello['home_tips_m'][k];steps(90)
    action('record_stop')
    actions=OUT/'sessions'/latest['session']['file'];doc=json.loads(actions.read_text())
    states=actions.with_name(actions.name.replace('-actions.json','-states.jsonl'))
    snapshots=[json.loads(line) for line in states.read_text().splitlines()]
    check('all_recorded_states_contiguous',len(snapshots)==len(doc['steps'])+1 and [s['session']['step_index'] for s in snapshots]==list(range(len(snapshots))))
    check('recorded_physics_state_and_identity',doc['schema']=='endoforge.actions.v2' and all(s['asset_fingerprint']==hello['asset_fingerprint'] and len(s['velocities_m_s'])==len(s['vertices']) and s['tetrahedra'] and s['fixed_indices'] and s['attachment_segments_m'] for s in snapshots))
    check('initial_snapshot_contains_bound_anatomy',snapshots[0]['anatomy_asset']==MODEL and hello['attachment_anchor_bindings']==MODEL['attachment_anchor_bindings'])
    close();start();action('replay_last',True)
    max_rms=0;max_node=0;max_force_difference=0;same_events=True;matched=set();first_difference=None;deadline=time.monotonic()+len(doc['steps'])*.4+20
    while time.monotonic()<deadline:
        send();receive();index=latest['session']['step_index']
        if index<len(snapshots):
            expected=snapshots[index]['vertices'];actual=latest['vertices']
            rms=math.sqrt(sum((a-b)**2 for p,q in zip(actual,expected) for a,b in zip(p,q))/len(actual));max_rms=max(max_rms,rms);matched.add(index)
            max_node=max(max_node,max(math.dist(p,q) for p,q in zip(actual,expected)))
            max_force_difference=max(max_force_difference,*(abs(a['force_n']-b['force_n']) for a,b in zip(latest['tools'],snapshots[index]['tools'])))
            same_events &= [[t['grasping'],t['grip_state']] for t in latest['tools']]==[[t['grasping'],t['grip_state']] for t in snapshots[index]['tools']]
            if rms>=1e-10 and first_difference is None:
                first_difference={'step_index':index,'rms_m':rms,'session':latest['session'],'expected_tools':snapshots[index]['tools'],'actual_tools':latest['tools']}
        if latest['session']['mode']=='replay_complete':break
    REPORT['replay']={'actions_file':str(actions),'states_file':str(states),'matched_received_frames':len(matched),'max_node_rms_m':max_rms,'max_single_node_m':max_node,'max_force_difference_n':max_force_difference,'same_events':same_events,'steps':len(doc['steps']),'first_difference':first_difference,'bitwise_geometry_diagnostic':max_rms<1e-10,'rms_tolerance_m':.0005,'acceptance_source':'Scripts/Phase5/acceptance-spec.json required.repeatability'}
    check('fresh_process_replay_complete',latest['session']['mode']=='replay_complete' and latest['session']['step_index']==len(doc['steps']))
    check('fresh_process_replay_geometry',max_rms<=.0005 and len(matched)>20)
    check('fresh_process_replay_events',same_events)
    stable=latest;command['tools'][0]['tip_m']=[.05,.05,.05];until(lambda s:s['state_id']>stable['state_id']+4)
    check('completed_replay_ignores_live_input',latest['vertices']==stable['vertices'])
    action('replay_stop');check('replay_stop_releases',all(not t['grasping'] for t in latest['tools']))
    close();REPORT['passed']=all(REPORT['checks'].values())
except Exception as exc: REPORT['error']=str(exc);REPORT['traceback']=traceback.format_exc()
finally:
    if sock:sock.close()
    if proc:
        proc.terminate()
        try:proc.wait(timeout=15)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
    log.close();(OUT/'report.json').write_text(json.dumps(REPORT,indent=2)+'\n')
raise SystemExit(0 if REPORT['passed'] else 2)
