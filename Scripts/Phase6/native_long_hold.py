"""Validate the additional long-hold contract without replacing native regression.

All fifteen traces retain per-step state checks. Whole-surface geometry audits
are separately required for the three nominal traces, the nine operating cases
and the endurance trace; offsets are not claimed as independently swept geometry.
"""
import json
import math
from pathlib import Path

from common import finite, passed, read, require, sha


HERE = Path(__file__).resolve().parent
REPRESENTATIVE_CASES = ('tool0-nominal', 'tool1-nominal', 'dual-2mm')
CONTROLLER = 'phase6-bilateral-load-latch-v1'


def expected_long_hold_cases():
    return list(REPRESENTATIVE_CASES) + [
        f'tool{tool}-{axis}-{direction}' for tool in (0, 1)
        for axis in 'xyz' for direction in ('minus', 'plus')]


def evidence(root, path):
    path = path.resolve()
    require(path.is_relative_to(root), 'Long-hold evidence escapes workspace')
    return {'path': str(path), 'relative_path': path.relative_to(root).as_posix(),
            'sha256': sha(path), 'bytes': path.stat().st_size}


def expected_options(name, gate):
    options = {'dual': name == 'dual-2mm', 'lift_m': .002 if name == 'dual-2mm' else .001,
               'speed_m_s': .005, 'grasp_hold_steps': gate['hold_steps_per_stage'],
               'traction_hold_steps': gate['hold_steps_per_stage'],
               'minimum_traction_increment_m': gate['dual_increment_minimum_m'] if name == 'dual-2mm' else gate['single_increment_minimum_m'],
               'assembly_compare': True}
    if name != 'dual-2mm':
        tool = int(name[4]); pose = list(gate['nominal_rest_ready_tips_m'][tool])
        label = name[6:]
        if label != 'nominal':
            axis, direction = label.split('-')
            pose['xyz'.index(axis)] += gate['pose_offset_m'] * (-1 if direction == 'minus' else 1)
        targets = [list(p) for p in gate['nominal_rest_ready_tips_m']]
        targets[tool] = pose
        options.update(single_tool=tool, targets=targets)
    return options


