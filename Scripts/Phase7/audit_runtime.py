"""Independently check actual Phase 7 rendering, timing and input evidence.

This does not invent a pass from DefaultEngine.ini. Runtime identities, UE logs,
measured controller events and same-state feature ablations are all required.
"""
import argparse
import json
import re
from pathlib import Path

from common import finite, passed, read, require, resolve_child, sha, write_new
from audit_appearance import audit_appearance, audit_manifest


FEATURES = ('lumen_gi', 'lumen_reflections', 'hardware_ray_tracing',
            'lumen_hardware_ray_tracing', 'high_quality_shadows')
RENDER_CVARS = {'r.DynamicGlobalIlluminationMethod': 1,
               'r.ReflectionMethod': 1, 'r.RayTracing': 1,
               'r.Lumen.HardwareRayTracing': 1}
MOTION_ROUNDOFF_MM = 1e-9


def audit_progression(runtime):
    """Reconstruct live throughput from paired, unfiltered transport polls.

    Actor frame deltas are not interchangeable with the wall timestamps of
    received native observations. In particular, unchanged native states still
    charge their full observed wall interval. Export/replay boundaries are
    explicit and never extrapolate native time to an unobserved endpoint.
    """
    clock = runtime.get('phase7_progression')
    require(isinstance(clock, dict), 'Missing paired progression evidence')
    require(clock.get('schema') == 'endoforge.phase7.paired-progression.v1',
            'Unknown paired progression schema')
    require(clock.get('sample_layout') ==
            ['poll_id', 'wall_s', 'native_s', 'simulation_id', 'mode', 'state_id'],
            'Unexpected paired progression sample layout')
    require(clock.get('valid') is True and clock.get('error') == '',
            'Paired progression clock reported an invalid observation')
    require(isinstance(clock.get('scope'), str) and len(clock['scope']) >= 30,
            'Paired progression observation scope is missing')
    rows, boundaries, segments = (clock.get(key) for key in ('samples', 'boundaries', 'segments'))
    require(isinstance(rows, list) and len(rows) >= 32,
            'Insufficient raw progression polls')
    require(isinstance(boundaries, list) and isinstance(segments, list),
            'Missing progression segments or boundaries')
    modes = {'idle', 'recording', 'replaying', 'replay_complete'}
    for index, row in enumerate(rows):
        require(isinstance(row, list) and len(row) == 6, 'Invalid progression poll shape')
        for column in (0, 3, 5):
            require(type(row[column]) is int and 0 <= row[column] < 2**53,
                    'Invalid progression identity')
        require(finite(row[1], 'progression.wall_s') >= 0 and
                finite(row[2], 'progression.native_s') >= 0 and row[4] in modes,
                'Invalid progression timestamp or mode')
        if index:
            previous = rows[index-1]
            require(row[0] > previous[0] and row[1] > previous[1],
                    'Progression polls or observed wall timestamps are not monotonic')
            require(row[3] != previous[3] or row[2] >= previous[2],
                    'Native progression reversed without a simulation change')
    allowed = {'startup', 'frozen_capture', 'render_proof', 'fence_recovery',
               'finish', 'disconnect', 'simulation_change', 'mode_change', 'replay'}
    resets = {}
    previous_count = -1
    for boundary in boundaries:
        count, reason = boundary.get('after_sample_count'), boundary.get('reason')
        require(type(count) is int and 0 <= count <= len(rows) and count >= previous_count,
                'Progression boundary is outside or out of order')
        previous_count = count
        require(reason in allowed, 'Unrecognized progression exclusion boundary')
        require(type(boundary.get('has_last_poll')) is bool and
                boundary['has_last_poll'] == (count > 0) and
                boundary.get('last_poll_id') == (rows[count-1][0] if count else 0),
                'Progression boundary is not bound to its last actual poll')
        if reason in ('simulation_change', 'mode_change'):
            column = 3 if reason == 'simulation_change' else 4
            require(0 < count < len(rows) and rows[count-1][column] != rows[count][column],
                    'Spurious progression identity-change boundary')
        elif reason == 'replay':
            require(count > 0 and rows[count-1][4] in ('replaying', 'replay_complete') and
                    (count == 1 or rows[count-2][4] != rows[count-1][4]),
                    'Spurious replay boundary')
        elif reason == 'startup':
            require(count == 0, 'Startup cannot exclude an already active live interval')
        elif reason == 'finish':
            require(count == len(rows), 'Progression continued after its finish boundary')
        resets.setdefault(count, set()).add(reason)
    require('startup' in resets.get(0, set()) and 'finish' in resets.get(len(rows), set()),
            'Progression evidence must include explicit startup and final boundaries')
    expected, active, stalls = [], None, 0
    for index, row in enumerate(rows):
        if index in resets:
            active = None
        if index:
            previous = rows[index-1]
            for column, reason in ((3, 'simulation_change'), (4, 'mode_change')):
                require(row[column] == previous[column] or reason in resets.get(index, set()),
                        'Unrecorded progression identity-change boundary')
        if row[4] not in ('idle', 'recording'):
            active = None
            continue
        if active is None:
            active = {'start_sample_index': index, 'end_sample_index': index,
                      'wall_s': 0.0, 'native_s': 0.0}
            expected.append(active)
        else:
            previous = rows[index-1]
            require(row[0] == previous[0]+1, 'An ordinary live transport poll was omitted')
            require(row[3:5] == previous[3:5], 'An interval crosses simulation or mode identity')
            active['end_sample_index'] = index
            active['wall_s'] += row[1]-previous[1]
            active['native_s'] += row[2]-previous[2]
            stalls += row[2] == previous[2]
    require(len(expected) == len(segments), 'Progression segment coverage differs from raw polls')
    for actual, rebuilt in zip(segments, expected):
        require(isinstance(actual, dict), 'Invalid progression segment')
        for key in ('start_sample_index', 'end_sample_index'):
            require(type(actual.get(key)) is int and actual[key] == rebuilt[key],
                    'Progression segment omits or adds raw polls')
        for key in ('wall_s', 'native_s'):
            require(abs(finite(actual.get(key), 'segment.'+key)-rebuilt[key]) <= 1e-8,
                    'Progression segment duration differs from paired endpoints')
    wall = sum(segment['wall_s'] for segment in expected)
    native = sum(segment['native_s'] for segment in expected)
    require(wall > 0 and stalls > 0, 'Live progression needs positive duration and retained no-state polls')
    perf = runtime['performance']
    for key, value in (('wall_s', wall), ('native_s', native)):
        require(abs(finite(clock.get(key), 'clock.'+key)-value) <= 1e-8,
                'Paired progression total differs from raw intervals')
    for key, value in (('measured_wall_seconds', wall), ('measured_native_seconds', native),
                       ('simulation_to_wall_ratio', native/wall)):
        require(abs(finite(perf.get(key), key)-value) <= 1e-8,
                'Runtime progression metric differs from the independently rebuilt clock')
    return {'sample_count': len(rows), 'segment_count': len(segments),
            'boundary_count': len(boundaries), 'no_native_advance_intervals': stalls,
            'wall_s': wall, 'native_s': native, 'simulation_to_wall_ratio': native/wall}


