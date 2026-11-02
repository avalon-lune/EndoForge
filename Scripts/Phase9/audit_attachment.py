"""Independently verify the recorded attachment ribbon against native springs.

This is a bounded display surface, not an additional physical membrane. Boundary
identity is derived from native triangle incidence. The complete triangle surface
is checked against the original ruled patches, including crossings of their
diagonal; vertex-only displacement checks are insufficient for nonplanar patches.
"""
import collections
import hashlib
import json
import math
from audit_uv import physics_contract


def require(ok, message):
    if not ok:
        raise ValueError('Attachment: '+message)


def vec(value, size, name):
    require(isinstance(value, list) and len(value) == size and
            all(type(x) in (int, float) and math.isfinite(x) for x in value), name)
    return value


def integer(value, name):
    require(type(value) is int and value >= 0, name)
    return value


def norm(v):
    return math.sqrt(sum(x*x for x in v))


def distance(a, b):
    return norm([x-y for x, y in zip(a, b)])


def combine(points, weights):
    return [sum(p[k]*w for p, w in zip(points, weights)) for k in range(3)]


def curve(points, t):
    # Hermite basis with central-difference tangents, independently expressed
    # from the renderer's expanded polynomial.
    p0, p1, p2, p3 = points
    tangents = [[(p2[k]-p0[k])/2 for k in range(3)],
                [(p3[k]-p1[k])/2 for k in range(3)]]
    return combine([p1, tangents[0], p2, tangents[1]],
                   [2*t**3-3*t*t+1, t**3-2*t*t+t, -2*t**3+3*t*t, t**3-t*t])


def ruled(corners, u, v, direction=1):
    a, b, c, d = corners
    if direction == -1:
        return combine([a, b, d], [1-u-v, u, v]) if u+v <= 1 else combine([b, c, d], [1-v, u+v-1, 1-u])
    return combine([a, b, c], [1-u, u-v, v]) if v <= u else combine([a, c, d], [1-v, u, v-u])


def complete_triangle_offset(corners, coordinates, positions, direction):
    """Exact maximum correspondence error over an affine display triangle."""
    maximum = max(distance(p, ruled(corners, *uv, direction)) for uv, p in zip(coordinates, positions))
    local = [(uv[0], uv[1], p) for uv, p in zip(coordinates, positions)]
    for a, b in zip(local, local[1:]+local[:1]):
        da, db = ((a[0]-a[1], b[0]-b[1]) if direction == 1 else
                  (a[0]+a[1]-1, b[0]+b[1]-1))
        if da*db < 0:
            t = da/(da-db)
            u, v = ((1-t)*a[k]+t*b[k] for k in (0, 1))
            displayed = combine([a[2], b[2]], [1-t, t])
            maximum = max(maximum, distance(displayed, ruled(corners, u, v, direction)))
    return maximum


