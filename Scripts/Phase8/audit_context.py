"""Conservative finite-path clearance of Phase 8 non-colliding context.

Whole-trace tissue AABBs contain all linear triangle interpolation; actual jaw
OBB circumspheres translated between centers contain every angular orientation,
including the independent Phase4/5 Gram-Schmidt interpolator. Positive envelope
to context-triangle AABB distance proves separation, not exact clearance.
Loose global envelopes are refined to individual intervals. Any unresolved
overlap FAILS, even if independent exact midpoint diagnostics find no contact.
This is not a claim about arbitrary motion, nonlinear native substeps or shafts.
"""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Phase5'))
from audit_phase4_collision_geometry import interpolate_frame, triangle_box_intersection, validate_pose
from audit_liver_contact import pair_intersects, point_triangle_sq, segment_segment_sq
from common import read, require, sha, write_new

CONTEXT_IDS = (300, 301, 310, 311)
HALF = np.array([.00725, .00125, .0007])
DISPLAY_MARGIN_M = .00012
NUMERICAL_MARGIN_M = 1e-8
SIGNS = np.array(list(itertools.product((-1, 1), repeat=3)))
BOX_FACES = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5],
                      [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
                      [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])


def vector_array(value, name):
    result = np.asarray(value, dtype=float)
    require(result.ndim == 2 and result.shape[1] == 3 and len(result) > 0 and np.isfinite(result).all(),
            'Invalid/nonfinite positions: ' + name)
    return result


def aabb_lower_bounds(lo, hi, triangles):
    gap = np.maximum(np.maximum(lo-triangles.max(1), triangles.min(1)-hi), 0)
    return np.linalg.norm(gap, axis=1)


