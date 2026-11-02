"""Author Phase 7 shared anatomy and a genuinely revised liver collider.

Run in installed Blender: -b --python Scripts/BlenderPhase7/build_assets.py -- --render
Input Phase 6 is read-only. Source images/atlas meshes are never imported.
Original appearance authoring and non-contact folds: EndoForge / Avalon.
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
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'Assets/Phase6'
OUT = ROOT / 'Assets/Phase7'
spec = importlib.util.spec_from_file_location('phase6_author', ROOT / 'Scripts/BlenderPhase6/build_assets.py')
p6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p6)
base = p6.base
PI = math.pi
sys.path.insert(0, str(Path(__file__).parent))
from organic_vessels import vascular_fields

PARAMETERS = [
    ('GallbladderSerosa', [.515, .465, .365], .255, 752, .060, .31, [.35, .235, .165], .89),
    ('HepaticCapsule', [.31, .145, .18], .245, 735, .13, .34, [.31, .105, .115], .94),
    ('PeritonealLining', [.485, .340, .355], .30, 713, .14, .36, [.36, .20, .18], .91),
    ('OmentalFat', [.725, .570, .355], .31, 719, .16, .35, [.55, .30, .12], .92),
    ('HepaticBedConnective', [.605, .460, .395], .30, 728, .15, .26, [.43, .235, .18], .90),
    ('BiliaryDuct', [.57, .495, .37], .29, 738, .17, .24, [.40, .24, .15], .93),
    ('ArterialLandmark', [.42, .165, .18], .29, 725, .12, .23, [.35, .10, .12], .94),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resize_bilinear(array, size):
    """Periodic-U interpolation, including texture-boundary continuity."""
    height, width = array.shape
    x = np.arange(size, dtype=np.float32) * width / size
    y = np.arange(size, dtype=np.float32) * (height - 1) / max(size - 1, 1)
    ix = x.astype(np.int32); iy = y.astype(np.int32)
    tx = x - ix; ty = y - iy
    a = array[iy[:, None], ix[None, :]]
    b = array[iy[:, None], (ix[None, :] + 1) % width]
    c = array[np.minimum(iy[:, None] + 1, height - 1), ix[None, :]]
    d = array[np.minimum(iy[:, None] + 1, height - 1), (ix[None, :] + 1) % width]
    return (a * (1 - tx)[None, :] + b * tx[None, :]) * (1 - ty)[:, None] + (c * (1 - tx)[None, :] + d * tx[None, :]) * ty[:, None]


def cellular_fields(size=1024, cells=22, seed=1):
    """Irregular continuous capsule/septal network, not a repeated cell stamp."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[:size, :size].astype(np.float32)
    xx = xx / size * cells; yy = yy / max(size - 1, 1) * cells
    warp_x = p6.periodic_noise(size, 7, seed + 10) - .5
    warp_y = p6.periodic_noise(size, 9, seed + 11) - .5
    xx += warp_x * 1.4; yy += warp_y * 1.2
    ix = np.floor(xx).astype(np.int32); iy = np.floor(yy).astype(np.int32)
    offsets = rng.uniform(.10, .90, (cells + 4, cells, 2)).astype(np.float32)
    nearest = np.full((size, size), 1e6, np.float32)
    second = nearest.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            cx = ix + dx; cy = iy + dy
            jitter = offsets[np.clip(cy + 1, 0, cells + 3), cx % cells]
            dist = np.sqrt((xx - cx - jitter[:, :, 0]) ** 2 + (yy - cy - jitter[:, :, 1]) ** 2)
            second = np.minimum(second, np.maximum(nearest, dist))
            nearest = np.minimum(nearest, dist)
    difference = second - nearest
    # Network widths vary along their length; no baked shading or specular.
    width = .022 + .020 * p6.periodic_noise(size, 14, seed + 12)
    net = np.exp(-(difference / width) ** 2)
    broad = np.exp(-(difference / (width * 3.5)) ** 2)
    return net.astype(np.float32), broad.astype(np.float32), nearest