def audit_attachment(obj, native, tolerance_cm=1e-5, physics_mesh=None):
    source, physical_source = physics_contract(physics_mesh, native)
    require(obj.get('object_id') == 500 and obj.get('name') == 'hepatic_attachment_visual_membrane',
            'wrong geometry identity')
    binding = obj.get('attachment_visual_binding', {})
    require(binding.get('schema') == 'endoforge.phase7.attachment_visual.v1', 'missing bounded ribbon binding')
    ids = native['attachment_vertex_ids']
    source_ids = source.get('attachment_vertex_ids')
    anchors = source.get('attachment_anchor_positions_m')
    weights = source.get('attachment_vertex_weights')
    require(isinstance(source_ids, list) and source_ids and isinstance(anchors, list) and
            isinstance(weights, list) and len(source_ids) == len(anchors) == len(weights),
            'explicit physical source spring identity/anchor/weight counts differ')
    require(ids == source_ids and len(set(ids)) == len(ids), 'native spring identities differ from the explicit physical source')
    for value in ids:
        integer(value, 'invalid native spring identity')
        require(value < len(source['vertices_m']), 'source spring identity is outside its material surface')
    for weight in weights:
        require(type(weight) in (int,float) and math.isfinite(weight) and weight > 0, 'invalid physical source spring weight')
    require(abs(sum(weights)-31) < 1e-12, 'authored spring weights must preserve the total weight 31')
    native_weights = native.get('attachment_vertex_weights')
    if native_weights is not None:
        require(isinstance(native_weights, list) and len(native_weights) == len(weights) and
                all(type(a) in (int,float) and math.isfinite(a) and abs(a-b) < 1e-12 for a,b in zip(native_weights,weights)),
                'reported native spring weights differ from the explicit physical source')
    segments = native['attachment_segments_m']
    require(len(segments) == len(ids) and all(isinstance(x, list) and len(x) == 2 for x in segments), 'native spring count')
    endpoints = [[100*x for x in vec(p, 3, 'native endpoint')] for pair in segments for p in pair]
    for index, anchor in enumerate(anchors):
        require(distance(endpoints[2*index+1], [100*x for x in vec(anchor, 3, 'physical source anchor')]) <= tolerance_cm,
                'native spring anchor differs from the explicit physical source')
    material_ids = native['material_node_ids']
    native_vertices = native['vertices']
    require(len(material_ids) == len(native_vertices), 'native material identities')
    by_id = {}
    for i, material_id in enumerate(material_ids):
        if material_id in ids:
            require(material_id not in by_id, 'split attachment node is outside this uncut scope')
            by_id[material_id] = i
    require(set(by_id) == set(ids), 'native attachment node missing')
    for i, material_id in enumerate(ids):
        require(distance(endpoints[2*i], [100*x for x in native_vertices[by_id[material_id]]]) <= tolerance_cm,
                'native spring tip differs from native material node')
    incidence = collections.Counter()
    for face in native['triangles']:
        if all(material_ids[i] in by_id for i in face):
            f = [material_ids[i] for i in face]
            for a, b in zip(f, f[1:]+f[:1]):
                incidence[tuple(sorted((a, b)))] += 1
    require(incidence and max(incidence.values()) <= 2, 'native patch is not manifold')
    boundary = {e for e, count in incidence.items() if count == 1}
    loop = binding.get('closed_boundary_material_ids')
    require(isinstance(loop, list) and len(loop) == len(boundary) and len(set(loop)) == len(loop) and set(loop) <= set(ids), 'boundary identity count')
    loop_edges = {tuple(sorted((loop[i], loop[(i+1) % len(loop)]))) for i in range(len(loop))}
    require(loop_edges == boundary, 'recorded loop differs from native patch boundary')
    # The frozen Phase6/7 source stores each original edge in ascending material
    # identity order. Derive that orientation independently, rather than allowing
    # an exported loop to silently substitute the other diagonal of a warped quad.
    original_edges = binding.get('original_boundary_edges')
    require(isinstance(original_edges, list) and len(original_edges) == len(boundary) and
            all(isinstance(e, list) and len(e) == 2 and type(e[0]) is int and type(e[1]) is int for e in original_edges)
            and {tuple(e) for e in original_edges} == boundary, 'original canonical boundary edges differ')
    directions = [1 if loop[i] < loop[(i+1) % len(loop)] else -1 for i in range(len(loop))]
    require(binding.get('original_edge_directions') == directions, 'original ruled-patch diagonal changed')
    require(binding.get('native_endpoint_prefix_count') == len(endpoints), 'endpoint prefix length')
    along, span = binding.get('along_subdivisions'), binding.get('span_subdivisions')
    require(type(along) is int and along == 6 and type(span) is int and span == 6, 'unexpected ribbon resolution')
    maximum = binding.get('max_offset_cm')
    require(type(maximum) in (int, float) and math.isfinite(maximum) and abs(maximum-.012) < 1e-12, 'offset envelope must be 0.12 mm')
    vertices, uv = obj['vertices_cm'], obj['uvs']
    vb = binding['vertex_bindings']
    columns, rows = len(loop)*along, span+1
    expected_count = len(endpoints)+(columns+1)*rows-2*len(loop)
    require(len(vertices) == len(uv) == len(vb) == expected_count, 'ribbon vertex/binding/UV count')
    for p in vertices:
        vec(p, 3, 'nonfinite display point')
    for p in uv:
        vec(p, 2, 'nonfinite display UV')
    index = {material_id: i for i, material_id in enumerate(ids)}
    points = [[endpoints[2*index[node]+side] for node in loop] for side in (0, 1)]
    mids = [combine([points[0][i], points[1][i]], [.5, .5]) for i in range(len(loop))]
    chord = [distance(mids[i], mids[(i+1) % len(loop)]) for i in range(len(loop))]
    total = sum(chord)
    require(total > 1e-8, 'collapsed native boundary')
    cumulative = [sum(chord[:i]) for i in range(len(loop)+1)]
    grid, params = {}, {}
    max_vertex_offset = max_reconstruction = 0.0
    for i, (actual, info) in enumerate(zip(vertices, vb)):
        vec(info, 3, 'invalid vertex binding')
        if i < len(endpoints):
            require(info == [-1, i//2, i % 2], 'native endpoint binding reordered')
            require(distance(actual, endpoints[i]) <= tolerance_cm, 'native endpoint moved')
            material_id = ids[i//2]
            if material_id not in loop:
                continue
            col, row = loop.index(material_id)*along, (i % 2)*span
        else:
            edge, u, v = info
            require(edge == int(edge) and 0 <= edge < len(loop) and 0 <= u <= 1 and 0 <= v <= 1, 'invalid parameter domain')
            col, row = int(edge)*along+round(u*along), round(v*span)
            require(abs(col-(edge*along+u*along)) < 1e-5 and abs(row-v*span) < 1e-5, 'off-grid binding')
            require(col == columns or u < 1, 'duplicate edge-end parameterization')
        require((col, row) not in grid and 0 <= col <= columns and 0 <= row <= span, 'repeated/out-of-range grid slot')
        grid[col, row] = i
        edge = min(col//along, len(loop)-1)
        u, v = ((col-edge*along)/along, row/span)
        params[i] = (edge, u, v)
        corners = [points[0][edge], points[0][(edge+1) % len(loop)], points[1][(edge+1) % len(loop)], points[1][edge]]
        base = ruled(corners, u, v, directions[edge])
        curves = [curve([side[(edge+delta) % len(loop)] for delta in (-1, 0, 1, 2)], u) for side in points]
        raw = combine(curves, [1-v, v])
        delta = [raw[k]-base[k] for k in range(3)]
        scale = min(1, maximum/norm(delta)) if norm(delta) else 1
        reconstructed = [base[k]+delta[k]*scale for k in range(3)]
        max_reconstruction = max(max_reconstruction, distance(actual, reconstructed))
        max_vertex_offset = max(max_vertex_offset, distance(actual, base))
        target_uv = [(cumulative[edge]+u*chord[edge])/total, v]
        require(distance(uv[i], target_uv) <= 1e-5, 'incorrect continuous arc-length UV')
    require(len(grid) == (columns+1)*rows, 'missing grid slot')
    require(max_reconstruction <= tolerance_cm, 'display surface is not reconstructed from native endpoints')
    require(max_vertex_offset <= maximum+tolerance_cm, 'vertex leaves ruled-surface envelope')
    measured = binding.get('measured_max_offset_cm')
    require(type(measured) in (int, float) and math.isfinite(measured) and abs(measured-max_vertex_offset) <= tolerance_cm, 'incorrect measured offset')
    faces = obj['triangles']
    patches = binding['triangle_patch_indices']
    require(len(faces) == columns*span*6 and len(patches)*3 == len(faces), 'triangle count')
    require(all(type(i) is int and 0 <= i < len(vertices) for i in faces) and
            all(type(i) is int and 0 <= i < len(loop) for i in patches), 'invalid triangle indices')
    expected_faces, expected_patches = [], []
    for col in range(columns):
        for row in range(span):
            a, b, c, d = [grid[x] for x in ((col, row), (col+1, row), (col+1, row+1), (col, row+1))]
            expected_faces.extend((a, c, b, a, d, c) if directions[col//along] == 1 else (a, d, b, b, d, c))
            expected_patches.extend((col//along, col//along))
    require(faces == expected_faces and patches == expected_patches, 'incorrect topology, winding or patch identity')
    seam = [[grid[0, row], grid[columns, row]] for row in range(rows)]
    require(binding.get('seam_vertex_pairs') == seam, 'wrong closed UV seam')
    require(all(distance(vertices[a], vertices[b]) <= tolerance_cm for a, b in seam), 'open geometric seam')
    # On either side of the original diagonal (u=v or u+v=1), both mappings are
    # affine. A convex norm attains its maximum on the clipped polygon vertices.
    # Thus checking triangle vertices AND its diagonal intersections certifies
    # every point on the displayed triangle, rather than sparse surface samples.
    max_surface_offset = max_vertex_offset
    for start in range(0, len(faces), 3):
        patch = patches[start//3]
        corners = [points[0][patch], points[0][(patch+1) % len(loop)], points[1][(patch+1) % len(loop)], points[1][patch]]
        tri = faces[start:start+3]
        a, b, c = [vertices[i] for i in tri]
        ab, ac = ([b[k]-a[k] for k in range(3)], [c[k]-a[k] for k in range(3)])
        cross = [ab[1]*ac[2]-ab[2]*ac[1], ab[2]*ac[0]-ab[0]*ac[2], ab[0]*ac[1]-ab[1]*ac[0]]
        require(norm(cross) > 1e-12, 'degenerate actual displayed triangle')
        local = []
        for vertex in tri:
            edge, u, v = params[vertex]
            # At a shared column, use this face's patch coordinate.
            u = u+(edge-patch)
            if patch == len(loop)-1 and edge == 0:
                u += len(loop)
            require(-1e-7 <= u <= 1+1e-7, 'triangle crosses distinct native ruled patches')
            local.append((u, v, vertices[vertex]))
        max_surface_offset = max(max_surface_offset,
            complete_triangle_offset(corners, [x[:2] for x in local], [x[2] for x in local], directions[patch]))
    require(max_surface_offset <= maximum+tolerance_cm, 'triangle interior leaves original ruled-surface envelope')
    return {'passed': True, 'native_spring_pairs': len(ids), 'boundary_edges': len(loop),
            'vertices': len(vertices), 'triangles': len(faces)//3,
            'maximum_reconstruction_error_mm': max_reconstruction*10,
            'maximum_vertex_offset_mm': max_vertex_offset*10,
            'maximum_complete_triangle_offset_mm': max_surface_offset*10,
            'original_patch_diagonals_independently_verified': True,
            'bound_mm': maximum*10,
            'physical_source':physical_source,'source_spring_weight_sum':sum(weights),
            'source_spring_weights_sha256':hashlib.sha256(json.dumps(weights,separators=(',',':')).encode('utf8')).hexdigest(),
            'source_spring_ids_anchors_and_weights_bound':True,
            'native_individual_weights_reported_and_compared':native_weights is not None,
            'weight_identity_scope':'Exact source bytes are bound by the native asset fingerprint; individual runtime weights are compared only if the state actually reports them. Geometry audit does not qualify spring-force application.',
            'scope': 'Explicit physical-source spring identity/anchors/weight bytes, continuous closed ribbon and complete triangle envelope; original reconstruction and offset thresholds retained. No membrane FEM, spring-force qualification or added collision claim.'}