def pair_distances(a, b):
    """Exact finite triangle-pair distance; intersections explicitly return zero."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    result = np.full(len(a), np.inf)
    for k in range(3):
        result = np.minimum(result, point_triangle_sq(a[:, k], b))
        result = np.minimum(result, point_triangle_sq(b[:, k], a))
    for i in range(3):
        for j in range(3):
            result = np.minimum(result, segment_segment_sq(a[:, i], a[:, (i+1) % 3], b[:, j], b[:, (j+1) % 3]))
    result[pair_intersects(a, b, tolerance=NUMERICAL_MARGIN_M)] = 0
    return np.sqrt(np.maximum(result, 0))


def sampled_surface_diagnostic(vertices, faces, context):
    """Exact distance at ONE state, never a continuous-motion pass criterion."""
    moving = np.asarray(vertices, dtype=float)[faces]
    # An arbitrary vertex pair is an upper bound; broad rejection cannot discard
    # the closest pair. Chunk finite exact pairs to bound allocation.
    minimum = float(np.linalg.norm(moving[0, 0]-context[0, 0]))
    count = 0
    for a in moving:
        distance = aabb_lower_bounds(a.min(0), a.max(0), context)
        candidates = np.flatnonzero(distance <= minimum+NUMERICAL_MARGIN_M)
        for group in np.array_split(candidates, max(1, math.ceil(len(candidates)/4096))):
            if not len(group):
                continue
            values = pair_distances(np.broadcast_to(a, (len(group), 3, 3)), context[group])
            minimum = min(minimum, float(values.min()))
            count += len(group)
        if minimum == 0:
            break
    return {'sample_surface_clearance_mm': 1000*minimum, 'exact_triangle_pairs': count,
            'sample_surface_intersection_or_touch': minimum == 0}


def sampled_jaw_diagnostic(pose, context):
    validate_pose(pose)
    center = np.asarray(pose['center_m'])
    axes = np.array([pose[k] for k in ('axis', 'side', 'normal')])
    corners = center + (SIGNS*HALF) @ axes
    # Triangle vs solid OBB also detects context triangles wholly inside jaws.
    local = (context-center) @ axes.T
    overlap = np.all(local.min(1) <= HALF+NUMERICAL_MARGIN_M, axis=1) & np.all(local.max(1) >= -HALF-NUMERICAL_MARGIN_M, axis=1)
    solid_hits = sum(triangle_box_intersection(t.tolist(), (HALF+NUMERICAL_MARGIN_M).tolist()) for t in local[overlap])
    result = sampled_surface_diagnostic(corners, BOX_FACES, context)
    result['context_triangles_intersecting_solid_jaw_at_sample'] = int(solid_hits)
    if solid_hits:
        result['sample_surface_clearance_mm'] = 0.0
    return result


def envelopes(state, other=None):
    states = (state,) if other is None else (state, other)
    vertices = np.concatenate([np.asarray(s['vertices'], dtype=float) for s in states])
    result = [(vertices.min(0)-DISPLAY_MARGIN_M, vertices.max(0)+DISPLAY_MARGIN_M)]
    radius = float(np.linalg.norm(HALF))
    for tool in range(2):
        for jaw in range(2):
            centers = np.array([s['tools'][tool]['jaw_poses'][jaw]['center_m'] for s in states])
            result.append((centers.min(0)-radius, centers.max(0)+radius))
    return result


def records(path):
    with Path(path).open(encoding='utf-8-sig') as stream:
        for index, line in enumerate(stream):
            yield index, json.loads(line)


def audit(presented, scene_path, native_reference, allow_phase6_preflight=False):
    scene_path = Path(scene_path).resolve()
    scene = read(scene_path)
    require(scene.get('phase') == 8, 'Context geometry must be the new Phase 8 scene')
    with Path(native_reference).open(encoding='utf-8-sig') as stream:
        mesh = json.loads(next(stream)); reference = json.loads(next(stream))
    require(mesh.get('type') == 'mesh' and reference.get('protocol') == 5, 'Invalid accepted mechanics reference')
    require(np.max(np.abs(np.asarray(mesh['jaw_half_extents_m'])-HALF)) < 1e-12,
            'Jaw dimensions differ from independently audited actual OBB geometry')
    faces = np.asarray(mesh['triangles'], dtype=int)
    count_vertices = len(mesh['rest_vertices'])
    require(faces.ndim == 2 and faces.shape[1] == 3 and faces.min() >= 0 and faces.max() < count_vertices,
            'Invalid reference topology')
    contexts = {}
    for object_id in CONTEXT_IDS:
        matches = [o for o in scene['static_objects'] if o['id'] == object_id]
        require(len(matches) == 1, 'Missing/duplicated Phase 8 context ID ' + str(object_id))
        obj = matches[0]
        require(obj.get('collision') is False, 'Audited context unexpectedly has collision implementation')
        require('display_mesh' not in obj, 'Context has a separate display mesh not audited by this path')
        v = vector_array(obj['vertices_m'], obj['name'])
        f = np.asarray(obj['triangles'], dtype=int)
        require(f.ndim == 2 and f.shape[1] == 3 and f.min() >= 0 and f.max() < len(v), 'Invalid context faces')
        t = v[f]
        require(np.all(np.linalg.norm(np.cross(t[:, 1]-t[:, 0], t[:, 2]-t[:, 0]), axis=1) > 1e-16),
                'Degenerate context triangle')
        contexts[object_id] = {'name': obj['name'], 'triangles': t}
    entity_names = ['tissue_with_0_12mm_display_envelope', 'tool0_jaw0', 'tool0_jaw1', 'tool1_jaw0', 'tool1_jaw1']
    overall = [(np.full(3, np.inf), np.full(3, -np.inf)) for _ in entity_names]
    count = intervals = resets = 0
    previous = None
    phase_set = set()
    manifest_sha1 = None
    for _, record in records(presented):
        phase_set.add(record.get('phase'))
        if record.get('phase') == 8:
            if manifest_sha1 is None:
                manifest_path=Path(presented).parent/'dataset'/'visual-manifest.json'
                manifest_bytes=manifest_path.read_bytes()
                manifest=json.loads(manifest_bytes.decode('utf-8-sig'))
                require(manifest.get('phase')==8 and manifest.get('mechanics_phase')==6, 'Invalid captured visual manifest identity')
                require(manifest['asset_file_hashes']['scene.json'].lower()==hashlib.sha1(scene_path.read_bytes()).hexdigest(), 'Context scene differs from captured scene')
                require(manifest['physics_fingerprint']==reference['asset_fingerprint'], 'Context reference differs from captured physical asset')
                manifest_sha1=hashlib.sha1(manifest_bytes).hexdigest()
            require(record.get('mechanics_phase')==6 and record.get('visual_manifest_sha1')==manifest_sha1,
                    'Presented record is not bound to the actual Phase 8 scene manifest')
        state = record['native_state']
        require(state.get('protocol') == 5 and state.get('type') == 'state', 'Invalid native state protocol')
        require(state.get('healthy') is True and state.get('safety_stops') == 0, 'Unhealthy recorded simulation')
        require(state['asset_fingerprint'] == reference['asset_fingerprint'] and state['config'] == reference['config'],
                'Presented states do not use accepted reference physics/configuration')
        require(state['triangles'] == mesh['triangles'], 'Presented topology differs from accepted reference')
        require(len(vector_array(state['vertices'], 'physical tissue')) == count_vertices, 'Tissue node count mismatch')
        require(len(state['tools']) == 2 and all(len(t['jaw_poses']) == 2 for t in state['tools']), 'Expected two jaws on each of two tools')
        for tool in state['tools']:
            for jaw in tool['jaw_poses']:
                vector_array([jaw['center_m'], jaw['axis'], jaw['side'], jaw['normal']], 'jaw frame')
                validate_pose(jaw)
        for i, (lo, hi) in enumerate(envelopes(state)):
            overall[i] = (np.minimum(overall[i][0], lo), np.maximum(overall[i][1], hi))
        if previous is not None:
            if state['simulation_id'] != previous['simulation_id'] or state['frame'] < previous['frame']:
                resets += 1
            else:
                intervals += 1
        previous = state
        count += 1
    require(count >= 30, 'At least 30 actual presented states are required')
    require(phase_set == {8} or (allow_phase6_preflight and phase_set == {6}), 'Missing fresh Phase 8 presented-state identity')
    mode = 'phase6_trace_geometry_preflight' if phase_set == {6} else 'fresh_phase8_presented_path'
    results = []
    failed = []
    for object_id, context in contexts.items():
        for entity, (lo, hi) in enumerate(overall):
            lower = float(aabb_lower_bounds(lo, hi, context['triangles']).min())
            item = {'context_id': object_id, 'context_name': context['name'], 'entity': entity_names[entity],
                    'global_envelope_lo_m': lo.tolist(), 'global_envelope_hi_m': hi.tolist(),
                    'clearance_lower_bound_mm': max(0, lower-NUMERICAL_MARGIN_M)*1000,
                    'proof': 'whole_trace_conservative_envelope', 'passed': lower > NUMERICAL_MARGIN_M}
            results.append(item)
            if not item['passed']:
                failed.append((entity, context, item))
    # Exact midpoint samples diagnose overlap; they never certify an interval.
    for entity, context, item in failed:
        previous = None
        unresolved = 0
        lower = math.inf
        diagnostics = []
        for index, record in records(presented):
            current = record['native_state']
            boundary = previous is None or current['simulation_id'] != previous['simulation_id'] or current['frame'] < previous['frame']
            lo, hi = envelopes(current, None if boundary else previous)[entity]
            interval_lower = float(aabb_lower_bounds(lo, hi, context['triangles']).min())
            lower = min(lower, interval_lower)
            if interval_lower <= NUMERICAL_MARGIN_M:
                unresolved += 1
                if len(diagnostics) < 4:
                    vertices, tools = (current['vertices'], current['tools']) if boundary else interpolate_frame(previous, current, .5)
                    diagnostic = sampled_surface_diagnostic(np.asarray(vertices), faces, context['triangles']) if entity == 0 else sampled_jaw_diagnostic(tools[(entity-1)//2]['jaw_poses'][(entity-1) % 2], context['triangles'])
                    diagnostics.append({'record_index': index, 'fraction': 1 if boundary else .5, **diagnostic})
            previous = current
        item.update(proof='per_state_and_interval_conservative_envelopes', unresolved_intervals=unresolved,
                    clearance_lower_bound_mm=max(0, lower-NUMERICAL_MARGIN_M)*1000,
                    diagnostic_samples_only=diagnostics, passed=unresolved == 0)
    dependencies = [Path(__file__).resolve().parents[1]/'audit_phase4_collision_geometry.py',
                    Path(__file__).resolve().parents[1]/'Phase5'/'audit_liver_contact.py']
    return {'schema': 'endoforge.phase8.context_clearance.v1', 'phase': 8, 'mode': mode,
            'presented_path': str(Path(presented).resolve()), 'presented_sha256': sha(presented),
            'visual_manifest_sha1': manifest_sha1,
            'scene_path': str(scene_path), 'scene_sha256': sha(scene_path),
            'physics_mesh_sha256': sha(scene_path.parent/'physics-mesh.json'),
            'native_reference_path': str(Path(native_reference).resolve()), 'native_reference_sha256': sha(native_reference),
            'physics_fingerprint': reference['asset_fingerprint'], 'audit_script_sha256': sha(__file__),
            'dependency_sha256': {str(p.relative_to(Path(__file__).resolve().parents[2])): sha(p) for p in dependencies},
            'recorded_states': count, 'tested_intervals': intervals, 'reset_boundaries': resets,
            'jaw_half_extents_m': HALF.tolist(), 'jaw_circumsphere_radius_m': float(np.linalg.norm(HALF)),
            'tissue_display_envelope_m': DISPLAY_MARGIN_M, 'numeric_margin_m': NUMERICAL_MARGIN_M,
            'context_triangle_counts': {str(k): len(v['triangles']) for k, v in contexts.items()},
            'minimum_proved_clearance_lower_bound_mm': min(r['clearance_lower_bound_mm'] for r in results),
            'assumptions': ['Native positions and center segments are metres. Scene context has identity world transform, independently bound to captured geometry by the dataset auditor.',
                            'Linear tissue interpolation plus 0.12 mm isotropic display envelope assumes separately audited bounded PN binding.',
                            'Actual accepted jaw OBB dimensions and exported orthonormal frames; circumspheres cover every angular orientation, including shared independent Gram-Schmidt interpolation.',
                            'Global envelope also covers reset jumps conservatively; interval refinement does not interpret resets as physical motion.',
                            'No claim about unrecorded nonlinear solver substeps, full instrument shafts/hinges, arbitrary trajectories, decorative-context force response, or clinical validation.'],
            'results': results,
            'checks': {'enough_recorded_states': count >= 30, 'all_context_envelopes_proved_separate': all(r['passed'] for r in results),
                       'fresh_phase8_evidence': mode == 'fresh_phase8_presented_path'},
            'geometry_preflight_passed': all(r['passed'] for r in results),
            'passed': all(r['passed'] for r in results) and mode == 'fresh_phase8_presented_path'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--presented', type=Path, required=True)
    parser.add_argument('--scene', type=Path, required=True)
    parser.add_argument('--native-reference', type=Path, required=True)
    parser.add_argument('--allow-phase6-preflight', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit(args.presented, args.scene, args.native_reference, args.allow_phase6_preflight)
    except (ValueError, KeyError, AssertionError, TypeError, OSError, StopIteration) as error:
        report = {'schema': 'endoforge.phase8.context_clearance.v1', 'passed': False, 'error': str(error), 'audit_script_sha256': sha(__file__)}
    write_new(args.output, report)
    print(json.dumps({k: report[k] for k in ('passed', 'geometry_preflight_passed', 'mode', 'minimum_proved_clearance_lower_bound_mm', 'error') if k in report}))
    raise SystemExit(0 if report.get('passed') or (args.allow_phase6_preflight and report.get('geometry_preflight_passed')) else 1)
