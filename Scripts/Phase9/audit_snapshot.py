"""Independent cubic PN geometry/projection audit for Phase 9 UE snapshots.

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
from audit_appearance import audit_appearance, audit_manifest
from audit_uv import audit_dynamic_uv, physics_contract
from audit_attachment import audit_attachment

ATTACHMENT_AUDITOR = Path(__file__).with_name('audit_attachment.py').resolve()


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


def area_weighted_normals(vertices, faces):
    accum = [[0.0, 0.0, 0.0] for _ in vertices]
    for a, b, c in faces:
        u = [vertices[b][i]-vertices[a][i] for i in range(3)]
        v = [vertices[c][i]-vertices[a][i] for i in range(3)]
        cross = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
        for node in (a, b, c):
            for axis in range(3):
                accum[node][axis] += cross[axis]
    result = []
    for n in accum:
        length = math.sqrt(sum(x*x for x in n))
        require(length > 1e-16, 'Physical boundary has undefined vertex normal')
        result.append([x/length for x in n])
    return result


def pn_position(points, normals, weights, maximum_cm):
    """Evaluate ten Bernstein control points independently from recorded nodes.

    Node normals are rebuilt from native boundary topology. No exported shading
    normal or UE-calculated expected position is trusted by this reconstruction.
    """
    control = {(3, 0, 0): points[0], (0, 3, 0): points[1], (0, 0, 3): points[2]}
    edge_points = []
    for i in range(3):
        for j in range(3):
            if i == j:
                continue
            dot = sum((points[j][k]-points[i][k])*normals[i][k] for k in range(3))
            point = [(2*points[i][k]+points[j][k]-dot*normals[i][k])/3 for k in range(3)]
            powers = [0, 0, 0]; powers[i] = 2; powers[j] = 1
            control[tuple(powers)] = point
            edge_points.append(point)
    control[(1, 1, 1)] = [1.5*sum(p[k] for p in edge_points)/6 -
                          .5*sum(p[k] for p in points)/3 for k in range(3)]
    pn = [0.0, 0.0, 0.0]
    for powers, point in control.items():
        coefficient = 6
        for power, weight in zip(powers, weights):
            coefficient *= weight**power/math.factorial(power)
        for axis in range(3):
            pn[axis] += coefficient*point[axis]
    linear = [sum(points[i][axis]*weights[i] for i in range(3)) for axis in range(3)]
    offset = [pn[i]-linear[i] for i in range(3)]
    length = math.sqrt(sum(x*x for x in offset))
    scale = maximum_cm*math.tanh(length/maximum_cm)/length if length else 1.0
    return [linear[i]+offset[i]*scale for i in range(3)], linear


def audit_welded_surface(positions, triangles, bindings, shading_normals, physical_faces,
                         position_tolerance_cm=0.0001):
    """Rebuild S8 support welding from identities, never spatial proximity.

    Each triangle's area vector comes from actual displayed positions. Normals
    accumulate through the same material point even across duplicated UV seams;
    disconnected physical identities never share a group. No position smoothing
    is performed or inferred by this check.
    """
    require(isinstance(shading_normals, list) and len(shading_normals) == len(positions),
            'Missing actual displayed shading normals')
    groups, keys, face_samples = {}, [], {}
    for index, binding in enumerate(bindings):
        nodes, weights = binding['nodes'], binding['weights']
        lattice = [int(math.floor(weight*8+.5)) for weight in weights]
        require(all(abs(weight*8-value) <= 1e-6 for weight,value in zip(weights,lattice)) and
                all(0 <= value <= 8 for value in lattice) and sum(lattice) == 8,
                'Actual displayed binding is not on its declared S8 barycentric lattice')
        key = tuple(sorted((node, weight) for node,weight in zip(nodes,lattice) if weight))
        require(key, 'Empty material support')
        keys.append(key)
        groups.setdefault(key, []).append(index)
        face = tuple(sorted(nodes))
        face_samples.setdefault(face, []).append(key)
        vector(shading_normals[index], 3, 'Invalid actual shading normal')
    physical_supports = {tuple(sorted(face)) for face in physical_faces}
    require(set(face_samples) == physical_supports, 'Displayed S8 support omits a physical boundary face')
    require(all(len(samples) == len(set(samples)) == 45 for samples in face_samples.values()),
            'A physical face lacks its complete 45 distinct S8 material samples')
    sums = {key: [0.0, 0.0, 0.0] for key in groups}
    face_triangles = {}
    for start in range(0, len(triangles), 3):
        a, b, c = triangles[start:start+3]
        face = tuple(sorted(bindings[a]['nodes']))
        require(all(tuple(sorted(bindings[i]['nodes'])) == face for i in (b,c)),
                'Displayed microtriangle crosses physical source faces')
        face_triangles[face] = face_triangles.get(face, 0)+1
        ab = [positions[b][k]-positions[a][k] for k in range(3)]
        ac = [positions[c][k]-positions[a][k] for k in range(3)]
        # UE render winding is reversed relative to the physical outward face.
        normal = [ac[1]*ab[2]-ac[2]*ab[1], ac[2]*ab[0]-ac[0]*ab[2], ac[0]*ab[1]-ac[1]*ab[0]]
        require(sum(x*x for x in normal) > 0, 'Degenerate actual displayed microtriangle')
        for index in (a,b,c):
            accumulator = sums[keys[index]]
            for axis in range(3):
                accumulator[axis] += normal[axis]
    require(set(face_triangles) == physical_supports and all(n == 64 for n in face_triangles.values()),
            'A physical face lacks its complete 64 S8 display triangles')
    maximum_position_gap = maximum_normal_gap = maximum_normal_error = 0.0
    shared = seam_samples = 0
    for key, indices in groups.items():
        normal = sums[key]
        length = math.sqrt(sum(x*x for x in normal))
        require(length > 1e-16, 'Welded displayed surface has an undefined area-weighted normal')
        expected = [x/length for x in normal]
        first = indices[0]
        if len(indices) > 1:
            shared += 1
            seam_samples += len(indices)
        for index in indices:
            maximum_position_gap = max(maximum_position_gap, distance(positions[first], positions[index]))
            maximum_normal_gap = max(maximum_normal_gap, distance(shading_normals[first], shading_normals[index]))
            maximum_normal_error = max(maximum_normal_error, distance(expected, shading_normals[index]))
    require(shared > 0, 'No shared-edge material samples were available for seam checks')
    require(maximum_position_gap <= position_tolerance_cm, 'Displayed physical-face seam has a positional gap')
    require(maximum_normal_gap <= 1e-5, 'Displayed physical-face seam has a shading-normal discontinuity')
    require(maximum_normal_error <= 1e-5, 'Shading normals differ from welded area-weighted actual microtriangles')
    return {'passed': True, 'subdivision': 8, 'weld_key': 'native-node-index plus integer barycentric weight at S8',
            'weld_groups': len(groups), 'shared_seam_groups': shared, 'shared_seam_samples': seam_samples,
            'maximum_seam_position_gap_cm': maximum_position_gap, 'maximum_seam_normal_vector_gap': maximum_normal_gap,
            'maximum_area_weighted_normal_vector_error': maximum_normal_error, 'normal_vector_tolerance': 1e-5,
            'normal_source': 'outward area vectors of actual displayed microtriangles; no normal-map input',
            'position_smoothing_applied': False}


def audit_dynamic_surface_geometry(obj, native, physics_mesh, position_tolerance_cm=0.0001):
    """Audit an actual exported dynamic object, reusable by stereo validation.

    Return evidence and independently reconstructed positions in centimetres.
    The physical state and explicit mesh bytes are authoritative. Exported
    expected positions, normals and precomputed error metrics are never inputs.
    """
    _, physical_source = physics_contract(physics_mesh, native)
    require(obj.get('object_id') == 100, 'Wrong actual dynamic object identity')
    vertices, faces = native['vertices'], native['triangles']
    require(isinstance(vertices, list) and 3 <= len(vertices) <= 10000, 'Invalid physical node count')
    for vertex in vertices:
        vector(vertex, 3, 'Invalid physical position')
    require(isinstance(faces, list) and faces, 'Missing physical boundary faces')
    supports = set()
    for face in faces:
        require(isinstance(face, list) and len(face) == len(set(face)) == 3 and
                all(type(i) is int and 0 <= i < len(vertices) for i in face), 'Invalid physical boundary face')
        supports.add(tuple(sorted(face)))
    require(len(supports) == len(faces), 'Repeated physical boundary face')
    positions, flat_bindings, triangles = (obj.get(name) for name in ('vertices_cm', 'render_bindings', 'triangles'))
    require(isinstance(positions, list) and isinstance(flat_bindings, list) and
            len(positions) == len(flat_bindings) >= 3, 'Actual geometry/binding counts differ')
    require(isinstance(triangles, list) and len(triangles) >= 3 and len(triangles) % 3 == 0 and
            all(type(i) is int and 0 <= i < len(positions) for i in triangles), 'Invalid actual display topology')
    normals = area_weighted_normals(vertices, faces)
    bindings, reconstructed = [], []
    maximum_error = maximum_linear_offset = 0.0
    cap_cm = .012
    for actual, flat in zip(positions, flat_bindings):
        vector(actual, 3, 'Invalid actual display position')
        vector(flat, 6, 'Invalid actual native-node/barycentric binding')
        nodes, weights = flat[:3], flat[3:]
        require(all(type(i) is int and 0 <= i < len(vertices) for i in nodes) and
                tuple(sorted(nodes)) in supports, 'Actual binding does not use one physical boundary face')
        require(abs(sum(weights)-1) <= 1e-5 and min(weights) >= -1e-6 and max(weights) <= 1+1e-6,
                'Invalid actual barycentric coordinates')
        expected, linear = pn_position([[100*x for x in vertices[node]] for node in nodes],
            [normals[node] for node in nodes], weights, cap_cm)
        maximum_error = max(maximum_error, distance(expected, actual))
        maximum_linear_offset = max(maximum_linear_offset, distance(linear, actual))
        reconstructed.append(expected)
        bindings.append({'nodes': nodes, 'weights': weights})
    require(maximum_error <= position_tolerance_cm, 'Independent smooth bounded PN reconstruction differs from actual display')
    require(maximum_linear_offset <= cap_cm+1e-5, 'Actual display leaves its 0.12 mm physical-triangle envelope')
    seam_evidence = audit_welded_surface(positions, triangles, bindings,
        obj.get('shading_vertex_normals'), faces, position_tolerance_cm)
    return {'passed': True, 'binding_method': 'smooth_bounded_pn_triangle_v1',
            'max_offset_mm': .12, 'render_vertices': len(positions), 'render_triangles': len(triangles)//3,
            'maximum_reconstruction_error_cm': maximum_error,
            'maximum_linear_surface_offset_mm': maximum_linear_offset*10,
            'seams_and_displayed_normals': seam_evidence, 'physical_source': physical_source}, reconstructed


def audit_snapshot(path: Path, pixel_tolerance=1.0, position_tolerance_cm=0.0001, expected_phase=9, physics_mesh=None, asset_dir=None):
    raw = path.read_bytes()
    data = json.loads(raw.decode('utf-8-sig'))
    require(expected_phase == 9 and data.get('phase') == 9, 'Snapshot must identify phase 9')
    require(data.get('mechanics_phase') == 6, 'Snapshot must identify its compatible solver generation')
    native = data['native_state']
    require(native.get('protocol') == 5 and native.get('type') == 'state', 'Expected compatible accepted native protocol 5 state')
    require(native.get('healthy') is True and native.get('safety_stops') == 0, 'Snapshot contains an unhealthy/protected simulation')
    _, physical_source = physics_contract(physics_mesh, native)
    if expected_phase==9:
        manifest=(path.parent/data['visual_manifest']).resolve()
        require(manifest.is_relative_to(path.parent.resolve()), 'Visual manifest path escapes snapshot directory')
        require(hashlib.sha1(manifest.read_bytes()).hexdigest()==data['visual_manifest_sha1'].lower(), 'Visual manifest digest mismatch')
        visual=json.loads(manifest.read_text(encoding='utf-8-sig'))
        _, appearance_evidence = audit_manifest(manifest, asset_dir)
        audit_appearance(data.get('appearance'), visual.get('appearance'))
        require(visual['physics_fingerprint']==native['asset_fingerprint'], 'Visual/physical identity mismatch')
        require(visual['asset_file_hashes']['physics-mesh.json'].lower() == physical_source['sha1'],
                'Snapshot manifest does not bind the explicit physical source bytes')
        objects=data['scene_geometry']['objects']
        require(len({o['object_id'] for o in objects})==len(objects), 'Repeated scene object identity')
        bridges=[o for o in objects if o['name']=='hepatic_attachment_visual_membrane']
        require(len(bridges)==1, 'Missing or duplicated hepatic attachment display')
        attachment_evidence=audit_attachment(bridges[0], native, physics_mesh=physics_mesh)
        dynamic=[o for o in objects if o['object_id']==100]
        require(len(dynamic)==1, 'Missing or duplicated actual dynamic geometry')
        uv_evidence=audit_dynamic_uv(dynamic[0],native,visual['dynamic_uv_source'],data['render_bindings'], physics_mesh)
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
    require(data.get('binding_method') == 'smooth_bounded_pn_triangle_v1', 'Phase9 smooth cubic binding method must be explicit')
    maximum_mm = data.get('max_offset_mm')
    require(finite(maximum_mm) and maximum_mm == .12, 'Phase9 visual/physical offset cap must be 0.12 mm')
    normals = area_weighted_normals(vertices, faces)
    reconstructed = []
    max_linear_offset = 0.0
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
        points = [[100*x for x in vertices[node]] for node in nodes]
        expected, linear = pn_position(points, [normals[node] for node in nodes], weights, maximum_mm/10)
        max_linear_offset = max(max_linear_offset, distance(linear, actual))
        reconstructed.append(expected)
        max_offset = max(max_offset, distance(expected, actual))
    require(max_offset <= position_tolerance_cm, f'Render binding mismatch: {max_offset} cm')
    require(max_linear_offset <= maximum_mm/10 + 1e-5, 'Rendered surface exceeds declared physical offset envelope')
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
    geometry_positions = dynamic[0]['vertices_cm']
    require(len(geometry_positions) == len(rendered) and dynamic[0]['triangles'] == render_faces,
            'Actual scene geometry differs from the independently reconstructed snapshot surface')
    require(max(distance(vector(p, 3, 'Invalid dynamic scene vertex'), actual)
                for p,actual in zip(geometry_positions,rendered)) <= position_tolerance_cm,
            'Snapshot top-level and actual scene positions differ')
    dynamic_evidence, _ = audit_dynamic_surface_geometry(dynamic[0], native, physics_mesh, position_tolerance_cm)
    seam_evidence = dynamic_evidence['seams_and_displayed_normals']
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
            'binding_method': 'smooth_bounded_pn_triangle_v1', 'max_linear_surface_offset_mm': max_linear_offset*10,
            'max_independent_pn_reconstruction_error_mm': max_offset*10,
            'visible_projection_samples': visible_samples, 'max_camera_model_error_px': max_camera_model_error,
            'appearance': appearance_evidence, 'attachment_geometry': attachment_evidence, 'dynamic_uv': uv_evidence,
            'displayed_surface_seams_and_normals': seam_evidence, 'physical_source': physical_source, 'mechanics_phase': 6,
            'screenshot': screenshot_info}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshots', nargs='+', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--phase', type=int, choices=(9,), default=9)
    parser.add_argument('--physics-mesh', type=Path, required=True)
    parser.add_argument('--assets', type=Path,
        help='Optional exact captured asset tree for scene/texture byte verification; the explicit physical mesh is always verified')
    args = parser.parse_args()
    results = []
    for path in args.snapshots:
        try:
            results.append(audit_snapshot(path,expected_phase=args.phase,physics_mesh=args.physics_mesh,asset_dir=args.assets))
        except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
            results.append({'file': str(path), 'passed': False, 'error': str(error)})
    report = {'schema': 'endoforge.phase9.snapshot-audit.v1',
              'phase': args.phase, 'kind': 'independent snapshot geometry and projection audit',
              'passed': bool(results) and all(r['passed'] for r in results), 'snapshots': results,
              'pixel_tolerance': 1.0, 'position_tolerance_cm': 0.0001,
              'asset_byte_verification_requested': args.assets is not None,
              'scope': 'Independent physical binding, UV, displayed normals, seams and camera projection. Captured manifest/settings are checked; scene/texture bytes are rechecked only when an exact --assets tree is provided. The explicit --physics-mesh bytes are always bound to the native state and manifest.',
              'audit_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    report['appearance_audit_script_sha256'] = hashlib.sha256(Path(__file__).with_name('audit_appearance.py').read_bytes()).hexdigest()
    report['attachment_audit_script_sha256'] = hashlib.sha256(ATTACHMENT_AUDITOR.read_bytes()).hexdigest()
    report['attachment_audit_script_path'] = str(ATTACHMENT_AUDITOR)
    report['uv_audit_script_sha256'] = hashlib.sha256(Path(__file__).with_name('audit_uv.py').read_bytes()).hexdigest()
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(text)
    print(text)
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
