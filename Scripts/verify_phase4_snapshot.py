"""Independent geometry/projection audit for Phase 4 UE state snapshots.

Uses only the Python standard library. The native mesh is reconstructed through
the exported bindings and projected independently of Unreal's projection call.
This checks snapshot consistency, not biological accuracy or pixel segmentation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct


def require(condition, message):
    if not condition:
        raise ValueError(message)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def vector(value, length, name):
    require(isinstance(value, list) and len(value) == length and all(finite(x) for x in value), name)
    return value


def integer(value, name, minimum=0):
    require(isinstance(value, int) and not isinstance(value, bool) and value >= minimum, name)
    return value


def distance(a, b):
    return math.sqrt(sum((x-y)**2 for x, y in zip(a, b)))


def audit_snapshot(path: Path, pixel_tolerance=1.0, position_tolerance_cm=0.001, expected_phase=4):
    raw = path.read_bytes()
    data = json.loads(raw.decode('utf-8-sig'))
    require(expected_phase in (4, 5) and data.get('phase') == expected_phase, f'Snapshot must identify phase {expected_phase}')
    native = data['native_state']
    require(native.get('protocol') == expected_phase and native.get('type') == 'state', f'Expected accepted native protocol {expected_phase} state')
    require(native.get('healthy') is True and native.get('safety_stops') == 0, 'Snapshot contains an unhealthy/protected simulation')
    if expected_phase==5:
        manifest=(path.parent/data['visual_manifest']).resolve()
        require(manifest.is_relative_to(path.parent.resolve()), 'Visual manifest path escapes snapshot directory')
        require(hashlib.sha1(manifest.read_bytes()).hexdigest()==data['visual_manifest_sha1'].lower(), 'Visual manifest digest mismatch')
        visual=json.loads(manifest.read_text(encoding='utf-8-sig'))
        require(visual['physics_fingerprint']==native['asset_fingerprint'], 'Visual/physical identity mismatch')
        objects=data['scene_geometry']['objects']
        require(len({o['object_id'] for o in objects})==len(objects), 'Repeated scene object identity')
        bridges=[o for o in objects if o['name']=='hepatic_attachment_visual_membrane']
        require(len(bridges)==1, 'Missing or duplicated hepatic attachment display')
        actual=bridges[0]['vertices_cm']
        expected=[[100*x for x in p] for segment in native['attachment_segments_m'] for p in segment]
        require(len(actual)==len(expected) and max(distance(a,b) for a,b in zip(actual,expected))<1e-5, 'Visual attachment differs from actual physical spring endpoints')
    for key in ('state_id', 'simulation_id', 'frame', 'reset_id', 'topology_revision'):
        integer(native[key], 'Invalid native ' + key)
    require(finite(native['time']) and native['time'] >= 0, 'Invalid simulation time')
    vertices = native['vertices']
    require(isinstance(vertices, list) and 3 <= len(vertices) <= 10000, 'Invalid physical node count')
    for p in vertices:
        vector(p, 3, 'Invalid physical vertex')
    for key in ('node_ids', 'material_node_ids'):
        require(isinstance(native[key], list) and len(native[key]) == len(vertices), 'Identity count mismatch: ' + key)
        for value in native[key]:
            integer(value, 'Invalid identity: ' + key)
    require(len(set(native['node_ids'])) == len(vertices), 'Duplicate node instance IDs')
    if 'parent_node_ids' in native:
        require(len(native['parent_node_ids']) == len(vertices), 'Parent identity count mismatch')
        for value in native['parent_node_ids']:
            integer(value, 'Invalid parent identity', minimum=-1)
    faces = native['triangles']
    require(isinstance(faces, list) and len(faces) > 0, 'Missing physical topology')
    face_set = set()
    for face in faces:
        require(isinstance(face, list) and len(face) == 3, 'Invalid physical triangle')
        for i in face:
            integer(i, 'Invalid physical triangle index')
            require(i < len(vertices), 'Physical triangle index out of range')
        require(len(set(face)) == 3, 'Degenerate physical triangle indices')
        face_set.add(tuple(sorted(face)))
    rendered = data['render_vertices_cm']
    bindings = data['render_bindings']
    require(isinstance(rendered, list) and len(rendered) >= 3 and len(bindings) == len(rendered), 'Render/binding count mismatch')
    reconstructed = []
    max_offset = 0.0
    for actual, binding in zip(rendered, bindings):
        vector(actual, 3, 'Invalid actual rendered vertex')
        nodes = binding['nodes']
        weights = vector(binding['weights'], 3, 'Invalid binding weights')
        require(isinstance(nodes, list) and len(nodes) == 3, 'Invalid binding node indices')
        for i in nodes:
            integer(i, 'Invalid binding node')
            require(i < len(vertices), 'Binding node out of range')
        require(tuple(sorted(nodes)) in face_set, 'Binding bridges a non-existent physical triangle')
        require(abs(sum(weights)-1) <= 1e-5 and min(weights) >= -1e-6 and max(weights) <= 1+1e-6, 'Invalid barycentric coordinates')
        expected = [100*sum(vertices[nodes[k]][axis]*weights[k] for k in range(3)) for axis in range(3)]
        reconstructed.append(expected)
        max_offset = max(max_offset, distance(expected, actual))
    require(max_offset <= position_tolerance_cm, f'Render binding mismatch: {max_offset} cm')
    render_faces = data['render_triangles']
    require(isinstance(render_faces, list) and len(render_faces) >= 3 and len(render_faces) % 3 == 0, 'Invalid render index array')
    for index in render_faces:
        integer(index, 'Invalid render triangle index')
        require(index < len(rendered), 'Render index out of range')
    for start in range(0, len(render_faces), 3):
        # Each subdivided triangle belongs to one physical boundary face. It
        # must not stitch disconnected material fans together after a cut.
        support = {tuple(sorted(bindings[i]['nodes'])) for i in render_faces[start:start+3]}
        require(len(support) == 1, 'Rendered triangle bridges distinct physical faces')
    camera = data['camera']
    viewport = vector(camera['viewport'], 2, 'Invalid viewport')
    require(all(x > 0 and x == int(x) for x in viewport), 'Invalid viewport dimensions')
    rect = vector(camera.get('view_rect', [0, 0, *viewport]), 4, 'Invalid view rectangle')
    require(0 <= rect[0] < rect[2] <= viewport[0] and 0 <= rect[1] < rect[3] <= viewport[1], 'View rectangle outside viewport')
    matrix = camera['view_projection_matrix']
    require(isinstance(matrix, list) and len(matrix) == 4, 'Invalid projection matrix')
    for row in matrix:
        vector(row, 4, 'Invalid projection matrix row')
    camera_position = vector(camera['position_cm'], 3, 'Invalid camera position')
    axes = [vector(camera[k], 3, 'Invalid camera ' + k) for k in ('forward', 'right', 'up')]
    for i, axis in enumerate(axes):
        require(abs(sum(x*x for x in axis)-1) <= 1e-4, 'Camera basis is not normalized')
        for other in axes[:i]:
            require(abs(sum(x*y for x, y in zip(axis, other))) <= 1e-4, 'Camera basis is not orthogonal')
    intrinsics = None
    if 'horizontal_fov_deg' in camera:
        fov = camera['horizontal_fov_deg']
        require(finite(fov) and 0 < fov < 180, 'Invalid horizontal camera FOV')
        intrinsics = [camera[k] for k in ('fx_px', 'fy_px', 'cx_px', 'cy_px')]
        require(all(finite(v) for v in intrinsics) and min(intrinsics[:2]) > 0, 'Invalid camera intrinsics')
        expected_focal = (rect[2]-rect[0])/(2*math.tan(math.radians(fov/2)))
        require(abs(intrinsics[0]-expected_focal) <= 1e-3, 'Camera focal length disagrees with FOV')
    samples = data['projected_samples']
    require(isinstance(samples, list) and len(samples) >= 16, 'At least 16 independent projection samples required')
    seen = set()
    max_pixel_error = 0.0
    max_camera_model_error = 0.0
    visible_samples = 0
    for sample in samples:
        index = integer(sample['render_index'], 'Invalid sample index')
        require(index < len(rendered) and index not in seen, 'Repeated/out-of-range projection sample')
        seen.add(index)
        pixel = vector(sample['pixel'], 2, 'Invalid UE projected pixel')
        point = reconstructed[index] + [1.0]
        clip = [sum(point[row]*matrix[row][column] for row in range(4)) for column in range(4)]
        require(clip[3] > 1e-9, 'Projection sample is behind camera')
        expected = [rect[0] + (1+clip[0]/clip[3])*.5*(rect[2]-rect[0]),
                    rect[1] + (1-clip[1]/clip[3])*.5*(rect[3]-rect[1])]
        max_pixel_error = max(max_pixel_error, distance(expected, pixel))
        visible_samples += rect[0] <= pixel[0] < rect[2] and rect[1] <= pixel[1] < rect[3]
        if intrinsics:
            relative = [reconstructed[index][i]-camera_position[i] for i in range(3)]
            forward, right, up = [sum(a*b for a, b in zip(relative, axis)) for axis in axes]
            require(forward > 1e-9, 'Camera basis places a sample behind the camera')
            fx, fy, cx, cy = intrinsics
            model_pixel = [cx+fx*right/forward, cy-fy*up/forward]
            max_camera_model_error = max(max_camera_model_error, distance(model_pixel, pixel))
    require(max_pixel_error <= pixel_tolerance, f'Independent projection error: {max_pixel_error} pixels')
    require(max_camera_model_error <= pixel_tolerance, f'Camera metadata projection error: {max_camera_model_error} pixels')
    require(visible_samples >= 16, 'At least 16 projection samples must be visible in the captured image')
    screenshot_name = data.get('screenshot') or data.get('screenshot_file')
    screenshot_info = None
    if screenshot_name:
        screenshot = (path.parent / screenshot_name).resolve()
        require(screenshot.is_relative_to(path.parent.resolve()), 'Screenshot path escapes snapshot directory')
        contents = screenshot.read_bytes()
        require(contents[:8] == b'\x89PNG\r\n\x1a\n' and contents[12:16] == b'IHDR', 'Screenshot is not a PNG')
        dimensions = list(struct.unpack('>II', contents[16:24]))
        require(dimensions == viewport, 'Screenshot size differs from captured viewport')
        if 'screenshot_size' in data:
            require(data['screenshot_size'] == dimensions, 'Screenshot callback size differs from PNG')
        screenshot_info = {'file': screenshot.name, 'sha256': hashlib.sha256(contents).hexdigest(), 'dimensions': dimensions}
    return {'file': path.name, 'passed': True, 'snapshot_sha256': hashlib.sha256(raw).hexdigest(),
            'state_id': native['state_id'], 'simulation_id': native['simulation_id'],
            'topology_revision': native['topology_revision'], 'specimen': native['specimen'],
            'render_vertices': len(rendered), 'projection_samples': len(samples),
            'max_binding_offset_cm': max_offset, 'max_projection_error_px': max_pixel_error,
            'visible_projection_samples': visible_samples, 'max_camera_model_error_px': max_camera_model_error,
            'screenshot': screenshot_info}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshots', nargs='+', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--phase', type=int, choices=(4,5), default=4)
    args = parser.parse_args()
    results = []
    for path in args.snapshots:
        try:
            results.append(audit_snapshot(path,expected_phase=args.phase))
        except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
            results.append({'file': str(path), 'passed': False, 'error': str(error)})
    report = {'phase': args.phase, 'kind': 'independent snapshot geometry and projection audit',
              'passed': bool(results) and all(r['passed'] for r in results), 'snapshots': results,
              'pixel_tolerance': 1.0, 'position_tolerance_cm': 0.001}
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    print(text)
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
