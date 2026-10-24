"""Independent surface/node OBB audit of native collision trajectories.

The surface metric is max_{p on each triangle} min_i(h_i-|p_i|), clipped
at zero. Polygon clipping tests eroded OBB intersection, then bisection
finds this maximum. It detects triangle interiors inside a jaw even when
all physical vertices are outside. Intermediate tests sample linearly
interpolated exported states and interpolated orthonormal jaw frames;
these are an additional tunnelling screen, NOT proof of continuous SOFA
substep geometry or arbitrary motion collision freedom.
"""
from __future__ import annotations
import argparse, concurrent.futures, datetime, hashlib, json, math, pathlib

REQUIRED_CASE_IDS=['curved_straight_regression']+[f'{shape}_{suffix}' for shape in ('flat','curved') for suffix in ('straight_90_fast','diagonal_75_slow','elbow_105_medium','tangent_60_fast','reverse_120_medium','vertical_90_slow','straight_90_slow','straight_90_medium')]+['curved_straight_90_approach_left','curved_straight_90_approach_right']
NODE_TOLERANCE=.00015
SURFACE_TOLERANCE=.00015

def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for block in iter(lambda:f.read(2**20),b''):h.update(block)
    return h.hexdigest()

def add(a,b):return [a[i]+b[i] for i in range(3)]
def sub(a,b):return [a[i]-b[i] for i in range(3)]
def dot(a,b):return sum(a[i]*b[i] for i in range(3))
def scale(a,v):return [x*v for x in a]
def norm(v):return math.sqrt(dot(v,v))
def unit(v):
    n=norm(v)
    if n<1e-12:raise ValueError('Degenerate jaw basis')
    return scale(v,1/n)
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def lerp(a,b,t):return [a[i]*(1-t)+b[i]*t for i in range(3)]

def triangle_box_intersection(triangle,half):
    polygon=[list(v) for v in triangle]
    for axis in range(3):
        for sign in (-1,1):
            if not polygon:return False
            clipped=[];previous=polygon[-1];pd=half[axis]-sign*previous[axis]
            for point in polygon:
                d=half[axis]-sign*point[axis]
                if (pd>=0)!=(d>=0):
                    weight=pd/(pd-d);clipped.append(lerp(previous,point,weight))
                if d>=0:clipped.append(point)
                previous=point;pd=d
            polygon=clipped
    return bool(polygon)

def triangle_depth(triangle,half,lower=0.):
    if not triangle_box_intersection(triangle,[h-lower for h in half]):return lower
    lo=lower;hi=min(half)
    for _ in range(18):
        mid=(lo+hi)/2
        if triangle_box_intersection(triangle,[h-mid for h in half]):lo=mid
        else:hi=mid
    return lo

def validate_pose(pose):
    axes=[pose[k] for k in ('axis','side','normal')]
    if any(abs(norm(a)-1)>1e-6 for a in axes):raise ValueError('Nonunit jaw frame')
    if any(abs(dot(axes[a],axes[b]))>1e-6 for a,b in ((0,1),(0,2),(1,2))):raise ValueError('Nonorthogonal jaw frame')
    if norm(sub(cross(axes[0],axes[1]),axes[2]))>1e-6:raise ValueError('Jaw handedness mismatch')

def geometry_depth(vertices,triangles,tools,half):
    """Returns node depth, surface depth, deepest surface triangle/tool/jaw."""
    maximum=0.;node_depth=0.;witness=None
    for tool_index,tool in enumerate(tools):
        for jaw_index,pose in enumerate(tool['jaw_poses']):
            validate_pose(pose)
            center=pose['center_m'];axes=[pose[k] for k in ('axis','side','normal')]
            local=[]
            for v in vertices:
                x=v[0]-center[0];y=v[1]-center[1];z=v[2]-center[2]
                local.append([x*a[0]+y*a[1]+z*a[2] for a in axes])
            # Exact vertex metric is independent of the native contacts value.
            for v in local:node_depth=max(node_depth,max(0.,min(half[i]-abs(v[i]) for i in range(3))))
            if any(min(v[i] for v in local)>=half[i]-maximum or max(v[i] for v in local)<=-half[i]+maximum for i in range(3)):continue
            for face_index,face in enumerate(triangles):
                a,b,c=(local[n] for n in face)
                if any(min(a[i],b[i],c[i])>=half[i]-maximum or max(a[i],b[i],c[i])<=-half[i]+maximum for i in range(3)):continue
                depth=triangle_depth((a,b,c),half,maximum)
                if depth>maximum:maximum=depth;witness={'triangle':face_index,'tool':tool_index,'jaw':jaw_index}
    return node_depth,maximum,witness

