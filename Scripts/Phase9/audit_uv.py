"""Independent periodic material-UV reconstruction for actual Phase9 surfaces.

The source chart is bound to scene.json by the appearance audit. Native material
identities select chart vertices; actual exported barycentric bindings determine
every displayed UV. This audits texture coordinates, not optical calibration.
"""
import hashlib
import json
import math
from pathlib import Path

ALGORITHM = 'periodic_u_triangle_unwrap_pole_mean_v1'


def require(condition, text):
    if not condition:
        raise ValueError('Dynamic UV: '+text)


def vector(value, size):
    require(isinstance(value, list) and len(value) == size and
            all(type(x) in (int, float) and math.isfinite(x) for x in value), 'invalid finite vector')
    return value


def physics_contract(physics_mesh, native=None):
    """Bind source UV size and identity to explicit physical source bytes.

    The runtime expands the authored wall into its native boundary, so its
    deformed positions are not compared with the undeformed middle surface.
    The native fingerprint binds the exact source used for that construction.
    """
    require(physics_mesh is not None, 'an explicit physics-mesh path is required')
    path = Path(physics_mesh).resolve()
    raw = path.read_bytes()
    mesh = json.loads(raw.decode('utf-8-sig'))
    require(mesh.get('schema') == 'endoforge.anatomy-mesh.v1' and mesh.get('units') == 'm',
            'invalid physical source schema/units')
    positions, normals, uvs, faces = (mesh.get(key) for key in ('vertices_m', 'normals', 'uvs', 'triangles'))
    require(isinstance(positions, list) and len(positions) >= 3 and
            isinstance(normals, list) and isinstance(uvs, list) and
            len(positions) == len(normals) == len(uvs), 'physical vertex/normal/UV counts differ')
    for p, n, uv in zip(positions, normals, uvs):
        vector(p, 3); vector(n, 3); vector(uv, 2)
        require(abs(math.sqrt(sum(x*x for x in n))-1) < 1e-5, 'invalid authored physical normal')
        require(all(0 <= x <= 1 for x in uv), 'physical UV outside normalized chart')
    require(isinstance(faces, list) and faces, 'missing physical source faces')
    seen = set()
    for face in faces:
        require(isinstance(face, list) and len(face) == len(set(face)) == 3 and
                all(type(i) is int and 0 <= i < len(positions) for i in face), 'invalid physical source triangle')
        support = tuple(sorted(face))
        require(support not in seen, 'duplicated physical source triangle')
        seen.add(support)
        a, b, c = (positions[i] for i in face)
        ab, ac = ([b[k]-a[k] for k in range(3)], [c[k]-a[k] for k in range(3)])
        cross = [ab[1]*ac[2]-ab[2]*ac[1], ab[2]*ac[0]-ab[0]*ac[2], ab[0]*ac[1]-ab[1]*ac[0]]
        require(sum(x*x for x in cross) > 0, 'degenerate physical source triangle')
    fingerprint = 14695981039346656037
    for byte in raw:
        fingerprint = ((fingerprint ^ byte)*1099511628211) & 0xffffffffffffffff
    fingerprint = f'fnv1a64:{fingerprint:016x}'
    require(isinstance(mesh.get('model_id'), str) and mesh['model_id'] and 'version' in mesh,
            'missing physical model identity')
    if native is not None:
        require(native.get('asset_fingerprint') == fingerprint, 'native state does not use the explicit physical source bytes')
        require(native.get('model_id') == mesh['model_id'] and str(native.get('model_version')) == str(mesh['version']),
                'native/source model identity differs')
    return mesh, {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                  'sha1': hashlib.sha1(raw).hexdigest(), 'asset_fingerprint': fingerprint,
                  'model_id': mesh['model_id'], 'model_version': mesh['version'],
                  'source_vertices': len(positions), 'source_triangles': len(faces), 'source_uv_count': len(uvs)}


def audit_source(source, authored_uvs=None, physics_mesh=None):
    require(isinstance(source, dict) and source.get('schema') == 'endoforge.phase7.dynamic_uv_source.v1', 'missing authored source chart')
    require(source.get('algorithm') == ALGORITHM, 'incorrect interpolation convention')
    require('material_node_ids modulo' in source.get('source_convention', '') and
            '1-v' in source.get('source_convention', ''), 'missing native mapping or vertical flip convention')
    require('TA_Wrap' in source.get('texture_address_u', ''), 'unwrapped U requires a repeating texture sampler')
    uvs = source.get('uvs')
    require(isinstance(uvs, list) and len(uvs) >= 3, 'missing original material chart')
    for uv in uvs:
        require(all(0 <= x <= 1 for x in vector(uv, 2)), 'source coordinates outside normalized chart')
    if physics_mesh is not None:
        mesh, _ = physics_contract(physics_mesh)
        require(len(uvs) == len(mesh['uvs']) and
                max(abs(a-b) for p,q in zip(uvs,mesh['uvs']) for a,b in zip(p,q)) < 1e-12,
                'recorded source chart differs from the explicit physical source')
    if authored_uvs is not None:
        require(isinstance(authored_uvs,list), 'invalid authored chart')
        for uv in authored_uvs:
            vector(uv,2)
        require(len(authored_uvs) == len(uvs) and
                max(abs(a-b) for p,q in zip(uvs, authored_uvs) for a,b in zip(p,q)) < 1e-12,
                'recorded source chart differs from hash-bound authored scene')
    return uvs


