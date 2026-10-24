"""Audit stereo exports independently using ray/triangle intersections, not raster code.

Requires NumPy and Pillow. Background and silhouette-exclusion masks are explicit;
GPU depth comparison never discards pixels merely because their error is large.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()


def expected_validity_mask(ids, geometry_depth, gpu_depth):
    """Rebuild geometric exclusions, never thresholding label error."""
    valid=np.zeros(ids.shape,dtype=bool)
    center=ids[1:-1,1:-1]
    inside=(center>0)&(ids[1:-1,:-2]==center)&(ids[1:-1,2:]==center)
    inside &= (ids[:-2,1:-1]==center)&(ids[2:,1:-1]==center)
    inside &= np.abs(geometry_depth[1:-1,:-2]-geometry_depth[1:-1,2:])<2
    inside &= np.abs(geometry_depth[:-2,1:-1]-geometry_depth[2:,1:-1])<2
    depth=gpu_depth[1:-1,1:-1]
    valid[1:-1,1:-1]=inside&np.isfinite(depth)&(depth>0)&(depth<5000)
    return valid


def intersect(origin,direction,triangles):
    e1=triangles[:,1]-triangles[:,0]; e2=triangles[:,2]-triangles[:,0]
    h=np.cross(np.broadcast_to(direction,e2.shape),e2)
    det=np.einsum('ij,ij->i',e1,h)
    safe=np.abs(det)>1e-12
    inv=np.divide(1.0,det,out=np.zeros_like(det),where=safe)
    s=origin-triangles[:,0]; u=inv*np.einsum('ij,ij->i',s,h)
    q=np.cross(s,e1); v=inv*np.einsum('ij,j->i',q,direction)
    dist=inv*np.einsum('ij,ij->i',e2,q)
    ok=safe & (u>=-1e-8) & (v>=-1e-8) & ((u+v)<=1+1e-8) & (dist>.15)
    distances=np.where(ok,dist,np.inf)
    j=int(np.argmin(distances))
    return j,distances[j]


class TriangleBVH:
    """Independent spatial acceleration; leaves retain exact triangle tests.

    Boxes only reject impossible candidates. There is no raster approximation,
    sample reduction, nearest-vertex substitution or tolerance relaxation.
    """
    def __init__(self, triangles, leaf_size=96):
        self.triangles = triangles
        self.lower = triangles.min(axis=1)
        self.upper = triangles.max(axis=1)
        self.centers = (self.lower+self.upper)*.5
        self.nodes = []

        def build(indices):
            low = self.lower[indices].min(axis=0)-1e-9
            high = self.upper[indices].max(axis=0)+1e-9
            node = len(self.nodes)
            self.nodes.append(None)
            if len(indices) <= leaf_size:
                self.nodes[node] = (low, high, -1, -1, np.sort(indices))
            else:
                spread = np.ptp(self.centers[indices], axis=0)
                axis = int(np.argmax(spread)); middle = len(indices)//2
                order = np.argpartition(self.centers[indices, axis], middle)
                left = build(indices[order[:middle]])
                right = build(indices[order[middle:]])
                self.nodes[node] = (low, high, left, right, None)
            return node
        build(np.arange(len(triangles)))

    @staticmethod
    def box_entry(origin, direction, lower, upper, nearest):
        entry, leave = .15, nearest
        for axis in range(3):
            d = direction[axis]
            if abs(d) < 1e-15:
                if origin[axis] < lower[axis] or origin[axis] > upper[axis]:
                    return np.inf
                continue
            a = (lower[axis]-origin[axis])/d
            b = (upper[axis]-origin[axis])/d
            if a > b:
                a, b = b, a
            entry = max(entry, a); leave = min(leave, b)
            if entry > leave:
                return np.inf
        return entry

    def intersect(self, origin, direction):
        nearest, index = np.inf, -1
        stack = [(0, .15)]
        while stack:
            node, entry = stack.pop()
            if entry > nearest:
                continue
            low, high, left, right, indices = self.nodes[node]
            if self.box_entry(origin, direction, low, high, nearest) == np.inf:
                continue
            if indices is not None:
                j, t = intersect(origin, direction, self.triangles[indices])
                candidate = int(indices[j])
                if t < nearest or (t == nearest and np.isfinite(t) and candidate < index):
                    index, nearest = candidate, t
            else:
                children = []
                for child in (left, right):
                    c = self.nodes[child]
                    t = self.box_entry(origin, direction, c[0], c[1], nearest)
                    if np.isfinite(t):
                        children.append((child, t))
                stack.extend(sorted(children, key=lambda item: item[1], reverse=True))
        return index, nearest


def audit_frame(frame_file):
    base=frame_file.parent; rec=json.loads(frame_file.read_text(encoding='utf-8-sig'))
    assert rec['schema'] in ('endoforge.phase5.stereo.v1', 'endoforge.phase6.stereo.v1') and rec['capture_complete'] is True
    assert rec.get('capture_hardware_ray_tracing_requested') is True
    assert type(rec.get('capture_warmup_frames')) is int and rec['capture_warmup_frames']>=8
    assert isinstance(rec.get('temporal_history'),str) and len(rec['temporal_history'])>=30
    assert 'no distortion' in rec['pixel_convention'] and 'no AA' in rec['pixel_convention']
    native=rec['native_state']
    assert native['healthy'] is True and native['safety_stops']==0
    assert rec['normal_winding_convention']=='ue_clockwise_cross_C_A_B_A'
    dynamic_id=rec['dynamic_object_id']
    manifest=(base/rec['visual_manifest']).resolve()
    assert manifest.parent==base.parent.parent.resolve() and manifest.name=='visual-manifest.json'
    assert hashlib.sha1(manifest.read_bytes()).hexdigest()==rec['visual_manifest_sha1'].lower()
    geometry=json.loads((base/rec['geometry']).read_text(encoding='utf-8-sig'))
    assert geometry['units']=='cm' and geometry['objects']
    all_tri=[]; all_ids=[]; object_ids=set()
    for obj in geometry['objects']:
        vertices=np.asarray(obj['vertices_cm'],dtype=np.float64)
        face=np.asarray(obj['triangles'],dtype=np.int64).reshape(-1,3)
        assert len(vertices)>0 and len(face)>0 and np.isfinite(vertices).all()
        assert face.min()>=0 and face.max()<len(vertices)
        assert obj['object_id']>0 and obj['object_id'] not in object_ids
        object_ids.add(obj['object_id'])
        all_tri.append(vertices[face]); all_ids.extend([obj['object_id']]*len(face))
        if obj['name']=='hepatic_attachment_visual_membrane':
            expected=np.asarray(native['attachment_segments_m'],dtype=np.float64).reshape(-1,3)*100
            assert vertices.shape==expected.shape and np.max(np.abs(vertices-expected))<1e-5
    triangles=np.concatenate(all_tri); triangle_ids=np.asarray(all_ids)
    acceleration=TriangleBVH(triangles)
    assert dynamic_id in object_ids
    assert any(o['name']=='hepatic_attachment_visual_membrane' for o in geometry['objects'])
    eyes=rec['eyes']; assert len(eyes)==2 and [e['eye'] for e in eyes]==['left','right']
    baseline=np.linalg.norm(np.asarray(eyes[1]['position_cm'])-eyes[0]['position_cm'])*10
    assert abs(baseline-5)<.0001 and abs(rec['baseline_mm']-5)<.0001
    results=[]
    for eye in eyes:
        name=eye['eye']; folder=base/name; w=eye['width']; h=eye['height']
        assert (w,h)==(640,512)
        rgb=np.asarray(Image.open(folder/'rgb.png').convert('RGB'))
        assert rgb.shape==(h,w,3) and rgb.std()>3
        depth=np.load(folder/'depth_mm.npy',allow_pickle=False)
        geo_depth=np.load(folder/'geometry_depth_mm.npy',allow_pickle=False)
        normals=np.load(folder/'geometric_normal_world.npy',allow_pickle=False)
        ids=np.load(folder/'object_id.npy',allow_pickle=False)
        validity=np.load(folder/'valid.npy',allow_pickle=False)
        assert depth.shape==geo_depth.shape==ids.shape==validity.shape==(h,w)
        assert normals.shape==(h,w,3) and depth.dtype==np.dtype('<f4')
        assert np.isfinite(geo_depth).all() and np.isfinite(normals).all()
        assert set(np.unique(ids)).issubset(object_ids|{0}) and set(np.unique(validity)).issubset({0,1})
        valid=validity.astype(bool); foreground=ids>0
        assert valid.sum()>1000 and int(valid.sum())==eye['valid_pixels'] and np.all(foreground[valid])
        assert np.isfinite(depth[valid]).all() and np.all((depth[valid]>0)&(depth[valid]<5000))
        # Reconstruct the documented geometric exclusion rule without consulting
        # GPU-versus-geometry error, so selective error rejection cannot pass.
        expected_valid=expected_validity_mask(ids,geo_depth,depth)
        assert np.array_equal(valid,expected_valid), f'Validity mask differs from geometry-only exclusion rule: {folder}'
        assert np.max(np.abs(np.linalg.norm(normals[foreground],axis=1)-1))<1e-4
        assert np.all(normals[~foreground]==0) and np.all(geo_depth[~foreground]==0)
        error=np.abs(depth[valid].astype(float)-geo_depth[valid])
        rms=float(np.sqrt(np.mean(error**2))); maximum=float(error.max()); p99=float(np.quantile(error,.99))
        # Depth agreement is a gate, not just a metric printed by the exporter.
        assert rms<=.10 and p99<=.15, f'GPU/geometry depth mismatch {folder}: rms={rms}, p99={p99}, max={maximum}'
        assert abs(rms-eye['gpu_vs_geometry_depth_rms_mm'])<.0001
        axes=np.asarray([eye['forward'],eye['right'],eye['up']],dtype=float)
        assert np.max(np.abs(axes@axes.T-np.eye(3)))<1e-5
        assert eye['fx_px']>0 and abs(eye['fx_px']-eye['fy_px'])<1e-6
        assert abs(eye['cx_px']-w/2)<1e-6 and abs(eye['cy_px']-h/2)<1e-6
        # Deterministic samples stratified by visible object, including organ/tools.
        pixels=[]
        for obj_id in np.unique(ids[valid]):
            p=np.flatnonzero(valid & (ids==obj_id))
            pixels.extend(p[np.linspace(0,len(p)-1,min(20,len(p)),dtype=int)].tolist())
        p=np.flatnonzero(valid); pixels.extend(p[np.linspace(0,len(p)-1,64,dtype=int)].tolist())
        ray_depth_error=ray_normal_error=0.0; sampled_ids=set()
        for p in sorted(set(pixels)):
            y,x=divmod(p,w)
            direction=axes[0]+((x+.5-eye['cx_px'])/eye['fx_px'])*axes[1]-((y+.5-eye['cy_px'])/eye['fy_px'])*axes[2]
            j,t=acceleration.intersect(np.asarray(eye['position_cm']),direction)
            assert np.isfinite(t) and triangle_ids[j]==ids[y,x], f'Independent ray/object mismatch: {folder} pixel={x},{y}'
            n=np.cross(triangles[j,2]-triangles[j,0],triangles[j,1]-triangles[j,0]); n/=np.linalg.norm(n)
            ray_depth_error=max(ray_depth_error,abs(t*10-float(geo_depth[y,x])))
            ray_normal_error=max(ray_normal_error,float(np.linalg.norm(n-normals[y,x])))
            sampled_ids.add(int(triangle_ids[j]))
        assert ray_depth_error<.01 and ray_normal_error<.001
        results.append({'eye':name,'valid_pixels':int(valid.sum()),'valid_fraction':float(valid.mean()),
                        'validity_rule_independently_reconstructed':True,
                        'foreground_pixels':int(foreground.sum()),'gallbladder_pixels':int((ids==dynamic_id).sum()),
                        'gpu_geometry_depth_rms_mm':rms,'gpu_geometry_depth_p99_mm':p99,'gpu_geometry_depth_max_mm':maximum,
                        'independent_ray_samples':len(set(pixels)),'ray_depth_max_error_mm':ray_depth_error,
                        'ray_normal_max_error':ray_normal_error,'ray_sampled_object_ids':sorted(sampled_ids)})
    return {'sequence':rec['sequence'],'frame':rec['frame'],'step':native['frame'],
            'simulation_id':native['simulation_id'],'state_id':native['state_id'],'time_s':native['time'],
            'model_id':native['model_id'],'model_version':native['model_version'],
            'asset_fingerprint':native['asset_fingerprint'],'frame_json_sha256':sha(frame_file),
            'capture_hardware_ray_tracing_requested':True,'capture_warmup_frames':rec['capture_warmup_frames'],
            'temporal_history':rec['temporal_history'],
            'visual_manifest_sha1':rec['visual_manifest_sha1'].lower(),
            'eyes':results,'passed':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--physics-mesh',type=Path,required=True)
    a=parser.parse_args()
    results=[audit_frame(p) for p in sorted(a.dataset.glob('*/*/frame.json'))]
    groups={}
    for r in results: groups.setdefault(r['sequence'],[]).append(r)
    assert len(groups)>=2 and all(len(items)>=12 for items in groups.values())
    assert all(len({r['step'] for r in items})>=12 for items in groups.values())
    for items in groups.values():
        assert len({r['simulation_id'] for r in items})==1
        assert all(a['step']<b['step'] and a['time_s']<b['time_s'] and a['state_id']<b['state_id'] for a,b in zip(items,items[1:]))
    assert len({(r['model_id'],r['model_version'],r['asset_fingerprint']) for r in results})==1
    raw=a.physics_mesh.read_bytes(); mesh=json.loads(raw)
    fingerprint=14695981039346656037
    for byte in raw: fingerprint=((fingerprint^byte)*1099511628211)&0xffffffffffffffff
    expected=f'fnv1a64:{fingerprint:016x}'
    assert all(r['model_id']==mesh['model_id'] and str(r['model_version'])==str(mesh['version']) and r['asset_fingerprint']==expected for r in results)
    assert len({r['visual_manifest_sha1'] for r in results})==1
    manifest_file=a.dataset/'visual-manifest.json'
    manifest=json.loads(manifest_file.read_text(encoding='utf-8-sig'))
    assert manifest['schema'] in ('endoforge.phase5.visual_manifest.v1', 'endoforge.phase6.visual_manifest.v1') and manifest['hash_algorithm']=='SHA1'
    assert manifest.get('phase')==6
    assert 'manual exposure' in manifest['exposure'] and 'no motion blur' in manifest['exposure'] and 'AA disabled' in manifest['exposure']
    assert manifest['physics_fingerprint']==expected and manifest['engine_version'] and manifest['render_build']
    assert len(manifest['asset_file_hashes'])>=23 and len(manifest['lights'])>=1
    endoscope=[light for light in manifest['lights'] if light.get('name') in ('EndoscopeLight','AnatomyEndoscopeLight')]
    assert len(endoscope)==1, 'The actual endoscope light must be identified exactly once'
    endoscope=endoscope[0]
    assert endoscope.get('class')=='SpotLightComponent' and endoscope.get('intensity_units')=='candela'
    assert type(endoscope.get('intensity')) in (int,float) and np.isfinite(endoscope['intensity']) and endoscope['intensity']>0
    assert endoscope.get('cast_shadows') is True
    for key in ('position_cm','forward','linear_color'):
        value=np.asarray(endoscope[key],dtype=float)
        assert value.shape==(3,) and np.isfinite(value).all()
    asset_dir=a.physics_mesh.parent.resolve()
    for name,expected_hash in manifest['asset_file_hashes'].items():
        asset=(asset_dir/name).resolve()
        assert asset.is_relative_to(asset_dir) and hashlib.sha1(asset.read_bytes()).hexdigest()==expected_hash.lower(),name
    report={'schema':'endoforge.phase6.dataset-audit.v1','passed':True,
            'audit_script_sha256':sha(Path(__file__)),'physics_mesh_sha256':sha(a.physics_mesh),'visual_manifest_sha256':sha(manifest_file),'frame_count':len(results),
            'sequences':{k:len(v) for k,v in groups.items()},'frames':results,
            'ray_acceleration':'independent triangle AABB hierarchy with unchanged exact leaf intersections; no ray/sample reduction',
            'validity_rule':'Exclude image borders, nonforeground/object-boundary pixels, horizontal/vertical opposite-neighbor geometric-depth changes >=2mm, and nonfinite/out-of-range GPU depth. Exact mask reconstructed independently; no depth-error-based rejection.',
            'lighting':{'recorded_lights':len(manifest['lights']),'endoscope':endoscope},
            'scope':'Frozen 640x512 stereo readiness samples. Z-depth mm; geometric normals in world axes; no distortion or motion blur. Independent rays verify sampled objects, depth and normals; GPU agreement covers all validity-mask pixels.'}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'frames':len(results),'sequences':report['sequences']}))