def audit_shader_log(log):
    """A successful startup/asset import cannot excuse a fallback material."""
    failure = re.search(r'Failed to compile Material|Default Material will be used in game|LAP_PHASE7_MATERIAL_ERROR|'
                        r'(?:shader|material)[^\r\n]{0,100}(?:compilation failed|compile failed)|'
                        r'(?:error|fatal error)[^\r\n]{0,100}(?:ShaderCompile|ShaderCompiler)|'
                        r'Failed to compile (?:global shader|shader)', log, re.I)
    require(failure is None, 'Shader/material compilation failure or fallback in actual UE log: ' +
            (failure.group(0) if failure else ''))
    return True


def audit_startup(runtime, log):
    startup = runtime.get('startup')
    require(isinstance(startup, dict), 'Missing shared product startup evidence')
    require(startup.get('ready') is True and startup.get('failed') is False,
            'Product startup did not become ready successfully')
    require(2 <= finite(startup.get('duration_s'), 'startup.duration_s') <= 90,
            'Product startup duration is outside the 2–90 second readiness window')
    for field in ('actor_ticks', 'rendered_viewport_frames', 'stable_viewport_frames', 'pending_at_ready',
                  'peak_pending', 'runtime_pso_creations'):
        require(type(startup.get(field)) is int and startup[field] >= 0,
                'Missing/noninteger startup counter: ' + field)
    require(startup['actor_ticks'] >= startup['rendered_viewport_frames'] >=
            startup['stable_viewport_frames'] >= 120,
            'Product startup needs at least 120 stable actual viewport draws')
    require(startup['pending_at_ready'] == 0, 'Shader/PSO work was pending at readiness')
    require(startup.get('rhi_fence_completed') is True,
            'Startup RHI submission fence did not complete')
    require(isinstance(startup.get('scope'), str) and len(startup['scope']) >= 30,
            'Startup preparation and measurement scope must be explicit')
    require('LAP_PHASE6_STARTUP failed:' not in log, 'UE log records startup failure')
    pattern = (r'LAP_PHASE6_STARTUP ready duration_s=([0-9.]+) frames=(\d+) '
               r'stable_frames=(\d+) pending=(\d+) peak_pending=(\d+) '
               r'runtime_psos=(\d+) rhi_fence=complete viewport_frames=(\d+)')
    matches = list(re.finditer(pattern, log))
    require(len(matches) == 1, 'UE log must contain exactly one complete startup readiness record')
    marker = log.find('LAP_PHASE6_STARTUP preparing actual viewport, input gated')
    require(0 <= marker < matches[0].start(), 'Startup preparation must precede readiness in the UE log')
    duration, frames, stable, pending, peak, psos, viewport_frames = matches[0].groups()
    require(abs(float(duration)-startup['duration_s']) <= .001,
            'Startup duration differs between runtime evidence and UE log')
    for field, value in (('actor_ticks', frames), ('stable_viewport_frames', stable),
                         ('rendered_viewport_frames', viewport_frames),
                         ('pending_at_ready', pending), ('peak_pending', peak),
                         ('runtime_pso_creations', psos)):
        require(startup[field] == int(value), 'Startup counter differs from UE log: ' + field)
    return startup