def interpolate_frame(previous,current,t):
    vertices=[lerp(a,b,t) for a,b in zip(previous['vertices'],current['vertices'])];tools=[]
    for before,after in zip(previous['tools'],current['tools']):
        poses=[]
        for a,b in zip(before['jaw_poses'],after['jaw_poses']):
            axis=unit(lerp(a['axis'],b['axis'],t));side_raw=lerp(a['side'],b['side'],t);side=unit(sub(side_raw,scale(axis,dot(axis,side_raw))))
            poses.append({'center_m':lerp(a['center_m'],b['center_m'],t),'axis':axis,'side':side,'normal':cross(axis,side)})
        tools.append({'jaw_poses':poses})
    return vertices,tools

def finite_tree(value):
    if isinstance(value,float):return math.isfinite(value)
    if isinstance(value,list):return all(finite_tree(v) for v in value)
    if isinstance(value,dict):return all(finite_tree(v) for v in value.values())
    return True

def audit_trajectory(path,swept_samples=3):
    path=pathlib.Path(path);max_node=0.;max_surface=0.;max_swept_node=0.;max_swept_surface=0.;max_cpp_error=0.;count=0;previous=None;worst=None;worst_swept=None;swept_count=0;errors=[];states_healthy=True;motion=0.;case=None
    with path.open(encoding='utf-8-sig') as f:
        mesh=json.loads(next(f));triangles=mesh['triangles'];half=mesh['jaw_half_extents_m'];n=len(mesh['rest_vertices']);case=mesh['case_id']
        if not finite_tree(mesh):raise ValueError('Nonfinite mesh metadata')
        if len(half)!=3 or any(abs(a-b)>1e-12 for a,b in zip(half,(.00725,.00125,.0007))):raise ValueError('Jaw dimensions differ from physical model')
        if abs(mesh['dt_s']-1/30)>1e-12:raise ValueError('Unexpected output timestep')
        if mesh['type']!='mesh' or n<3 or not triangles or len(half)!=3 or min(half)<=0:raise ValueError('Invalid mesh header')
        for face in triangles:
            if len(face)!=3 or len(set(face))!=3 or any(type(i) is not int or not 0<=i<n for i in face):raise ValueError('Invalid surface topology')
        for line in f:
            frame=json.loads(line)
            if not finite_tree(frame):raise ValueError('Nonfinite raw geometry')
            if frame['type']!='collision_frame' or len(frame['vertices'])!=n or len(frame['tools'])!=2:raise ValueError('Invalid frame')
            if frame['frame']!=count-1 or frame['step_index']!=count:raise ValueError('Missing/reordered frame')
            if abs(frame['time_s']-count*mesh['dt_s'])>1e-6:raise ValueError('Unexpected timebase')
            states_healthy &= frame['healthy'] and frame['safety_stops']==0 and frame['min_tet_volume_ratio']>0 and frame['min_triangle_area_ratio']>0
            node,surface,witness=geometry_depth(frame['vertices'],triangles,frame['tools'],half)
            max_node=max(max_node,node);max_surface=max(max_surface,surface);max_cpp_error=max(max_cpp_error,abs(surface-frame['surface_depth_m']))
            if worst is None or surface>worst['surface_depth_m']:worst={'frame':frame['frame'],'phase':frame['phase'],'surface_depth_m':surface,'witness':witness}
            if previous:
                motion+=norm(sub(frame['actual_tip_m'],previous['actual_tip_m']))
                for sample in range(1,swept_samples+1):
                    t=sample/(swept_samples+1);vertices,tools=interpolate_frame(previous,frame,t);sn,ss,sw=geometry_depth(vertices,triangles,tools,half);swept_count+=1
                    max_swept_node=max(max_swept_node,sn);max_swept_surface=max(max_swept_surface,ss)
                    if worst_swept is None or ss>worst_swept['surface_depth_m']:worst_swept={'previous_frame':previous['frame'],'current_frame':frame['frame'],'fraction':t,'phase':frame['phase'],'surface_depth_m':ss,'witness':sw}
            previous=frame;count+=1
    if count<2:raise ValueError('No motion trajectory')
    checks={'raw_states_healthy':bool(states_healthy),'node_depth_within_0_15mm':max_node<=NODE_TOLERANCE,'surface_depth_within_0_15mm':max_surface<=SURFACE_TOLERANCE,'native_surface_metric_matches':max_cpp_error<=5e-8,'sampled_swept_node_depth_within_0_15mm':max_swept_node<=NODE_TOLERANCE,'sampled_swept_surface_depth_within_0_15mm':max_swept_surface<=SURFACE_TOLERANCE,'actual_tool_motion_over_25mm':motion>=.025}
    return {'id':case,'trajectory_file':path.name,'trajectory_sha256':sha(path),'frame_count':count,'checks':checks,'passed':all(checks.values()),'metrics':{'max_node_depth_m':max_node,'max_surface_depth_m':max_surface,'max_sampled_swept_node_depth_m':max_swept_node,'max_sampled_swept_surface_depth_m':max_swept_surface,'max_native_surface_metric_error_m':max_cpp_error,'swept_sample_count':swept_count,'actual_tool_travel_m':motion},'worst_output_state':worst,'worst_sampled_sweep':worst_swept}

