"""Read-only UE editor validation of actual Phase 6 imported render buffers.

Run after generate_assets.py. Never substitutes FBX-payload checks for UE import
checks: actual LOD0 vertices, triangle soup, UVs and normals are inspected here.
"""
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
import unreal

ROOT=Path(__file__).resolve().parents[3]
ASSET=ROOT/'Assets'/'Phase6'
OUT=ROOT/'tmp'/'phase6'/'ue-static-asset-verification.json'
TOL=.0002  # cm = 2 micrometres, well below the 0.12mm visual binding allowance.
GRID=.0001


def xyz(v):return (float(v.x),float(v.y),float(v.z))
def key(p):return tuple(round(v/GRID) for v in p)
def norm(p):return math.sqrt(sum(v*v for v in p))
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    scene=json.loads((ASSET/'scene.json').read_text(encoding='utf8'))
    items=[]
    subsystem=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    for obj in scene['static_objects']:
        geometry=obj.get('display_mesh',obj)
        expected=[tuple(x*100 for x in p) for p in geometry['vertices_m']]
        buckets=defaultdict(list)
        for i,p in enumerate(expected):buckets[key(p)].append(i)
        mesh=unreal.EditorAssetLibrary.load_asset(obj['static_mesh_asset'])
        if not isinstance(mesh,unreal.StaticMesh):raise RuntimeError('Missing static mesh '+obj['static_mesh_asset'])
        positions=[];triangles=[];normals=[];uvs=[]
        for section in range(mesh.get_num_sections(0)):
            p,t,n,uv,tan=unreal.ProceduralMeshLibrary.get_section_from_static_mesh(mesh,0,section)
            first=len(positions);positions.extend(xyz(v) for v in p)
            triangles.extend(first+int(i) for i in t);normals.extend(xyz(v) for v in n)
            uvs.extend((float(v.x),float(v.y)) for v in uv)
        assert positions and len(triangles)%3==0
        mapping=[];error=0.;uv_error=0.;normal_min=1.;missing=0
        for i,p in enumerate(positions):
            pk=key(p);candidates=list(buckets.get(pk,[]))
            if not candidates:
                for dx in (-1,0,1):
                    for dy in (-1,0,1):
                        for dz in (-1,0,1):candidates+=buckets.get((pk[0]+dx,pk[1]+dy,pk[2]+dz),[])
            candidates=[j for j in candidates if norm(sub(p,expected[j]))<=TOL]
            if not candidates:
                missing+=1;mapping.append(None);continue
            chosen=min(candidates,key=lambda j:norm(sub(p,expected[j])))
            error=max(error,norm(sub(p,expected[chosen])));mapping.append(key(expected[chosen]))
            def uv_distance(j):
                u,v=geometry['uvs'][j];du=uvs[i][0]-u;du-=round(du)
                return max(abs(du),abs(uvs[i][1]-(1-v)))
            uv_error=max(uv_error,min(uv_distance(j) for j in candidates))
            if 'normals' in geometry:
                corresponding=[j for j in candidates if uv_distance(j)<.00005]
                if corresponding:
                    normal_min=min(normal_min,max(dot(normals[i],geometry['normals'][j]) / max(norm(normals[i])*norm(geometry['normals'][j]),1e-15) for j in corresponding))
                else:normal_min=-1
        expected_soup=Counter(tuple(sorted(key(expected[i]) for i in face)) for face in geometry['triangles'])
        actual_soup=Counter();clockwise=0;finite=True
        for j in range(0,len(triangles),3):
            ids=triangles[j:j+3]
            if all(mapping[i] is not None for i in ids):actual_soup[tuple(sorted(mapping[i] for i in ids))]+=1
            a,b,c=[positions[i] for i in ids];gn=cross(sub(b,a),sub(c,a));sn=tuple(sum(normals[i][axis] for i in ids) for axis in range(3))
            clockwise+=dot(gn,sn)<0
        for p in positions+normals:finite &= all(math.isfinite(v) for v in p)
        build=subsystem.get_lod_build_settings(mesh,0)
        nanite=mesh.get_editor_property('nanite_settings').get_editor_property('enabled')
        checks={'actual_lod0_position_correspondence':missing==0 and error<=TOL,
                'actual_lod0_triangle_soup_exact':actual_soup==expected_soup,
                'uv_v_flip_matches_runtime_material':missing==0 and uv_error<.00005,
                'pn_custom_normals_match':missing==0 and normal_min>.998,
                'finite_positions_and_normals':finite,
                'ray_tracing_supported':bool(mesh.get_editor_property('support_ray_tracing')),
                'lumen_cards_requested':build.get_editor_property('max_lumen_mesh_cards')>=32,
                'high_precision_tangents':bool(build.get_editor_property('use_high_precision_tangent_basis')),
                'nanite_disabled_for_exact_lod0':not nanite}
        items.append({'id':obj['id'],'asset':obj['static_mesh_asset'],'passed':all(checks.values()),'checks':checks,
                      'render_vertices':len(positions),'render_triangles':len(triangles)//3,
                      'coordinate_max_error_cm':error,'missing_correspondences':missing,
                      'uv_max_error':uv_error,'minimum_pn_shading_normal_dot':normal_min,
                      'ue_clockwise_triangle_fraction':clockwise/(len(triangles)//3),
                      'bounds_cm':[[min(p[a] for p in positions),max(p[a] for p in positions)] for a in range(3)],
                      'lumen_note':'Build-setting request only; actual Lumen cards/RT scene participation require packaged runtime evidence.'})
    result={'schema':'endoforge.phase6.ue-static-assets.v1','passed':all(o['passed'] for o in items),
            'scene_sha256':sha(ASSET/'scene.json'),'objects':items,
            'coordinate_tolerance_cm':TOL,'material_uv_convention':'FBX importer flips V; UE uses matching 1-V UV plus green-channel inversion for Blender normal textures.'}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(result,indent=2),encoding='utf8')
    unreal.log('LAP_PHASE6_STATIC_VERIFY '+json.dumps({'passed':result['passed'],'objects':len(items),'report':str(OUT)}))
    if not result['passed']:raise RuntimeError('Imported Phase 6 geometry/material convention failed; see '+str(OUT))


main()
