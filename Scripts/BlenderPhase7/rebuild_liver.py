"""Continuous original macro-liver and smooth constrained hepatic-bed authoring.

The inherited equator switched nonzero upper corrections off abruptly. This
revision uses smooth Cartesian angular terms and a C2 quintic hemisphere window.
It revises the actual closed collision surface; GB FEM and anchor positions are
retained. Full physical qualification is mandatory for every resulting identity.
"""
import importlib.util
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def physical_bytes(physical):
    """Frozen Phase 7 format: compact JSON plus one explicit Windows CRLF.

    Explicit termination reproduces the qualified byte identity across Python
    text/newline settings; geometry and numbers are not rounded or reordered.
    """
    return (json.dumps(physical, separators=(',', ':')) + '\r\n').encode('utf8')


def smooth01(t):
    t = np.clip(t, 0, 1)
    return t*t*t*(t*(t*6-15)+10)


def continuous_liver(theta, phi):
    s = math.sin(theta); c = math.cos(theta)
    ux = s * math.cos(phi); uy = s * math.sin(phi)
    x = .010 + .104 * ux
    y = .052 + .079 * uy * (1 - .17 * ux)
    negative_x = .5 * (math.sqrt(ux*ux + .02**2) - ux)
    negative_y = .5 * (math.sqrt(uy*uy + .02**2) - uy)
    z = -.018 + .040 * c * (1 - .23 * negative_x) - .007 * negative_y * s*s
    upper = float(smooth01(max(c, 0) / .40))
    bed = math.exp(-((x - .002) / .024) ** 2 - ((y - .012) / .035) ** 2)
    harmonic = (3 * ux * ux * uy - uy ** 3) * math.cos(.4) + (ux ** 3 - 3 * ux * uy * uy) * math.sin(.4)
    z += upper * (-.006 * bed + .0024 * harmonic)
    return [x, y, z]


