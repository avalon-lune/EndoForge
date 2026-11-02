"""Original Phase9 anatomy. Run with installed full Blender, background Python.

Physical mesh supplied explicitly; every change needs new native qualification.
No source photographs or third-party anatomical vertices enter exported assets.
"""
import copy
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent))
import geometry
import textures
spec=importlib.util.spec_from_file_location('phase8_author',ROOT/'Scripts/BlenderPhase8/build_assets.py')
p8=importlib.util.module_from_spec(spec);spec.loader.exec_module(p8)
p7,p6,base=p8.p7,p8.p6,p8.base
OUT=ROOT/'Assets/Phase9';SOURCE=ROOT/'Assets/Phase8'


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()


def soft_omental_form(item):
    """Unequal rounded lobules and broad folds with smooth overlaps.

    The prior maximum of neighboring lobule fields introduced derivative
    creases. Weighted additive fields avoid that polygon-like ridge pattern.
    These surrounding structures remain explicitly non-contact context.
    """
    uv=np.asarray(item['uvs']);u,v=uv.T;oid=item['id']
    if oid==311:
        x=(u-.5)*.35;y=-.15+v*.32
        z=-.047+.018*(x/.175)**2+.006*((y-.03)/.16)**2
        z+=.005*np.exp(-((y+.065-.012*np.sin(x*17))/.023)**2)
        z+=.0034*np.exp(-((y-.08+.020*np.cos(x*22))/.034)**2)
    else:
        x=(u-.5)*.30;y=-.112+v*.045+.006*np.sin(2*math.pi*u)
        z=-.024+.009*v+.004*np.sin(3*math.pi*u)**2
        z+=.004*np.exp(-((v-.55-.10*np.sin(u*12))/.21)**2)
    rng=np.random.default_rng(9100+oid);lobules=np.zeros_like(u)
    for cy in np.arange(y.min()-.015,y.max()+.015,.012):
        for cx in np.arange(x.min()-.015,x.max()+.015,.012):
            px=cx+rng.uniform(-.0045,.0045);py=cy+rng.uniform(-.0045,.0045)
            rx,ry=rng.uniform(.0035,.0075,2);a=rng.uniform(-math.pi,math.pi)
            dx=(x-px)*math.cos(a)+(y-py)*math.sin(a)
            dy=-(x-px)*math.sin(a)+(y-py)*math.cos(a)
            lobules+=rng.uniform(.0011,.0030)*np.exp(-((dx/rx)**2+(dy/ry)**2)*1.3)
    density=.48+.35*np.sin(x*23+.6)**2
    interval=np.exp(-((y+.018+.014*np.sin(x*13))/.023)**2)
    z+=lobules*density*(1-.65*interval)
    return np.column_stack((x,y,z)).tolist()


