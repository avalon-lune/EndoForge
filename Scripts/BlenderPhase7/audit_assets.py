"""Independent deterministic Phase 7 geometry/binding/texture audit.

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
ASSET=ROOT/'Assets'/'Phase7'
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
    original=ROOT/'Assets'/'Phase6'/'physics-mesh.json'
    previous=json.loads(original.read_text())
    core=[k for k in previous if k not in ('static_liver','attachment_anchor_bindings')]
    checks={'gallbladder_fem_and_attachment_values_preserved':all(previous[k]==physical.get(k) for k in core),
            'liver_physical_revision_declared':bool(physical.get('phase7_liver_revision')) and physical['static_liver']!=previous['static_liver'],
            'dynamic_base_triangles_preserved':scene['dynamic_surface']['triangles']==physical['triangles'],
            'original_model_identity':scene['model_id']==physical['model_id'] and scene['version']==physical['version']}
    import copy
    checks['original_ready_rig_preserved']=physical['phase6_interaction']==previous['phase6_interaction']
    dyntop=topology(scene['dynamic_display']);dynbind=binding(scene['dynamic_display'],scene['dynamic_surface'])
    checks['dynamic_closed_nondegenerate']=dyntop['boundary_edges_after_weld']==0 and dyntop['nonmanifold_edges_after_weld']==0 and dyntop['degenerate_triangles']==0
    checks['dynamic_bound']=dynbind['passed']
    result={'dynamic_topology':dyntop,'dynamic_binding':dynbind,'static':[],'textures':[],
            'preservation':{'core_fields':core,'previous_physics_sha256':digest(original),'scope':'Exact Phase 6 gallbladder/FEM/material/anchor positions and original rig. Closed liver collider and anchor triangle bindings intentionally revised; requires full physical qualification.'}}
    for obj in scene['static_objects']:
        geo=obj.get('display_mesh',obj);top=topology(geo)
        item={'id':obj['id'],'topology':top}
        if obj['id']==200:
            checks['liver_scene_matches_new_collision']=obj['vertices_m']==physical['static_liver']['vertices_m'] and obj['triangles']==physical['static_liver']['triangles']
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
    old=json.loads((ROOT/'Assets/Phase6/scene.json').read_text())
    for key in ('vertices_m','triangles','uvs','material_vertex_ids'):
        checks['phase6_dynamic_surface_'+key]=scene['dynamic_surface'][key]==old['dynamic_surface'][key]
    for key in ('vertices_m','triangles','barycentrics','source_triangle_ids','max_offset_m'):
        checks['phase6_dynamic_display_'+key]=scene['dynamic_display'][key]==old['dynamic_display'][key]
    for key in ('surface_material_vertex_ids','anchors_m','boundary_edges'):
        checks['phase6_attachment_'+key]=scene['attachment_bridge'][key]==old['attachment_bridge'][key]
    checks['new_liver_anchor_bindings']=scene['attachment_bridge']['anchor_bindings']==physical['attachment_anchor_bindings']
    checks['phase7_stable_object_ids']=[o['id'] for o in scene['static_objects']]==[o['id'] for o in old['static_objects']]
    checks['phase7_asset_namespace']=all(o['static_mesh_asset'].startswith('/Game/Phase7/Meshes/') for o in scene['static_objects'])
    checks['phase7_material_namespace']=all(m['ue_material']=='/Game/Phase7/Materials/M_AnatomyPhase7' for m in scene['material_sets'].values())
    checks['phase7_identity']=scene['phase']==7 and scene['appearance_identity']['physical_asset_sha256']==digest(ASSET/'physics-mesh.json')
    organ=np.asarray(scene['dynamic_surface']['vertices_m']);lo,hi=organ.min(axis=0),organ.max(axis=0)
    result['context_clearance']=[];result['shading_normals']=[]
    for obj in scene['static_objects']:
        geo=obj.get('display_mesh',obj);n=np.asarray(geo.get('normals',[]));valid=n.shape==(len(geo['vertices_m']),3)
        error=float(np.max(abs(np.linalg.norm(n,axis=1)-1))) if valid else float('inf')
        checks['authored_unit_shading_normals_'+str(obj['id'])]=valid and error<1e-5
        result['shading_normals'].append({'id':obj['id'],'max_unit_length_error':error})
        if obj['id'] in (300,301,310,311):
            p=np.asarray(obj['vertices_m']);f=np.asarray(obj['triangles']);a,b=p[f].min(axis=1),p[f].max(axis=1)
            disjoint=np.any((b<lo-.005)|(a>hi+.005),axis=1)
            checks['context_rest_organ_box_5mm_'+str(obj['id'])]=bool(disjoint.all())
            result['context_clearance'].append({'id':obj['id'],'intersecting_aabbs':int((~disjoint).sum()),'scope':'Conservative static rest screen only; moving tools and tissue require runtime gates.'})
    liver_geometry=json.loads((ASSET/'liver-geometry-check.json').read_text())
    checks['new_liver_exact_geometry_audit']=liver_geometry['passed'] and liver_geometry['sha256']==digest(ASSET/'physics-mesh.json')
    result.update({'schema':'endoforge.phase7.independent-asset-audit.v2','passed':all(checks.values()),'checks':checks,
                   'physical_asset_sha256':digest(ASSET/'physics-mesh.json'),'scene_sha256':digest(ASSET/'scene.json'),
                   'ue_import_verification':'separate runtime gate; this checks authored FBX payload, not UE imported transforms',
                   'full_physical_requalification_required':True})
    (ASSET/'independent-asset-audit.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({'passed':result['passed'],'failed':[k for k,v in checks.items() if not v],
                      'dynamic':dynbind,'static_triangles':sum(o['topology']['triangles'] for o in result['static'])}),flush=True)
    if not result['passed']:raise RuntimeError('Phase7 asset audit failed')


if __name__=='__main__':main()
