"""Independent deterministic Phase 6 geometry/binding/texture audit.

Run with Blender so FBX binary arrays can be checked without importing a scene.
Does not change scene.json, textures, meshes or the .blend source.
"""
import hashlib
import json
import struct
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from io_scene_fbx import parse_fbx

ROOT=Path(__file__).resolve().parents[2]
ASSET=ROOT/'Assets'/'Phase6'
if '--asset-dir' in sys.argv:ASSET=Path(sys.argv[sys.argv.index('--asset-dir')+1]).resolve()


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def topology(geo):
    p=np.asarray(geo['vertices_m']);t=np.asarray(geo['triangles'],dtype=int)
    # PN pieces intentionally duplicate UV seam vertices. Audit manifoldness
    # after a 1e-9m weld rather than calling every patch boundary a hole.
    _,ids=np.unique(np.round(p,9),axis=0,return_inverse=True)
    tw=ids[t];edges=np.concatenate([tw[:,[0,1]],tw[:,[1,2]],tw[:,[2,0]]]);edges.sort(axis=1)
    _,counts=np.unique(edges,axis=0,return_counts=True)
    area=np.linalg.norm(np.cross(p[t[:,1]]-p[t[:,0]],p[t[:,2]]-p[t[:,0]]),axis=1)*.5
    return {'vertices':len(p),'triangles':len(t),'welded_vertices':int(ids.max()+1),
            'boundary_edges_after_weld':int(np.sum(counts==1)),
            'nonmanifold_edges_after_weld':int(np.sum(counts>2)),
            'degenerate_triangles':int(np.sum(area<1e-14)),
            'finite':bool(np.isfinite(p).all()),'minimum_area_m2':float(area.min())}


def binding(display,source):
    p=np.asarray(display['vertices_m']);b=np.asarray(display['barycentrics']);ids=np.asarray(display['source_triangle_ids'],dtype=int)
    sp=np.asarray(source['vertices_m']);st=np.asarray(source['triangles'],dtype=int)
    linear=np.einsum('ni,nij->nj',b,sp[st[ids]])
    distances=np.linalg.norm(p-linear,axis=1)
    locked=set(display.get('locked_source_vertex_ids',[]))
    in_locked=np.array([all(v in locked for v in face) for face in st])[ids]
    lockmax=float(distances[in_locked].max()) if in_locked.any() else 0
    # Every rendered microtriangle stays within one parent triangle. Convexity
    # then proves the cap at all interpolated points, not just mesh vertices.
    tri=np.asarray(display['triangles']);parentids=ids[tri]
    same=bool(np.all(parentids==parentids[:,:1]))
    cap=float(display['max_offset_m'])
    return {'passed':bool(np.min(b)>=-1e-12 and np.max(abs(b.sum(axis=1)-1))<1e-12 and distances.max()<=cap+1e-12 and lockmax<1e-12 and same),
            'max_offset_m':float(distances.max()),'cap_m':cap,
            'locked_neighborhood_max_offset_m':lockmax,'fully_locked_triangle_count':int(sum(all(v in locked for v in face) for face in st)),
            'all_microtriangles_single_physical_parent':same,
            'offset_bound_proof':'For each microtriangle, linear interpolation of its bounded vertex offsets lies within a convex Euclidean ball of radius cap; barycentrics interpolate inside the same parent triangle.'}


def fbx_arrays(path):
    root,version=parse_fbx.parse(str(path))
    def children(element,name):return [e for e in element.elems if e.id==name]
    objs=children(root,b'Objects')[0]
    geometry=children(objs,b'Geometry')[0]
    positions=np.asarray(children(geometry,b'Vertices')[0].props[0]).reshape(-1,3)
    raw=np.asarray(children(geometry,b'PolygonVertexIndex')[0].props[0]);ends=raw<0
    decoded=np.where(ends,-raw-1,raw)
    model=children(objs,b'Model')[0]
    properties=children(model,b'Properties70')[0]
    scales=[list(e.props[-3:]) for e in properties.elems if e.id==b'P' and e.props[0]==b'Lcl Scaling']
    scale=scales[0] if scales else [1,1,1]
    return positions,decoded.reshape(-1,3),version,scale