def run():
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    if '--mesh' not in args:raise ValueError('Pass an explicit reviewed --mesh; no diagnostic mesh is selected implicitly.')
    meshpath=Path(args[args.index('--mesh')+1])
    mesh=json.loads(meshpath.read_text());OUT.mkdir(parents=True,exist_ok=True)
    before={p.relative_to(SOURCE).as_posix():sha(p) for p in SOURCE.rglob('*') if p.is_file()}
    (OUT/'physics-mesh.json').write_bytes(meshpath.read_bytes())
    scene=json.loads((SOURCE/'scene.json').read_text())
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE/'EndoForge_Anatomy.blend'),use_scripts=False)
    bpy.context.preferences.filepaths.save_version=0
    p8.OUT=p7.OUT=p6.OUT=base.OUT=OUT
    textures.p7,textures.p6,textures.base=p7,p6,base
    parameters=copy.deepcopy(p8.PARAMS)
    parameters['GallbladderSerosa']=([.54,.515,.455],.255,852,.38,.30,[.41,.22,.16],.34)
    parameters['HepaticCapsule']=([.45,.285,.315],.225,935,.65,.32,[.36,.12,.14],.28)
    parameters['OmentalFat']=([.70,.60,.435],.32,919,.48,.30,[.62,.38,.17],.4)
    materials={};statistics=[]
    reuse='--reuse-textures' in args
    previous=json.loads((OUT/'scene.json').read_text()) if reuse else None
    for name,values in parameters.items():
        if reuse:desc=previous['material_sets'][name];st={'name':name,'reused':True}
        else:desc,st=textures.texture_fields(name,*values)
        desc['ue_material']='/Game/Phase9/Materials/M_AnatomyPhase9'
        materials[name]=desc;statistics.append(st);p7.update_material(desc)
        print('PHASE9_MATERIAL_READY',name,flush=True)
    def visit(value):
        if isinstance(value,dict):
            for k,v in list(value.items()):
                if k in ('material','attachment_material') and isinstance(v,dict) and v.get('name') in materials:value[k]=copy.deepcopy(materials[v['name']])
                else:visit(v)
        elif isinstance(value,list):
            for v in value:visit(v)
    visit(scene);scene['material_sets']=materials
    outer=np.asarray(mesh['vertices_m'])+np.asarray(mesh['normals'])*mesh['thickness_m']*.5
    d=scene['dynamic_surface'];d.update(vertices_m=outer.tolist(),triangles=mesh['triangles'],uvs=mesh['uvs'],material_vertex_ids=list(range(len(outer))),binding='Exact outer layer of the Phase9 physical wall.')
    dyn=geometry.display_surface(outer,mesh['triangles'],mesh['uvs'])
    scene['dynamic_display']={**dyn,'id':100,'binding':'Smooth radial-saturated PN rebuilt from every accepted native state; actual displayed geometry also drives outputs.'}
    p7.replace_mesh(bpy.data.objects['Gallbladder_HighPrecision_Display'],dyn['vertices_m'],dyn['triangles'],dyn['uvs'],dyn['normals'],bpy.data.materials['GallbladderSerosa'])
    proxy=bpy.data.objects['Gallbladder_Physics_Proxy']
    p7.replace_mesh(proxy,d['vertices_m'],d['triangles'],d['uvs'],geometry.normals(outer,mesh['triangles']).tolist(),bpy.data.materials['GallbladderSerosa'])
    for g in list(proxy.vertex_groups):proxy.vertex_groups.remove(g)
    for name,ids in [('HepaticBedAttachment',mesh['attachment_vertex_ids']),('NeckConstraint',mesh['fixed_vertex_ids'])]:proxy.vertex_groups.new(name=name).add(ids,1,'REPLACE')
    ids=mesh['attachment_vertex_ids'];idset=set(ids);edges={}
    for face in mesh['triangles']:
        if all(i in idset for i in face):
            for a,b in zip(face,face[1:]+face[:1]):
                key=tuple(sorted((a,b)));edges[key]=edges.get(key,0)+1
    scene['attachment_bridge'].update(surface_material_vertex_ids=ids,anchors_m=mesh['attachment_anchor_positions_m'],anchor_bindings=mesh['attachment_anchor_bindings'],boundary_edges=[list(e) for e,n in edges.items() if n==1])
    changes=[]
    for item in scene['static_objects']:
        oid=item['id'];name='Liver_HighPrecision_Capsule' if oid==200 else item['name'];geo=item.get('display_mesh',item)
        if oid in (310,311):
            item['vertices_m']=soft_omental_form(item)
            item['normals']=geometry.normals(item['vertices_m'],item['triangles']).tolist();geo=item
            item['description']='Original Phase9 smooth unequal omental lobules and folds; non-contact contextual anatomy.'
        p7.replace_mesh(bpy.data.objects[name],geo['vertices_m'],geo['triangles'],geo['uvs'],geo['normals'],bpy.data.materials[item['material']['name']])
        item.update(p6.fbx(bpy.data.objects[name],oid));item['static_mesh_asset']=f'/Game/Phase9/Meshes/SM_{oid}.SM_{oid}'
        changes.append({'id':oid,'vertices':len(geo['vertices_m']),'triangles':len(geo['triangles']),'geometry_changed':oid in (310,311)})
    scene.update(phase=9,model_id=mesh['model_id'],version=mesh['version'],asset_revision='phase9-natural-surface-review02')
    for key in ('grasp_targets_m','home_tips_m','phase6_interaction'):
        if key in mesh:scene[key]=copy.deepcopy(mesh[key])
    scene['appearance_identity']={'id':'endoforge-phase9-natural-surface-review02','version':2,'physical_model_id':mesh['model_id'],'physical_model_version':mesh['version'],'physical_asset_sha256':sha(OUT/'physics-mesh.json')}
    scene['phase9_render']=scene.pop('phase8_render');scene['phase9_render'].update(schema='endoforge.phase9.render_profile.v1',id='phase9-common-natural-tissue-v1')
    scene['phase9_material_profile']=scene.pop('phase8_material_profile');scene['phase9_material_profile']['schema']='endoforge.phase9.subsurface-profile.v1'
    scene['appearance_notes']=[
        'Phase9 original asymmetric refined physical gallbladder; all mechanics require fresh qualification.',
        'Dynamic display: smooth radial-saturated PN, at most 0.12 mm from current physical triangles; support-welded normals of actual displayed triangles.',
        'Original multiscale tissue colour/finish; smooth non-contact omental lobules, no baked lighting or photographed pixels.',
        'Liver physical and bounded display geometry are retained from Phase8; new attachment points bind to its actual triangles.',
        'Synthetic local anatomy and engineering mechanical/optical parameters; clinical calibration and human visual approval pending.']
    (OUT/'scene.json').write_text(json.dumps(scene,separators=(',',':'))+'\n')
    names={p.name for p in (OUT/'textures').glob('*.png')}
    for image in list(bpy.data.images):
        if image.source=='FILE':
            if image.users==0:bpy.data.images.remove(image)
            elif Path(bpy.path.abspath(image.filepath)).name in names:image.filepath='//textures/'+Path(bpy.path.abspath(image.filepath)).name
    bpy.context.scene['phase9_scope']='Original anatomy revision; UE diagnostics and new physical qualification required.'
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'EndoForge_Anatomy.blend'),relative_remap=False)
    assert before=={p.relative_to(SOURCE).as_posix():sha(p) for p in SOURCE.rglob('*') if p.is_file()},'Phase8 assets changed'
    dependencies=[Path(__file__),Path(geometry.__file__),Path(textures.__file__),Path(p8.__file__),Path(p7.__file__),Path(p6.__file__),Path(base.__file__)]
    report={'schema':'endoforge.phase9.provenance.v1','creator':'Avalon / EndoForge','source_assets_unchanged':True,'physical_geometry_changed':True,'physics_sha256':sha(OUT/'physics-mesh.json'),'script_sha256':sha(__file__),'geometry_script_sha256':sha(Path(geometry.__file__)),'authoring_dependencies_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in dependencies},'source_assets_sha256':before,'dynamic_display':{'vertices':len(dyn['vertices_m']),'triangles':len(dyn['triangles']),'max_offset_m':dyn['measured_max_offset_m']},'static_changes':changes,'texture_statistics':statistics,'acceptance':'PENDING actual UE review and new native qualification','files':{p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='provenance.json'}}
    (OUT/'provenance.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PHASE9_ASSETS_CREATED',OUT,flush=True)


if __name__=='__main__':run()