def macro_mesh(rings=40, sides=96):
    assert rings % 2 == 0
    spec = importlib.util.spec_from_file_location('original_phase5_author', ROOT / 'Scripts/BlenderPhase5/build_assets.py')
    author = importlib.util.module_from_spec(spec); spec.loader.exec_module(author)
    vertices, faces, uvs = author.radial_mesh(continuous_liver, rings=rings, sides=sides)
    equator_start = 1 + (rings//2 - 1) * sides
    equator = list(range(equator_start, equator_start + sides))
    f = np.asarray(faces)
    top_faces = f[np.all(f < equator_start + sides, axis=1)]
    bottom_faces = f[np.all(f >= equator_start, axis=1)]
    return {'vertices_m': vertices, 'triangles': faces, 'uvs': uvs,
            'top_triangles': top_faces.tolist(), 'bottom_triangles': bottom_faces.tolist(), 'equator': equator,
            'parameterization': 'Continuous asymmetric analytic ellipsoid/wedge; quintic upper window and Cartesian third-order harmonic; no jump at equator.'}


def build(physical, extra_coordinates=None, refine=True):
    import copy
    from mathutils import Vector
    from mathutils.geometry import delaunay_2d_cdt
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    import smooth_bed
    import bed_field
    from geometry_metrics import geometric_angles

    original = copy.deepcopy(physical)
    physical = copy.deepcopy(physical)
    model = macro_mesh()
    mv = np.asarray(model['vertices_m']); equator = model['equator']
    # Keep the original parameter-space triangulation of the steep outer
    # hemisphere. XY Delaunay there creates skinny radial slivers and false
    # dihedral corners even when every vertex samples a smooth surface.
    cap_start = 1 + (14 - 1) * 96
    cap_boundary = list(range(cap_start, cap_start + 96))
    anchors = np.asarray(physical['attachment_anchor_positions_m'])
    evaluate, field, field_metadata = bed_field.make_field(original)
    top_count = max(equator) + 1
    cap_count = max(cap_boundary) + 1
    coordinates = [tuple(x) for x in mv[:cap_count, :2]]
    polygon = smooth_bed.hull(mv[cap_boundary, :2])
    # A denser local bed discretizes the smooth coordinate field; it is not a
    # second independently displaced render surface.
    for y in np.arange(-.037, .051, .002):
        for x in np.arange(-.033, .035, .002):
            xy = np.asarray([[x, y]])
            if smooth_bed.hull_distance(xy, polygon)[0] < 1e-12:
                coordinates.append((round(float(x), 9), round(float(y), 9)))
    for y in np.arange(.003, .0351, .001):
        for x in np.arange(-.019, .0251, .001):
            coordinates.append((round(float(x), 9), round(float(y), 9)))
    for y in np.arange(.008, .0226, .0005):
        for x in np.arange(-.012, .0161, .0005):
            coordinates.append((round(float(x), 9), round(float(y), 9)))
    coordinates.extend(extra_coordinates or [])
    anchor_inputs = []
    for point in anchors:
        anchor_inputs.append(len(coordinates)); coordinates.append(tuple(point[:2]))
    constraints = list(zip(cap_boundary, cap_boundary[1:] + cap_boundary[:1]))
    coords, _, triangles, original_ids, _, _ = delaunay_2d_cdt([Vector(x) for x in coordinates], constraints, [], 0, 1e-9, True)
    xy = np.asarray([tuple(x) for x in coords]); height = evaluate(xy)
    p = np.column_stack([xy, height]).tolist(); f = []
    input_to_output = {}
    for i, ids in enumerate(original_ids):
        for source in ids: input_to_output[source] = i
    # Exact common equator coordinates sew both hemispheres and avoid float32
    # triangulator rounding becoming a crack in the physical surface.
    for source in cap_boundary: p[input_to_output[source]][:2] = mv[source, :2].tolist()
    for source, anchor in zip(anchor_inputs, anchors): p[input_to_output[source]] = anchor.tolist()
    for face in triangles:
        t = np.asarray(p)[face]
        f.append(list(face) if np.cross(t[1] - t[0], t[2] - t[0])[2] > 0 else list(face)[::-1])
    old_to_new = {source: input_to_output[source] for source in cap_boundary}
    for source in range(cap_count, top_count):
        old_to_new[source] = len(p)
        point = mv[source].copy()
        if source not in equator: point[2] = evaluate(point[None, :2])[0]
        p.append(point.tolist())
    for face in model['top_triangles']:
        if all(source >= cap_start for source in face): f.append([old_to_new[source] for source in face])
    for source in range(top_count, len(mv)):
        old_to_new[source] = len(p); p.append(mv[source].tolist())
    for face in model['bottom_triangles']: f.append([old_to_new[source] for source in face])
    bindings = []
    for source in anchor_inputs:
        index = input_to_output[source]
        tid = next(i for i, face in enumerate(f) if index in face)
        bary = [0., 0., 0.]; bary[f[tid].index(index)] = 1.
        bindings.append({'triangle_id': tid, 'barycentric': bary})
    before = geometric_angles(physical['static_liver']['vertices_m'], physical['static_liver']['triangles'])
    physical['static_liver'] = {'vertices_m': p, 'triangles': f}
    physical['attachment_anchor_bindings'] = bindings
    physical['phase7_liver_revision'] = {'construction': 'Continuous analytic macroform and exact 31-anchor bed; posterior operative field uses a regularized cubic radial fit to accepted height samples, with smooth broad blending and local conforming refinement. Closed matching lower surface.',
                                        'source_asset_version': physical['version'], 'macro_rings': 40, 'macro_sides': 96,
                                        'local_grid_spacing_m': .002, 'collar_width_m': .024,
                                        'fixed_anchor_count': 31, 'clinical_review': 'pending',
                                        'posterior_field': field_metadata,
                                        'local_transition_spacing_m': .001, 'neck_spacing_m': .0005,
                                        'adaptive_added_vertices': len(extra_coordinates or []),
                                        'ready_recipe': 'Original Phase 6 recipe retained; clearance guard unchanged.'}
    pp = np.asarray(p); ff = np.asarray(f)
    report = {'schema': 'endoforge.phase7.continuous-liver-rebuild.v1', 'before': before,
              'after': geometric_angles(p, f), 'anchor_count': len(anchors),
              'max_anchor_field_residual_m': float(np.max(abs(evaluate(anchors[:, :2]) - anchors[:, 2]))),
              'anchor_matrix_condition': field.condition, 'anchor_positions_unchanged': physical['attachment_anchor_positions_m'] == anchors.tolist(),
              'full_physical_requalification_required': True,
              'signed_liver_volume_m3': float(np.einsum('ij,ij->i', pp[ff[:, 0]], np.cross(pp[ff[:, 1]], pp[ff[:, 2]])).sum() / 6)}
    if refine:
        normals = np.cross(pp[ff[:, 1]] - pp[ff[:, 0]], pp[ff[:, 2]] - pp[ff[:, 0]])
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-15)
        edges = {}
        for index, face in enumerate(ff):
            for a, b in zip(face, np.roll(face, -1)):
                edges.setdefault(tuple(sorted((int(a), int(b)))), []).append(index)
        additions = []
        for edge, adjacent in edges.items():
            if len(adjacent) != 2: continue
            angle = np.degrees(np.arccos(np.clip(np.dot(normals[adjacent[0]], normals[adjacent[1]]), -1, 1)))
            if angle > 28 and np.linalg.norm(pp[edge[0]] - pp[edge[1]]) > .00005:
                additions.append(tuple(np.round(pp[list(edge), :2].mean(0), 9)))
                for face_id in adjacent:
                    additions.append(tuple(np.round(pp[ff[face_id], :2].mean(0), 9)))
        if additions:
            # One targeted conforming pass samples the same field, rather than
            # displacing vertices or changing contact geometry independently.
            return build(original, list(dict.fromkeys(additions)), refine=False)
    return physical, report


if __name__ == '__main__':
    import sys
    path = ROOT / 'tmp/phase7/asset-review/liver-candidates/continuous-macro.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    model = macro_mesh()
    path.write_text(json.dumps(model, separators=(',', ':')) + '\n', encoding='utf8')
    print('CONTINUOUS_MACRO', len(model['vertices_m']), len(model['triangles']), path, flush=True)
    if '--candidate' in sys.argv:
        physical, report = build(json.loads((ROOT / 'Assets/Phase6/physics-mesh.json').read_text()))
        (path.parent / 'phase7-liver-final.json').write_bytes(physical_bytes(physical))
        (path.parent / 'phase7-liver-final-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
        print('CONTINUOUS_BED', json.dumps(report['after']), flush=True)
