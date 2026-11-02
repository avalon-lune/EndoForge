"""Phase9 authored tissue fields, derived from the local Phase8 texture builder.

Fine vessels replace thick uninterrupted painted branches. Hepatic capsule
reticulation uses a finer, lower-contrast band. No baked lighting or photo pixels.
"""
import math
from pathlib import Path
import numpy as np
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Scripts/BlenderPhase8'))
from vascular import vascular_fields
# The authoring caller supplies the shared deterministic Blender helpers.
p7=p6=base=None
OUT=ROOT/'Assets/Phase9'

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
    major, buried = vascular_fields(2048, seed + 70, amount=3 if name == 'GallbladderSerosa' else 9, width_scale=.85, length_scale=1 if name == 'GallbladderSerosa' else .48)
    minor, soft = vascular_fields(2048, seed + 119, amount=10, width_scale=.25, length_scale=.55)
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
        mix([.345, .135, .17], major * .58)
        mix([.43, .21, .245], minor * .36)
        # Fade chart variation at both poles; prevent colored triangular wedges.
        polar=np.clip(np.sin(math.pi*yy)*5,0,1)[:,:,None]
        tint=tint*polar+np.asarray(color,np.float32)*(1-polar)
    elif name == 'HepaticCapsule':
        mix([.54, .35, .36], np.clip((low-.28)*1.3, 0, .35))
        mix([.38, .205, .27], np.clip((.56-broad)*1.3, 0, .35))
        # Pale connective branches, a capsule pattern rather than skin pores.
        net,fringe,_=p7.cellular_fields(1024,83,seed+410)
        net=p7.resize_bilinear(net,size);fringe=p7.resize_bilinear(fringe,size)
        coverage=np.clip((low-.39)*3.0,0,.65)*(.25+.75*broad)
        mix([.68, .51, .51], (fringe*.065+net*.055)*coverage+buried*.08+major*.05)
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
                ue_material='/Game/Phase9/Materials/M_AnatomyPhase9',
                shading_model='short-distance-subsurface-profile',
                nominal_texture_span_m=.060,
                wet_surface_model='Original multiscale pigment and roughness, short-distance scattering and dual specular profile; no WPO or clinical calibration.', **paths)
    return desc, stats

