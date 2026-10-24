"""Phase 2 real TCP tests; starts/stops its own hidden native SOFA service."""
import json, socket, subprocess, time, pathlib, math, hashlib, datetime
BASE=pathlib.Path(__file__).resolve().parent
runtime=BASE/'runtime'
report={'phase':2,'experimental':False,'passed':False,'checks':{},'tested_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'executable_sha256':hashlib.sha256((runtime/'LapPhysics.exe').read_bytes()).hexdigest()}
log=(runtime/'phase2-network-test.log').open('w',encoding='utf8')
proc=subprocess.Popen([str(runtime/'LapPhysics.exe'),'--phase2'],cwd=runtime,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
sock=None;buf=b'';latest=None;seq=0;rid=0
try:
    for _ in range(100):
        try: sock=socket.create_connection(('127.0.0.1',47322),timeout=.5);break
        except OSError: time.sleep(.1)
    assert sock,'service did not listen'
    sock.settimeout(.06)
    def receive():
        global buf,latest
        try:
            data=sock.recv(262144)
            if not data: raise ConnectionError('disconnected')
            buf+=data
        except socket.timeout: pass
        messages=[]
        while b'\n' in buf:
            line,buf=buf.split(b'\n',1);j=json.loads(line);messages.append(j)
            if j['type']=='state': latest=j
        return messages
    def send(tip=(0,-.015,.025),closed=0,roll=0,reset=None):
        global seq
        seq+=1;packet=dict(type='command',seq=seq,tip_m=tip,closed=closed,roll_deg=roll,reset_id=rid if reset is None else reset,paused=False)
        sock.sendall((json.dumps(packet)+'\n').encode())
    def check(name,value):
        report['checks'][name]=bool(value);assert value,name
    def phase(seconds,tip,closed=0,roll=0):
        start=latest['time'];deadline=time.monotonic()+max(5,seconds*4)
        while time.monotonic()<deadline:
            send(tip,closed,roll);receive()
            if latest['time']>=start+seconds-.0001: break
        else: raise AssertionError('simulation time stalled')
        check('all_received_states_healthy',latest['healthy'])
        assert all(math.isfinite(n) for v in latest['vertices'] for n in v)
        return latest
    def reset(tip=(0,-.015,.025),roll=0):
        global rid
        rid+=1;deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            send(tip,0,roll);receive()
            if latest['reset_id']==rid: return
        raise AssertionError('reset did not acknowledge')
    hello=None;deadline=time.monotonic()+3
    while time.monotonic()<deadline and (not hello or not latest):
        for j in receive():
            if j['type']=='hello': hello=j
    check('protocol2',hello['protocol']==2 and hello['material_validated'] is False and hello['node_count']==351)
    report['dt_s']=hello['dt'];check('30_hz_fixed_step',abs(hello['dt']-1/30)<1e-10)
    reset((0,-.052,.006),90);check('preset_reset_atomic_pose',math.dist(latest['tip_m'],(0,-.052,.006))<1e-8 and latest['jaw_open_fraction']>.99)
    phase(1,(0,-.037,.006),0,90);j=phase(1.6,(0,-.037,.006),1,90);check('native_bilateral_grip',j['grasping'] and j['contact_count']>1)
    j=phase(1.2,(.003,-.038,.014),1,90);check('frictional_8mm_lift',j['grasping'] and j['max_displacement_m']>.006)
    report['lift_load_n']=j['contact_force_n'];report['lift_displacement_m']=j['max_displacement_m']
    deadline=time.monotonic()+.9
    while time.monotonic()<deadline:
        sock.sendall(b'{}\n{"type":"unknown"}\n');receive()
    check('ignored_packets_do_not_refresh_watchdog',not latest['grasping'] and latest['jaw_open_fraction']>.5)
    for _ in range(10):
        reset();check('ten_clean_resets',latest['max_displacement_m']<1e-8)
    saved=rid
    for bad in [-1,1.5,'11',None,10**20]:
        sock.sendall((json.dumps(dict(type='command',seq=seq+1,tip_m=[0,0,.022],closed=0,reset_id=bad,paused=False))+'\n').encode())
        deadline=time.monotonic()+.12
        while time.monotonic()<deadline: receive()
        check('invalid_reset_ids_rejected',latest['reset_id']==saved)
    for update in [dict(paused='bad'),dict(tip_m=[0,'bad',0]),dict(closed=None),dict(roll_deg=[]),dict(roll_deg=1e309)]:
        packet=dict(type='command',seq=seq+1,tip_m=[0,0,.022],closed=0,reset_id=saved+1,paused=False);packet.update(update)
        sock.sendall((json.dumps(packet)+'\n').encode());deadline=time.monotonic()+.12
        while time.monotonic()<deadline: receive()
        check('malformed_commands_atomic',latest['reset_id']==saved)
    sock.sendall(b'not json\n');phase(.2,(0,-.015,.025));check('malformed_json_recovers',latest['healthy'])
    reset((0,-.015,.025),359);j=phase(.1,(0,-.015,.025),0,-359);check('roll_shortest_path_and_normalized',abs(j['roll_deg']-1)<.001)
    for pose in j['jaw_poses']:
        ax,side,n=pose['axis'],pose['side'],pose['normal']
        dot=lambda a,b:sum(x*y for x,y in zip(a,b))
        check('jaw_pose_orthonormal',all(abs(dot(v,v)-1)<1e-8 for v in [ax,side,n]) and abs(dot(ax,side))<1e-8 and abs(dot(ax,n))<1e-8)
    sock.close();time.sleep(.2);sock=socket.create_connection(('127.0.0.1',47322),timeout=.5);sock.settimeout(.06);buf=b'';latest=None
    deadline=time.monotonic()+2
    while time.monotonic()<deadline and latest is None: receive()
    check('reconnect_resets_session',latest['reset_id']==0 and not latest['grasping'])
    sock.sendall(b'{"padding":"'+b'x'*5000+b'"}\n');deadline=time.monotonic()+2;disconnected=False
    while time.monotonic()<deadline:
        try:
            if not sock.recv(262144): disconnected=True;break
        except (ConnectionResetError,ConnectionAbortedError): disconnected=True;break
        except socket.timeout: pass
    check('oversize_packet_disconnects',disconnected)
    report['passed']=all(report['checks'].values())
finally:
    if sock: sock.close()
    proc.terminate();proc.wait(timeout=5);log.close()
    (runtime/'phase2-network-test-results.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))