def audit_matrix(matrix_path,swept_samples=3,workers=1):
    if swept_samples<3:raise ValueError('Acceptance needs at least three sweep samples')
    matrix_path=pathlib.Path(matrix_path).resolve();matrix=json.loads(matrix_path.read_text(encoding='utf-8-sig'));root=matrix_path.parent
    paths=[]
    for case in matrix['cases']:
        path=(root/case['trajectory_file']).resolve()
        if not path.is_relative_to(root):raise ValueError('External trajectory path')
        paths.append(path)
    if workers>1:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:cases=list(pool.map(audit_trajectory,paths,[swept_samples]*len(paths)))
    else:cases=[audit_trajectory(p,swept_samples) for p in paths]
    report={'schema':'endoforge.collision.geometry-audit.v1','matrix_sha256':sha(matrix_path),'audit_script_sha256':sha(__file__),'test_header_sha256':sha(pathlib.Path(__file__).resolve().parents[1]/'Physics/Phase4CollisionTests.h'),'tested_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'node_tolerance_m':NODE_TOLERANCE,'surface_tolerance_m':SURFACE_TOLERANCE,'swept_samples_between_outputs':swept_samples,'surface_metric':'maximum inward min-distance to six jaw OBB faces over whole tissue triangles; eroded-box polygon intersection and bisection','sweep_scope':'quarter/mid/three-quarter samples of linear tissue vertex interpolation and interpolated orthonormal OBB poses between accepted outputs; a tunnelling screen, not continuous-time or SOFA internal-substep proof','cases':cases,'passed':bool(cases) and all(c['passed'] for c in cases)}
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--matrix',required=True,type=pathlib.Path);ap.add_argument('--output',required=True,type=pathlib.Path);ap.add_argument('--swept-samples',type=int,default=3);ap.add_argument('--workers',type=int,default=2);a=ap.parse_args()
    if a.swept_samples<3:ap.error('At least three interpolation samples are required for acceptance')
    report=audit_matrix(a.matrix,a.swept_samples,a.workers);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({'passed':report['passed'],'cases':[{'id':c['id'],'passed':c['passed'],'metrics':c['metrics']} for c in report['cases']]}));raise SystemExit(0 if report['passed'] else 2)
if __name__=='__main__':main()
