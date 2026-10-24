"""Supplemental protocol-4 test for one explicitly selected material/fixation config."""
import datetime,hashlib,json,math,pathlib,socket,subprocess,time,traceback
BASE=pathlib.Path(__file__).resolve().parent;RT=BASE/'runtime';PORT=47328
config=json.loads((BASE/'configs/curved.json').read_text(encoding='utf-8'));config.update(fixed_rows=2,young_modulus_pa=30000)
config_file=RT/'phase4-configuration-test-input.json';config_file.write_text(json.dumps(config,indent=2),encoding='utf-8')
report={'phase':4,'kind':'supplemental_configuration','config':config,'checks':{},'passed':False,'tested_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'executable_sha256':hashlib.sha256((RT/'LapPhysics.exe').read_bytes()).hexdigest(),'test_script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()}
command={'type':'command','reset_id':0,'paused':False,'active_tool':0,'tools':[{'tip_m':[-.022,-.047,.006],'closed':0,'roll_deg':90},{'tip_m':[.022,-.047,.006],'closed':0,'roll_deg':90}]}
proc=None;sock=None;buf=b'';latest=None;hello=None;fixed=[];max_fixed_error=0.;max_disp=0.;gripped=0;states=0;max_stops=0;finite=True
log=(RT/'phase4-configuration-test.log').open('w',encoding='utf-8')
def receive():
    global buf,latest,hello,fixed,max_fixed_error,max_disp,gripped,states,max_stops,finite
    try:
        data=sock.recv(524288)
        if not data:raise ConnectionError('Unexpected service disconnect')
        buf+=data
    except socket.timeout:pass
    while b'\n' in buf:
        line,buf=buf.split(b'\n',1);j=json.loads(line)
        if j['type']=='hello':
            hello=j;fixed=[i for i,m in enumerate(j['material_node_ids']) if (m%425)//25>=15]
        elif j['type']=='state':
            latest=j;states+=1;max_stops=max(max_stops,j['safety_stops']);max_disp=max(max_disp,j['max_displacement_m']);gripped+=j['tools'][0]['grasping'];finite &= j['healthy'] and all(math.isfinite(x) for v in j['vertices'] for x in v)
            for i in fixed:max_fixed_error=max(max_fixed_error,math.dist(j['vertices'][i],hello['vertices'][i]))
def run(n):
    initial=latest['session']['step_index'] if latest else 0;deadline=time.monotonic()+max(20,n*.4)
    while time.monotonic()<deadline:
        sock.sendall((json.dumps(command)+'\n').encode());receive()
        if latest and latest['session']['step_index']>=initial+n:return
    raise AssertionError('Simulation did not advance')
def check(name,ok):report['checks'][name]=bool(ok);assert ok,name
try:
    probe=socket.socket();probe.bind(('127.0.0.1',PORT));probe.close()
    proc=subprocess.Popen([str(RT/'LapPhysics.exe'),'--config',str(config_file),'--port',str(PORT),'--exit-after-client'],cwd=RT,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(100):
        try:sock=socket.create_connection(('127.0.0.1',PORT),timeout=.2);break
        except OSError:time.sleep(.1)
    assert sock;sock.settimeout(.03);run(2)
    check('effective_configuration_matches_file',all(hello['config'][k]==v for k,v in config.items()))
    check('two_rows_identified_in_both_layers',len(fixed)==100)
    target=[-.022,-.034,.0045+.012*math.sin(math.pi*.006/.08)]
    command['tools'][0]['tip_m']=target;run(45);command['tools'][0]['closed']=1;run(50)
    check('modified_configuration_bilateral_grasp',latest['tools'][0]['grasping'])
    command['tools'][0]['tip_m']=target[:2]+[target[2]+.004];run(35)
    check('modified_configuration_transfers_traction',latest['tools'][0]['grasping'] and max_disp>.002)
    command['tools'][0]['closed']=0;run(30);command['tools'][0]['tip_m']=[-.022,-.047,.006];run(90)
    check('fixed_nodes_remain_fixed_during_manipulation',max_fixed_error<1e-9)
    check('released_after_manipulation',not latest['tools'][0]['grasping'])
    check('all_received_states_finite_and_healthy',finite and max_stops==0)
    sock.close();sock=None;proc.wait(timeout=10);check('clean_disconnect_exit',proc.returncode==0)
    report['metrics']={'received_states':states,'fixed_physical_nodes':len(fixed),'max_fixed_node_error_m':max_fixed_error,'max_displacement_m':max_disp,'gripped_states':gripped,'safety_stops':max_stops}
    report['passed']=all(report['checks'].values())
except Exception as exc:report.update(error=str(exc),traceback=traceback.format_exc())
finally:
    if sock:sock.close()
    if proc and proc.poll() is None:proc.terminate();proc.wait(timeout=10)
    log.close();(RT/'phase4-configuration-test-results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':report['passed'],'checks':report['checks'],'metrics':report.get('metrics',{}),'error':report.get('error')},indent=2))
raise SystemExit(0 if report['passed'] else 2)