def triangle_uvs(corners):
    """Cut the circular chart in its largest empty arc, independently of UE.

    Pole U is undefined geometrically. Exclude it while selecting the circular
    interval, then assign the mean of the two adjacent unwrapped coordinates.
    """
    poles = [abs(p[1]) <= 1e-8 or abs(p[1]-1) <= 1e-8 for p in corners]
    require(sum(poles) <= 1, 'unexpected triangle with multiple spherical poles')
    ordered = sorted(set(p[0] for p,pole in zip(corners,poles) if not pole))
    gaps = [(ordered[(i+1) % len(ordered)] + (1 if i+1 == len(ordered) else 0)-u, i)
            for i,u in enumerate(ordered)]
    _, gap_index = max(gaps)
    first = ordered[(gap_index+1) % len(ordered)]
    unwrapped = [p[0]+(1 if p[0] < first-1e-12 else 0) for p in corners]
    for i, pole in enumerate(poles):
        if pole:
            unwrapped[i] = sum(unwrapped[j] for j in range(3) if j != i)/2
    return [[u,1-p[1]] for u,p in zip(unwrapped,corners)]


def audit_dynamic_uv(obj, native, source, snapshot_bindings=None, physics_mesh=None):
    _, contract = physics_contract(physics_mesh, native)
    chart = audit_source(source, physics_mesh=physics_mesh)
    require(obj.get('object_id') == 100 and obj.get('dynamic_uv_algorithm') == ALGORITHM, 'wrong actual dynamic surface/convention')
    bindings, actual = obj.get('render_bindings'), obj.get('uvs')
    positions = obj['vertices_cm']
    require(isinstance(bindings,list) and isinstance(actual,list) and len(bindings) == len(actual) == len(positions) > 0,
            'actual UV/binding/position counts differ')
    if snapshot_bindings is not None:
        require(len(snapshot_bindings) == len(bindings), 'snapshot/geometry binding counts differ')
    ids = native['material_node_ids']
    nodes = native['vertices']
    require(len(ids) == len(nodes) and all(type(i) is int and i >= 0 for i in ids), 'invalid native material identities')
    for node in nodes:
        vector(node,3)
    require(all(isinstance(face,list) and len(face)==3 and len(set(face))==3 and
                all(type(i) is int and 0 <= i < len(nodes) for i in face) for face in native['triangles']),
            'invalid native triangle topology')
    native_faces = {tuple(sorted(face)) for face in native['triangles']}
    cache, supports = {}, []
    error = offset = 0.0
    seam_samples = pole_samples = 0
    for i,(binding, uv, actual_position) in enumerate(zip(bindings, actual, positions)):
        vector(binding,6); vector(uv,2); vector(actual_position,3)
        face, weights = binding[:3], binding[3:]
        require(all(type(j) is int and 0 <= j < len(nodes) for j in face), 'invalid native binding node')
        key = tuple(face); support = tuple(sorted(face))
        require(support in native_faces, 'UV binding bridges a nonexistent physical face')
        require(min(weights) >= -1e-7 and max(weights) <= 1+1e-7 and abs(sum(weights)-1) < 1e-6, 'invalid barycentric coordinates')
        if snapshot_bindings is not None:
            old = snapshot_bindings[i]
            require(old['nodes'] == face and max(abs(a-b) for a,b in zip(old['weights'],weights)) < 1e-12,
                    'geometry UV binding differs from independently checked snapshot geometry binding')
        if key not in cache:
            original = [chart[ids[j] % len(chart)] for j in face]
            cache[key] = (triangle_uvs(original), max(p[0] for p in original)-min(p[0] for p in original) > .5,
                          any(abs(p[1]) <= 1e-8 or abs(p[1]-1) <= 1e-8 for p in original))
        mapped, seam, pole = cache[key]
        expected = [sum(p[k]*w for p,w in zip(mapped,weights)) for k in range(2)]
        # Strict branch equality matters: independently wrapped per-vertex U
        # would introduce a new interpolation discontinuity inside a triangle.
        error = max(error,max(abs(a-b) for a,b in zip(uv,expected)))
        linear = [sum(nodes[j][k]*100*w for j,w in zip(face,weights)) for k in range(3)]
        offset = max(offset,math.sqrt(sum((a-b)**2 for a,b in zip(actual_position,linear))))
        supports.append(support)
        seam_samples += seam; pole_samples += pole
    require(error <= 1e-5, 'displayed UV differs from periodic source reconstruction: '+str(error))
    require(offset <= .01201, 'UV binding is detached from its native physical triangle envelope')
    faces = obj['triangles']
    require(len(faces) % 3 == 0 and all(type(i) is int and 0 <= i < len(bindings) for i in faces), 'invalid display topology')
    require(all(len({supports[i] for i in faces[k:k+3]}) == 1 for k in range(0,len(faces),3)), 'display triangle crosses material charts')
    return {'passed':True,'algorithm':ALGORITHM,'source_uv_count':len(chart),'actual_uv_count':len(actual),
            'native_face_charts':len(cache),'seam_chart_samples':seam_samples,'pole_chart_samples':pole_samples,
            'maximum_uv_coordinate_error':error,'maximum_binding_envelope_offset_mm':offset*10,
            'source_chart_checked_against_authored_asset':True,'physical_source':contract,
            'scope':'Actual UV reconstructed from native material identities and per-vertex bindings; chart and native identity bind the explicit physical source bytes. No optical calibration claim.'}
