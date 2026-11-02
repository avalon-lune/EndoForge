"""Independent whole-triangle closed-liver / GB rest contact audit. NumPy Python."""
import json,importlib.util,numpy as np,hashlib,time
from pathlib import Path
root=Path(__file__).resolve().parents[2];sp=importlib.util.spec_from_file_location('audit',root/'Scripts/Phase5/audit_liver_contact.py');a=importlib.util.module_from_spec(sp);sp.loader.exec_module(a)
p=root/'Assets/Phase7/physics-mesh.json';d=json.loads(p.read_text());v=np.array(d['static_liver']['vertices_m']);f=np.array(d['static_liver']['triangles']);tri=v[f]
g=np.array(d['vertices_m'])+np.array(d['normals'])*d['thickness_m']*.5;gf=np.array(d['triangles']);gt=g[gf]
report={'candidate':str(p.relative_to(root)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'closed_mesh':a.oriented_closed(v,f)}
lo=tri.min(1);hi=tri.max(1);indices=[]
for start in range(0,len(tri),400):
 stop=min(start+400,len(tri));i,j=np.nonzero(np.all((hi[start:stop,None]+1e-9>=lo[None])&(lo[start:stop,None]-1e-9<=hi[None]),axis=2));i+=start;mask=i<j
 if mask.any():indices.append(np.stack([i[mask],j[mask]],axis=1))
pairs=np.concatenate(indices);i,j=pairs.T;adj=np.any(f[i,:,None]==f[j,None,:],axis=(1,2));hit=a.pair_intersects(tri[i[~adj]],tri[j[~adj]])
ta=tri[i[adj]];tb=tri[j[adj]];ta=ta.mean(1)[:,None]+(ta-ta.mean(1)[:,None])*(1-1e-6);tb=tb.mean(1)[:,None]+(tb-tb.mean(1)[:,None])*(1-1e-6);inside=a.pair_intersects(ta,tb,tolerance=1e-11)
report['self_intersections']={'broad_pairs':len(i),'nonadjacent':int(hit.sum()),'adjacent_contracted_interiors':int(inside.sum())}
gi,li=np.nonzero(np.all((gt.max(1)[:,None]+1e-9>=lo[None])&(gt.min(1)[:,None]-1e-9<=hi[None]),axis=2));inter=a.pair_intersects(gt[gi],tri[li]);contained,error=a.winding(g,tri,v.min(0),v.max(0));clearance,tested=a.exact_clearance(g,gf,tri,v)
report['gallbladder']={'intersecting_triangle_pairs':int(inter.sum()),'contained_vertices':int(contained.sum()),'winding_error':float(error),'whole_triangle_clearance_mm':clearance*1000,'distance_pairs_tested':tested,'examples':np.stack([gi[inter],li[inter]],axis=1)[:20].tolist()}
anchors=np.array(d['attachment_anchor_positions_m']);distances=a.nearest_surface_points(anchors,tri);report['max_anchor_distance_m']=max(distances)
report['passed']=report['closed_mesh']['signed_volume_m3']>0 and not hit.any() and not inside.any() and not inter.any() and not contained.any() and clearance>.0003 and max(distances)<1e-8
(root/'Assets/Phase7/liver-geometry-check.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2));assert report['passed']
