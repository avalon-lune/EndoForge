"""Original shared Phase8 look-development assets; run with installed Blender.

Reads the frozen Phase7 scene. Never writes to earlier phases. Physical contact
geometry stays byte-identical; non-contact duct/artery landmarks are reauthored.
Textures are original mathematical pigment/finish fields, not photographed truth.
"""
import copy
import hashlib
import importlib.util
import json
import math
import shutil
import sys
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'Assets/Phase7'
OUT = ROOT / 'Assets/Phase8'
spec = importlib.util.spec_from_file_location('phase7_author', ROOT / 'Scripts/BlenderPhase7/build_assets.py')
p7 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p7)
p6, base = p7.p6, p7.base
sys.path.insert(0, str(ROOT / 'Scripts/BlenderPhase7'))
sys.path.insert(0, str(Path(__file__).parent))
from vascular import vascular_fields

PHYSICS_SHA = '9405cfab1fb00e36290b242579d8ce4f085f6fa4505228aee72f723770a0de38'
PARAMS = {
    'GallbladderSerosa': ([.61, .565, .475], .235, 852, .72, .32, [.41, .22, .16], .34),
    'HepaticCapsule': ([.515, .335, .355], .205, 835, .94, .32, [.36, .12, .14], .28),
    'PeritonealLining': ([.52, .365, .375], .30, 813, .65, .30, [.42, .22, .20], .30),
    'OmentalFat': ([.77, .62, .385], .30, 819, .72, .30, [.62, .38, .17], .40),
    'HepaticBedConnective': ([.50, .365, .34], .30, 828, .68, .30, [.44, .24, .20], .28),
    'BiliaryDuct': ([.57, .50, .395], .29, 838, .65, .30, [.42, .26, .17], .30),
    'ArterialLandmark': ([.46, .235, .245], .28, 825, .45, .30, [.37, .13, .14], .24),
}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def texture_fields(name, color, roughness, seed, strength, specular, scatter, opacity):
    """Independent pigment and microsurface fields in material coordinates.

    Broad color variation, buried vascular fringe, tapering fine vessels and
    capsule fibers use distinct spatial bands. No baked shading or high-frequency
    displacement. Nominal feature scales are authoring choices, not calibration.
    """
    size = 4096 if name in ('GallbladderSerosa', 'HepaticCapsule') else 2048
    def noise(grid, offset): return p6.periodic_noise(size, grid, seed + offset)
    low, broad, mid, fine = noise(5, 0), noise(13, 1), noise(51, 2), noise(180, 3)
    yy, xx = np.mgrid[:size, :size].astype(np.float32) / size
    # Different lengths and directions avoid a uniform vascular grid.
    major, buried = vascular_fields(2048, seed + 70, amount=5 if name == 'GallbladderSerosa' else 9, width_scale=2.0, length_scale=1 if name == 'GallbladderSerosa' else .48)
    minor, soft = vascular_fields(2048, seed + 119, amount=7, width_scale=.34, length_scale=.55)
    if size!=2048:
        major,buried,minor,soft=[p7.resize_bilinear(a,size) for a in (major,buried,minor,soft)]
    tint = np.broadcast_to(np.asarray(color, np.float32), (size, size, 3)).copy()
    tint += ((mid - .5) * .035 + (fine - .5) * .015)[:, :, None] * [1, .85, .78]
    def mix(target, weight):
        nonlocal tint
        a = np.clip(weight, 0, 1).astype(np.float32)[:, :, None]
        tint = tint * (1-a) + np.asarray(target, np.float32) * a
    # Soft irregular striae interrupt broad smooth areas without cell outlines.
    phase = xx * math.tau * 67 + 9 * (broad-.5) + 5 * np.sin(yy * math.tau * 3)
    fibers = np.exp(-((np.sin(phase) / .19) ** 2)) * np.clip((low-.40) * 3, 0, .8)
    if name == 'GallbladderSerosa':
        mix([.69, .625, .46], np.clip((low-.32)*1.0, 0, .25))
        mix([.625, .445, .43], np.clip((broad-.38)*1.4, 0, .30))
        mix([.48, .515, .455], np.clip((.48-low)*1.2, 0, .18))
        mix([.77, .70, .58], fibers * .025)
        mix([.48, .275, .29], buried * .28 + soft * .12)
        mix([.345, .135, .17], major * .78)
        mix([.43, .21, .245], minor * .45)
        # Fade chart variation at both poles; prevent colored triangular wedges.
        polar=np.clip(np.sin(math.pi*yy)*5,0,1)[:,:,None]
        tint=tint*polar+np.asarray(color,np.float32)*(1-polar)
    elif name == 'HepaticCapsule':
        mix([.54, .35, .36], np.clip((low-.28)*1.3, 0, .35))
        mix([.38, .205, .27], np.clip((.56-broad)*1.3, 0, .35))
        # Pale connective branches, a capsule pattern rather than skin pores.
        net,fringe,_=p7.cellular_fields(1024,31,seed+410)
        net=p7.resize_bilinear(net,size);fringe=p7.resize_bilinear(fringe,size)
        coverage=np.clip((low-.39)*3.0,0,.65)*(.25+.75*broad)
        mix([.68, .51, .51], (fringe*.14+net*.14)*coverage+buried*.17+major*.15)
        mix([.59, .42, .43], fibers * .025)
    elif name == 'OmentalFat':
        mix([.88, .745, .51], np.clip((low-.27)*1.8, 0, .55))
        mix([.64, .365, .285], np.clip((broad-.48)*1.8, 0, .32))
        mix([.52, .245, .23], buried * .20 + major * .48 + minor * .27)
    elif name == 'PeritonealLining':
        mix([.65, .515, .405], np.clip((low-.22)*1.4, 0, .55))
        mix([.365, .275, .385], np.clip((broad-.40)*1.9, 0, .44))
        mix([.66, .54, .50], fibers * .12)
        mix([.40, .175, .225], buried * .18 + major * .60 + minor * .36)
    elif name == 'HepaticBedConnective':
        mix([.63, .49, .425], np.clip((low-.28)*1.5, 0, .42))
        mix([.40, .235, .265], np.clip((broad-.46)*1.5, 0, .35))
        mix([.72, .60, .53], fibers * .25)
        mix([.34, .13, .165], buried * .22 + major * .55 + minor * .35)
    else:
        mix(np.asarray(color)*.77, np.clip((broad-.25)*.6, 0, .3))
        mix([.41, .205, .215], major * .35 + minor * .16)
        mix([.68, .56, .465], fibers * .12)
    folder = OUT / 'textures'; folder.mkdir(parents=True, exist_ok=True)
    paths = {k: f'textures/{name}_{suffix}.png' for k, suffix in [('base_color_texture','base'),('roughness_texture','roughness'),('normal_texture','normal')]}
    base.write_png(OUT / paths['base_color_texture'], tint)
    stats = {'name': name, 'seed': seed, 'base_mean_srgb': tint.mean((0,1)).tolist(), 'base_std_srgb': tint.std((0,1)).tolist()}
    del tint, major, buried, minor, soft, xx, yy
    # At 2048 texels, sample these resolved microstructures without a very large
    # normal amplitude. Their finite slopes break a perfectly plastic highlight.
    if size == 4096:
        low, broad, mid, fine, fibers = [a[::2, ::2] for a in (low,broad,mid,fine,fibers)]
    micro = p6.periodic_noise(2048, 405, seed + 30)
    rough = np.clip(roughness + (broad-.5)*.135 + (mid-.5)*.105 + (fine-.5)*.06 + fibers*.025, .13, .43)
    height = .035 * mid + .014 * fine + .0018 * micro + .001 * fibers
    if name == 'GallbladderSerosa': height *= .80
    if name == 'HepaticCapsule': height *= 1.15
    gy, gx = np.gradient(height)
    # Texture domain nominally spans 60 mm. Derivatives are deliberately modest;
    # no normal perturbation can change collision or exported geometric normals.
    normal = np.stack([-gx*80, -gy*80, np.ones_like(gx)], axis=-1)
    normal /= np.maximum(np.linalg.norm(normal, axis=-1, keepdims=True), 1e-12)
    base.write_png(OUT / paths['roughness_texture'], np.repeat(rough[:,:,None], 3, axis=2))
    base.write_png(OUT / paths['normal_texture'], normal*.5+.5)
    stats.update(roughness_min=float(rough.min()), roughness_max=float(rough.max()), maximum_tangent_normal=float(np.linalg.norm(normal[:,:,:2],axis=2).max()))
    desc = dict(name=name, base_color=color, roughness=roughness, metallic=0, specular=specular,
                subsurface_color=scatter, subsurface_opacity=opacity, subsurface_weight=.10, ior=1.38,
                normal_strength=strength, base_color_gain=[1,1,1], roughness_scale=1, roughness_bias=0,
                base_texture_resolution=size, aux_texture_resolution=2048,
                ue_material='/Game/Phase8/Materials/M_AnatomyPhase8',
                shading_model='short-distance-subsurface-profile',
                nominal_texture_span_m=.060,
                wet_surface_model='Original multiscale pigment and roughness, short-distance scattering and dual specular profile; no WPO or clinical calibration.', **paths)
    return desc, stats