def make_textures(name, color, roughness, seed, normal_strength, specular, sss_color, opacity):
    """Reference-guided original material fields. PNG color is encoded sRGB."""
    size = 4096 if name in ('GallbladderSerosa', 'HepaticCapsule') else 2048
    folder = OUT / 'textures'; folder.mkdir(parents=True, exist_ok=True)
    n0 = p6.periodic_noise(size, 5, seed)
    n1 = p6.periodic_noise(size, 23, seed + 1)
    n2 = p6.periodic_noise(size, 145, seed + 2)
    n3 = p6.periodic_noise(size, 11, seed + 3)
    net0, fringe0, cells0 = cellular_fields(1024, 37 if name == 'HepaticCapsule' else 30, seed)
    net = resize_bilinear(net0, size); fringe = resize_bilinear(fringe0, size)
    rgb = np.broadcast_to(np.asarray(color, dtype=np.float32), (size, size, 3)).copy()
    rgb += ((n1 - .5) * .045 + (n2 - .5) * .020)[:, :, None] * np.array([1, .9, .83], np.float32)
    def mix(target, alpha):
        nonlocal rgb
        alpha = np.clip(alpha, 0, 1).astype(np.float32)[:, :, None]
        rgb = rgb * (1 - alpha) + np.asarray(target, np.float32) * alpha
    vessels, buried = vascular_fields(size, seed + 54, amount=6 if name == 'GallbladderSerosa' else 9,
                                     width_scale=2.1 if name == 'GallbladderSerosa' else .9)
    # Vessels have variable opacity along their course and a blurred buried fringe.
    vessels *= .48 + .52 * n3
    if name == 'GallbladderSerosa':
        mix([.68, .54, .34], np.clip((n0 - .25) * 1.35, 0, .48))
        mix([.57, .315, .305], np.clip((n3 - .30) * 2.1, 0, .62))
        mix([.30, .38, .34], np.clip((.50 - n0) * 1.9, 0, .42))
        mix([.69, .635, .52], fringe * .025)
        mix([.53, .30, .32], buried * .36)
        mix([.36, .17, .21], vessels * .46)
    elif name == 'HepaticCapsule':
        mix([.385, .20, .22], np.clip((n0 - .24) * 1.15, 0, .43))
        mix([.25, .11, .155], np.clip((.57 - n3) * .95, 0, .38))
        # Sparse elongated, tapering connective filaments. Complete cellular
        # outlines read as reptile/cracked-leather skin rather than liver capsule.
        capsule = p6.vessel_mask(size, seed + 301, amount=8, width_scale=2.0)
        coverage = np.clip((n0 - .28) * 2.2, 0, .85) * (.30 + .70 * n3)
        capsule *= coverage
        mix([.50, .33, .35], capsule ** .32 * .105)
        mix([.54, .37, .39], capsule * .22)
        del capsule
        mix([.28, .105, .13], vessels * .12)
    elif name == 'OmentalFat':
        mix([.84, .705, .46], np.clip((n0 - .20) * 1.15, 0, .55))
        mix([.62, .36, .28], np.clip((n3 - .48) * .75, 0, .22))
        mix([.86, .745, .535], np.clip((n1 - .52) * .40, 0, .15))
        mix([.55, .29, .24], buried * .14)
        mix([.48, .205, .19], vessels * .20)
    elif name == 'PeritonealLining':
        mix([.58, .435, .34], np.clip((n0 - .21) * 1.2, 0, .52))
        mix([.35, .26, .38], np.clip((n3 - .4) * 1.1, 0, .4))
        mix([.67, .56, .49], fringe * .018 + net * .025)
        mix([.36, .13, .19], vessels * .30)
    elif name == 'HepaticBedConnective':
        mix([.73, .635, .51], np.clip((n0 - .25) * 1.2, 0, .42))
        mix([.53, .29, .29], np.clip((n3 - .43) * .85, 0, .3))
        mix([.78, .68, .57], fringe * .05 + net * .07)
        mix([.40, .19, .20], vessels * .23)
    else:
        mix(np.asarray(color) * .80, (n0 - .25) * .25)
        mix([.68, .52, .44], fringe * .08)
    paths = {key: f'textures/{name}_{suffix}.png' for key, suffix in [('base_color_texture', 'base'), ('roughness_texture', 'roughness'), ('normal_texture', 'normal')]}
    base.write_png(OUT / paths['base_color_texture'], rgb)
    color_stats = {'mean_srgb': rgb.mean(axis=(0, 1)).tolist(), 'std_srgb': rgb.std(axis=(0, 1)).tolist()}
    del rgb, vessels, buried, net, fringe, n0, n3
    if size == 4096:
        n1 = n1[::2, ::2]; n2 = n2[::2, ::2]
    aux_size = 2048
    micro = p6.periodic_noise(aux_size, 390, seed + 32)
    net = resize_bilinear(net0, aux_size); fringe = resize_bilinear(fringe0, aux_size)
    if name == 'OmentalFat': fringe = np.zeros_like(fringe)
    rough = np.clip(roughness + (n1 - .5) * .105 + (n2 - .5) * .045 + (micro - .5) * .018 + fringe * .012, .16, .43)
    # Shading relief only: small-scale serosa/capsule roughness, never WPO.
    height = n1 * .28 + n2 * .33 + micro * .14 + fringe * .025
    if name == 'GallbladderSerosa': height = n1 * .10 + n2 * .08 + micro * .025
    gy, gx = np.gradient(height)
    normal = np.stack([-gx * 6.5, -gy * 6.5, np.ones_like(height)], axis=-1)
    normal /= np.maximum(np.linalg.norm(normal, axis=-1, keepdims=True), 1e-15)
    base.write_png(OUT / paths['roughness_texture'], np.repeat(rough[:, :, None], 3, axis=2))
    base.write_png(OUT / paths['normal_texture'], normal * .5 + .5)
    desc = {'name': name, 'base_color': color, 'roughness': roughness, 'metallic': 0,
            'specular': specular, 'subsurface_color': sss_color, 'subsurface_opacity': opacity,
            'subsurface_weight': .075, 'ior': 1.38, 'normal_strength': normal_strength,
            'base_color_gain': [1, 1, 1], 'roughness_scale': 1, 'roughness_bias': 0,
            'base_texture_resolution': size, 'aux_texture_resolution': aux_size,
            'ue_material': '/Game/Phase7/Materials/M_AnatomyPhase7',
            'wet_surface_model': 'Opaque subsurface shading with spatial microfacet roughness; normals are shading-only. No displacement, baked highlights or clinical optical calibration.', **paths}
    return desc, {'name': name, **color_stats, 'roughness_min': float(rough.min()), 'roughness_max': float(rough.max()), 'seed': seed}


