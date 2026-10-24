"""Open the delivered blend through Blender and validate editable data and links."""
import hashlib
import json
from pathlib import Path

import bpy

ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'Assets/Phase5'
blend=ASSETS/'EndoForge_Anatomy.blend'
bpy.ops.wm.open_mainfile(filepath=str(blend),use_scripts=False)
assert bpy.data.objects.get('Gallbladder_Wall_Outer')
assert bpy.data.objects.get('Liver_HepaticSupport')
assert len(bpy.data.objects['Gallbladder_Wall_Outer'].data.vertices)==266
assert bpy.data.objects['Gallbladder_Wall_Outer'].modifiers.get('EditableDisplaySubdivision')
assert bpy.data.objects['Gallbladder_Wall_Outer'].vertex_groups.get('HepaticBedAttachment')
assert bpy.data.objects['Liver_HepaticSupport'].vertex_groups.get('HepaticBedLocalSurface')
assert bpy.data.objects['Liver_HepaticSupport'].vertex_groups.get('HepaticBedAnchorVertices')
assert bpy.data.objects.get('HepaticBedReference') is None
assert bpy.context.scene.camera
external_images=[]
for image in bpy.data.images:
    if image.source!='FILE':continue
    path=Path(bpy.path.abspath(image.filepath)).resolve()
    assert path.exists(),str(path)
    assert path.is_relative_to(ASSETS.resolve()),str(path)
    image.reload()
    assert tuple(image.size)==(1024,1024),(image.name,tuple(image.size))
    external_images.append(str(path.relative_to(ASSETS)))
assert len(external_images)==21
report={'schema':'endoforge.native-blend-verification.v1','passed':True,
        'blender_version':bpy.app.version_string,'blend_sha256':hashlib.sha256(blend.read_bytes()).hexdigest(),
        'editable_objects':len(bpy.data.objects),'texture_links_loaded':len(external_images),
        'native_reopen':True,'texture_paths':external_images}
(ASSETS/'blend-verification.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print('PHASE5_BLEND_REOPEN_PASSED',json.dumps(report))