def audit(capture, spec):
    import numpy as np
    from PIL import Image

    runtime_path = capture / 'phase6-runtime.json'
    interaction_path = capture / 'phase6-interaction-test.json'
    log_path = capture / 'unreal.log'
    runtime, interaction = read(runtime_path), read(interaction_path)
    require(runtime.get('phase') == interaction.get('phase') == 7, 'Missing actual Phase 7 runtime identity')
    require(runtime.get('mechanics_phase') == interaction.get('mechanics_phase') == 6,
            'Presentation must explicitly retain the accepted mechanics generation')
    manifest, appearance_evidence = audit_manifest(capture / 'dataset' / 'visual-manifest.json')
    require(runtime.get('visual_manifest_sha1') == appearance_evidence['manifest_sha1'],
            'Runtime is not bound to the captured visual manifest')
    audit_appearance(runtime.get('appearance'), manifest['appearance'])
    require(runtime.get('run_kind') == 'acceptance_test', 'Normal interactive observations cannot substitute for acceptance evidence')
    require(runtime.get('rhi') in ('D3D12', 'DirectX 12'), 'Actual rendering RHI must be D3D12')
    require('SM6' in runtime.get('shader_model', ''), 'Actual shaders must use SM6')
    for name in FEATURES:
        require(runtime['features'].get(name) is True, 'Missing enabled runtime feature: ' + name)
    for name, value in RENDER_CVARS.items():
        require(runtime['cvars'].get(name) == value, 'Incorrect actual runtime cvar: ' + name)
    require(runtime.get('proof_capture_hardware_ray_tracing_requested') is True,
            'Proof SceneCapture did not request hardware ray tracing')
    capture_rt = finite(runtime.get('ray_tracing_scene_captures_cvar'),
                        'ray_tracing_scene_captures_cvar')
    require(capture_rt != 0, 'Hardware ray tracing is disabled for SceneCapture components')
    # Virtual shadow maps or hardware ray-traced shadows must be recorded. The
    # separate images verify actual illumination changes in this close-up scene.
    require(runtime['cvars'].get('r.Shadow.Virtual.Enable') == 1 or
            runtime['cvars'].get('r.RayTracing.Shadows') == 1,
            'No high-quality shadow mode proved')
    log = log_path.read_text(encoding='utf-8-sig', errors='replace')
    audit_shader_log(log)
    startup = audit_startup(runtime, log)
    log_evidence = {
        'd3d12': bool(re.search(r'LogD3D12RHI|RHI[^\n]*D3D12', log, re.I)),
        'sm6': bool(re.search(r'PCD3D_SM6|Shader[^\n]*SM6|Feature Level[^\n]*SM6', log, re.I)),
        'hardware_rt': bool(re.search(r'Ray tracing is enabled|RayTracing[^\n]*(?:enabled|Enabled)|RayTracingPipeline|ray tracing acceleration', log, re.I)),
        'shared_product_startup_ready': True,
        'no_shader_compile_failure_or_fallback': True,
    }
    require(all(log_evidence.values()), 'Actual D3D12/SM6/hardware RT initialization missing from UE log: ' + str(log_evidence))
    progression = audit_progression(runtime)
    perf = runtime['performance']; gate = spec['performance']
    require([perf.get('width'), perf.get('height')] == [gate['width'], gate['height']], 'Measured display resolution differs from acceptance')
    require(finite(perf.get('mean_fps'), 'mean_fps') >= gate['display_mean_fps_minimum'], 'Display FPS below target')
    require(finite(perf.get('simulation_to_wall_ratio'), 'simulation_to_wall_ratio') >= gate['simulation_to_wall_ratio_minimum'], 'Physics simulation is slower than the acceptance progression rate')
    measured_wall = finite(perf.get('measured_wall_seconds'), 'measured_wall_seconds')
    measured_native = finite(perf.get('measured_native_seconds'), 'measured_native_seconds')
    require(measured_wall > 0 and measured_native >= 0, 'Measured progression durations must be nonnegative with positive wall time')
    require(abs(measured_native / measured_wall - perf['simulation_to_wall_ratio']) <= 1e-9,
            'Simulation/wall ratio differs from the recorded durations')
    display_wall = finite(perf.get('display_measured_wall_seconds'), 'display_measured_wall_seconds')
    require(display_wall > 0, 'Measured display wall duration must be positive')
    require(isinstance(perf.get('progression_scope'), str) and len(perf['progression_scope']) >= 30,
            'Display versus live-physics timing scopes must be stated explicitly')
    require('post-readiness' in perf['progression_scope'].lower(),
            'Performance scope must disclose the shared product readiness boundary')
    display_frames = perf.get('display_frames')
    require(type(display_frames) is int and display_frames > 0, 'Missing measured display frame count')
    require(abs(display_frames / display_wall - perf['mean_fps']) <= .001,
            'Display FPS differs from the measured frame count and wall duration')
    for name in ('frame_p95_ms', 'physics_step_mean_ms', 'physics_step_p95_ms'):
        require(finite(perf.get(name), name) > 0, 'Timing must be a measured positive number: ' + name)
    require(perf['frame_p95_ms'] <= gate['display_p95_frame_ms_maximum'],
            'Display frame P95 exceeds the Phase 7 interaction-quality limit')
    require(perf.get('capture_freeze_excluded') is True, 'Performance must exclude frozen export intervals')
    require(perf.get('concurrent_acceptance_workloads') == 0, 'Performance must be measured without concurrent acceptance workloads')
    if perf.get('gpu_frame_ms') is not None:
        require(finite(perf['gpu_frame_ms'], 'gpu_frame_ms') > 0, 'GPU time must be positive or explicitly unavailable')
    passed('interaction', interaction)
    metrics = interaction['metrics']; igate = spec['interaction']
    for field, limit in (('response_p95_ms', 'response_p95_ms_maximum'),
                         ('target_lead_max_mm', 'target_lead_mm_maximum'),
                         ('stop_residual_travel_max_mm', 'stop_residual_travel_mm_maximum')):
        roundoff = MOTION_ROUNDOFF_MM if field != 'response_p95_ms' else 0
        require(0 <= finite(metrics.get(field), field) <= igate[limit] + roundoff, 'Input acceptance limit exceeded: ' + field)
    samples = interaction.get('samples', [])
    require(len(samples) >= 12, 'Insufficient actual input samples')
    latency = []
    for sample in samples:
        event = finite(sample.get('input_event_time_s'), 'input_event_time_s')
        returned = finite(sample.get('accepted_state_received_time_s'), 'accepted_state_received_time_s')
        require(returned >= event, 'Input latency timestamps are reversed')
        require(sample.get('input_source') in ('PlayerControllerKeyboard', 'PlayerControllerMouse'), 'Synthetic native pose injection is not an input test')
        require(type(sample.get('state_id')) is int, 'Missing accepted native state identity')
        latency.append((returned-event)*1000)
    calculated_p95 = float(np.percentile(latency, 95))
    require(abs(calculated_p95-metrics['response_p95_ms']) <= 1, 'Reported latency P95 differs from raw samples')
    require(calculated_p95 <= igate['response_p95_ms_maximum'], 'Raw latency P95 fails')
    require({sample['input_source'] for sample in samples} == {'PlayerControllerKeyboard', 'PlayerControllerMouse'}, 'Both keyboard and mouse paths must be sampled')
    require({sample.get('tool') for sample in samples} == {0, 1}, 'Both tools must be sampled')
    motion = interaction['motion_samples']
    require(len(motion) >= 32, 'Raw motion/stop samples are required')
    trials = {}
    raw_lead = 0.0
    for sample in motion:
        actual = np.asarray(sample['actual_tip_cm'], dtype=float)
        target = np.asarray(sample['target_tip_cm'], dtype=float)
        require(actual.shape == target.shape == (3,) and np.isfinite(actual).all() and np.isfinite(target).all(), 'Invalid raw instrument positions')
        raw_lead = max(raw_lead, float(np.linalg.norm(target-actual))*10)
        trials.setdefault(sample['trial'], []).append(sample)
    require(set(trials) == set(range(16)), 'Sixteen raw input trials required')
    raw_stop = 0.0
    for number, rows in trials.items():
        stopped = [row for row in rows if row['after_release']]
        require(len(stopped) >= 3, 'Insufficient stopped-path samples')
        require(stopped[-1]['time_s']-stopped[0]['time_s'] >= .4, 'Stop response observation too short')
        positions = np.asarray([row['actual_tip_cm'] for row in stopped], dtype=float)
        travel = float(np.linalg.norm(np.diff(positions, axis=0), axis=1).sum())*10
        raw_stop = max(raw_stop, travel)
    require(abs(raw_lead-metrics['target_lead_max_mm']) <= .001, 'Reported target lead differs from raw positions')
    require(abs(raw_stop-metrics['stop_residual_travel_max_mm']) <= .001, 'Reported stop travel differs from raw positions')
    require(raw_lead <= igate['target_lead_mm_maximum'] + MOTION_ROUNDOFF_MM and
            raw_stop <= igate['stop_residual_travel_mm_maximum'] + MOTION_ROUNDOFF_MM,
            'Raw input motion violates acceptance')
    images = {item['variant']: item for item in runtime['render_comparisons']}
    require(set(images) == {'full', 'full_repeat', 'gi_off', 'reflections_off', 'shadows_off'}, 'Five fixed-state comparison images are required')
    identity = {(item['state_id'], item['simulation_id'], json.dumps(item['camera'], sort_keys=True)) for item in images.values()}
    require(len(identity) == 1, 'Render comparison images are not the same state/camera')
    pixels = {}; image_evidence = []
    for variant, item in images.items():
        require(item.get('phase') == 7 and item.get('visual_manifest_sha1') == appearance_evidence['manifest_sha1'],
                'Render comparison is not bound to the Phase 7 appearance identity')
        audit_appearance(item.get('appearance'), manifest['appearance'])
        path = resolve_child(capture, item['file'])
        pixels[variant] = np.asarray(Image.open(path).convert('RGB'), dtype=np.float64)
        require(pixels[variant].shape == (gate['height'], gate['width'], 3), 'Unexpected comparison image dimensions')
        require(pixels[variant].std() > 3, 'Comparison image is empty or flat')
        require(item.get('exposure_locked') is True and item.get('displayed_geometry_frozen') is True, 'Uncontrolled lighting comparison')
        require(item.get('native_simulation_paused') is False, 'Capture must accurately disclose that native mechanics continue while the accepted displayed state is frozen')
        require(item.get('warmup_frames', 0) >= 8, 'Comparison image temporal history not settled')
        image_evidence.append({'variant': variant, 'file': item['file'], 'sha256': sha(path)})
    for variant in ('full', 'full_repeat'):
        for name, value in RENDER_CVARS.items():
            require(images[variant]['cvars'].get(name) == value, 'Full-feature image cvars differ')
    require(images['gi_off']['cvars'].get('r.Lumen.DiffuseIndirect.Allow') == 0 or images['gi_off']['cvars'].get('r.DynamicGlobalIlluminationMethod') == 0, 'GI ablation was not disabled')
    require(images['reflections_off']['cvars'].get('r.Lumen.Reflections.Allow') == 0 or images['reflections_off']['cvars'].get('r.ReflectionMethod') == 0, 'Reflection ablation was not disabled')
    require(images['shadows_off']['cvars'].get('r.ShadowQuality') == 0, 'Shadow ablation was not disabled')
    reference = pixels['full']
    noise = float(np.sqrt(np.mean((pixels['full_repeat']-reference)**2)))
    ablations = {}
    for variant in ('gi_off', 'reflections_off', 'shadows_off'):
        diff = pixels[variant]-reference
        rmse = float(np.sqrt(np.mean(diff**2)))
        changed = float(np.mean(np.max(np.abs(diff), axis=2) > 2))
        require(rmse > max(0.1, 1.25*noise), 'Feature effect is not distinguishable from repeated-capture variation: ' + variant)
        ablations[variant] = {'rmse_8bit': rmse, 'changed_pixels_fraction_above_2_levels': changed}
    return {'schema': 'endoforge.phase7.runtime-audit.v1', 'phase': 7, 'passed': True,
            'checks': {'actual_dx12_sm6_hardware_rt': True, 'lumen_and_shadow_feature_effects': True,
                       'controller_latency_and_no_backlog': True, 'display_and_physics_progression': True,
                       'shared_product_startup_readiness': True, 'appearance_identity_and_actual_parameters': True,
                       'display_frame_p95': True},
            'runtime_sha256': sha(runtime_path), 'interaction_sha256': sha(interaction_path),
            'unreal_log_sha256': sha(log_path), 'log_evidence': log_evidence,
            'startup': startup, 'performance': perf, 'paired_progression': progression,
            'interaction_metrics': metrics, 'latency_samples': len(samples),
            'raw_latency_p95_ms': calculated_p95, 'repeat_image_rmse_8bit': noise,
            'raw_target_lead_max_mm': raw_lead, 'raw_stop_travel_max_mm': raw_stop,
            'motion_float_roundoff_tolerance_mm': MOTION_ROUNDOFF_MM,
            'proof_capture_hardware_ray_tracing_requested': True,
            'ray_tracing_scene_captures_cvar': capture_rt,
            'ablations': ablations, 'images': image_evidence,
            'appearance': appearance_evidence, 'mechanics_phase': 6,
            'appearance_audit_script_sha256': sha(Path(__file__).with_name('audit_appearance.py')),
            'uv_audit_script_sha256': sha(Path(__file__).with_name('audit_uv.py')),
            'scope': 'Local input-to-accepted-state latency, controlled fixed-state rendering and measured runtime. No hardware motion-to-photon or clinical calibration claim.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--spec', type=Path, default=Path(__file__).with_name('acceptance-spec.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit(args.capture.resolve(), read(args.spec))
        report['audit_script_sha256'] = sha(__file__)
        report['acceptance_spec_sha256'] = sha(args.spec)
    except (AssertionError, ValueError, KeyError, TypeError, OSError) as error:
        report = {'schema': 'endoforge.phase7.runtime-audit.v1', 'phase': 7,
                  'passed': False, 'error': str(error), 'audit_script_sha256': sha(__file__)}
    write_new(args.output, report)
    print(json.dumps(report))
    raise SystemExit(0 if report['passed'] else 1)