def update_material(desc):
    mat = bpy.data.materials.get(desc['name']) or bpy.data.materials.new(desc['name'])
    mat.use_nodes = True; mat.use_fake_user = True
    nodes = mat.node_tree.nodes; links = mat.node_tree.links
    nodes.clear(); output = nodes.new('ShaderNodeOutputMaterial'); bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    bsdf.inputs['IOR'].default_value = desc['ior']
    bsdf.inputs['Roughness'].default_value = desc['roughness']
    bsdf.inputs['Subsurface Weight'].default_value = .075
    bsdf.inputs['Subsurface Radius'].default_value = (.0012, .0006, .0003)
    bsdf.inputs['Coat Weight'].default_value = 0
    for key, target in [('base_color_texture', 'Base Color'), ('roughness_texture', 'Roughness')]:
        node = nodes.new('ShaderNodeTexImage'); node.image = bpy.data.images.load(str(OUT / desc[key]), check_existing=False)
        node.image.filepath = '//' + desc[key]
        if key != 'base_color_texture': node.image.colorspace_settings.name = 'Non-Color'
        links.new(node.outputs['Color'], bsdf.inputs[target])
    node = nodes.new('ShaderNodeTexImage'); node.image = bpy.data.images.load(str(OUT / desc['normal_texture']), check_existing=False)
    node.image.filepath = '//' + desc['normal_texture']; node.image.colorspace_settings.name = 'Non-Color'
    normal = nodes.new('ShaderNodeNormalMap'); normal.inputs['Strength'].default_value = desc['normal_strength']
    links.new(node.outputs['Color'], normal.inputs['Color']); links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def surface_normals(vertices, faces):
    p = np.asarray(vertices, dtype=float); f = np.asarray(faces, dtype=np.int32)
    normals = np.zeros_like(p); face = np.cross(p[f[:, 1]] - p[f[:, 0]], p[f[:, 2]] - p[f[:, 0]])
    for i in range(3): np.add.at(normals, f[:, i], face)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-15)
    return normals


