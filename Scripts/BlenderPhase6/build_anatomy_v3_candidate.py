"""Isolated, reviewable liver-shape candidate; never promotes project assets.

blender -b --python Scripts/BlenderPhase6/build_anatomy_v3_candidate.py -- \
  --out tmp/phase6/anatomy-v3/candidate-01 [--render]

The gallbladder FEM, all anchors and every triangle intersecting the protected
hepatic-bed region are immutable. Only remote static-liver vertices and the two
noninteractive duct landmarks change. The collider and display share that new
liver shape, so the anatomy asset version and fingerprint necessarily change.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import math
import shutil
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
CURRENT=ROOT/'Assets/Phase6'


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


author=module('phase6_candidate_author',Path(__file__).with_name('build_assets.py'))
contact=module('phase6_candidate_contact_audit',ROOT/'Scripts/Phase5/audit_liver_contact.py')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
canonical=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def hull(points):
    pts=sorted(set(tuple(p) for p in points))
    def cross(o,a,b):
        e=np.asarray(a)-o;f=np.asarray(b)-o
        return e[0]*f[1]-e[1]*f[0]
    lo=[];hi=[]
    for p in pts:
        while len(lo)>=2 and cross(lo[-2],lo[-1],p)<=0:lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi)>=2 and cross(hi[-2],hi[-1],p)<=0:hi.pop()
        hi.append(p)
    return np.asarray(lo[:-1]+hi[:-1],dtype=float)


def in_convex(point,polygon):
    if len(polygon)<3:return False
    edge=np.roll(polygon,-1,axis=0)-polygon
    cross=edge[:,0]*(point[1]-polygon[:,1])-edge[:,1]*(point[0]-polygon[:,0])
    e=polygon[1]-polygon[0];f=polygon[2]-polygon[0];area=e[0]*f[1]-e[1]*f[0]
    return abs(area)>1e-15 and (np.all(cross>=-1e-14) or np.all(cross<=1e-14))


def point_segment(p,a,b):
    edge=b-a;den=np.dot(edge,edge)
    t=np.clip(np.dot(p-a,edge)/den,0,1) if den>1e-24 else 0
    return float(np.linalg.norm(p-a-t*edge))


def segment_distance(a,b,c,d):
    def orient(p,q,r):
        e=q-p;f=r-p
        return float(e[0]*f[1]-e[1]*f[0])
    o1,o2,o3,o4=orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b)
    if o1*o2<0 and o3*o4<0:return 0.
    return min(point_segment(a,c,d),point_segment(b,c,d),point_segment(c,a,b),point_segment(d,a,b))


def polygon_distance(a,b):
    if any(in_convex(p,b) for p in a) or any(in_convex(p,a) for p in b):return 0.
    return min(segment_distance(p,q,r,s) for p,q in zip(a,np.roll(a,-1,axis=0))
               for r,s in zip(b,np.roll(b,-1,axis=0)))


def smooth(t):
    t=np.clip(t,0,1)
    return t*t*t*(t*(t*6-15)+10)


def reshape_liver(physics):
    old=np.asarray(physics['static_liver']['vertices_m'],dtype=float)
    faces=np.asarray(physics['static_liver']['triangles'],dtype=np.int32)
    bed=hull(np.asarray(physics['attachment_anchor_positions_m'])[:,:2])
    # This protects whole triangle interiors, not just attachment vertices.
    # The existing shoulder is 7 mm; the requested additional margin is 20 mm.
    guard=.007+.020
    distances=np.asarray([polygon_distance(t[:,:2],bed) for t in old[faces]])
    protected_faces=np.flatnonzero(distances<=guard+1e-12)
    protected_vertices=np.unique(faces[protected_faces])
    locked=np.zeros(len(old),dtype=bool);locked[protected_vertices]=True
    # C2 taper away from the complete protected mesh. Keeping original topology
    # also keeps the existing anchor triangle IDs and barycentrics unchanged.
    distance=np.linalg.norm(old[:,None,:2]-old[protected_vertices][None,:,:2],axis=2).min(1)
    weight=smooth(distance/.025);weight[locked]=0
    x,y,z=old.T
    left=smooth((-x-.020)/.065)
    right=smooth((x-.035)/.060)
    shaped=old.copy()
    # Taper the remote side lobe in AP depth and thickness. The broad main lobe
    # remains dominant. These are original reference-guided shapes, not copies.
    shaped[:,1]=y+weight*left*(.052-y)*.30
    shaped[:,2]=z+weight*left*((-.015+(z+.015)*.40)-z)
    shaped[:,2]-=weight*right*.003*smooth((z+.030)/.045)
    # A small anterior notch and superior shallow interlobar depression remain
    # outside the protected operative support. Neither is a painted dark line.
    anterior=1-smooth((y+.006)/.050)
    notch=np.exp(-((x+.059)/.014)**2)
    shaped[:,1]+=weight*anterior*notch*.010
    superior=smooth((z+.025)/.045)
    fissure=np.exp(-((x+.057)/.010)**2)
    shaped[:,2]-=weight*superior*fissure*.003
    shaped[locked]=old[locked]
    assert np.array_equal(shaped[faces[protected_faces]],old[faces[protected_faces]])
    report={'protection_definition':'Convex XY footprint of all 31 bed anchors, plus the full 7mm shoulder and an additional 20mm margin; every intersecting original triangle is locked in full.',
            'protected_footprint_xy_m':bed.tolist(),'shoulder_width_m':.007,'additional_margin_m':.020,
            'locked_triangle_ids':protected_faces.tolist(),'locked_vertex_ids':protected_vertices.tolist(),
            'protected_triangle_positions_sha256_before':canonical(old[faces[protected_faces]].tolist()),
            'protected_triangle_positions_sha256_after':canonical(shaped[faces[protected_faces]].tolist()),
            'max_protected_triangle_corner_change_m':float(np.max(np.abs(shaped[faces[protected_faces]]-old[faces[protected_faces]]))),
            'whole_triangle_invariance_proof':'Topology and every corner of each protected triangle are identical, therefore every barycentric point in each full protected triangle is identical.',
            'maximum_remote_vertex_displacement_mm':float(np.linalg.norm(shaped-old,axis=1).max()*1000),
            'changed_vertex_count':int(np.any(shaped!=old,axis=1).sum()),
            'collider_vertex_count_unchanged':len(shaped),'collider_triangle_count_unchanged':len(faces),
            'bounds_before_m':[old.min(0).tolist(),old.max(0).tolist()],
            'bounds_after_m':[shaped.min(0).tolist(),shaped.max(0).tolist()]}
    return shaped,locked,report


def self_intersection(vertices,faces):
    triangles=vertices[faces];lo=triangles.min(1);hi=triangles.max(1)
    ia,ib=np.nonzero(np.all((hi[:,None]+1e-9>=lo[None])&(hi[None]+1e-9>=lo[:,None]),axis=2))
    keep=ia<ib;ia=ia[keep];ib=ib[keep]
    adjacent=np.any(faces[ia,:,None]==faces[ib,None,:],axis=(1,2))
    ordinary=contact.pair_intersects(triangles[ia[~adjacent]],triangles[ib[~adjacent]])
    # Adjacent triangles intentionally touch. Test their interiors after a tiny
    # barycentric contraction; report this numerical limitation explicitly.
    a=triangles[ia[adjacent]];b=triangles[ib[adjacent]]
    a=a.mean(1)[:,None]+(a-a.mean(1)[:,None])*(1-1e-6)
    b=b.mean(1)[:,None]+(b-b.mean(1)[:,None])*(1-1e-6)
    inner=contact.pair_intersects(a,b,tolerance=1e-11)
    return {'candidate_pairs':len(ia),'nonadjacent_pair_count':int((~adjacent).sum()),
            'nonadjacent_intersections':int(ordinary.sum()),'adjacent_interior_intersections':int(inner.sum()),
            'nonadjacent_tolerance_m':1e-9,'adjacent_barycentric_contraction':1e-6,
            'adjacent_tolerance_m':1e-11,'passed':not ordinary.any() and not inner.any(),
            'scope':'Every AABB-overlapping triangle pair; adjacent boundaries excluded by 1e-6 barycentric contraction. Not a claim of exact-arithmetic intersection freedom below these tolerances.'}


def bezier(points,count=97):
    a,b,c,d=np.asarray(points)
    return [(a*(1-t)**3+3*b*(1-t)**2*t+3*c*(1-t)*t*t+d*t**3).tolist() for t in np.linspace(0,1,count)]


def update_object(name,geo,material,normal=None):
    obj=bpy.data.objects[name]
    tmp=author.base.make_object('CandidateTemporary',*geo,material)
    old=obj.data;obj.data=tmp.data;bpy.data.objects.remove(tmp,do_unlink=True)
    if old.users==0:bpy.data.meshes.remove(old)
    if normal:obj.data.normals_split_custom_set_from_vertices(normal)
    return obj


def build(out,render=False):
    started=time.monotonic();out=out.resolve()
    allowed=(ROOT/'tmp/phase6/anatomy-v3').resolve()
    assert out.is_relative_to(allowed) and out!=allowed,'Candidate must be a new isolated subdirectory of tmp/phase6/anatomy-v3'
    if out.exists():raise FileExistsError('Use a fresh candidate directory to preserve earlier evidence')
    source_scene=json.loads((CURRENT/'scene.json').read_text(encoding='utf8'))
    source_physics=json.loads((CURRENT/'physics-mesh.json').read_text(encoding='utf8'))
    scene=copy.deepcopy(source_scene);physics=copy.deepcopy(source_physics)
    new_liver,locked,protection=reshape_liver(physics)
    faces=np.asarray(physics['static_liver']['triangles'])
    topology=contact.oriented_closed(new_liver,faces)
    crossing=self_intersection(new_liver,faces)
    assert topology['signed_volume_m3']>0 and crossing['passed']
    outer=np.asarray(physics['vertices_m'])+np.asarray(physics['normals'])*physics['thickness_m']*.5
    organ_faces=np.asarray(physics['triangles'])
    clearance,pairs=contact.exact_clearance(outer,organ_faces,new_liver[faces],new_liver)
    inside,ambiguity=contact.winding(outer,new_liver[faces],new_liver.min(0),new_liver.max(0))
    anchors=contact.nearest_surface_points(np.asarray(physics['attachment_anchor_positions_m']),new_liver[faces])
    assert clearance>.0003 and not inside.any() and max(anchors)<1e-10
    physics['static_liver']['vertices_m']=new_liver.tolist()
    physics['version']=source_physics['version']+1
    physics['phase6_liver_revision']={'scope':'Remote rigid liver shape only; operative bed and complete gallbladder FEM unchanged',
                                     'source_version':source_physics['version'],'protected_margin_m':.027,'clinical_review':'pending'}
    unchanged={k:canonical(source_physics[k]) for k in source_physics if k not in ('static_liver','version')}
    assert all(canonical(physics[k])==digest for k,digest in unchanged.items())
    assert physics['static_liver']['triangles']==source_physics['static_liver']['triangles']
    assert source_scene['dynamic_surface']==scene['dynamic_surface'] and source_scene['dynamic_display']==scene['dynamic_display']
    stale={'asset-contract-check.json','blend-verification.json','geometry-audit.json',
           'independent-asset-audit.json','material-revision.json','provenance.json',
           'anatomy-preview.png','README.md'}
    shutil.copytree(CURRENT,out/'Assets',ignore=lambda folder,names:stale.intersection(names))
    assets=out/'Assets';author.OUT=assets;author.base.OUT=assets
    bpy.ops.wm.open_mainfile(filepath=str(CURRENT/'EndoForge_Anatomy.blend'),use_scripts=False)
    bpy.context.preferences.filepaths.save_version=0
    # Restore any source material which Blender previously discarded because
    # its runtime-only attachment bridge is not a separate authoring object.
    sys.argv.append('--reuse-textures')
    try:
        for args in author.MATERIAL_PARAMETERS:
            if bpy.data.materials.get(args[0]) is None:author.material(*args)
    finally:sys.argv.remove('--reuse-textures')
    for image in list(bpy.data.images):
        if image.source=='FILE' and image.users==0:bpy.data.images.remove(image)
    # Rebase copied textures; no current asset or reference path is writable.
    for image in bpy.data.images:
        if image.source=='FILE':
            # pathlib on Windows interprets Blender //textures/name as a UNC
            # share, whose final name may be empty. Split Blender paths directly.
            name=image.filepath.replace('\\','/').rsplit('/',1)[-1]
            assert name and (assets/'textures'/name).is_file()
            image.filepath='//textures/'+name
    for material in bpy.data.materials:material.use_fake_user=True
    liver=next(o for o in scene['static_objects'] if o['id']==200)
    liver['vertices_m']=new_liver.tolist()
    display=author.pn_surface(liver['vertices_m'],liver['triangles'],liver['uvs'],4,locked)
    liver['display_mesh']=display
    obj=update_object('Liver_HighPrecision_Capsule',(display['vertices_m'],display['triangles'],display['uvs']),bpy.data.materials['HepaticCapsule'],display['normals'])
    for group in list(obj.vertex_groups):obj.vertex_groups.remove(group)
    protected=set(np.flatnonzero(locked));whole=[i for i,tid in enumerate(display['source_triangle_ids']) if all(v in protected for v in liver['triangles'][tid])]
    obj.vertex_groups.new(name='HepaticBedLockedDisplay').add(whole,1,'REPLACE')
    liver.update(author.fbx(obj,200))
    duct_specs=[(400,'CysticDuctLandmark',.00145,'BiliaryDuct',
                 [[.0035,.022,.025],[.008,.034,.031],[.025,.052,.009],[.038,.071,-.009]]),
                (401,'CysticArteryLandmark',.00055,'ArterialLandmark',
                 [[.0055,.019,.0245],[.013,.035,.032],[.032,.055,.011],[.044,.075,-.007]])]
    endpoints=[]
    for oid,name,radius,material,controls in duct_specs:
        pts=bezier(controls);geo=author.base.tube_mesh(pts,radius,32)
        item=next(o for o in scene['static_objects'] if o['id']==oid)
        item.update(vertices_m=geo[0],triangles=geo[1],uvs=geo[2],
                    description='Noninteractive orientation landmark with continuous curved route; terminal caps buried within organ volumes, not a simulated duct or artery.')
        item.pop('display_mesh',None)
        obj=update_object(name,geo,bpy.data.materials[material]);item.update(author.fbx(obj,oid))
        start_cap=np.asarray(geo[0][:32]+[pts[0]])
        end_cap=np.asarray(geo[0][(len(pts)-1)*32:len(pts)*32]+[pts[-1]])
        start_inside,_=contact.winding(start_cap,outer[organ_faces],outer.min(0),outer.max(0))
        end_inside,_=contact.winding(end_cap,new_liver[faces],new_liver.min(0),new_liver.max(0))
        endpoints.append({'id':oid,'start_center_m':pts[0],'end_center_m':pts[-1],
                          'all_start_cap_vertices_inside_gallbladder_volume':bool(start_inside.all()),
                          'all_end_cap_vertices_inside_liver_volume':bool(end_inside.all()),
                          'minimum_centerline_y_m':min(p[1] for p in pts),
                          'scope':'Visual landmarks only; both full cap rings and centers checked. This is not a lumen/wall junction or vascular mechanics model.'})
        assert start_inside.all() and end_inside.all()
    scene['version']=physics['version'];scene['asset_revision']='phase6-anatomy-v3-candidate'
    scene['appearance_notes'].append('Candidate static liver macroform: altered collider and display beyond the protected hepatic bed; gallbladder material mesh unchanged. Noninteractive ducts have continuous routes and buried terminal centers. Clinical anatomy review pending.')
    (assets/'scene.json').write_text(json.dumps(scene,separators=(',',':')),encoding='utf8')
    (assets/'physics-mesh.json').write_text(json.dumps(physics,separators=(',',':')),encoding='utf8')
    bpy.ops.wm.save_as_mainfile(filepath=str(assets/'EndoForge_Anatomy.blend'),relative_remap=False)
    for image in bpy.data.images:
        if image.source=='FILE':
            target=Path(bpy.path.abspath(image.filepath)).resolve()
            assert target.is_file() and target.is_relative_to(assets)
            image.reload()
    report={'schema':'endoforge.phase6.anatomy-v3-candidate.v1','passed':True,'candidate_only':True,
            'source_physics_sha256':sha(CURRENT/'physics-mesh.json'),'candidate_physics_sha256':sha(assets/'physics-mesh.json'),
            'version_before':source_physics['version'],'version_after':physics['version'],
            'unchanged_physics_field_hashes':unchanged,'all_original_fem_and_attachment_fields_identical':True,
            'gallbladder_dynamic_surface_and_display_identical':True,'liver_triangle_indices_identical':True,
            'protected_region':protection,'liver_topology':topology,'liver_self_intersection':crossing,
            'rest_clearance':{'minimum_mm':clearance*1000,'candidate_triangle_pairs':pairs,'gallbladder_vertices_inside_liver':int(inside.sum()),
                              'winding_ambiguity':ambiguity,'maximum_anchor_surface_distance_m':max(anchors)},
            'duct_landmarks':endpoints,'changed_fbx_ids':[200,400,401],
            'proposed_camera':{'position_m':[.026,-.087,.121],'target_m':[.003,.003,.019],'fov_degrees':64,
                               'scope':'Proposal only; runtime default remains root-owned.'},
            'required_before_promotion':['Independent asset and UE imported render-buffer geometry audits',
                'New physics asset fingerprint/version and compatible capture/replay metadata',
                'Full native contact, liver-intersection, endurance, replay and performance regression',
                'Actual packaged UE interaction, four-view visual review and dataset/snapshot audit'],
            'clinical_anatomy_validated':False,'render_scope':'Offline Blender comparison only; not runtime or performance acceptance.',
            'elapsed_seconds_before_render':time.monotonic()-started}
    (out/'candidate-report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    shutil.copyfile(CURRENT/'anatomy-preview.png',out/'before-same-camera.png')
    if render:
        s=bpy.context.scene;s.render.filepath=str(out/'after-same-camera.png');bpy.ops.render.render(write_still=True)
        shutil.copyfile(out/'after-same-camera.png',assets/'anatomy-preview.png')
        cam=s.camera;previous=cam.location.copy();cam.location=report['proposed_camera']['position_m'];target=Vector(report['proposed_camera']['target_m'])
        cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
        for light in (o for o in bpy.data.objects if o.type=='LIGHT'):
            light.location+=cam.location-previous
            light.rotation_euler=(target-light.location).to_track_quat('-Z','Y').to_euler()
        s.render.filepath=str(out/'after-proposed-camera.png');bpy.ops.render.render(write_still=True)
    (assets/'README.md').write_text('Isolated Phase 6 anatomy v3 candidate. Not accepted or promoted.\n'
        'Gallbladder FEM and full protected hepatic bed are unchanged; remote liver collider/display and two noninteractive duct landmarks are revised.\n'
        'The new asset version/fingerprint requires native, replay, UE import, package and dataset validation. See ../candidate-report.json.\n'
        'Blender previews are offline comparisons, not UE performance evidence or clinical anatomical validation.\n',encoding='utf8')
    provenance={'schema':'endoforge.phase6.anatomy-candidate-provenance.v1','candidate_only':True,
                'script_sha256':sha(__file__),'author_helpers_sha256':sha(Path(__file__).with_name('build_assets.py')),
                'source_scene_sha256':sha(CURRENT/'scene.json'),'source_physics_sha256':sha(CURRENT/'physics-mesh.json'),
                'source_blend_sha256':sha(CURRENT/'EndoForge_Anatomy.blend'),
                'reference_policy':'Existing teacher-reference previews were inspected; no third-party mesh or photograph pixels imported.',
                'files':{p.relative_to(assets).as_posix():sha(p) for p in sorted(assets.rglob('*')) if p.is_file()}}
    (assets/'provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf8')
    print('PHASE6_ANATOMY_CANDIDATE_COMPLETE',json.dumps({'candidate':str(out),'passed':True,'elapsed_seconds':time.monotonic()-started,
           'locked_faces':len(protection['locked_triangle_ids']),'changed_vertices':protection['changed_vertex_count']}),flush=True)


if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);parser.add_argument('--render',action='store_true')
    options=parser.parse_args(args);build(ROOT/options.out,options.render)