def audit_states(path, name, report, gate):
    tested = (0, 1) if name == 'dual-2mm' else (report['options']['single_tool'],)
    retained_stages = ('extended_grasp_hold', 'traction', 'extended_traction_hold', 'loaded_retraction')
    counts = {}; angles = {}; max_drift = 0.0; max_force = 0.0; max_depth = 0.0
    max_rate = max_normal = 0.0
    controller = gate['controller_parameters']; reconstructed_steps = 0
    min_volume = min_area = math.inf; min_contacts = [None, None]
    grace_samples = [0, 0]; previous = None; state_count = 0; times = {}
    pre_lift = last_traction = retained_traction = None
    with path.open(encoding='utf-8-sig') as stream:
        header = json.loads(next(stream))
        require(header['type'] == 'mesh' and header['case_id'] == name, 'Wrong long-hold trace header')
        for line in stream:
            state = json.loads(line); stage = state.get('stage')
            require(state.get('type') == 'state' and state.get('case_id') == name,
                    'Unexpected long-hold state identity')
            require(state['sample'] == state_count, 'Long-hold samples are not contiguous')
            require(state['config'] == report['config'], 'Long-hold state model changed')
            require(state['healthy'] is True and state['safety_stops'] == 0, 'Unhealthy long-hold state')
            adaptive=state['adaptive_solver']
            require(adaptive['accepted'] is True and adaptive['substeps'] in (1,2,4,8,16) and
                    0 <= finite(adaptive['maximum_substep_node_travel_m'],'adaptive.node_travel') <= report['config']['thickness_m']+1e-12 and
                    0 <= finite(adaptive['maximum_constraint_residual'],'adaptive.residual') <= 1e-5,
                    'Unaccepted or insufficiently converged physical step')
            require(state['triangles'] == header['triangles'], 'Long-hold topology changed')
            time = finite(state['time'], 'long_hold.time')
            if previous is not None:
                require(state['simulation_id'] == previous['simulation_id'] and
                        abs(time-previous['time']-gate['time_step_s']) < 1e-8,
                        'Long-hold trace skipped or reset a physical step')
            min_volume = min(min_volume, finite(state['min_tet_volume_ratio'], 'long_hold.volume'))
            min_area = min(min_area, finite(state['min_triangle_area_ratio'], 'long_hold.area'))
            require(len(state['vertices']) == len(header['rest_vertices']) and
                    all(len(v) == 3 and all(type(x) in (int, float) and math.isfinite(x) for x in v)
                        for v in state['vertices']), 'Nonfinite long-hold geometry')
            require(len(state['tools']) == 2, 'Missing long-hold tool state')
            for tool, value in enumerate(state['tools']):
                force = finite(value['force_n'], 'long_hold.force_n')
                depth = finite(value['penetration_m'], 'long_hold.penetration_m')
                require(force >= 0 and 0 <= depth <= .00015, 'Invalid force or excessive native node penetration')
                max_force = max(max_force, force); max_depth = max(max_depth, depth)
                normals = value['inner_normal_force_n']
                require(len(normals) == 2 and all(finite(v, 'long_hold.normal_force_n') >= 0 for v in normals),
                        'Invalid bilateral normal-force telemetry')
                require(sum(normals) <= force+1e-10,
                        'Bilateral inner normal components exceed the total contact-force magnitude')
                if value['grasping'] and previous is not None and not previous['tools'][tool]['grasping']:
                    require(min(normals)>=controller['grasp_acquisition_minimum_inner_normal_n'] and sum(normals)>=controller['grasp_acquisition_minimum_total_inner_normal_n'],
                            'Grip acquired without the declared bilateral contact load')
                max_normal = max(max_normal, *normals)
                guard=value['motion_guard']
                require(guard['implementation']=='phase6-rcm-jaw-liver-ccd-v1' and guard['initial_valid'] is True and
                        0 <= finite(guard['accepted_fraction'], 'guard.fraction') <= 1 and
                        finite(guard['endpoint_clearance_m'], 'guard.clearance') > .00015,
                        'Invalid continuous collision admission in long-hold state')
                contacts = value['inner_contacts']
                require(len(contacts) == 2 and all(type(n) is int and n >= 0 for n in contacts),
                        'Invalid long-hold contact counters')
                if stage in retained_stages and tool in tested:
                    require(value['grasping'] is True, 'Grip lost in long-hold/traction/retraction: ' + name)
                    angle = finite(value['jaw_angle_deg'], 'long_hold.jaw_angle_deg')
                    angles.setdefault(tool, angle)
                    max_drift = max(max_drift, abs(angle-angles[tool]))
                    requested_rate = finite(value['post_contact_requested_angle_rate_deg_s'], 'long_hold.requested_rate')
                    actual_rate = finite(value['actual_jaw_angle_rate_deg_s'], 'long_hold.actual_rate')
                    max_rate = max(max_rate, abs(actual_rate))
                    require(value['post_contact_requested_gap_stroke_m']==0 and
                            abs(angle-value['initial_contact_jaw_angle_deg'])<=1e-10 and
                            abs(angle-value['commanded_latch_angle_deg'])<=1e-10,
                            'Holding jaw angle differs from its accepted first-contact mechanical latch')
                    require(abs(requested_rate)<=1e-10 and abs(actual_rate)<=1e-10,
                            'Fixed first-contact angle changed while gripping')
                    if previous is not None and previous['tools'][tool]['grasping'] is True:
                        old=previous['tools'][tool]
                        require(abs(angle-old['jaw_angle_deg'])<=1e-10 and
                                abs(actual_rate-(angle-old['jaw_angle_deg'])/gate['time_step_s'])<=1e-8,
                                'Consecutive held angles/rates do not match fixed mechanical closure')
                        reconstructed_steps += 1
                    min_contacts[tool] = min(contacts) if min_contacts[tool] is None else min(min_contacts[tool], *contacts)
                    grace_samples[tool] += int(min(contacts) == 0 or force <= .00001)
            counts[stage] = counts.get(stage, 0) + 1
            if stage == 'extended_grasp_hold':
                pre_lift = state['vertices']
            elif stage == 'traction':
                last_traction = state['vertices']
            elif stage == 'extended_traction_hold':
                retained_traction = state['vertices']
            if stage in ('extended_grasp_hold', 'extended_traction_hold'):
                times.setdefault(stage, [time, time])[1] = time
            previous = state; state_count += 1
    for stage in ('extended_grasp_hold', 'extended_traction_hold'):
        require(counts.get(stage) == gate['hold_steps_per_stage'], 'Incomplete raw hold stage: ' + name)
        require(abs(times[stage][1]-times[stage][0]+gate['time_step_s']-gate['hold_seconds_per_stage']) < 1e-7,
                'Raw hold duration differs from contract')
    require(counts.get('loaded_retraction', 0) >= 50 and counts.get('release', 0) >= 45,
            'Closed retraction/release missing from long-hold trace')
    require(min_volume > .1 and min_area > .1 and reconstructed_steps >= 2*gate['hold_steps_per_stage'],
            'Long-hold element or mechanical latch coverage failed')
    require(state_count == report['metrics']['samples'], 'Report and raw trace state counts differ')
    require(pre_lift is not None and last_traction is not None and retained_traction is not None,
            'Raw pre-lift/traction geometry missing')
    raw_increment = max(math.dist(a, b) for a, b in zip(pre_lift, last_traction))
    raw_retained_increment = max(math.dist(a, b) for a, b in zip(pre_lift, retained_traction))
    for field, measured in (('traction_increment_from_pre_lift_m', raw_increment),
                            ('retained_traction_increment_from_pre_lift_m', raw_retained_increment)):
        require(abs(measured-report[field]) <= 1e-10 and measured >= report['options']['minimum_traction_increment_m'],
                'Raw geometry does not support meaningful retained traction: ' + name)
    return {'passed': True, 'states': state_count, 'stage_counts': counts,
            'maximum_force_n': max_force, 'maximum_native_node_penetration_m': max_depth,
            'minimum_tet_volume_ratio': min_volume, 'minimum_triangle_area_ratio': min_area,
            'maximum_latched_angle_excursion_deg': max_drift,
            'maximum_latched_angular_rate_deg_s': max_rate,
            'maximum_inner_normal_force_n': max_normal,
            'reconstructed_controller_steps': reconstructed_steps,
            'raw_traction_increment_from_pre_lift_m': raw_increment,
            'raw_retained_traction_increment_from_pre_lift_m': raw_retained_increment,
            'minimum_bilateral_contact_count_per_tested_tool': min_contacts,
            'contact_grace_samples_per_tool': grace_samples,
            'scope': 'Every accepted step: finite geometry/total and bilateral normal forces, native node penetration, healthy state and positive elements; every hold/traction/closed-retraction step retains grip. Adjacent latched states verify the unchanged first-contact jaw angle and zero subsequent closure stroke/rate; no force servo or artificial grasp spring. Every tool state carries a valid continuous rigid-liver admission and positive clearance. Contact-grace samples disclose the unchanged native nine-step loss grace; these checks are not whole-face collision verification.'}