def filtered_normals(vertices, faces, strength=.28, iterations=3):
    """Smooth shading directions only; no vertex or collision displacement."""
    f = np.asarray(faces, dtype=np.int32); n = surface_normals(vertices, faces)
    edge = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]); edge = np.vstack([edge, edge[:, ::-1]])
    for _ in range(iterations):
        total = np.zeros_like(n); count = np.zeros(len(n))
        np.add.at(total, edge[:, 0], n[edge[:, 1]]); np.add.at(count, edge[:, 0], 1)
        n = n * (1 - strength) + total / np.maximum(count[:, None], 1) * strength
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-15)
    return n


def original_noncontact_geometry(obj):
    """New irregular continuous omental/cavity forms, safely below/behind tools."""
    oid = obj['id']; uv = np.asarray(obj['uvs']); u, v = uv[:, 0], uv[:, 1]
    old = np.asarray(obj['vertices_m']); p = old.copy()
    if oid in (310, 311):
        rng = np.random.default_rng(7100 + oid)
        # Model coherent anatomical folds, then variable ellipsoidal lobules.
        if oid == 311:
            x = (u - .5) * .35; y = -.15 + v * .32
            z = -.046 + .018 * (x / .175) ** 2 + .006 * ((y - .03) / .16) ** 2
            z += .0050 * np.exp(-((y + .065 - .012 * np.sin(x * 17)) / .023) ** 2)
            z += .0026 * np.exp(-((y - .08 + .020 * np.cos(x * 22)) / .034) ** 2)
            z += .0018 * np.exp(-((x + .08 + .015 * np.sin(y * 14)) / .026) ** 2)
        else:
            x = (u - .5) * .30; y = -.112 + v * .045 + .006 * np.sin(2 * PI * u)
            z = -.022 + .009 * v + .004 * np.sin(3 * PI * u) ** 2
            z += .0032 * np.exp(-((v - .55 - .10 * np.sin(u * 12)) / .21) ** 2)
        # Randomized physical lobule dimensions instead of regular sinusoids.
        height = np.zeros_like(u)
        xmin, xmax = x.min(), x.max(); ymin, ymax = y.min(), y.max()
        spacing = .009
        for j, cy in enumerate(np.arange(ymin - spacing, ymax + spacing, spacing)):
            for cx in np.arange(xmin - spacing, xmax + spacing, spacing):
                px = cx + rng.uniform(-.0035, .0035) + (j % 2) * spacing * .45
                py = cy + rng.uniform(-.0035, .0035)
                rx, ry = rng.uniform(.0042, .0085, 2); angle = rng.uniform(-PI, PI)
                xx = (x - px) * math.cos(angle) + (y - py) * math.sin(angle)
                yy = -(x - px) * math.sin(angle) + (y - py) * math.cos(angle)
                lobule = rng.uniform(.0011, .0032) * np.exp(-((xx / rx) ** 2 + (yy / ry) ** 2) * 1.6)
                height = np.maximum(height, lobule)
        # Broad smooth connective intervals interrupt lobule density. These are
        # real form changes, not flat colour masks or uniformly repeated bumps.
        density = .24 + .62 * np.clip(.5 + .35 * np.sin(x * 29 + .6) + .28 * np.cos(y * 31 - x * 9), 0, 1)
        smooth_interval = np.exp(-((y + .018 + .014 * np.sin(x * 13)) / .023) ** 2)
        density *= 1 - .70 * smooth_interval
        z += height * density
        p = np.column_stack([x, y, z])
    elif oid == 300:
        # Directional, aperiodic pleats in the posterior serosal lining.
        az = PI * u; lat = -PI * .46 + PI * .87 * v
        fold = .00075 * np.sin(13 * az + 1.6 * np.sin(lat * 3.2))
        fold += .00027 * np.sin(31 * az + 3.3 * np.cos(lat * 2.7)) * (.3 + .7 * np.sin(lat * 2.4) ** 2)
        fold += .00020 * np.sin(19 * lat + 1.4 * np.sin(az * 5.3))
        p = np.column_stack([(.19 + fold) * np.cos(lat) * np.cos(az), .029 + (.18 + fold) * np.cos(lat) * np.sin(az), .003 + (.119 + fold) * np.sin(lat)])
    elif oid == 301:
        x = (u - .5) * .38; y = -.15 + v * .35
        z = -.066 + .023 * (x / .19) ** 2 + .014 * ((y - .03) / .17) ** 2
        z += .00055 * np.sin(23 * PI * u + 3.5 * np.sin(3 * PI * v))
        z += .00023 * np.sin(41 * PI * u + 2 * PI * v)
        p = np.column_stack([x, y, z])
    return p.tolist(), float(np.max(np.linalg.norm(p - old, axis=1)))


