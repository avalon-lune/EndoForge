"""Integrate accepted engineering rig, lowered hilar landmark routes and camera.

Creates a fresh candidate; it never writes source/ or previous deliveries.
The hollow-wall FEM, attachment anchors and static liver remain byte-equivalent
JSON values to the supplied candidate. Duct/artery are visual landmarks only.
"""
import argparse,hashlib,importlib.util,json,shutil,sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
p=Path(__file__).with_name('build_anatomy_v3_candidate.py')
spec=importlib.util.spec_from_file_location('candidate_author',p);a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

def run(source,out,landmarks):
    source=source.resolve();out=out.resolve()
    assert source.is_relative_to(ROOT/'tmp/phase6') and out.is_relative_to(ROOT/'tmp/phase6')
    shutil.copytree(source,out)
    a.author.OUT=out;a.author.base.OUT=out
    scene=json.loads((out/'scene.json').read_text());mesh=json.loads((out/'physics-mesh.json').read_text())
    bpy.ops.wm.open_mainfile(filepath=str(out/'EndoForge_Anatomy.blend'))
    bpy.context.preferences.filepaths.save_version=0
    # Freeze complete operative triangles, including their far corners, rather
    # than freezing individual vertices and changing the neighboring face.
    previous=json.loads((ROOT/'Assets/Phase5/physics-mesh.json').read_text())
    original=np.asarray(previous['static_liver']['vertices_m']);faces=np.asarray(previous['static_liver']['triangles']);vertices=np.asarray(mesh['static_liver']['vertices_m'])
    organ_rest=np.asarray(previous['vertices_m']);near=np.linalg.norm(original[:,None,:]-organ_rest[None,:,:],axis=2).min(axis=1)<.030
    protected=np.unique(faces[np.any(near[faces],axis=1)])
    restored=int(np.sum(np.linalg.norm(vertices[protected]-original[protected],axis=1)>1e-12));vertices[protected]=original[protected]
    liver=next(o for o in scene['static_objects'] if o['id']==200);locked=np.zeros(len(vertices),dtype=bool);locked[liver['display_mesh']['locked_source_vertex_ids']]=True;locked[protected]=True
    liver['vertices_m']=vertices.tolist();mesh['static_liver']['vertices_m']=vertices.tolist()
    display=a.author.pn_surface(liver['vertices_m'],liver['triangles'],liver['uvs'],4,locked);liver['display_mesh']=display
    obj=a.update_object('Liver_HighPrecision_Capsule',(display['vertices_m'],display['triangles'],display['uvs']),bpy.data.materials['HepaticCapsule'],display['normals'])
    for group in list(obj.vertex_groups):obj.vertex_groups.remove(group)
    protected_set=set(np.flatnonzero(locked));ids=[i for i,tid in enumerate(display['source_triangle_ids']) if all(v in protected_set for v in liver['triangles'][tid])]
    obj.vertex_groups.new(name='HepaticBedLockedDisplay').add(ids,1,'REPLACE');liver.update(a.author.fbx(obj,200))
    mesh['version']=scene['version']=mesh['version']+1;scene['asset_revision']='phase6-integrated-anatomy-v'+str(mesh['version'])
    crossing=a.self_intersection(vertices,faces);assert crossing['passed'],'Static liver self intersection'
    outer=np.asarray(mesh['vertices_m'])+np.asarray(mesh['normals'])*mesh['thickness_m']*.5
    organ=np.asarray(mesh['triangles']);lv=np.asarray(mesh['static_liver']['vertices_m']);lf=np.asarray(mesh['static_liver']['triangles'])
    caps=[]
    for variant in json.loads(landmarks.read_text()):
        item=next(o for o in scene['static_objects'] if o['id']==variant['id'])
        geo=(variant['vertices_m'],variant['triangles'],variant['uvs'])
        item.update(vertices_m=geo[0],triangles=geo[1],uvs=geo[2],description='Noninteractive hilar orientation landmark. Continuous posterior/inferior course with buried terminal caps; no lumen or vascular mechanics model.')
        material=bpy.data.objects[variant['name']].data.materials[0]
        obj=a.update_object(variant['name'],geo,material);item.update(a.author.fbx(obj,variant['id']))
        pts=a.bezier(variant['controls_m']);v=np.asarray(geo[0]);start=np.vstack([v[:32],pts[0]]);end=np.vstack([v[(len(pts)-1)*32:len(pts)*32],pts[-1]])
        inside_start,_=a.contact.winding(start,outer[organ],outer.min(0),outer.max(0));inside_end,_=a.contact.winding(end,lv[lf],lv.min(0),lv.max(0))
        assert inside_start.all() and inside_end.all(),'Detached landmark cap'
        caps.append({'id':variant['id'],'controls_m':variant['controls_m'],'all_start_cap_vertices_inside_organ':True,'all_end_cap_vertices_inside_liver':True})
    s=bpy.context.scene;cam=s.camera;previous_camera=cam.location.copy();cam.location=scene['camera']['position_m'];target=Vector(scene['camera']['target_m'])
    cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
    for light in (o for o in bpy.data.objects if o.type=='LIGHT'):
        light.location+=cam.location-previous_camera;light.rotation_euler=(target-light.location).to_track_quat('-Z','Y').to_euler()
    for material in bpy.data.materials:material.use_fake_user=True
    scene['appearance_notes'].append('Final candidate: hilar orientation landmarks take a posterior/inferior course into the liver instead of arching through the working jaws; anatomy review remains pending.')
    (out/'scene.json').write_text(json.dumps(scene,separators=(',',':'))+'\n')
    (out/'physics-mesh.json').write_text(json.dumps(mesh,separators=(',',':'))+'\n')
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'EndoForge_Anatomy.blend'),relative_remap=False)
    for image in bpy.data.images:
        if image.source=='FILE':assert Path(bpy.path.abspath(image.filepath)).resolve().is_relative_to(out) and Path(bpy.path.abspath(image.filepath)).is_file()
    s.cycles.samples=64;s.render.filepath=str(out/'anatomy-preview.png');bpy.ops.render.render(write_still=True)
    sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
    core=[k for k in previous if k not in ('version','home_tips_m','static_liver')];assert all(previous[k]==mesh[k] for k in core)
    report={'schema':'endoforge.phase6.final-anatomy-candidate.v1','candidate_only':True,'clinical_anatomy_validated':False,'physics_json_sha256':sha(out/'physics-mesh.json'),'gallbladder_fem_and_attachments_unchanged':True,'restored_operative_liver_corner_count':restored,'liver_self_intersection':crossing,'landmark_caps':caps,'camera':scene['camera'],'script_sha256':sha(__file__),'source_provenance':json.loads((source/'provenance.json').read_text()),'files':{p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file() and p.name!='provenance.json'}}
    (out/'provenance.json').write_text(json.dumps(report,indent=2)+'\n')
    print('FINAL_CANDIDATE_CREATED',out)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--landmarks',type=Path,required=True)
    opts=p.parse_args(sys.argv[sys.argv.index('--')+1:]);run(ROOT/opts.source,ROOT/opts.out,ROOT/opts.landmarks)
