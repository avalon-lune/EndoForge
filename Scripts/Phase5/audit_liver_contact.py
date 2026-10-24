"""Independent sampled gallbladder-wall/fixed-liver separation audit.

All recorded states: broad-phase AABBs, full triangle/triangle separating-axis
intersection tests (including coplanar axes), and closed-liver winding-number
containment for every wall vertex. Exact triangle-pair distances are additionally
computed at stage boundaries and a configurable stride; their minimum is not
claimed to be a lower bound between those sampled states. No CCD claim is made.
Requires NumPy only. Coordinates and all computations are in metres.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()


def oriented_closed(vertices,faces):
    assert vertices.ndim==2 and vertices.shape[1]==3 and np.isfinite(vertices).all()
    assert faces.ndim==2 and faces.shape[1]==3 and faces.min()>=0 and faces.max()<len(vertices)
    assert np.all(np.diff(np.sort(faces,axis=1),axis=1)>0)
    directed=Counter((int(a),int(b)) for face in faces for a,b in zip(face,np.roll(face,-1)))
    assert all(count==1 and directed[(b,a)]==1 for (a,b),count in directed.items())
    assert len(set(faces.ravel()))==len(vertices)
    t=vertices[faces]
    assert np.all(np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1)>1e-12)
    volume=np.einsum('ij,ij->i',t[:,0],np.cross(t[:,1],t[:,2])).sum()/6
    return {'vertices':len(vertices),'triangles':len(faces),'closed_oriented':True,'signed_volume_m3':float(volume)}


def point_segment_sq(p,a,b):
    edge=b-a
    den=np.einsum('ij,ij->i',edge,edge)
    u=np.divide(np.einsum('ij,ij->i',p-a,edge),den,out=np.zeros(len(p)),where=den>1e-24)
    q=a+np.clip(u,0,1)[:,None]*edge
    return np.einsum('ij,ij->i',p-q,p-q)


def point_triangle_sq(p,tri):
    a,b,c=tri[:,0],tri[:,1],tri[:,2]
    e=b-a; f=c-a; n=np.cross(e,f)
    n2=np.einsum('ij,ij->i',n,n)
    pa=p-a
    nd=np.einsum('ij,ij->i',pa,n)
    projection=pa-n*(nd/n2)[:,None]
    ee=np.einsum('ij,ij->i',e,e); ef=np.einsum('ij,ij->i',e,f); ff=np.einsum('ij,ij->i',f,f)
    pe=np.einsum('ij,ij->i',projection,e); pf=np.einsum('ij,ij->i',projection,f)
    det=ee*ff-ef*ef
    u=(pe*ff-pf*ef)/det; v=(pf*ee-pe*ef)/det
    inside=(u>=0)&(v>=0)&(u+v<=1)
    edge=np.minimum.reduce([point_segment_sq(p,a,b),point_segment_sq(p,b,c),point_segment_sq(p,c,a)])
    return np.where(inside,nd*nd/n2,edge)


def segment_segment_sq(a,b,c,d):
    e=b-a; f=d-c; r=a-c
    ee=np.einsum('ij,ij->i',e,e); ff=np.einsum('ij,ij->i',f,f)
    ef=np.einsum('ij,ij->i',e,f); er=np.einsum('ij,ij->i',e,r); fr=np.einsum('ij,ij->i',f,r)
    det=ee*ff-ef*ef; good=det>1e-24
    u=np.divide(ef*fr-ff*er,det,out=np.zeros(len(a)),where=good)
    v=np.divide(ee*fr-ef*er,det,out=np.zeros(len(a)),where=good)
    delta=r+u[:,None]*e-v[:,None]*f
    interior=np.where(good&(u>=0)&(u<=1)&(v>=0)&(v<=1),np.einsum('ij,ij->i',delta,delta),np.inf)
    return np.minimum.reduce([point_segment_sq(a,c,d),point_segment_sq(b,c,d),point_segment_sq(c,a,b),point_segment_sq(d,a,b),interior])


def pair_intersects(a,b,tolerance=1e-9):
    """Conservative SAT: true includes boundary touching within tolerance."""
    ea=np.roll(a,-1,axis=1)-a; eb=np.roll(b,-1,axis=1)-b
    na=np.cross(ea[:,0],ea[:,1]); nb=np.cross(eb[:,0],eb[:,1])
    axes=[na,nb]
    axes.extend(np.cross(ea[:,i],eb[:,j]) for i in range(3) for j in range(3))
    axes.extend(np.cross(na,ea[:,i]) for i in range(3))
    axes.extend(np.cross(nb,eb[:,i]) for i in range(3))
    result=np.ones(len(a),dtype=bool)
    for axis in axes:
        length=np.linalg.norm(axis,axis=1); good=length>1e-18
        n=np.divide(axis,length[:,None],out=np.zeros_like(axis),where=good[:,None])
        pa=np.einsum('nkj,nj->nk',a,n); pb=np.einsum('nkj,nj->nk',b,n)
        separated=(pa.max(1)<pb.min(1)-tolerance)|(pb.max(1)<pa.min(1)-tolerance)
        result &= ~(good & separated)
    return result


def winding(points,triangles,lo,hi):
    inside=np.zeros(len(points),dtype=bool); maximum_ambiguity=0.0
    candidates=np.flatnonzero(np.all((points>=lo)&(points<=hi),axis=1))
    for group in np.array_split(candidates,max(1,math.ceil(len(candidates)/64))):
        if not len(group):continue
        rel=triangles[None,:,:,:]-points[group,None,None,:]
        a,b,c=rel[:,:,0],rel[:,:,1],rel[:,:,2]
        la=np.linalg.norm(a,axis=2);lb=np.linalg.norm(b,axis=2);lc=np.linalg.norm(c,axis=2)
        numerator=np.einsum('nij,nij->ni',a,np.cross(b,c))
        denominator=la*lb*lc+np.einsum('nij,nij->ni',a,b)*lc+np.einsum('nij,nij->ni',b,c)*la+np.einsum('nij,nij->ni',c,a)*lb
        w=np.abs((2*np.arctan2(numerator,denominator)).sum(axis=1)/(4*np.pi))
        inside[group]=w>.5
        maximum_ambiguity=max(maximum_ambiguity,float(np.minimum(w,np.abs(w-1)).max()))
    return inside,maximum_ambiguity


def nearest_surface_points(points,liver):
    results=[]
    for point in points:
        distance=point_triangle_sq(np.broadcast_to(point,(len(liver),3)),liver)
        results.append(float(np.sqrt(distance.min())))
    return results


def closest_point_on_mesh(point,triangles):
    """Exact closest surface point and triangle ID; supports attachment diagnostics."""
    p=np.broadcast_to(point,(len(triangles),3)); a,b,c=triangles[:,0],triangles[:,1],triangles[:,2]
    e=b-a;f=c-a;n=np.cross(e,f);n2=np.einsum('ij,ij->i',n,n)
    pa=p-a;nd=np.einsum('ij,ij->i',pa,n);projected=p-n*(nd/n2)[:,None]
    ee=np.einsum('ij,ij->i',e,e);ef=np.einsum('ij,ij->i',e,f);ff=np.einsum('ij,ij->i',f,f)
    pe=np.einsum('ij,ij->i',projected-a,e);pf=np.einsum('ij,ij->i',projected-a,f)
    det=ee*ff-ef*ef;u=(pe*ff-pf*ef)/det;v=(pf*ee-pe*ef)/det
    inside=(u>=0)&(v>=0)&(u+v<=1)
    candidates=[projected];distances=[np.where(inside,np.einsum('ij,ij->i',p-projected,p-projected),np.inf)]
    for start,end in ((a,b),(b,c),(c,a)):
        edge=end-start;den=np.einsum('ij,ij->i',edge,edge)
        s=np.divide(np.einsum('ij,ij->i',p-start,edge),den,out=np.zeros(len(p)),where=den>1e-24)
        q=start+np.clip(s,0,1)[:,None]*edge;candidates.append(q);distances.append(np.einsum('ij,ij->i',p-q,p-q))
    distances=np.asarray(distances);feature,index=np.unravel_index(np.argmin(distances),distances.shape)
    return candidates[feature][index],int(index),float(np.sqrt(distances[feature,index]))


def exact_clearance(vertices,faces,liver,liver_vertices):
    # Nearest vertex pair is an upper bound on the nearest surface pair.
    upper=float(np.linalg.norm(vertices[:,None,:]-liver_vertices[None,:,:],axis=2).min())
    tissue=vertices[faces]; tlo=tissue.min(1);thi=tissue.max(1);llo=liver.min(1);lhi=liver.max(1)
    gap=np.maximum(np.maximum(tlo[:,None]-lhi[None],llo[None]-thi[:,None]),0)
    candidate=np.einsum('ijk,ijk->ij',gap,gap)<=upper*upper+1e-24
    ti,li=np.nonzero(candidate); a=tissue[ti];b=liver[li]
    if not len(a):return upper,0
    minimum=np.full(len(a),np.inf)
    for k in range(3):
        minimum=np.minimum(minimum,point_triangle_sq(a[:,k],b))
        minimum=np.minimum(minimum,point_triangle_sq(b[:,k],a))
    for i in range(3):
        for j in range(3):minimum=np.minimum(minimum,segment_segment_sq(a[:,i],a[:,(i+1)%3],b[:,j],b[:,(j+1)%3]))
    return float(np.sqrt(max(0,float(minimum.min())))),len(a)


def audit(path,stride=30):
    start=time.monotonic(); count=pair_count=inside_count=intersect_count=0;worst_inside=[];worst_pairs=[]; stages={};clearances=[]
    max_winding_error=0.0;fingerprint=None; previous_stage=None;anchors=None
    with path.open(encoding='utf-8-sig') as handle:
        header=json.loads(next(handle));faces=np.asarray(header['triangles'],dtype=np.int64)
        liver_vertices=np.asarray(header['static_liver']['vertices_m'],dtype=float)
        lf=np.asarray(header['static_liver']['triangles'],dtype=np.int64);liver=liver_vertices[lf]
        liver_audit=oriented_closed(liver_vertices,lf)
        assert liver_audit['signed_volume_m3']>0
        # The inner wall is oppositely oriented as a boundary of the wall solid.
        wall_audit=oriented_closed(np.asarray(header['rest_vertices'],dtype=float),faces)
        assert wall_audit['signed_volume_m3']>0
        llo=liver.min(1);lhi=liver.max(1);lo=liver_vertices.min(0);hi=liver_vertices.max(0)
        for line in handle:
            state=json.loads(line);vertices=np.asarray(state['vertices'],dtype=float)
            assert vertices.shape==(len(header['rest_vertices']),3) and np.isfinite(vertices).all()
            assert state['healthy'] is True and state['safety_stops']==0 and state['triangles']==header['triangles']
            if fingerprint is None:fingerprint=state['asset_fingerprint']
            assert fingerprint==state['asset_fingerprint']
            stage=state.get('stage','unknown');stages[stage]=stages.get(stage,0)+1
            tissue=vertices[faces];tlo=tissue.min(1);thi=tissue.max(1)
            # Safe broad phase: restrict liver faces by the whole moving-wall AABB.
            relevant=np.flatnonzero(np.all((lhi+1e-9>=vertices.min(0))&(llo-1e-9<=vertices.max(0)),axis=1))
            candidate=np.all((thi[:,None]+1e-9>=llo[relevant][None])&(tlo[:,None]-1e-9<=lhi[relevant][None]),axis=2)
            ti,idx=np.nonzero(candidate);li=relevant[idx];pair_count+=len(ti)
            hit=pair_intersects(tissue[ti],liver[li]) if len(ti) else np.zeros(0,dtype=bool)
            if hit.any():
                intersect_count+=1
                if len(worst_pairs)<10:worst_pairs.append({'sample':count,'stage':stage,'pairs':[[int(a),int(b)] for a,b in zip(ti[hit][:20],li[hit][:20])]})
            contained,error=winding(vertices,liver,lo,hi);max_winding_error=max(max_winding_error,error)
            if contained.any():
                inside_count+=1
                if len(worst_inside)<10:worst_inside.append({'sample':count,'stage':stage,'wall_vertex_ids':np.flatnonzero(contained).tolist()})
            if count%stride==0 or stage!=previous_stage:
                distance,tested=exact_clearance(vertices,faces,liver,liver_vertices)
                clearances.append({'sample':count,'stage':stage,'minimum_mm':distance*1000,'triangle_pairs_considered':tested})
            if anchors is None and state.get('attachment_segments_m'):
                anchors=np.asarray([segment[1] for segment in state['attachment_segments_m']],dtype=float)
            previous_stage=stage;count+=1
    checks={'all_recorded_states_tested':count>=30,'zero_wall_liver_triangle_intersections_or_touch':intersect_count==0,
            'zero_wall_vertices_inside_closed_liver':inside_count==0,'unambiguous_winding_classification':max_winding_error<1e-5}
    result={'case_id':header['case_id'],'trajectory':str(path),'trajectory_sha256':sha(path),'asset_fingerprint':fingerprint,
            'liver_mesh':liver_audit,'wall_boundary_mesh':wall_audit,'recorded_states_tested':count,'stages':stages,
            'broad_phase_candidate_pairs_tested':pair_count,'intersecting_or_touching_states':intersect_count,
            'wall_inside_liver_states':inside_count,'intersection_examples':worst_pairs,'containment_examples':worst_inside,
            'maximum_winding_integer_error':max_winding_error,'clearance_state_count':len(clearances),
            'minimum_clearance_mm_among_distance_samples':min(s['minimum_mm'] for s in clearances),
            'distance_samples':clearances,'checks':checks,'passed':all(checks.values()),'elapsed_seconds':time.monotonic()-start}
    if anchors is not None:
        distances=nearest_surface_points(anchors,liver)
        result['fixed_anchor_surface_diagnostic']={'anchor_count':len(anchors),
             'distance_mm':[v*1000 for v in distances],'minimum_mm':min(distances)*1000,'maximum_mm':max(distances)*1000,
             'scope':'All fixed endpoints must lie on actual hepatic triangles; maximum permitted geometric binding error is 1e-8m.'}
        checks['all_fixed_anchors_on_actual_hepatic_surface']=max(distances)<=1e-8
    else:
        checks['all_fixed_anchors_on_actual_hepatic_surface']=False
    result['passed']=all(checks.values())
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--trajectory',type=Path,action='append',required=True)
    p.add_argument('--clearance-stride',type=int,default=30);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();assert a.clearance_stride>=1
    cases=[]
    for path in a.trajectory:
        case=audit(path,a.clearance_stride);cases.append(case)
        print(json.dumps({k:case[k] for k in ('case_id','recorded_states_tested','passed','minimum_clearance_mm_among_distance_samples','elapsed_seconds')}),flush=True)
    report={'schema':'endoforge.phase5.liver-contact-audit.v1','audit_script_sha256':sha(__file__),'passed':bool(cases) and all(c['passed'] for c in cases),
        'intersection_tolerance_m':1e-9,'clearance_stride':a.clearance_stride,'cases':cases,
        'scope':'Every recorded state checks both closed wall surfaces against all relevant fixed-liver faces with conservative triangle SAT, including face interiors and coplanar axes, plus winding containment of every wall vertex. Mesh orientation/closure checked. Minimum Euclidean triangle-surface distances are sampled at stage starts and stride, not certified between those samples. No continuous collision, interpolated motion, liver self-intersection or clinical-anatomy guarantee.'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    raise SystemExit(0 if report['passed'] else 1)
