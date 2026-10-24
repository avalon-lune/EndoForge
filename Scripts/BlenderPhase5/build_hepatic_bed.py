"""Build a continuous closed hepatic support with a locally conforming bed.

Only the posterior attachment patch is refined. The frozen gallbladder material
mesh is unchanged. Run in Blender; its constrained Delaunay triangulator joins
the refined bed into the same closed hepatic volume, without a separate island.
"""
import importlib.util
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt

ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'Assets/Phase5'
sys.path.insert(0,str(Path(__file__).parent))
import build_assets as author


def refine_patch(vertices,faces,levels=2):
    vertices=[list(p) for p in vertices]
    for _ in range(levels):
        cache={};new=[]
        def midpoint(a,b):
            key=tuple(sorted((a,b)))
            if key not in cache:
                cache[key]=len(vertices)
                vertices.append([(vertices[a][k]+vertices[b][k])*.5 for k in range(3)])
            return cache[key]
        for a,b,c in faces:
            ab=midpoint(a,b);bc=midpoint(b,c);ca=midpoint(c,a)
            new.extend([[a,ab,ca],[ab,b,bc],[ca,bc,c],[ab,bc,ca]])
        faces=new
    return vertices,faces


def barycentric_xy(xy,tri):
    a,b,c=tri[:,0,:2],tri[:,1,:2],tri[:,2,:2]
    e=b-a;f=c-a;p=np.asarray(xy)-a
    det=e[:,0]*f[:,1]-e[:,1]*f[:,0]
    u=(p[:,0]*f[:,1]-p[:,1]*f[:,0])/det
    v=(e[:,0]*p[:,1]-e[:,1]*p[:,0])/det
    return np.stack([1-u-v,u,v],axis=1)


def create(data):
    # Recover the original support from its deterministic source. This allows
    # rerunning on v2 without repeatedly lifting or refining an already edited bed.
    oldv,oldf,_=author.radial_mesh(author.liver,16,32)
    oldv=np.asarray(oldv);oldf=np.asarray(oldf)
    equator_start=1+7*32
    equator=list(range(equator_start,equator_start+32))
    top_faces=oldf[np.all(oldf<equator_start+32,axis=1)]
    bottom_faces=oldf[np.all(oldf>=equator_start,axis=1)]
    top_tri=oldv[top_faces]
    ids=data['attachment_vertex_ids'];id_to_patch={v:i for i,v in enumerate(ids)}
    g=np.asarray(data['vertices_m']);n=np.asarray(data['normals'])
    outer=g+n*data['thickness_m']*.5
    anchors=outer[ids]+n[ids]*.00095
    faces=[[id_to_patch[i] for i in f] for f in data['triangles'] if all(i in id_to_patch for i in f)]
    # The gallbladder underside is outward-down; reverse for the hepatic top.
    faces=[f[::-1] for f in faces]
    pv,pf=refine_patch(anchors.tolist(),faces,2)
    ptri=np.asarray(pv)[pf]
    boundary=Counter(tuple(sorted((a,b))) for f in pf for a,b in zip(f,f[1:]+f[:1]))
    boundary=[(a,b) for (a,b),count in boundary.items() if count==1]
    pva=np.asarray(pv)
    boundary_a=pva[[a for a,b in boundary]];boundary_b=pva[[b for a,b in boundary]]
    edge_xy=boundary_b[:,:2]-boundary_a[:,:2]
    edge_len=np.einsum('ij,ij->i',edge_xy,edge_xy)

    def old_height(xy):
        w=barycentric_xy(xy,top_tri)
        good=np.flatnonzero(np.all(w>=-1e-7,axis=1))
        if not len(good):raise ValueError(('No original top face',xy))
        i=good[0];return float(w[i]@top_tri[i,:,2])

    def height(xy):
        w=barycentric_xy(xy,ptri)
        good=np.flatnonzero(np.all(w>=-1e-7,axis=1))
        if len(good):
            i=good[0];return float(w[i]@ptri[i,:,2])
        orig=old_height(xy)
        p=np.asarray(xy)-boundary_a[:,:2]
        t=np.clip(np.einsum('ij,ij->i',p,edge_xy)/edge_len,0,1)
        q=boundary_a+t[:,None]*(boundary_b-boundary_a)
        dist=np.linalg.norm(q[:,:2]-xy,axis=1);i=int(dist.argmin());d=float(dist[i])
        if d>=.007:return orig
        s=d/.007;s=s*s*(3-2*s)
        # A short descending continuous shoulder joins the lifted bed to the
        # unchanged broad liver. It stays under tissue beyond the bed boundary.
        return float((1-s)*(q[i,2]-d*.8)+s*orig)

    inputs=[];exact=[];input_to_original={};patch_input=[]
    for i in range(equator_start+32):
        inputs.append(tuple(oldv[i,:2]));exact.append([*oldv[i,:2],height(oldv[i,:2])])
        input_to_original[i]=i
    for p in pv:
        patch_input.append(len(inputs));inputs.append(tuple(p[:2]));exact.append(p)
    constraints=[]
    for a,b in zip(equator,equator[1:]+equator[:1]):constraints.append((a,b))
    pe=set(tuple(sorted((patch_input[a],patch_input[b]))) for f in pf for a,b in zip(f,f[1:]+f[:1]))
    constraints.extend(sorted(pe))
    # Fine points around the bed, without unnecessarily refining the full organ.
    for y in np.arange(-.013,.027,.002):
        for x in np.arange(-.021,.023,.002):
            w=barycentric_xy((x,y),ptri)
            if np.any(np.all(w>=-1e-8,axis=1)):continue
            inputs.append((float(x),float(y)));exact.append([float(x),float(y),height((x,y))])
    result=delaunay_2d_cdt([Vector(p) for p in inputs],constraints,[],0,1e-10,True)
    coords,_,triangles,original_ids,_,_=result
    verts=[];input_to_output={}
    for i,(xy,orig_ids) in enumerate(zip(coords,original_ids)):
        for source in orig_ids:input_to_output[source]=i
        if orig_ids:
            source=next((j for j in orig_ids if j in patch_input),orig_ids[0])
            verts.append(list(exact[source]))
        else:verts.append([float(xy.x),float(xy.y),height((xy.x,xy.y))])
    # Constrained triangulation emits CCW top faces. Normalize their orientation
    # explicitly, and then sew the original underside along the shared equator.
    final_faces=[]
    for f in triangles:
        a,b,c=np.asarray(verts)[f]
        final_faces.append(f if np.cross(b-a,c-a)[2]>0 else f[::-1])
    original_to_final={i:input_to_output[i] for i in equator}
    for i in range(equator_start+32,len(oldv)):
        original_to_final[i]=len(verts);verts.append(oldv[i].tolist())
    for f in bottom_faces:final_faces.append([original_to_final[int(i)] for i in f])
    # Anchors are exact vertices of actual liver triangles. The explicit
    # barycentric bindings remove any inferred or floating endpoint semantics.
    bindings=[];final_anchors=[]
    for j in range(len(ids)):
        index=input_to_output[patch_input[j]]
        triangle_id=next(i for i,f in enumerate(final_faces) if index in f)
        f=final_faces[triangle_id];bary=[0.,0.,0.];bary[f.index(index)]=1.
        bindings.append({'triangle_id':triangle_id,'barycentric':bary})
        final_anchors.append(verts[index])
    data['version']=2
    data['grasp_targets_m']=[[-.004,-.028,.025],[.004,-.028,.025]]
    data['attachment_anchor_positions_m']=final_anchors
    data['attachment_anchor_bindings']=bindings
    data['static_liver']={'vertices_m':verts,'triangles':final_faces}
    data['hepatic_bed']={'construction':'Locally refined continuous top of the same closed hepatic support',
        'outer_wall_normal_offset_m':.00095,'patch_source_material_vertex_ids':ids,
        'subdivision_levels':2,'target_edge_length_m':.002,
        'shoulder_transition_width_m':.007,'clinical_anatomy_review':'pending'}
    return data


