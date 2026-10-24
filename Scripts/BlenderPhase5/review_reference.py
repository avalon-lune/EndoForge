"""Read-only visual comparison of teacher's male atlas; outputs stay in tmp."""
import json
from pathlib import Path
import bpy
from mathutils import Vector

root=Path(__file__).resolve().parents[2]
reference=root/'source/full_male_anatomy_blender_anim_rigged_v1.6.3/full_male_anatomy_blender_rigged_v1.6.blend'
out=root/'tmp/phase5-reference-review';out.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(reference),use_scripts=False,load_ui=False)
selected=[]
for obj in bpy.context.scene.objects:
    keep=obj.type=='MESH' and obj.name in ('gallbladder','liver_left','liver_right','liver_ligament')
    obj.hide_render=not keep
    if keep:
        obj.hide_set(False);selected.append(obj)
        m=bpy.data.materials.new('ReadOnlyInspection_'+obj.name);m.use_nodes=True
        p=m.node_tree.nodes.get('Principled BSDF')
        p.inputs['Base Color'].default_value=(.23,.40,.12,1) if obj.name=='gallbladder' else (.38,.12,.10,1)
        p.inputs['Roughness'].default_value=.47
        obj.data.materials.clear();obj.data.materials.append(m)
inspection=bpy.data.scenes.new('TeacherAtlasInspection')
for obj in selected:
    inspection.collection.objects.link(obj)
    for modifier in obj.modifiers:modifier.show_render=False
bpy.context.window.scene=inspection
corners=[obj.matrix_world @ Vector(c) for obj in selected for c in obj.bound_box]
center=sum(corners,Vector())/len(corners)
radius=max((v-center).length for v in corners)
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=24
scene.render.resolution_x=1000;scene.render.resolution_y=800;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.film_transparent=False
world=bpy.data.worlds.new('ReadOnlyInspectionWorld');world.use_nodes=True
world.node_tree.nodes['Background'].inputs['Color'].default_value=(.07,.08,.10,1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value=.35;scene.world=world
camd=bpy.data.cameras.new('ReadOnlyInspectionCamera');cam=bpy.data.objects.new('ReadOnlyInspectionCamera',camd);scene.collection.objects.link(cam);scene.camera=cam
camd.clip_start=.0001;camd.clip_end=10;camd.type='ORTHO';camd.ortho_scale=radius*2.4
lightd=bpy.data.lights.new('ReadOnlyInspectionLight','AREA');lightd.energy=4;lightd.size=radius*2
light=bpy.data.objects.new('ReadOnlyInspectionLight',lightd);scene.collection.objects.link(light)
for label,direction in [('anterior',(0,-1,-.25)),('inferior',(0,-.25,-1))]:
    cam.location=center+Vector(direction).normalized()*radius*4
    cam.rotation_euler=(center-cam.location).to_track_quat('-Z','Y').to_euler()
    light.location=cam.location+Vector((radius,0,radius));light.rotation_euler=(center-light.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(out/f'male-reference-{label}.png');bpy.ops.render.render(write_still=True)
(out/'reference-review.json').write_text(json.dumps({'source':str(reference),'selected_objects':[o.name for o in selected],'method':'opened without scripts, rendered selected meshes with inspection material; did not save source or export mesh into EndoForge'},indent=2),encoding='utf8')