def landmark(oid):
    """Closed, gently curved landmark with an overlapping tapered neck root.

    Kept outside the supported grasp zones. Non-contact reference geometry only;
    both visible rendering and output geometry use these same sampled triangles.
    """
    arterial = oid == 401
    root = np.array([.0035, .02555, .026])
    if arterial: root += [.0033, -.001, -.0007]
    direction = np.array([.019, .034, -.014]); tangent = direction / np.linalg.norm(direction)
    root -= tangent * .003
    def center(t):
        p = root + direction * t
        p += np.array([.004*math.sin(math.pi*t), -.002*math.sin(math.pi*t), .0028*math.sin(1.4*math.pi*t)])
        if arterial: p += np.array([.0012*math.sin(math.pi*t), .001*math.sin(math.pi*t), .0012*math.sin(math.pi*t)])
        return p
    def surface(theta, phi):
        t = (1-math.cos(theta))*.5
        d = center(min(t+1e-4,1))-center(max(t-1e-4,0)); d /= np.linalg.norm(d)
        u = np.cross(d,[0,0,1]); u /= np.linalg.norm(u); v = np.cross(d,u)
        radius = (.00064 if arterial else .0016) * (1 + .28*math.exp(-t*9) + .065*math.sin(t*math.tau*2))
        end = min(t,1-t) * .043
        if end < radius: radius = math.sqrt(max(0, radius*radius-(radius-end)**2))
        radial = u*math.cos(phi)+v*math.sin(phi)
        return (center(t)+radius*radial).tolist()
    return base.radial_mesh(surface, rings=96, sides=32)