if __name__=='__main__':
    d=json.loads((ASSETS/'physics-mesh.json').read_text(encoding='utf8'))
    d=create(d)
    path=ROOT/'tmp/phase5/physics-mesh-v2-candidate.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(d,separators=(',',':')),encoding='utf8')
    # Use the separate root-owned geometric auditor rather than inspecting only
    # our own generation assumptions.
    spec=importlib.util.spec_from_file_location('liver_contact_auditor',ROOT/'Scripts/Phase5/audit_liver_contact.py')
    audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    v=np.asarray(d['static_liver']['vertices_m']);f=np.asarray(d['static_liver']['triangles'])
    topology=audit.oriented_closed(v,f)
    outer=np.asarray(d['vertices_m'])+np.asarray(d['normals'])*d['thickness_m']*.5
    distance,pairs=audit.exact_clearance(outer,np.asarray(d['triangles']),v[f],v)
    distances=audit.nearest_surface_points(np.asarray(d['attachment_anchor_positions_m']),v[f])
    tissue=outer[np.asarray(d['triangles'])];liver=v[f]
    pair_t,pair_l=np.nonzero(np.all((tissue.max(1)[:,None]+1e-9>=liver.min(1)[None])&(tissue.min(1)[:,None]-1e-9<=liver.max(1)[None]),axis=2))
    hits=audit.pair_intersects(tissue[pair_t],liver[pair_l])
    inside,winding_error=audit.winding(outer,liver,v.min(0),v.max(0))
    boundary_edges=[np.linalg.norm(np.asarray(d['vertices_m'])[a]-np.asarray(d['vertices_m'])[b])/4 for t in d['triangles'] if all(i in d['attachment_vertex_ids'] for i in t) for a,b in zip(t,t[1:]+t[:1])]
    report={'schema':'endoforge.hepatic-bed-generation.v2','liver':topology,
        'anchor_count':len(distances),'max_anchor_surface_distance_m':max(distances),
        'outer_wall_minimum_surface_clearance_m':distance,'candidate_triangle_pairs':pairs,
        'rest_triangle_intersections':int(hits.sum()),'rest_wall_vertices_inside_liver':int(inside.sum()),
        'maximum_winding_integer_error':float(winding_error),
        'maximum_local_patch_edge_m':max(boundary_edges),'candidate_path':str(path)}
    (ASSETS/'hepatic-bed-generation-check.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report),flush=True)
