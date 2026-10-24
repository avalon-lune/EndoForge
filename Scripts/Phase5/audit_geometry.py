"""Independent topology/scale audit of the authored Phase 5 physics source."""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path


def sub(a,b): return [x-y for x,y in zip(a,b)]
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
def norm(a): return math.sqrt(dot(a,a))


def mesh_check(vertices, faces):
    assert vertices and faces
    assert all(len(v)==3 and all(isinstance(x,(float,int)) and math.isfinite(x) for x in v) for v in vertices)
    edges=collections.Counter(); orientations=collections.Counter(); used=set(); areas=[]; volume=0
    unique=set()
    for f in faces:
        assert len(f)==3 and len(set(f))==3 and all(type(i) is int and 0<=i<len(vertices) for i in f)
        key=tuple(sorted(f)); assert key not in unique; unique.add(key)
        a,b,c=(vertices[i] for i in f)
        area=norm(cross(sub(b,a),sub(c,a)))*.5
        assert area>1e-12, 'Degenerate triangle'
        areas.append(area); volume+=dot(a,cross(b,c))/6
        used.update(f)
        for u,v in zip(f,f[1:]+f[:1]):
            key=tuple(sorted((u,v))); edges[key]+=1; orientations[key]+=1 if u<v else -1
    boundary=sum(n==1 for n in edges.values())
    nonmanifold=sum(n>2 for n in edges.values())
    winding=sum(n!=0 for edge,n in orientations.items() if edges[edge]==2)
    adjacency={i:set() for i in used}
    for u,v in edges: adjacency[u].add(v); adjacency[v].add(u)
    pending=set(used); components=0
    while pending:
        components+=1; stack=[pending.pop()]
        while stack:
            node=stack.pop(); connected=adjacency[node]&pending
            pending.difference_update(connected); stack.extend(connected)
    return {'vertex_count':len(vertices),'triangle_count':len(faces),
            'boundary_edges':boundary,'nonmanifold_edges':nonmanifold,
            'inconsistent_winding_edges':winding,'unused_vertices':len(vertices)-len(used),
            'connected_components':components,
            'signed_volume_m3':volume,'minimum_triangle_area_m2':min(areas),
            'bounds_m':[[min(v[k] for v in vertices),max(v[k] for v in vertices)] for k in range(3)],
            'passed':boundary==0 and nonmanifold==0 and winding==0 and len(used)==len(vertices) and volume>0 and components==1}


def audit(path):
    raw=path.read_bytes(); data=json.loads(raw)
    assert data['schema']=='endoforge.anatomy-mesh.v1' and data['units']=='m'
    v=data['vertices_m']; faces=data['triangles']; normals=data['normals']; thickness=data['thickness_m']
    gall=mesh_check(v,faces)
    liver=mesh_check(data['static_liver']['vertices_m'],data['static_liver']['triangles'])
    assert len(normals)==len(v) and all(abs(norm(n)-1)<1e-5 for n in normals)
    assert .0003<=thickness<=.005
    fixed=data['fixed_vertex_ids']; attached=data['attachment_vertex_ids']; anchors=data['attachment_anchor_positions_m']
    assert fixed and attached and len(attached)==len(anchors)
    assert len(set(fixed))==len(fixed) and len(set(attached))==len(attached)
    assert all(type(i) is int and 0<=i<len(v) for i in fixed+attached)
    assert len(data['grasp_targets_m'])==len(data['home_tips_m'])==2
    assert all(len(p)==3 and all(math.isfinite(x) for x in p) for p in anchors+data['grasp_targets_m']+data['home_tips_m'])
    # Independently reconstruct the documented two-layer prism discretization.
    outer=[[p[k]+n[k]*thickness*.5 for k in range(3)] for p,n in zip(v,normals)]
    inner=[[p[k]-n[k]*thickness*.5 for k in range(3)] for p,n in zip(v,normals)]
    bindings=data['attachment_anchor_bindings']; assert len(bindings)==len(anchors)
    lv=data['static_liver']['vertices_m']; lf=data['static_liver']['triangles']
    errors=[]; rest_gaps=[]
    for material,anchor,binding in zip(attached,anchors,bindings):
        tri=binding['triangle_id']; weights=binding['barycentric']
        assert type(tri) is int and 0<=tri<len(lf)
        assert len(weights)==3 and all(math.isfinite(w) and -1e-9<=w<=1+1e-9 for w in weights) and abs(sum(weights)-1)<1e-9
        reconstructed=[sum(weights[k]*lv[lf[tri][k]][axis] for k in range(3)) for axis in range(3)]
        errors.append(norm(sub(anchor,reconstructed))); rest_gaps.append(norm(sub(outer[material],anchor)))
    assert max(errors)<=1e-8, 'Attachment anchor is not on its actual hepatic triangle'
    assert min(rest_gaps)>=.00045 and max(rest_gaps)<=.002, 'Bed connection must be apposed within the declared local rest gap'
    volumes=[]
    for face in faces:
        A,B,C=sorted(face)
        for tet in ((inner[A],inner[B],inner[C],outer[C]),
                    (inner[A],inner[B],outer[B],outer[C]),
                    (inner[A],outer[A],outer[B],outer[C])):
            a,b,c,d=tet
            volumes.append(abs(dot(sub(b,a),cross(sub(c,a),sub(d,a))))/6)
    assert min(volumes)>1e-15, 'Degenerate wall tetrahedron'
    return {'schema':'endoforge.phase5.independent-geometry.v1',
            'asset_sha256':hashlib.sha256(raw).hexdigest(),'model_id':data['model_id'],
            'gallbladder_middle_surface':gall,'static_liver':liver,
            'wall_thickness_mm':thickness*1000,'wall_tetrahedra':len(volumes),
            'minimum_rest_tet_volume_m3':min(volumes),'total_wall_volume_m3':sum(volumes),
            'fixed_material_vertices':len(fixed),'attached_material_vertices':len(attached),
            'maximum_anchor_binding_error_m':max(errors),
            'attachment_rest_gap_range_mm':[min(rest_gaps)*1000,max(rest_gaps)*1000],
            'passed':gall['passed'] and liver['passed'],
            'limits':'Topology/scale/wall-prism audit only; does not establish self-intersection freedom, clinical anatomy or material calibration.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--mesh',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=audit(args.mesh)
    result['audit_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 1)