def replace_mesh(obj, positions, faces, uvs, normals, material):
    old = obj.data
    temp = base.make_object(obj.name + '_Reauthor', positions, faces, uvs, material)
    obj.data = temp.data
    bpy.data.objects.remove(temp, do_unlink=True)
    if old.users == 0: bpy.data.meshes.remove(old)
    obj.data.normals_split_custom_set_from_vertices(normals)
    return obj


def rounded_landmark(oid):
    """Closed smooth orientation tubes with rounded ends inside their path extent.

    These remain explicitly non-contact landmarks, not a biliary/arterial model.
    Their sampled exported mesh is also the dataset geometry; no render modifier.
    """
    radius = .00145 if oid == 400 else .00055
    offset = np.zeros(3) if oid == 400 else np.array([.003, .003, .001])
    def center(t):
        return np.array([.0035 + .019*t + .002*math.sin(PI*t), .025 + .034*t,
                         .026 - .014*t + .002*math.sin(PI*t)]) + offset
    samples = np.array([center(t) for t in np.linspace(0, 1, 129)])
    length = float(np.linalg.norm(np.diff(samples, axis=0), axis=1).sum())
    def surface(theta, phi):
        t = (1 - math.cos(theta)) * .5
        axis = np.array([.019 + .002*PI*math.cos(PI*t), .034, -.014 + .002*PI*math.cos(PI*t)])
        axis /= np.linalg.norm(axis)
        u = np.cross(axis, [0, 0, 1]); u /= np.linalg.norm(u)
        v = np.cross(axis, u)
        distance = min(t, 1-t) * length
        r = math.sqrt(max(0, radius*radius - (radius-distance)**2)) if distance < radius else radius
        return (center(t) + r * (u*math.cos(phi) + v*math.sin(phi))).tolist()
    return base.radial_mesh(surface, rings=64, sides=24)


