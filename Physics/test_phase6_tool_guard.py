"""Exercise production TCP commands, blocked motion, retreat and recorded replay."""
import argparse
import hashlib
import json
import math
import pathlib
import select
import socket
import subprocess
import time
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXE = ROOT / 'Physics/runtime/LapPhysics.exe'
ASSET = ROOT / 'Assets/Phase6/physics-mesh.json'

def run(out):
    out.mkdir(parents=True, exist_ok=False)
    report = {'passed': False, 'checks': {}, 'scope': 'Production TCP rigid-liver block/retreat and recording replay; no tissue or actual tool pose writes.',
              'executable_sha256': hashlib.sha256(EXE.read_bytes()).hexdigest(),
              'asset_sha256': hashlib.sha256(ASSET.read_bytes()).hexdigest()}
    checks = report['checks']
    proc = sock = None
    log = (out/'service.log').open('w', encoding='utf-8')
    raw = (out/'native-responses.jsonl').open('wb')
    events = (out/'receipts.jsonl').open('w', encoding='utf-8')
    buffer = b''
    latest = None
    sequence = 0
    command = None
    stage = 'connect'
    stages = {}
    replay = {}
    def receive(timeout=.01):
        nonlocal buffer, latest
        if not select.select([sock], [], [], timeout)[0]: return
        chunk=sock.recv(2**20)
        if not chunk: raise RuntimeError('service disconnected')
        buffer+=chunk
        while b'\n' in buffer:
            line,buffer=buffer.split(b'\n',1)
            raw.write(line+b'\n')
            d=json.loads(line)
            if d['type']!='state': continue
            latest=d
            if not d['healthy'] or d['safety_stops']:
                raise AssertionError('Numerical failure: '+d.get('message',''))
            events.write(json.dumps({'stage':stage,'state_id':d['state_id'],'step_index':d['session']['step_index']})+'\n')
            stages.setdefault(stage,[]).append(d)
            if d['session']['mode'] in ('replaying','replay_complete'):
                replay[d['session']['step_index']]=d
    def send():
        nonlocal sequence
        sequence+=1;command['seq']=sequence
        sock.sendall((json.dumps(command)+'\n').encode())
    def pump(name, seconds, predicate=None):
        nonlocal stage
        stage=name;end=time.monotonic()+seconds;next_send=0
        while time.monotonic()<end:
            if time.monotonic()>=next_send:
                send();next_send=time.monotonic()+1/60
            receive()
            if predicate and predicate(latest): return
        if predicate: raise AssertionError('Timed out: '+name)
    def move(name, tip, roll=None, seconds=8):
        command['tools'][0]['tip_m']=tip
        if roll is not None:command['tools'][0]['roll_deg']=roll
        pump(name,seconds,lambda s:s and math.dist(s['tools'][0]['tip_m'],tip)<1e-8 and (roll is None or abs(s['tools'][0]['roll_deg']-roll)<1e-8))
    def action(name, aid, reset=False):
        if reset: command['reset_id']+=1
        command['session_action']=name;command['action_id']=aid
        pump(name,5,lambda s:s and s['session']['action_id']==aid)
        command.pop('session_action');command.pop('action_id')
    try:
        proc=subprocess.Popen([str(EXE),'--phase6','--mesh',str(ASSET),'--session-dir',str(out/'recordings'),'--port','47335','--exit-after-client'],
                              cwd=EXE.parent,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        end=time.monotonic()+20
        while time.monotonic()<end:
            try:sock=socket.create_connection(('127.0.0.1',47335),timeout=.3);break
            except OSError:
                if proc.poll() is not None:raise RuntimeError('Native exited '+str(proc.returncode))
                time.sleep(.05)
        if sock is None:raise RuntimeError('No service')
        while latest is None and time.monotonic()<end:receive()
        if latest is None:raise RuntimeError('No initial snapshot')
        command={'type':'command','reset_id':latest['reset_id'],'paused':False,'active_tool':0,
                 'tools':[{'tip_m':t['tip_m'],'closed':0,'roll_deg':t['roll_deg']} for t in latest['tools']]}
        action('record_start',1,True)
        move('lift_clear',[-.011,-.048,.065])
        move('move_lateral',[.055,.025,.065],0)
        command['tools'][0]['tip_m']=[.055,.025,-.002]
        pump('drive_into_liver',8,lambda s:s['tools'][0]['motion_guard']['blocked'])
        pump('sustained_block',1)
        blocked=stages['sustained_block'][-1]['tools'][0]
        checks['downward_motion_blocked']=blocked['motion_guard']['blocked']
        checks['ordinary_block_not_safety_stop']=latest['healthy'] and latest['safety_stops']==0
        checks['requested_target_retained']=latest['commanded_tips_m'][0][2] < blocked['tip_m'][2]-.001
        checks['sustained_block_keeps_positive_clearance']=all(t['tools'][0]['motion_guard']['endpoint_clearance_m']>.00015 for t in stages['sustained_block'])
        checks['stationary_block_does_not_drift']=max(math.dist(s['tools'][0]['tip_m'],blocked['tip_m']) for s in stages['sustained_block'])<1e-7
        report['blocked_pose']=blocked
        move('retreat',[.055,.025,.065])
        checks['retreat_away_from_boundary_succeeds']=not latest['tools'][0]['motion_guard']['blocked']
        # A second pass rotates the open jaws at the guarded boundary.
        command['tools'][0]['tip_m']=[.055,.025,-.002]
        pump('approach_boundary_again',8,lambda s:s['tools'][0]['motion_guard']['blocked'])
        command['tools'][0]['tip_m']=latest['tools'][0]['tip_m']
        command['tools'][0]['roll_deg']=90
        pump('roll_at_boundary',1.7)
        checks['rotation_attempt_at_boundary_is_guarded']=any(s['tools'][0]['motion_guard']['blocked'] for s in stages['roll_at_boundary'])
        command['tools'][0]['roll_deg']=latest['tools'][0]['roll_deg']
        move('retreat_after_roll',[.055,.025,.065])
        # Closed jaws descend at 90 degrees. Opening sweeps a jaw downward into
        # the rigid surface; it must be blocked even though tip command is fixed.
        move('orient_closed_test',[.055,.025,.065],90)
        command['tools'][0]['closed']=1
        pump('close_clear_of_liver',3,lambda s:s['tools'][0]['jaw_angle_deg']<1e-8)
        command['tools'][0]['tip_m']=[.055,.025,-.002]
        pump('closed_jaws_to_boundary',8,lambda s:s['tools'][0]['motion_guard']['blocked'])
        command['tools'][0]['tip_m']=latest['tools'][0]['tip_m']
        command['tools'][0]['closed']=0
        pump('opening_at_boundary',1)
        checks['opening_sweep_blocked_at_fixed_tip']=all(s['tools'][0]['motion_guard']['blocked'] for s in stages['opening_at_boundary'][-10:])
        checks['blocked_opening_does_not_snap_to_fully_open']=latest['tools'][0]['jaw_angle_deg']<.1
        checks['geometric_block_does_not_fabricate_contact_force']=max(s['tools'][0]['force_n'] for s in stages['opening_at_boundary'])<1e-12
        command['tools'][0]['closed']=1
        move('withdraw_closed_jaws',[.055,.025,.065])
        command['tools'][0]['closed']=0
        pump('opening_after_withdrawal',3,lambda s:s['tools'][0]['jaw_angle_deg']>39.999999)
        checks['opening_succeeds_after_withdrawal']=not latest['tools'][0]['motion_guard']['blocked']
        action('record_stop',2)
        record=json.loads((out/'recordings/last-session.json').read_text())
        checks['recording_binds_guard_configuration']='tool_motion_guard' in record['config'] and record['config']['tool_motion_guard']['implementation']=='phase6-rcm-jaw-liver-ccd-v1'
        checks['force_scope_excludes_geometric_liver_reaction']='no_reaction_force' in record['config']['force_scope']
        action('replay_last',3,True)
        pump('replay',len(record['steps'])/30+15,lambda s:s['session']['mode']=='replay_complete')
        reference_path=next((out/'recordings').glob('*-states.jsonl'))
        reference={}
        for line in reference_path.read_text().splitlines():
            d=json.loads(line);reference[d['session']['step_index']]=d
        maximum_pose=maximum_node=0;guard_equal=True;comparisons=0
        for index,d in replay.items():
            if index not in reference:continue
            r=reference[index];comparisons+=1
            for a,b in zip(d['tools'],r['tools']):
                maximum_pose=max(maximum_pose,math.dist(a['tip_m'],b['tip_m']),abs(a['roll_deg']-b['roll_deg']),abs(a['jaw_angle_deg']-b['jaw_angle_deg']))
                guard_equal &= a['motion_guard']==b['motion_guard']
            maximum_node=max(maximum_node,max(math.dist(a,b) for a,b in zip(d['vertices'],r['vertices'])))
        checks['replay_reaches_last_recorded_step']=latest['session']['step_index']==len(record['steps'])
        checks['replay_matches_actual_pose_and_guard']=comparisons>100 and maximum_pose<1e-12 and guard_equal
        checks['replay_matches_tissue']=maximum_node<1e-9
        report['replay']={'compared_steps':comparisons,'maximum_pose_difference':maximum_pose,'maximum_node_difference_m':maximum_node,'identical_guard_telemetry':guard_equal}
        checks['all_native_states_healthy']=True
        report['passed']=all(checks.values())
    except Exception:
        report['error']=traceback.format_exc()
    finally:
        if sock:sock.close()
        if proc:
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.terminate();proc.wait(timeout=5)
        raw.close();events.close();log.close()
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:v for k,v in report.items() if k!='blocked_pose'},indent=2))
    return 0 if report['passed'] else 2

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,required=True)
    raise SystemExit(run(p.parse_args().output.resolve()))
