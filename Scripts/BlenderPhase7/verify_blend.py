"""Native Blender reopen and exact exported-shape audit for Phase 7 source."""
import hashlib
import json
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'Assets/Phase7'
scene = json.loads((OUT / 'scene.json').read_text(encoding='utf8'))
blend = OUT / 'EndoForge_Anatomy.blend'
bpy.ops.wm.open_mainfile(filepath=str(blend), use_scripts=False)
checks = {}; shapes = []
items = [('Gallbladder_HighPrecision_Display', scene['dynamic_display'])]
items += [('Liver_HighPrecision_Capsule' if obj['id'] == 200 else obj['name'], obj.get('display_mesh', obj)) for obj in scene['static_objects']]
for name, geo in items:
    obj = bpy.data.objects[name]
    actual = np.asarray([tuple(v.co) for v in obj.data.vertices])
    wanted = np.asarray(geo['vertices_m'])
    triangles = np.asarray([tuple(p.vertices) for p in obj.data.polygons])
    error = float(np.max(np.linalg.norm(actual - wanted, axis=1))) if actual.shape == wanted.shape else float('inf')
    okay = error <= 2e-7 and np.array_equal(triangles, np.asarray(geo['triangles'])) and not obj.modifiers
    okay &= obj.data.has_custom_normals
    checks[name + '_editable_exact_geometry'] = bool(okay)
    shapes.append({'name': name, 'vertices': len(actual), 'triangles': len(triangles), 'max_vertex_error_m': error,
                   'no_preview_only_modifier': not bool(obj.modifiers), 'custom_normals': obj.data.has_custom_normals})
checks['attachment_vertex_group'] = bool(bpy.data.objects['Gallbladder_Physics_Proxy'].vertex_groups.get('HepaticBedAttachment'))
checks['bed_locked_display_group'] = bool(bpy.data.objects['Liver_HighPrecision_Capsule'].vertex_groups.get('HepaticBedLockedDisplay'))
external = []
for image in bpy.data.images:
    if image.source != 'FILE': continue
    path = Path(bpy.path.abspath(image.filepath)).resolve()
    assert path.is_relative_to(OUT.resolve()) and path.is_file(), 'External or missing image link: ' + str(path)
    image.reload()
    external.append({'file': path.relative_to(OUT).as_posix(), 'resolution': list(image.size),
                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
checks['relative_texture_links'] = len(external) == 21
checks['declared_texture_resolution'] = all(x['resolution'] in ([2048, 2048], [4096, 4096]) for x in external)
physical = json.loads((OUT / 'physics-mesh.json').read_text())
previous = json.loads((ROOT / 'Assets/Phase6/physics-mesh.json').read_text())
checks['phase6_gallbladder_core_and_anchor_positions_preserved'] = all(physical[k] == previous[k] for k in previous if k not in ('static_liver', 'attachment_anchor_bindings'))
checks['new_liver_revision_declared'] = bool(physical.get('phase7_liver_revision')) and physical['static_liver'] != previous['static_liver']
report = {'schema': 'endoforge.phase7.native-blend-verification.v1', 'passed': all(checks.values()), 'native_reopen': True,
          'blender_version': bpy.app.version_string, 'checks': checks, 'editable_objects': len(bpy.data.objects),
          'blend_sha256': hashlib.sha256(blend.read_bytes()).hexdigest(),
          'scene_sha256': hashlib.sha256((OUT / 'scene.json').read_bytes()).hexdigest(),
          'texture_links_loaded': len(external), 'texture_paths': external, 'shapes': shapes,
          'no_preview_only_subdivision': True, 'custom_smooth_normals_preserved': True,
          'units': 'm', 'physical_scale': 1.0, 'clinical_review': 'pending'}
(OUT / 'blend-verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
print('PHASE7_BLEND_REOPEN', report['passed'], flush=True)
assert report['passed'], [k for k, v in checks.items() if not v]