def run(render=False, reuse_textures=False):
    OUT.mkdir(parents=True, exist_ok=True)
    p6.OUT = OUT; base.OUT = OUT
    before = {p.relative_to(SOURCE).as_posix(): sha(p) for p in SOURCE.rglob('*') if p.is_file()}
    scene = json.loads((SOURCE / 'scene.json').read_text(encoding='utf8'))
    original_physics = json.loads((SOURCE / 'physics-mesh.json').read_text(encoding='utf8'))
    sys.path.insert(0, str(Path(__file__).parent))
    import rebuild_liver
    physics, liver_report = rebuild_liver.build(original_physics)
    serialized_physics = rebuild_liver.physical_bytes(physics)
    assert hashlib.sha256(serialized_physics).hexdigest() == '9405cfab1fb00e36290b242579d8ce4f085f6fa4505228aee72f723770a0de38', 'Frozen Phase 7 physical identity changed'
    if not (OUT / 'physics-mesh.json').is_file() or (OUT / 'physics-mesh.json').read_bytes() != serialized_physics:
        (OUT / 'physics-mesh.json').write_bytes(serialized_physics)
    (OUT / 'liver-rebuild-report.json').write_text(json.dumps(liver_report, indent=2) + '\n', encoding='utf8')
    scene['attachment_bridge']['anchor_bindings'] = copy.deepcopy(physics['attachment_anchor_bindings'])
    scene['phase7_liver_revision'] = copy.deepcopy(physics['phase7_liver_revision'])
    if 'phase6_interaction' in scene: scene['phase6_interaction'] = copy.deepcopy(physics['phase6_interaction'])
    previous_scene = json.loads((OUT / 'scene.json').read_text(encoding='utf8')) if reuse_textures else None
    previous_stats = json.loads((OUT / 'provenance.json').read_text(encoding='utf8'))['texture_statistics'] if reuse_textures else []
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE / 'EndoForge_Anatomy.blend'), use_scripts=False)
    bpy.context.preferences.filepaths.save_version = 0
    descriptions = {}; texture_stats = []
    for args in PARAMETERS:
        if reuse_textures:
            desc = previous_scene['material_sets'][args[0]]
            stats = next(s for s in previous_stats if s['name'] == args[0])
            assert all((OUT / desc[k]).is_file() for k in ('base_color_texture', 'normal_texture', 'roughness_texture'))
        else:
            desc, stats = make_textures(*args)
        descriptions[args[0]] = desc; texture_stats.append(stats); update_material(desc)
        print('PHASE7_MATERIAL_READY', args[0], flush=True)
    def replace(value):
        if isinstance(value, dict):
            for key, item in list(value.items()):
                if key in ('material', 'attachment_material') and isinstance(item, dict) and item.get('name') in descriptions:
                    value[key] = copy.deepcopy(descriptions[item['name']])
                else: replace(item)
        elif isinstance(value, list):
            for item in value: replace(item)
    replace(scene); scene['material_sets'] = descriptions
    changes = []
    for item in scene['static_objects']:
        oid = item['id']
        name = 'Liver_HighPrecision_Capsule' if oid == 200 else item['name']
        obj = bpy.data.objects[name]; geo = item.get('display_mesh', item)
        material = bpy.data.materials[item['material']['name']]
        delta = 0
        if oid in (300, 301, 310, 311):
            item['vertices_m'], delta = original_noncontact_geometry(item)
            item['description'] = ('Original Phase 7 irregular serosal fold / lobulated omentum reconstruction. Static non-contact context; no invented physical response.')
            normals = surface_normals(item['vertices_m'], item['triangles']).tolist()
            item['normals'] = normals; geo = item
        elif oid == 200:
            # The inherited spherical atlas had its pole in the exposed hepatic
            # bed, pinching a full texture into long rings. A continuous planar
            # operative UV chart removes that singularity without moving tissue.
            item['vertices_m'] = copy.deepcopy(physics['static_liver']['vertices_m'])
            item['triangles'] = copy.deepcopy(physics['static_liver']['triangles'])
            source_positions = np.asarray(item['vertices_m'])
            xy_min = source_positions[:, :2].min(axis=0)
            xy_span = np.maximum(np.ptp(source_positions[:, :2], axis=0), 1e-12)
            item['uvs'] = ((source_positions[:, :2] - xy_min) / xy_span).tolist()
            anchors = np.asarray(physics['attachment_anchor_positions_m'])
            locked = np.min(np.linalg.norm(source_positions[:, None] - anchors[None], axis=2), axis=1) < .005
            geo = p6.pn_surface(item['vertices_m'], item['triangles'], item['uvs'], 2, locked)
            item['display_mesh'] = geo
            display_positions = np.asarray(geo['vertices_m'])
            geo['uvs'] = ((display_positions[:, :2] - xy_min) / xy_span).tolist()
            item['uv_mapping'] = 'Continuous operative XY projection; no UV pole at gallbladder bed. Back surface shares this chart; no patient texture correspondence is claimed.'
            n = filtered_normals(item['vertices_m'], item['triangles'])
            tid = np.asarray(geo['source_triangle_ids']); bary = np.asarray(geo['barycentrics']); faces = np.asarray(item['triangles'])
            normals = np.einsum('ni,nij->nj', bary, n[faces[tid]])
            normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-15)
            geo['normals'] = normals.tolist(); normals = geo['normals']
            item['description'] = 'Phase 7 continuous macro-liver with exact 31-anchor interpolating bed. This is a new closed collision surface and requires full physical requalification. Matching bounded PN display has at most 0.12 mm offset; 5 mm anchor neighborhood is locked.'
        else:
            if oid in (400, 401):
                item['vertices_m'], item['triangles'], item['uvs'] = rounded_landmark(oid)
                item['description'] = 'Smooth closed orientation landmark with rounded ends; non-contact engineering anatomy, without duct cutting, fluid or arterial simulation.'
                geo = item
            normals = surface_normals(geo['vertices_m'], geo['triangles']).tolist()
            geo['normals'] = normals
        replace_mesh(obj, geo['vertices_m'], geo['triangles'], geo['uvs'], normals, material)
        if oid == 200:
            locked = set(geo['locked_source_vertex_ids'])
            ids = [i for i, tid in enumerate(geo['source_triangle_ids']) if all(v in locked for v in item['triangles'][tid])]
            for group in list(obj.vertex_groups): obj.vertex_groups.remove(group)
            obj.vertex_groups.new(name='HepaticBedLockedDisplay').add(ids, 1, 'REPLACE')
        item.update(p6.fbx(obj, oid)); item['static_mesh_asset'] = f'/Game/Phase7/Meshes/SM_{oid}.SM_{oid}'
        changes.append({'id': oid, 'name': name, 'vertices': len(geo['vertices_m']), 'triangles': len(geo['triangles']),
                        'maximum_geometry_change_m': delta if oid not in (200, 400, 401) else None, 'contact_geometry_changed': oid == 200,
                        'geometry_change_note': 'Original smooth orientation tube with rounded closed ends; topology changed, so a per-vertex displacement is not comparable.' if oid in (400, 401) else None,
                        'shading_normals': 'Smoothed source-normal field' if oid == 200 else 'Area-weighted smooth normals'})
    for image in list(bpy.data.images):
        if image.source == 'FILE' and image.users == 0: bpy.data.images.remove(image)
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and obj.name != 'Gallbladder_Physics_Proxy':
            obj['phase7_role'] = 'Original shared appearance foundation; geometry exported for matching labels'
    scene['phase'] = 7
    scene['asset_revision'] = 'phase7-common-anatomy-v5-operative-fossa'
    scene['appearance_identity'] = {'id': 'endoforge-phase7-common-appearance-v5', 'version': 5,
                                    'physical_model_id': physics['model_id'], 'physical_model_version': physics['version'],
                                    'physical_asset_sha256': sha(OUT / 'physics-mesh.json')}
    scene['phase7_render'] = {'schema': 'endoforge.phase7.render_profile.v1', 'id': 'phase7-common-foundation-v1',
                              'light_intensity_cd': .12, 'light_color_linear': [1, .97, .92], 'light_source_radius_cm': .16,
                              'exposure_bias': 0, 'vignette': .08, 'bloom': .025,
                              'motion_blur': False, 'depth_of_field': False, 'distortion': False,
                              'scope': 'Shared scene foundation; no calibrated endoscope or project-specific image degradation.'}
    scene['appearance_notes'] += [
        'Phase 7: original irregular serosal folds and lobulated yellow/cream omentum; unchanged IDs and matching exported geometry.',
        'Phase 7: reference-guided pale ivory/pink/grey gallbladder, reticular burgundy hepatic capsule and variable fine wet roughness; no photographic pixels imported.',
        'Phase 7: gallbladder FEM and 31 attachment endpoint positions are preserved. The closed liver collider is rebuilt continuously and attachment triangle bindings are recomputed exactly; new physics identity requires full native qualification. Bounded display follows this new collider.',
        'Clinical/anatomical and optical calibration remains pending; this is not a new patient-specific organ or surgical procedure model.'
    ]
    (OUT / 'scene.json').write_text(json.dumps(scene, separators=(',', ':')) + '\n', encoding='utf8')
    s = bpy.context.scene
    s['phase7_scope'] = 'Original common model/material refinement; source image viewing only; no teacher mesh or image data imported.'
    s.cycles.samples = 64; s.cycles.use_denoising = True
    s.render.resolution_x = 1920; s.render.resolution_y = 1080; s.render.resolution_percentage = 100
    # Authoring preview is deliberately labelled; UE renders are the acceptance evidence.
    for light in (o for o in bpy.data.objects if o.type == 'LIGHT'):
        light.data.color = (1, .97, .92)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'EndoForge_Anatomy.blend'), relative_remap=False)
    if render:
        s.render.filepath = str(OUT / 'anatomy-preview.png'); bpy.ops.render.render(write_still=True)
    after = {p.relative_to(SOURCE).as_posix(): sha(p) for p in SOURCE.rglob('*') if p.is_file()}
    assert before == after, 'Phase 6 assets changed'
    retained = [k for k in original_physics if k not in ('static_liver', 'attachment_anchor_bindings')]
    assert all(physics[k] == original_physics[k] for k in retained), 'Gallbladder mechanics or rig changed'
    provenance = {'schema': 'endoforge.phase7.original-appearance-provenance.v1', 'creator': 'Avalon / EndoForge',
                  'script': 'Scripts/BlenderPhase7/build_assets.py', 'script_sha256': sha(__file__),
                  'authoring_dependencies': {p.name: sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
                  'physical_asset_sha256': sha(OUT / 'physics-mesh.json'), 'phase6_assets_unchanged': True,
                  'reference_policy': 'Teacher laparoscopic images and anatomy atlas previews inspected visually only. No source imagery, meshes or photographic texels copied into generated assets.',
                  'reference_note': 'tmp/phase7/reference-review/reference-review.md (local reference evidence, not redistributed)',
                  'geometry_changes': changes, 'texture_statistics': texture_stats,
                  'physical_revision': {'retained_phase6_fields': retained, 'changed_fields': ['static_liver', 'attachment_anchor_bindings'], 'rebuild_report': 'liver-rebuild-report.json', 'full_physical_requalification_required': True},
                  'limitations': ['Gallbladder remains the previous engineering shape; the liver is an original continuous engineering reconstruction requiring new physical qualification.', 'No patient-specific geometry, clinical tissue calibration or calibrated optical properties.', 'Cavity and omentum are non-contact context outside the supported operative workspace.', 'Independent imported UE geometry, moving-scene appearance and data alignment still require runtime acceptance.'],
                  'files': {p.relative_to(OUT).as_posix(): sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name not in ('provenance.json', 'asset-contract-check.json', 'independent-asset-audit.json', 'blend-verification.json')}}
    (OUT / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf8')
    print('PHASE7_ASSETS_CREATED', OUT, flush=True)


if __name__ == '__main__':
    run('--render' in sys.argv, '--reuse-textures' in sys.argv)
