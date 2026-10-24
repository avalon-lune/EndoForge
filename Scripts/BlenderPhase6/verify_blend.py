"""Reopen the Phase 6 source, validate editable geometry and relative textures."""
import hashlib
import json
import sys
from pathlib import Path
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'Assets'/'Phase6'
if '--asset-dir' in sys.argv:OUT=Path(sys.argv[sys.argv.index('--asset-dir')+1]).resolve()
blend=OUT/'EndoForge_Anatomy.blend'
scene=json.loads((OUT/'scene.json').read_text(encoding='utf8'))
bpy.ops.wm.open_mainfile(filepath=str(blend),use_scripts=False)
gb=bpy.data.objects['Gallbladder_HighPrecision_Display']
assert len(gb.data.vertices)==len(scene['dynamic_display']['vertices_m'])
assert len(gb.data.polygons)==len(scene['dynamic_display']['triangles'])
assert not gb.modifiers, 'No Blender-only smoothing may hide the runtime topology'
assert gb.data.has_custom_normals
assert bpy.data.objects['Gallbladder_Physics_Proxy'].vertex_groups.get('HepaticBedAttachment')
assert bpy.data.objects['Liver_HighPrecision_Capsule'].vertex_groups.get('HepaticBedLockedDisplay')
assert bpy.data.objects['Liver_HighPrecision_Capsule'].data.has_custom_normals
external=[]
for im in bpy.data.images:
    if im.source!='FILE':continue
    path=Path(bpy.path.abspath(im.filepath)).resolve()
    assert path.exists() and path.is_relative_to(OUT.resolve())
    im.reload();assert tuple(im.size) in ((2048,2048),(4096,4096))
    external.append({'file':path.relative_to(OUT).as_posix(),'resolution':list(im.size)})
assert len(external)==21 and sum(x['resolution']==[4096,4096] for x in external)==2
report={'schema':'endoforge.native-blend-verification.v1','passed':True,'native_reopen':True,
        'blender_version':bpy.app.version_string,'blend_sha256':hashlib.sha256(blend.read_bytes()).hexdigest(),
        'scene_sha256':hashlib.sha256((OUT/'scene.json').read_bytes()).hexdigest(),
        'editable_objects':len(bpy.data.objects),'texture_links_loaded':len(external),'texture_paths':external,
        'no_preview_only_subdivision':True,'custom_smooth_normals_preserved':True,
        'units':'m','physical_scale':1.0,'clinical_review':'pending'}
(OUT/'blend-verification.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print('PHASE6_BLEND_REOPEN_PASSED',json.dumps(report),flush=True)
