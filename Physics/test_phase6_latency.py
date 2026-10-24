"""Measure real TCP command/accepted-state response; this is not a UI latency claim."""
import argparse
import datetime
import hashlib
import json
import math
import pathlib
import select
import socket
import subprocess
import time
import traceback


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=pathlib.Path, required=True)
    ap.add_argument('--port', type=int, default=47331)
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    exe = pathlib.Path(__file__).resolve().parent / 'runtime/LapPhysics.exe'
    report = {'phase': 6, 'passed': False, 'checks': {}, 'scope': 'Local TCP input to accepted native state; UE event/display latency is a separate test.',
              'executable_sha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
              'created_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    proc = sock = None
    trace = (out / 'responses.jsonl').open('w', encoding='utf-8')
    log = (out / 'service.log').open('w', encoding='utf-8')
    buffer = b''
    latest = hello = None
    sequence = 0
    sent = {}
    latencies = []
    command = None
    next_send = 0
    def send():
        nonlocal sequence
        sequence += 1
        command['seq'] = sequence
        stamp = time.perf_counter()
        sock.sendall((json.dumps(command, separators=(',', ':')) + '\n').encode())
        sent[sequence] = stamp
        return sequence, stamp
    def receive(timeout=.005):
        nonlocal buffer, latest, hello
        if not select.select([sock], [], [], timeout)[0]:
            return
        chunk = sock.recv(524288)
        if not chunk:
            raise RuntimeError('Native service disconnected')
        buffer += chunk
        now = time.perf_counter()
        while b'\n' in buffer:
            line, buffer = buffer.split(b'\n', 1)
            state = json.loads(line)
            if state['type'] == 'hello':
                hello = state
            elif state['type'] == 'state':
                latest = state
                assert state['healthy'] and state['safety_stops'] == 0
                seq = state.get('applied_command_seq', 0)
                latency = now - sent[seq] if seq in sent else None
                if latency is not None:
                    latencies.append(latency)
                trace.write(json.dumps({'receipt_time': now, 'applied_seq': seq, 'latency_s': latency,
                                        'native_time': state['time'], 'tips_m': [t['tip_m'] for t in state['tools']],
                                        'commanded_tips_m': state.get('commanded_tips_m'), 'step_ms': state['step_ms']}) + '\n')
    def pump(seconds, update=None):
        nonlocal next_send
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            if time.perf_counter() >= next_send:
                if update:
                    update()
                send()
                next_send = time.perf_counter() + 1 / 60
            receive()
    try:
        proc = subprocess.Popen([str(exe), '--phase6', '--port', str(args.port), '--exit-after-client'],
                                cwd=exe.parent, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.perf_counter() + 20
        while time.perf_counter() < deadline:
            try:
                sock = socket.create_connection(('127.0.0.1', args.port), timeout=.2)
                break
            except OSError:
                if proc.poll() is not None:
                    raise RuntimeError(f'Native exited {proc.returncode}')
                time.sleep(.05)
        assert sock
        sock.setblocking(True)
        while latest is None and time.perf_counter() < deadline:
            receive()
        assert latest and hello
        command = {'type': 'command', 'reset_id': 0, 'paused': False, 'active_tool': 0, 'specimen': 'gallbladder',
                   'tools': [{'tip_m': p, 'roll_deg': 90, 'closed': 0, 'hold_tip': True, 'hold_roll': True,
                              'bounded_target': True} for p in hello['home_tips_m']]}
        pump(.5)
        trials = []
        wall0, native0 = time.perf_counter(), latest['time']
        for direction in (1, -1, 1, -1, 1, -1, 1, -1, 1, -1):
            tool = command['tools'][0]
            before = latest['tools'][0]['tip_m'][:]
            def move():
                tool['hold_tip'] = False
                tool['tip_m'] = latest['tools'][0]['tip_m'][:]
                tool['tip_m'][0] += direction * .001
            move()
            start_seq, start_time = send()
            first_movement = None
            deadline = start_time + .15
            while time.perf_counter() < deadline:
                receive()
                if latest.get('applied_command_seq', 0) >= start_seq and math.dist(latest['tools'][0]['tip_m'], before) > 1e-7:
                    first_movement = time.perf_counter() - start_time
                    break
            assert first_movement is not None, 'First movement was not returned in 150 ms'
            pump(.25, move)
            last_visible = latest['tools'][0]['tip_m'][:]
            tool['hold_tip'] = True
            # Deliberately stale feedback must never become a reverse target.
            tool['tip_m'] = before
            stop_seq, stop_time = send()
            stop_ack = None
            deadline = stop_time + .15
            while time.perf_counter() < deadline:
                receive()
                if latest.get('applied_command_seq', 0) >= stop_seq:
                    stop_ack = time.perf_counter() - stop_time
                    break
            assert stop_ack is not None, 'Hold acknowledgement exceeded 150 ms'
            at_ack = latest['tools'][0]['tip_m'][:]
            pump(.2)
            after = latest['tools'][0]['tip_m'][:]
            trials.append({'direction': direction, 'movement_response_s': first_movement, 'hold_response_s': stop_ack,
                           'motion_after_last_visible_state_m': math.dist(at_ack, last_visible),
                           'motion_after_hold_ack_m': math.dist(after, at_ack)})
        wall = time.perf_counter() - wall0
        progress = latest['time'] - native0
        p95 = lambda values: sorted(values)[int(.95 * (len(values) - 1))]
        report['trials'] = trials
        report['metrics'] = {'movement_response_p95_ms': 1000 * p95([x['movement_response_s'] for x in trials]),
                             'hold_response_p95_ms': 1000 * p95([x['hold_response_s'] for x in trials]),
                             'accepted_command_response_p95_ms': 1000 * p95(latencies),
                             'maximum_stop_drift_mm': 1000 * max(x['motion_after_last_visible_state_m'] for x in trials),
                             'maximum_drift_after_hold_ack_mm': 1000 * max(x['motion_after_hold_ack_m'] for x in trials),
                             'native_progress_s': progress, 'wall_duration_s': wall, 'simulated_time_per_wall_time': progress / wall}
        report['checks'] = {'ten_motion_trials': len(trials) == 10,
                            'response_p95_at_most_150ms': report['metrics']['movement_response_p95_ms'] <= 150,
                            'hold_p95_at_most_150ms': report['metrics']['hold_response_p95_ms'] <= 150,
                            'stop_drift_at_most_1mm': report['metrics']['maximum_stop_drift_mm'] <= 1.00001,
                            'no_motion_after_hold_ack': report['metrics']['maximum_drift_after_hold_ack_mm'] < 1e-8,
                            'near_real_time_progress': progress / wall >= .95}
        sock.close(); sock = None
        proc.wait(timeout=20)
        report['checks']['service_clean_exit'] = proc.returncode == 0
        report['passed'] = all(report['checks'].values())
    except Exception as exc:
        report['error'] = str(exc)
        report['traceback'] = traceback.format_exc()
    finally:
        if sock:
            sock.close()
        if proc and proc.poll() is None:
            proc.terminate(); proc.wait(timeout=20)
        trace.close(); log.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('passed', 'checks', 'metrics', 'error') if k in report}, indent=2))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