def main():
    scene=json.loads((ASSET/'scene.json').read_text(encoding='utf8'))
    physical=json.loads((ASSET/'physics-mesh.json').read_text(encoding='utf8'))
    original=ROOT/'Assets'/'Phase5'/'physics-mesh.json'
    previous=json.loads(original.read_text())
    core=[k for k in previous if k not in ('version','home_tips_m','static_liver')]
    old_liver=np.asarray(previous['static_liver']['vertices_m']);new_liver=np.asarray(physical['static_liver']['vertices_m']);old_faces=np.asarray(previous['static_liver']['triangles'])
    organ=np.asarray(previous['vertices_m']);near=np.linalg.norm(old_liver[:,None,:]-organ[None,:,:],axis=2).min(axis=1)<.030
    protected_faces=np.any(near[old_faces],axis=1);protected_vertices=np.unique(old_faces[protected_faces])
    anchors=np.asarray([b['triangle_id'] for b in previous['attachment_anchor_bindings']]);anchor_vertices=np.unique(old_faces[anchors])
    protected=np.unique(np.concatenate([protected_vertices,anchor_vertices]))
    checks={'gallbladder_fem_and_attachment_values_preserved':all(previous[k]==physical.get(k) for k in core),
            'whole_operative_liver_triangles_preserved':previous['static_liver']['triangles']==physical['static_liver']['triangles'] and bool(np.array_equal(old_liver[protected],new_liver[protected])),
            'dynamic_base_triangles_preserved':scene['dynamic_surface']['triangles']==physical['triangles'],
            'original_model_identity':scene['model_id']==physical['model_id'] and scene['version']==physical['version']}
    dyntop=topology(scene['dynamic_display']);dynbind=binding(scene['dynamic_display'],scene['dynamic_surface'])
    checks['dynamic_closed_nondegenerate']=dyntop['boundary_edges_after_weld']==0 and dyntop['nonmanifold_edges_after_weld']==0 and dyntop['degenerate_triangles']==0
    checks['dynamic_bound']=dynbind['passed']
    result={'dynamic_topology':dyntop,'dynamic_binding':dynbind,'static':[],'textures':[],
            'preservation':{'core_fields':core,'previous_physics_sha256':digest(original),'protected_full_triangle_count':int(protected_faces.sum()),'protected_vertices':len(protected),'scope':'Every full triangle with a vertex within30mm of an original gallbladder vertex, plus all bound hepatic-bed anchor triangles. Remote liver shape and authored interaction rig are versioned changes.'}}
    for obj in scene['static_objects']:
        geo=obj.get('display_mesh',obj);top=topology(geo)
        item={'id':obj['id'],'topology':top}
        if obj['id']==200:
            checks['liver_collision_unchanged']=obj['vertices_m']==physical['static_liver']['vertices_m'] and obj['triangles']==physical['static_liver']['triangles']
            item['binding']=binding(geo,obj);checks['liver_bound_and_bed_locked']=item['binding']['passed']
            checks['liver_closed_after_weld']=top['boundary_edges_after_weld']==0
        pos,tri,version,node_scale=fbx_arrays(ASSET/obj['fbx_file'])
        expected=np.asarray(geo['vertices_m'])*np.array([100,-100,100])
        err=float(np.max(np.linalg.norm(pos-expected,axis=1))) if pos.shape==expected.shape else float('inf')
        # Mesh.flip_normals reverses polygon order, preserving cyclic identity.
        expected_tri=np.asarray(geo['triangles'])[:,::-1]
        same_tri=len(tri)==len(expected_tri) and bool(np.all(np.any(np.stack([np.all(tri==np.roll(expected_tri,k,axis=1),axis=1) for k in range(3)]),axis=0)))
        # Blender mesh storage is float32; FBX stores the resulting float values
        # in doubles. Accept 2 micrometres physical precision, then UE is audited.
        fbxpass=err<.0002 and same_tri and max(abs(v-1) for v in node_scale)<1e-12
        checks['fbx_'+str(obj['id'])]=fbxpass
        checks['topology_'+str(obj['id'])]=top['finite'] and top['degenerate_triangles']==0 and top['nonmanifold_edges_after_weld']==0
        item['fbx']={'passed':fbxpass,'version':version,'vertex_max_error_cm':err,'triangles_exact_after_handedness':same_tri,'node_scale':node_scale,'sha256':digest(ASSET/obj['fbx_file'])}
        result['static'].append(item)
    for mat in scene['material_sets'].values():
        for key in ('base_color_texture','roughness_texture','normal_texture'):
            path=ASSET/mat[key];raw=path.read_bytes();w,h=struct.unpack('>II',raw[16:24])
            required=mat['base_texture_resolution'] if key=='base_color_texture' else mat['aux_texture_resolution']
            okay=w==required and h==required and raw[:8]==b'\x89PNG\r\n\x1a\n'
            checks[mat['name']+'_'+key]=okay
            result['textures'].append({'file':mat[key],'size':[w,h],'sha256':digest(path),'passed':okay})
    result.update({'schema':'endoforge.phase6.independent-asset-audit.v1','passed':all(checks.values()),'checks':checks,
                   'physical_asset_sha256':digest(ASSET/'physics-mesh.json'),'scene_sha256':digest(ASSET/'scene.json'),
                   'ue_import_verification':'separate runtime gate; this checks authored FBX payload, not UE imported transforms'})
    (ASSET/'independent-asset-audit.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({'passed':result['passed'],'failed':[k for k,v in checks.items() if not v],
                      'dynamic':dynbind,'static_triangles':sum(o['topology']['triangles'] for o in result['static'])}),flush=True)
    if not result['passed']:raise RuntimeError('Phase6 asset audit failed')


if __name__=='__main__':main()
