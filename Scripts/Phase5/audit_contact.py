"""Independently audit recorded Phase 5 triangle surfaces against actual jaw OBBs."""
import argparse
import hashlib
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit_phase4_collision_geometry import geometry_depth, interpolate_frame, finite_tree, dot, cross, sub, norm, unit


def sha(p):
    with Path(p).open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()


def jaw_overlap(tools,half):
    """15-axis OBB SAT. Returns minimum translation overlap along tested axes."""
    result=0.0
    for a in tools[0]['jaw_poses']:
        for b in tools[1]['jaw_poses']:
            aa=[a[k] for k in ('axis','side','normal')]
            bb=[b[k] for k in ('axis','side','normal')]
            axes=aa+bb+[cross(x,y) for x in aa for y in bb]
            d=sub(b['center_m'],a['center_m']); overlap=math.inf
            for axis in axes:
                if norm(axis)<1e-9: continue
                axis=unit(axis)
                r=sum(half[i]*(abs(dot(axis,aa[i]))+abs(dot(axis,bb[i]))) for i in range(3))
                overlap=min(overlap,r-abs(dot(axis,d)))
            result=max(result,overlap)
    return result


def inside_closed_mesh(point,vertices,triangles,bounds):
    if any(point[i]<=bounds[i][0] or point[i]>=bounds[i][1] for i in range(3)): return False
    direction=unit([1,.173,.413]); hits=[]
    for face in triangles:
        a,b,c=(vertices[i] for i in face)
        e1=sub(b,a); e2=sub(c,a); h=cross(direction,e2); det=dot(e1,h)
        if abs(det)<1e-14: continue
        s=sub(point,a); u=dot(s,h)/det
        if u<0 or u>1: continue
        q=cross(s,e1); v=dot(direction,q)/det
        if v<0 or u+v>1: continue
        distance=dot(e2,q)/det
        if distance>1e-9: hits.append(distance)
    unique=[]
    for t in sorted(hits):
        if not unique or t-unique[-1]>1e-8: unique.append(t)
    return len(unique)%2==1