def validate_long_hold(root, path, native_hash, model_config=None, inspect_states=False):
    root = root.resolve(); path = path.resolve(); summary = read(path)
    gate = read(HERE/'acceptance-spec.json')['physics']['long_hold']
    require(summary.get('schema') == 'endoforge.phase6.long-hold.v1', 'Wrong long-hold summary schema')
    passed('long hold', summary)
    require(all(v is True for v in summary['checks'].values()), 'Incomplete long-hold runner checks')
    require(set(summary['cases']) == set(expected_long_hold_cases()), 'All fifteen long-hold cases are mandatory')
    require(summary['native_binary']['sha256'] == native_hash, 'Long-hold native binary mismatch')
    require(summary['runner_sha256'] == sha(root/'Physics/run_phase6_long_hold.py'), 'Long-hold runner changed')
    for name, value in summary['sources_sha256'].items():
        require(sha(root/'Physics'/name) == value, 'Long-hold source changed: ' + name)
    items = {}; raw = {}
    for name in expected_long_hold_cases():
        case = summary['cases'][name]; report_path = Path(case['report']).resolve()
        require(report_path == path.parent/(name+'.json'), 'Long-hold report path mismatch')
        require(case['passed'] is True and case['exit_code'] == 0 and sha(report_path) == case['report_sha256'],
                'Long-hold case failed or changed: ' + name)
        report = read(report_path); passed(name, report)
        require(report['phase'] == 6 and report['case_id'] == name, 'Wrong native long-hold case identity')
        require(all(v is True for v in report['checks'].values()) and case['checks'] == report['checks'],
                'Long-hold case checks differ or fail')
        options_path = path.parent/(name+'-options.json'); options = expected_options(name, gate)
        require(sha(options_path) == case['options_sha256'] and read(options_path) == report['options'] == options,
                'Long-hold options differ from required duration/pose/traction: ' + name)
        require(report['config']['grasp_controller_implementation'] == CONTROLLER, 'Wrong grasp controller')
        for field, value in gate['controller_parameters'].items():
            require(finite(report['config'].get(field), field) == value,
                    'Long-hold controller parameter differs from acceptance contract: ' + field)
        if model_config is not None:
            require(report['config'] == model_config, 'Long hold uses a different physics configuration')
        for stage in ('extended_grasp_hold', 'extended_traction_hold'):
            require(report.get(stage+'_completed_steps') == gate['hold_steps_per_stage'], 'Incomplete hold steps')
            require(0 <= finite(report.get(stage+'_maximum_closure_rate_deg_s'), 'hold.closure_rate') <=
                    gate['controller_parameters']['grasp_post_contact_closure_rate_deg_s']+1e-12,
                    'Latched mechanical latch angular-rate bound failed')
            for suffix in ('_every_step_retained', '_normal_force_finite_nonnegative', '_closure_rate_bounded'):
                require(report['checks'].get(stage+suffix) is True, 'Missing hold check: '+stage+suffix)
        for check in ('extended_traction_deformation_retained', 'grip_retained_during_loaded_retraction',
                      'assembly_matches_sofa_at_every_stage', 'all_states_healthy', 'all_states_finite',
                      'node_penetration_bound', 'valid_positive_elements', 'both_released'):
            require(report['checks'].get(check) is True, 'Missing long-hold check: ' + check)
        for field in ('traction_increment_from_pre_lift_m', 'retained_traction_increment_from_pre_lift_m'):
            require(finite(report.get(field), field) >= options['minimum_traction_increment_m'],
                    'Meaningful long-hold traction was not retained')
        trace = Path(report['trace']).resolve()
        require(trace == path.parent/(name+'-states.jsonl'), 'Wrong long-hold trace path')
        item = evidence(root, report_path); item['trajectory'] = evidence(root, trace)
        item['options_file'] = evidence(root, options_path); item['log'] = evidence(root, path.parent/(name+'.log'))
        item['checks'] = report['checks']; item['options'] = options
        if inspect_states:
            raw[name] = audit_states(trace, name, report, gate)
        items['long-hold-'+name] = item
    return {'summary': evidence(root, path), 'evidence': items, 'raw_state_audits': raw,
            'case_count': len(items), 'hold_seconds_per_case': 2*gate['hold_seconds_per_stage'],
            'independent_geometry_cases': list(REPRESENTATIVE_CASES),
            'geometry_scope': 'Independent whole-face/interpolated contact and closed-liver checks on three nominal long-hold traces plus the separate nine-case operating matrix and endurance trace. The twelve offset traces have every-step native/raw-state checks, not additional independent whole-face geometry audits.'}