def run(reuse=False, render=False):
    OUT.mkdir(parents=True, exist_ok=True)
    before = {p.relative_to(SOURCE).as_posix(): sha(p) for p in SOURCE.rglob('*') if p.is_file()}
    assert sha(SOURCE/'physics-mesh.json') == PHYSICS_SHA
    shutil.copy2(SOURCE/'physics-mesh.json', OUT/'physics-mesh.json')
    scene = json.loads((SOURCE/'scene.json').read_text(encoding='utf8'))
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE/'EndoForge_Anatomy.blend'), use_scripts=False)
    bpy.context.preferences.filepaths.save_version = 0
    p7.OUT = OUT; p6.OUT = OUT; base.OUT = OUT
    materials = {}; stats = []
    previous = json.loads((OUT/'scene.json').read_text()) if reuse else None
    for name, args in PARAMS.items():
        if reuse: desc, st = previous['material_sets'][name], {'name':name, 'reused':True}
        else: desc, st = texture_fields(name,*args)
        materials[name] = desc; stats.append(st); p7.update_material(desc)
        print('PHASE8_MATERIAL_READY',name,flush=True)
    def visit(value):
        if isinstance(value,dict):
            for key,item in list(value.items()):
                if key in ('material','attachment_material') and isinstance(item,dict) and item.get('name') in materials: value[key] = copy.deepcopy(materials[item['name']])
                else: visit(item)
        elif isinstance(value,list):
            for item in value: visit(item)
    visit(scene); scene['material_sets'] = materials
    changes=[]
    for item in scene['static_objects']:
        oid=item['id']; name='Liver_HighPrecision_Capsule' if oid==200 else item['name']
        obj=bpy.data.objects[name]; geo=item.get('display_mesh',item)
        if oid in (400,401):
            item['vertices_m'],item['triangles'],item['uvs']=landmark(oid)
            item['normals']=p7.surface_normals(item['vertices_m'],item['triangles']).tolist()
            geo=item
            item['description']='Phase8 original curved closed orientation landmark, overlapping neck root. Non-contact; not functional duct/arterial anatomy.'
        p7.replace_mesh(obj,geo['vertices_m'],geo['triangles'],geo['uvs'],geo['normals'],bpy.data.materials[item['material']['name']])
        item.update(p6.fbx(obj,oid)); item['static_mesh_asset']=f'/Game/Phase8/Meshes/SM_{oid}.SM_{oid}'
        changes.append({'id':oid,'triangles':len(geo['triangles']),'geometry_changed':oid in (400,401),'contact_geometry_changed':False})
    scene.update(phase=8, asset_revision='phase8-shared-foundation-candidate03')
    scene['appearance_identity']={'id':'endoforge-phase8-common-appearance-candidate03','version':3,'physical_asset_sha256':PHYSICS_SHA,'physical_model_id':scene['model_id'],'physical_model_version':scene['version']}
    scene['phase8_render']=scene.pop('phase7_render')
    scene['phase8_render'].update(schema='endoforge.phase8.render_profile.v1',id='phase8-short-scatter-wet-tissue-candidate03',light_intensity_cd=.16,light_source_radius_cm=.075,light_color_linear=[1,.98,.95],vignette=.04,bloom=.015)
    scene['phase8_material_profile']={'schema':'endoforge.phase8.subsurface-profile.v1','mean_free_path_distance_cm':.1,'mean_free_path_color':[.6,.288,.168],'world_unit_scale':1,'roughness0':.72,'roughness1':1.5,'lobe_mix':.35,'ior':1.38,'implementation':'separable','scope':'Synthetic short tissue-scatter authoring profile; not measured tissue optics.'}
    scene['appearance_notes'].append('Phase8 original multi-scale vascular pigment, wetness and short-distance tissue profile; reauthored non-contact neck landmarks. Qualified physical surfaces retained exactly.')
    (OUT/'scene.json').write_text(json.dumps(scene,separators=(',',':'))+'\n',encoding='utf8')
    for im in list(bpy.data.images):
        if im.source=='FILE':
            if im.users==0: bpy.data.images.remove(im)
            elif Path(bpy.path.abspath(im.filepath)).name in {p.name for p in (OUT/'textures').glob('*.png')}:
                im.filepath='//textures/'+Path(bpy.path.abspath(im.filepath)).name
    bpy.context.scene['phase8_scope']='Shared foundation candidate; original authored appearance, unchanged qualified mechanics. Actual UE review pending.'
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'EndoForge_Anatomy.blend'),relative_remap=False)
    if render:
        s=bpy.context.scene; s.render.resolution_percentage=75; s.cycles.samples=48
        s.render.filepath=str(OUT/'authoring-preview.png'); bpy.ops.render.render(write_still=True)
    assert before=={p.relative_to(SOURCE).as_posix():sha(p) for p in SOURCE.rglob('*') if p.is_file()},'Phase7 changed'
    provenance={'schema':'endoforge.phase8.provenance.v1','creator':'Avalon / EndoForge','phase7_assets_unchanged':True,'physics_sha256':PHYSICS_SHA,'physical_geometry_changed':False,'script_sha256':sha(__file__),'reference_analysis':'docs/PHASE8-CASE-STUDIES.md','geometry_changes':changes,'texture_statistics':stats,'acceptance':'NOT_ACCEPTED: actual UE appearance and integrated regression pending','limitations':['Synthetic anatomy and optical parameters; supervisor review pending.','Non-contact landmark geometry has no duct/arterial mechanics.','No source photograph or third-party mesh copied.'],'files':{p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='provenance.json'}}
    provenance['authoring_dependencies']={p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__), Path(__file__).with_name('vascular.py'), ROOT/'Scripts/BlenderPhase7/build_assets.py', ROOT/'Scripts/BlenderPhase6/build_assets.py', ROOT/'Scripts/BlenderPhase5/build_assets.py']}
    (OUT/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf8')
    print('PHASE8_ASSETS_CREATED',OUT,flush=True)


if __name__=='__main__': run('--reuse-textures' in sys.argv,'--render' in sys.argv)