def audit(path, sweeps=3):
    maximum_node=maximum_surface=maximum_swept=0.0
    max_liver=max_jaw=0.0; worst_jaw=worst_liver=None; enclosed_centers=0
    count=samples=reset_boundaries=0
    holds=[0,0]; dual=0; motion=[0.0,0.0]; previous=None
    min_volume=1.0; min_area=1.0; healthy=True
    with path.open(encoding='utf-8-sig') as handle:
        mesh=json.loads(next(handle)); faces=mesh['triangles']; half=mesh['jaw_half_extents_m']
        n=len(mesh['rest_vertices']); liver=mesh.get('static_liver')
        liver_bounds=[(min(v[i] for v in liver['vertices_m']),max(v[i] for v in liver['vertices_m'])) for i in range(3)] if liver else None
        def count_inside(tools):
            if not liver: return 0
            return sum(inside_closed_mesh(p['center_m'],liver['vertices_m'],liver['triangles'],liver_bounds) for t in tools for p in t['jaw_poses'])
        assert mesh['type']=='mesh' and n>=3 and faces and len(half)==3 and min(half)>0
        for f in faces:
            assert len(f)==3 and len(set(f))==3 and all(type(i) is int and 0<=i<n for i in f)
        for line in handle:
            frame=json.loads(line)
            assert finite_tree(frame) and len(frame['vertices'])==n and len(frame['tools'])==2
            healthy &= frame['healthy'] is True and frame['safety_stops']==0
            min_volume=min(min_volume,frame['min_tet_volume_ratio'])
            min_area=min(min_area,frame['min_triangle_area_ratio'])
            node,surface,_=geometry_depth(frame['vertices'],faces,frame['tools'],half)
            maximum_node=max(maximum_node,node); maximum_surface=max(maximum_surface,surface)
            jaw=jaw_overlap(frame['tools'],half)
            enclosed_centers+=count_inside(frame['tools'])
            if jaw>max_jaw: max_jaw=jaw; worst_jaw={'sample':count,'stage':frame.get('stage')}
            if liver:
                _,ld,_=geometry_depth(liver['vertices_m'],liver['triangles'],frame['tools'],half)
                if ld>max_liver: max_liver=ld; worst_liver={'sample':count,'stage':frame.get('stage')}
            for k,t in enumerate(frame['tools']):
                holds[k]+=int(t.get('grasping',False))
            dual+=int(all(t.get('grasping',False) for t in frame['tools']))
            if previous is not None and (frame.get('simulation_id')!=previous.get('simulation_id') or frame.get('frame',0)<previous.get('frame',0)):
                previous=None; reset_boundaries+=1
            if previous is not None:
                for k in range(2):
                    before=previous['tools'][k]['jaw_poses'][0]['center_m']
                    after=frame['tools'][k]['jaw_poses'][0]['center_m']
                    motion[k]+=math.dist(before,after)
                for i in range(1,sweeps+1):
                    v,t=interpolate_frame(previous,frame,i/(sweeps+1))
                    a,b,_=geometry_depth(v,faces,t,half)
                    maximum_swept=max(maximum_swept,a,b); samples+=1
                    jaw=jaw_overlap(t,half)
                    enclosed_centers+=count_inside(t)
                    if jaw>max_jaw: max_jaw=jaw; worst_jaw={'sample':count,'fraction':i/(sweeps+1),'stage':frame.get('stage')}
                    if liver:
                        _,ld,_=geometry_depth(liver['vertices_m'],liver['triangles'],t,half)
                        if ld>max_liver: max_liver=ld; worst_liver={'sample':count,'fraction':i/(sweeps+1),'stage':frame.get('stage')}
            previous=frame; count+=1
    checks={'enough_recorded_states':count>=30,'finite_healthy_states':healthy,
            'positive_element_ratios':min_volume>0 and min_area>0,
            'node_penetration_within_0_15mm':maximum_node<=.00015,
            'whole_triangle_penetration_within_0_15mm':maximum_surface<=.00015,
            'interpolated_penetration_within_0_15mm':maximum_swept<=.00015,
            'tested_jaws_do_not_overlap_over_0_15mm':max_jaw<=.00015,
            'tested_liver_surface_does_not_enter_jaws_over_0_15mm':liver is not None and max_liver<=.00015,
            'no_jaw_centers_enclosed_by_fixed_liver':enclosed_centers==0,
            'actual_jaw_travel_over_5mm':max(motion)>=.005}
    return {'case_id':mesh['case_id'],'path':str(path),'sha256':sha(path),
            'states':count,'interpolated_samples':samples,'reset_boundaries_not_interpolated':reset_boundaries,'grasping_states_per_tool':holds,
            'simultaneous_grasping_states':dual,'jaw_travel_mm':[v*1000 for v in motion],
            'maximum_node_depth_mm':maximum_node*1000,
            'maximum_whole_triangle_depth_mm':maximum_surface*1000,
            'maximum_interpolated_depth_mm':maximum_swept*1000,
            'maximum_inter_tool_jaw_overlap_mm':max_jaw*1000,'worst_jaw_overlap':worst_jaw,
            'maximum_liver_surface_in_jaw_mm':max_liver*1000,'worst_liver_overlap':worst_liver,
            'liver_enclosed_jaw_centers':enclosed_centers,
            'minimum_tet_volume_ratio':min_volume,'minimum_triangle_area_ratio':min_area,
            'checks':checks,'passed':all(checks.values())}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--trajectory',type=Path,action='append',required=True)
    p.add_argument('--sweeps',type=int,default=3)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,default=1)
    args=p.parse_args()
    if args.workers>1:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            results=list(pool.map(audit,args.trajectory,[args.sweeps]*len(args.trajectory)))
    else:
        results=[audit(path,args.sweeps) for path in args.trajectory]
    out={'schema':'endoforge.phase5.independent-contact.v1',
         'audit_script_sha256':sha(__file__),
         'geometry_kernel_sha256':sha(Path(__file__).resolve().parents[1]/'audit_phase4_collision_geometry.py'),
         'cases':results,'passed':bool(results) and all(r['passed'] for r in results),
         'scope':'Whole-face inward depth into jaw OBBs; inter-tool jaw OBB separating axes; liver boundary/jaw overlap and jaw-center containment. Interpolated output samples screen tunnelling, not continuous collision proof. Shafts and background surfaces are excluded.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,indent=2),encoding='utf-8')
    print(json.dumps(out))
    raise SystemExit(0 if out['passed'] else 1)
