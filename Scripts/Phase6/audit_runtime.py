"""Independently check actual Phase 6 rendering, timing and input evidence.

This does not invent a pass from DefaultEngine.ini. Runtime identities, UE logs,
measured controller events and same-state feature ablations are all required.
"""
import argparse
import json
import re
from pathlib import Path

from common import finite, passed, read, require, resolve_child, sha, write_new


FEATURES = ('lumen_gi', 'lumen_reflections', 'hardware_ray_tracing',
            'lumen_hardware_ray_tracing', 'high_quality_shadows')
RENDER_CVARS = {'r.DynamicGlobalIlluminationMethod': 1,
               'r.ReflectionMethod': 1, 'r.RayTracing': 1,
               'r.Lumen.HardwareRayTracing': 1}
MOTION_ROUNDOFF_MM = 1e-9


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
    require(runtime.get('phase') == interaction.get('phase') == 6, 'Missing actual Phase 6 runtime identity')
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
    startup = audit_startup(runtime, log)
    log_evidence = {
        'd3d12': bool(re.search(r'LogD3D12RHI|RHI[^\n]*D3D12', log, re.I)),
        'sm6': bool(re.search(r'PCD3D_SM6|Shader[^\n]*SM6|Feature Level[^\n]*SM6', log, re.I)),
        'hardware_rt': bool(re.search(r'Ray tracing is enabled|RayTracing[^\n]*(?:enabled|Enabled)|RayTracingPipeline|ray tracing acceleration', log, re.I)),
        'shared_product_startup_ready': True,
    }
    require(all(log_evidence.values()), 'Actual D3D12/SM6/hardware RT initialization missing from UE log: ' + str(log_evidence))
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
    return {'schema': 'endoforge.phase6.runtime-audit.v1', 'phase': 6, 'passed': True,
            'checks': {'actual_dx12_sm6_hardware_rt': True, 'lumen_and_shadow_feature_effects': True,
                       'controller_latency_and_no_backlog': True, 'display_and_physics_progression': True,
                       'shared_product_startup_readiness': True},
            'runtime_sha256': sha(runtime_path), 'interaction_sha256': sha(interaction_path),
            'unreal_log_sha256': sha(log_path), 'log_evidence': log_evidence,
            'startup': startup, 'performance': perf, 'interaction_metrics': metrics, 'latency_samples': len(samples),
            'raw_latency_p95_ms': calculated_p95, 'repeat_image_rmse_8bit': noise,
            'raw_target_lead_max_mm': raw_lead, 'raw_stop_travel_max_mm': raw_stop,
            'motion_float_roundoff_tolerance_mm': MOTION_ROUNDOFF_MM,
            'proof_capture_hardware_ray_tracing_requested': True,
            'ray_tracing_scene_captures_cvar': capture_rt,
            'ablations': ablations, 'images': image_evidence,
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
        report = {'schema': 'endoforge.phase6.runtime-audit.v1', 'phase': 6,
                  'passed': False, 'error': str(error), 'audit_script_sha256': sha(__file__)}
    write_new(args.output, report)
    print(json.dumps(report))
    raise SystemExit(0 if report['passed'] else 1)
