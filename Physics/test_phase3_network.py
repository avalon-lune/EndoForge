"""Phase 3 real TCP commands only; owns and stops its own hidden service."""
import datetime, hashlib, json, math, pathlib, socket, statistics, subprocess, time, traceback

BASE = pathlib.Path(__file__).resolve().parent
RUNTIME = BASE / 'runtime'
PORT = 47324
report = {'phase': 3, 'passed': False, 'checks': {}, 'stages': [],
          'tested_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'executable_sha256': hashlib.sha256((RUNTIME / 'LapPhysics.exe').read_bytes()).hexdigest()}
log = (RUNTIME / 'phase3-network-test.log').open('w', encoding='utf8')
probe = socket.socket()
probe.bind(('127.0.0.1', PORT))
probe.close()
proc = subprocess.Popen([str(RUNTIME / 'LapPhysics.exe'), '--phase3', '--port', str(PORT)], cwd=RUNTIME,
                        stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
sock = None
buffer = b''
latest = None
hello = None
seq = 0
rid = 0
active = 0
commands = [dict(tip_m=[-.022, -.047, .006], closed=0, roll_deg=90),
            dict(tip_m=[.022, -.047, .006], closed=0, roll_deg=90)]
healthy_history = True
safety_stops_highwater = 0
costs = []
try:
    for _ in range(100):
        try:
            sock = socket.create_connection(('127.0.0.1', PORT), timeout=.3)
            break
        except OSError:
            time.sleep(.1)
    assert sock, 'service did not listen'
    sock.settimeout(.04)

    def receive():
        global buffer, latest, hello, healthy_history, safety_stops_highwater
        try:
            data = sock.recv(262144)
            if not data:
                raise ConnectionError('unexpected disconnect')
            buffer += data
        except socket.timeout:
            pass
        while b'\n' in buffer:
            line, buffer = buffer.split(b'\n', 1)
            j = json.loads(line)
            if j['type'] == 'hello':
                hello = j
            elif j['type'] == 'state':
                latest = j
                healthy_history &= j['healthy']
                safety_stops_highwater = max(safety_stops_highwater, j['safety_stops'])
                costs.append(j['step_ms'])
                assert all(math.isfinite(n) for v in j['vertices'] for n in v)
                assert all(0 <= i < len(j['vertices']) for tri in j['triangles'] for i in tri)
                assert len(j['tools']) == 2

    def send():
        global seq
        seq += 1
        packet = dict(type='command', seq=seq, reset_id=rid, paused=False,
                      active_tool=active, tools=commands)
        sock.sendall((json.dumps(packet) + '\n').encode())

    def check(name, ok):
        report['checks'][name] = bool(ok)
        assert ok, name

    def phase(seconds, name=None):
        start = latest['time']
        deadline = time.monotonic() + max(10, seconds * 8)
        while time.monotonic() < deadline:
            send()
            receive()
            assert latest['healthy'], 'solver unhealthy in ' + str(name)
            if latest['time'] >= start + seconds - .00001:
                if name:
                    j = {k: v for k, v in latest.items() if k not in ('vertices', 'triangles', 'jaw_poses')}
                    j['stage'] = name
                    report['stages'].append(j)
                return latest
        raise AssertionError('simulation stalled in ' + str(name))

    def reset():
        global rid, commands, active
        rid += 1
        active = 0
        commands = [dict(tip_m=[-.022, -.047, .006], closed=0, roll_deg=90),
                    dict(tip_m=[.022, -.047, .006], closed=0, roll_deg=90)]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            send()
            receive()
            if latest and latest['reset_id'] == rid:
                return
        raise AssertionError('reset not acknowledged')

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and (not hello or not latest):
        receive()
    check('protocol3_and_two_tools', hello['protocol'] == 3 and hello['tool_count'] == 2 and not hello['material_validated'])
    reset()
    initial_nodes = len(latest['vertices'])
    commands[0]['tip_m'] = [-.022, -.034, .0045]
    phase(.8, 'grasp_approach')
    commands[0]['closed'] = 1
    phase(1.5, 'bilateral_grasp')
    check('bilateral_friction_grip', latest['tools'][0]['grasping'])
    commands[0]['tip_m'][2] = .0085
    phase(1., 'traction')
    check('frictional_traction', latest['tools'][0]['grasping'] and latest['max_displacement_m'] > .003)
    active = 1
    point = min(latest['vertices'][:len(latest['vertices'])//2], key=lambda v: (v[0] - .040) ** 2 + (v[1] + .035) ** 2)
    commands[1]['tip_m'] = [point[0], point[1], point[2] - .002]
    phase(1.5, 'scissor_approach_to_deformed_tissue')
    commands[1]['closed'] = 1
    phase(1., 'first_physical_cut')
    check('contact_closure_splits_mesh', latest['cut_count'] > 0 and len(latest['vertices']) > initial_nodes)
    check('other_tool_remains_holding_during_cut', latest['tools'][0]['grasping'])
    count = latest['cut_count']
    phase(.5, 'closed_scissors_remain_stable')
    check('one_cut_event_per_closure', latest['cut_count'] == count)
    commands[1]['closed'] = 0
    phase(.8, 'open_after_cut')
    check('cut_fragment_release_stable', latest['healthy'])
    # Move across the deforming membrane with ordinary public commands. Each
    # new target comes from the current surface, not a hard-coded rest plane.
    for i, x in enumerate([.032, .024, .016, .008, 0., -.008, -.016, -.024, -.032, -.040, -.048, -.056]):
        if latest['cut_count'] >= 2 and latest['component_count'] >= 2:
            break
        point = min(latest['vertices'][:len(latest['vertices'])//2], key=lambda v: (v[0] - x) ** 2 + (v[1] + .029) ** 2)
        # Withdraw the open scissors before translating to the next bite. This
        # is a normal safe approach path, not a teleport through an existing cut.
        commands[1]['tip_m'][2] += .012
        phase(.85, 'withdraw_between_bites_' + str(i))
        commands[1]['tip_m'] = [point[0], point[1], point[2] + .012]
        phase(1., 'translate_above_tissue_' + str(i))
        # The membrane can relax substantially while the tool is withdrawn.
        # Refresh the actual upper surface immediately before the new approach.
        point = min(latest['vertices'][:len(latest['vertices'])//2], key=lambda v: (v[0] - x) ** 2 + (v[1] + .029) ** 2)
        commands[1]['tip_m'] = [point[0], point[1], point[2] - .002]
        phase(1.)
        commands[1]['closed'] = 1
        phase(.9, 'continued_bite_' + str(i))
        commands[1]['closed'] = 0
        phase(.75)
    check('repeated_cutting_events', latest['cut_count'] >= 2)
    check('disconnected_component_created_by_tool', latest['component_count'] >= 2)
    check('continued_cutting_healthy', latest['healthy'])
    count = latest['cut_count']
    active = 0
    commands[1]['closed'] = 1
    phase(1., 'inactive_scissors_close')
    check('inactive_scissors_no_cut', latest['cut_count'] == count)
    commands[0]['closed'] = 0
    commands[1]['closed'] = 0
    phase(.8, 'both_open')
    check('grasp_release_after_cut', not latest['tools'][0]['grasping'])
    reset()
    check('reset_restores_mesh_and_counters', len(latest['vertices']) == initial_nodes and latest['component_count'] == 1 and latest['cut_count'] == 0)
    # A blade hovering with its open blade geometry clear of a flat membrane must not cut even though its
    # mesh-resolution snapping radius could encompass nearby material edges.
    active = 1
    commands[1]['tip_m'] = [.022, -.047, .024]
    phase(1.2, 'withdraw_before_noncontact_hover')
    commands[1]['tip_m'] = [.020, -.030, .024]
    phase(1.2)
    commands[1]['tip_m'] = [.020, -.030, .014]
    phase(1.5)
    check('hover_has_no_native_contact_before_close', latest['tools'][1]['contact_count'] == 0)
    commands[1]['closed'] = 1
    phase(1., 'near_miss_above_membrane')
    check('near_miss_no_native_blade_contact_no_cut', latest['cut_count'] == 0 and latest['tools'][1]['contact_count'] == 0)
    reset()
    saved = rid
    malformed = dict(type='command', seq=-1, reset_id=rid+100, paused=False, active_tool=1, tools=commands)
    sock.sendall((json.dumps(malformed)+'\n').encode())
    phase(.1)
    check('invalid_command_atomic_rejection', latest['reset_id'] == saved)
    commands[0]['closed'] = commands[1]['closed'] = 1
    phase(.3)
    deadline = time.monotonic() + 1.1
    while time.monotonic() < deadline:
        sock.sendall(b'{}\n')
        receive()
    check('invalid_packets_do_not_refresh_watchdog', all(t['jaw_open_fraction'] > .8 and not t['grasping'] for t in latest['tools']))
    check('all_received_states_healthy', healthy_history)
    check('no_terminal_numerical_protection', safety_stops_highwater == 0)
    report['metrics'] = {'received_states': len(costs), 'step_p95_ms': sorted(costs)[int(.95*(len(costs)-1))], 'step_max_ms': max(costs)}
    report['passed'] = all(report['checks'].values())
except Exception:
    report['error'] = traceback.format_exc()
    if latest:
        report['failure_state'] = {k: v for k, v in latest.items() if k not in ('vertices', 'triangles', 'jaw_poses')}
finally:
    if sock:
        sock.close()
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    log.close()
    (RUNTIME / 'phase3-network-test-results.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k != 'stages'}, indent=2))
raise SystemExit(0 if report['passed'] else 2)
