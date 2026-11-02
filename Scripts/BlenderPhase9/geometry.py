"""Original Phase9 geometry and diagnostics, usable outside Blender.

All coordinates are metres. Reference photographs inform anatomy only; no
photograph or atlas vertices are consumed. Physical changes require new tests.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def normals(p, f):
    p, f = np.asarray(p, float), np.asarray(f, int)
    area = np.cross(p[f[:, 1]]-p[f[:, 0]], p[f[:, 2]]-p[f[:, 0]])
    n = np.zeros_like(p)
    for k in range(3): np.add.at(n, f[:, k], area)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-15)


def surface(theta, phi, sculpt=1.0):
    """Asymmetric broad fundus/body and a tapered, gently curved neck.

    Coherent broad shoulder fields live on the exposed wall; the posterior bed
    stays near its qualified macroform. No stochastic geometry or tiny bumps.
    """
    t = (1-math.cos(theta))*.5
    st = math.sin(theta)
    x = .0035*t*t
    y = -.035 + .060*t
    z = .022 + .004*t
    rx = .018*st*(1-.63*t)
    rz = .012*st*(1-.35*t)
    exposed = (.5+.5*math.sin(phi))**2
    taper = st**2
    # Two broad unequal shoulders and an oblique shallow hollow; not a sphere
    # deformed by random noise. These are authored engineering shape choices.
    shoulder = .00105*math.exp(-((t-.28)/.19)**2)*math.cos(phi-.55)
    shoulder -= .00072*math.exp(-((t-.63)/.16)**2)*math.cos(phi+.35)
    gentle = .00038*math.sin(2*phi+2.2*t)*math.exp(-((t-.46)/.27)**2)
    radial = sculpt*exposed*taper*(shoulder+gentle)
    x += sculpt*.00065*taper*exposed*math.sin(1.5*math.pi*t)
    y += sculpt*.00048*taper*exposed*math.cos(phi+.6)
    return [x+(rx+radial)*math.cos(phi), y,
            z+(rz+radial*.75)*math.sin(phi)]


def radial(rings, sides, sculpt, ring_sides=None):
    if ring_sides:
        assert len(ring_sides)==rings-1
        p=[surface(0,0,sculpt)];uv=[[.5,0]];rows=[]
        for j,count in enumerate(ring_sides,1):
            rows.append(list(range(len(p),len(p)+count)))
            for k in range(count):
                p.append(surface(math.pi*j/rings,math.tau*k/count,sculpt));uv.append([k/count,j/rings])
        end=len(p);p.append(surface(math.pi,0,sculpt));uv.append([.5,1])
        f=[[0,rows[0][k],rows[0][(k+1)%len(rows[0])]] for k in range(len(rows[0]))]
        for a,b in zip(rows,rows[1:]):
            i=j=0;na,nb=len(a),len(b)
            while i<na or j<nb:
                ai,bj=a[i%na],b[j%nb]
                aa,bb=(i+1)*nb,(j+1)*na
                if aa==bb:
                    f.extend([[ai,bj,b[(j+1)%nb]],[ai,b[(j+1)%nb],a[(i+1)%na]]]);i+=1;j+=1
                elif aa<bb:f.append([ai,bj,a[(i+1)%na]]);i+=1
                else:f.append([ai,bj,b[(j+1)%nb]]);j+=1
        f.extend([rows[-1][k],end,rows[-1][(k+1)%len(rows[-1])]] for k in range(len(rows[-1])))
        p,f=np.asarray(p),np.asarray(f)
        if np.einsum('ij,ij->i',p[f[:,0]],np.cross(p[f[:,1]],p[f[:,2]])).sum()<0:f=f[:,[0,2,1]]
        return p,f,np.asarray(uv)
    p=[surface(0,0,sculpt)]; uv=[[.5,0.0]]
    for j in range(1,rings):
        for k in range(sides):
            p.append(surface(math.pi*j/rings,math.tau*k/sides,sculpt))
            uv.append([k/sides,j/rings])
    end=len(p);p.append(surface(math.pi,0,sculpt));uv.append([.5,1])
    ix=lambda j,k:1+(j-1)*sides+k%sides
    f=[]
    for k in range(sides):f.append([0,ix(1,k),ix(1,k+1)])
    for j in range(1,rings-1):
        for k in range(sides):
            a,b,c,d=ix(j,k),ix(j,k+1),ix(j+1,k),ix(j+1,k+1)
            f.extend([[a,c,d],[a,d,b]])
    for k in range(sides):f.append([ix(rings-1,k),end,ix(rings-1,k+1)])
    p,f=np.asarray(p),np.asarray(f)
    volume=np.einsum('ij,ij->i',p[f[:,0]],np.cross(p[f[:,1]],p[f[:,2]])).sum()/6
    if volume<0:f=f[:,[0,2,1]]
    return p,f,np.asarray(uv)


def liver_height_bind(xy, liver):
    """Highest actual liver triangle below/above this XY, with exact binding."""
    p=np.asarray(liver['vertices_m']);f=np.asarray(liver['triangles']);tri=p[f]
    a=tri[:,0,:2];b=tri[:,1,:2]-a;c=tri[:,2,:2]-a;d=np.asarray(xy)-a
    den=b[:,0]*c[:,1]-b[:,1]*c[:,0]
    valid=np.abs(den)>1e-14
    u=np.divide(d[:,0]*c[:,1]-d[:,1]*c[:,0],den,out=np.full_like(den,-9),where=valid)
    v=np.divide(b[:,0]*d[:,1]-b[:,1]*d[:,0],den,out=np.full_like(den,-9),where=valid)
    valid&=(u>=-1e-9)&(v>=-1e-9)&(u+v<=1+1e-9)
    ids=np.flatnonzero(valid)
    if len(ids)==0:raise ValueError('No liver support under attachment')
    z=tri[:,0,2]*(1-u-v)+tri[:,1,2]*u+tri[:,2,2]*v
    face=int(ids[np.argmax(z[ids])]);w=np.array([1-u[face]-v[face],u[face],v[face]])
    return (w@tri[face]).tolist(),{'triangle_id':face,'barycentric':w.tolist()}


def curvature_report(p, f, cap=.00012):
    """Measure PN offset demand at barycentric samples, before any clamp."""
    n=normals(p,f);p=np.asarray(p);f=np.asarray(f)
    largest=0.;total=0;clamped=0
    for i in range(9):
        for j in range(9-i):
            u,v=i/8,j/8;w=1-u-v
            linear, curved=pn(p,n,f,np.array([u,v,w]))
            d=np.linalg.norm(curved-linear,axis=1)
            largest=max(largest,float(d.max()));total+=len(d);clamped+=int((d>cap).sum())
    edges={}
    area=np.cross(p[f[:,1]]-p[f[:,0]],p[f[:,2]]-p[f[:,0]])
    face_n=area/np.maximum(np.linalg.norm(area,axis=1,keepdims=True),1e-15)
    for k,t in enumerate(f):
        for a,b in zip(t,np.roll(t,-1)):edges.setdefault(tuple(sorted((int(a),int(b)))),[]).append(k)
    angles=[]
    for adj in edges.values():
        if len(adj)==2:angles.append(math.degrees(math.acos(float(np.clip(face_n[adj[0]]@face_n[adj[1]],-1,1)))))
    return {'vertices':len(p),'triangles':len(f),'native_nodes':2*len(p),'native_tets':3*len(f),
            'boundary_edges':sum(len(x)==1 for x in edges.values()),'nonmanifold_edges':sum(len(x)>2 for x in edges.values()),
            'degenerate_triangles':int((np.linalg.norm(area,axis=1)<1e-12).sum()),
            'unclamped_pn_max_offset_mm':largest*1000,'hard_cap_affected_sample_fraction':clamped/max(total,1),
            'physical_adjacent_face_angle_deg_p95':float(np.percentile(angles,95)),
            'physical_adjacent_face_angle_deg_max':max(angles)}


def pn(p,n,f,bary):
    a,b,c=p[f[:,0]],p[f[:,1]],p[f[:,2]]
    na,nb,nc=n[f[:,0]],n[f[:,1]],n[f[:,2]]
    edge=lambda x,y,nx:(2*x+y-((y-x)*nx).sum(axis=1)[:,None]*nx)/3
    ab,ba,ac,ca,bc,cb=edge(a,b,na),edge(b,a,nb),edge(a,c,na),edge(c,a,nc),edge(b,c,nb),edge(c,b,nc)
    e=(ab+ba+ac+ca+bc+cb)/6;center=e+(e-(a+b+c)/3)*.5
    u,v,w=bary
    q=a*u**3+b*v**3+c*w**3+3*(ab*u*u*v+ba*u*v*v+ac*u*u*w+ca*u*w*w+bc*v*v*w+cb*v*w*w)+6*center*u*v*w
    return a*u+b*v+c*w,q


def display_surface(p,f,uv,subdivision=8,cap=.00012):
    """Same smooth bounded PN positions and support-welded normals as UE."""
    p,f,uv=np.asarray(p),np.asarray(f,int),np.asarray(uv);n=normals(p,f)
    bary=np.array([[1-(i+j)/subdivision,i/subdivision,j/subdivision]
                   for i in range(subdivision+1) for j in range(subdivision+1-i)])
    linear=[];curved=[]
    for w in bary:
        a,b=pn(p,n,f,w);d=b-a;length=np.linalg.norm(d,axis=1)
        scale=np.divide(cap*np.tanh(length/cap),length,out=np.ones_like(length),where=length>1e-15)
        linear.append(a);curved.append(a+d*scale[:,None])
    linear=np.stack(linear,axis=1).reshape(-1,3);out=np.stack(curved,axis=1).reshape(-1,3)
    local={(i,j):k for k,(i,j) in enumerate(( (i,j) for i in range(subdivision+1) for j in range(subdivision+1-i) ))}
    faces=[]
    for i in range(subdivision):
        for j in range(subdivision-i):
            faces.append([local[i,j],local[i+1,j],local[i,j+1]])
            if i+j<subdivision-1:faces.append([local[i+1,j],local[i+1,j+1],local[i,j+1]])
    faces=(np.asarray(faces)[None]+np.arange(len(f))[:,None,None]*len(bary)).reshape(-1,3)
    chart=uv[f].copy()
    unwrap=np.ptp(chart[:,:,0],axis=1)>.5
    chart[:,:,0]+=unwrap[:,None] & (chart[:,:,0]<.5)
    for k in range(3):
        pole=(chart[:,k,1]<1e-8)|(chart[:,k,1]>1-1e-8)
        chart[pole,k,0]=(chart[pole,(k+1)%3,0]+chart[pole,(k+2)%3,0])*.5
    tex=np.einsum('wi,tij->twj',bary,chart).reshape(-1,2)
    group={};groups=[]
    for t in f:
        for w in bary:
            key=tuple(sorted((int(i),int(round(v*subdivision))) for i,v in zip(t,w) if v>1e-8))
            if key not in group:group[key]=len(group)
            groups.append(group[key])
    groups=np.asarray(groups);sums=np.zeros((len(group),3))
    area=np.cross(out[faces[:,1]]-out[faces[:,0]],out[faces[:,2]]-out[faces[:,0]])
    for k in range(3):np.add.at(sums,groups[faces[:,k]],area)
    sums/=np.maximum(np.linalg.norm(sums,axis=1,keepdims=True),1e-15)
    return {'vertices_m':out.tolist(),'triangles':faces.tolist(),'uvs':tex.tolist(),'normals':sums[groups].tolist(),
            'source_triangle_ids':np.repeat(np.arange(len(f)),len(bary)).tolist(),
            'barycentrics':np.tile(bary,(len(f),1)).tolist(),'subdivision':subdivision,
            'method':'smooth_bounded_pn_triangle_v1','max_offset_m':cap,
            'measured_max_offset_m':float(np.linalg.norm(out-linear,axis=1).max()),'locked_source_vertex_ids':[]}


def build(rings=16,sides=32,sculpt=1.0,adaptive=False):
    source=json.loads((ROOT/'Assets/Phase8/physics-mesh.json').read_text())
    ring_sides=[12,20,28,32,32,32,32,32,32,32,28,20,12] if adaptive else None
    if adaptive:rings=14;sides=32
    p,f,uv=radial(rings,sides,sculpt,ring_sides);n=normals(p,f)
    candidates=np.flatnonzero((p[:,1]>=-.006)&(p[:,1]<=.020)&(n[:,2]<-.55))
    ids=[];anchors=[];bindings=[]
    for i in candidates:
        anchor,binding=liver_height_bind(p[i,:2],source['static_liver'])
        # The preserved liver tapers away near the neck. Only apposed wall is
        # part of the bed; a long spring across that open space is not anatomy.
        gap=np.linalg.norm(p[i]+n[i]*source['thickness_m']*.5-np.asarray(anchor))
        if .00045<=gap<=.002:
            ids.append(i);anchors.append(anchor);bindings.append(binding)
    ids=np.asarray(ids,int)
    # Lumped rest surface area preserves the old total bed stiffness/damping
    # when physical resolution changes. The reference total is 31 springs.
    areas=np.linalg.norm(np.cross(p[f[:,1]]-p[f[:,0]],p[f[:,2]]-p[f[:,0]]),axis=1)*.5
    lump=np.zeros(len(p))
    for k in range(3):np.add.at(lump,f[:,k],areas/3)
    weights=lump[ids]/lump[ids].sum()*31
    data=copy.deepcopy(source)
    data.update(model_id='endoforge-gallbladder-phase9',version=1,phase=9,
                vertices_m=p.tolist(),triangles=f.tolist(),normals=n.tolist(),uvs=uv.tolist(),
                fixed_vertex_ids=[len(p)-1],attachment_vertex_ids=ids.tolist(),
                attachment_anchor_positions_m=anchors,attachment_anchor_bindings=bindings,
                attachment_vertex_weights=weights.tolist(),
                phase9_physics_output={'schema':'endoforge.phase9-physics-output.v1'},
                phase9_geometry={'schema':'endoforge.phase9.geometry.v1','rings':rings,'sides':sides,'ring_sides':ring_sides,'sculpt':sculpt,
                  'attachment_weight_sum':float(weights.sum()),'scope':'Original smooth asymmetric local anatomy. New mechanical geometry, not inherited acceptance; calibration pending.'})
    data['hepatic_bed'].update(patch_source_material_vertex_ids=ids.tolist(),construction='New Phase9 wall patch bound barycentrically to actual preserved hepatic collision triangles; lumped-area spring weights normalize total attachment stiffness.')
    report=curvature_report(p,f)
    report.update(phase=9,attachment_sites=len(ids),attachment_weights_sum=float(weights.sum()),
                  minimum_vertical_outer_wall_anchor_gap_mm=float(np.min((p[ids,2]+n[ids,2]*data['thickness_m']*.5-np.array(anchors)[:,2])*1000)),
                  accepted=False,clinical_review='pending')
    return data,report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--rings',type=int,default=16);parser.add_argument('--sides',type=int,default=32)
    parser.add_argument('--sculpt',type=float,default=1);parser.add_argument('--adaptive',action='store_true');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    data,report=build(args.rings,args.sides,args.sculpt,args.adaptive)
    raw=(json.dumps(data,separators=(',',':'))+'\n').encode();(args.output/'physics-mesh.json').write_bytes(raw)
    report['physics_sha256']=hashlib.sha256(raw).hexdigest()
    (args.output/'geometry-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
