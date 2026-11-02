"""Verify recorded Phase 9 appearance identities and actual material settings.

This validates provenance and parameter agreement, not anatomical accuracy or
photorealism. Numeric geometry kernels remain in the independent data auditors.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from common import read, require, resolve_child, sha, write_new
from audit_uv import ALGORITHM, audit_source


ASSETS = {
    'anatomy_material_asset': '/Game/Phase9/Materials/M_AnatomyPhase9.M_AnatomyPhase9',
    'instrument_material_asset': '/Game/Phase9/Materials/M_MetalPhase9.M_MetalPhase9',
    'insulation_material_asset': '/Game/Phase9/Materials/M_InsulationPhase9.M_InsulationPhase9',
}
SUBSURFACE_ASSET = '/Game/Phase9/Materials/SP_TissuePhase9.SP_TissuePhase9'
SUBSURFACE_SETTINGS = {
    'mean_free_path_distance_cm': .1,
    'mean_free_path_color': [.6, .288, .168],
    'world_unit_scale': 1,
    'roughness0': .72,
    'roughness1': 1.5,
    'lobe_mix': .35,
    'ior': 1.38,
    'implementation': 'separable',
}


def number(value, name):
    require(type(value) in (float, int) and math.isfinite(value), 'Invalid appearance number: '+name)
    return value


def close(actual, expected, name, tolerance=1e-5):
    if isinstance(expected, dict):
        require(isinstance(actual, dict) and set(actual) == set(expected), 'Appearance keys differ: '+name)
        for key, value in expected.items():
            close(actual[key], value, name+'.'+key, tolerance)
    elif isinstance(expected, list):
        require(isinstance(actual, list) and len(actual) == len(expected), 'Appearance array differs: '+name)
        for i, (a, b) in enumerate(zip(actual, expected)):
            close(a, b, name+f'[{i}]', tolerance)
    elif type(expected) in (int, float):
        require(abs(number(actual, name)-number(expected, name)) <= tolerance, 'Appearance value differs: '+name)
    else:
        require(type(actual) is type(expected) and actual == expected, 'Appearance value differs: '+name)


def audit_subsurface_profile(actual, authored=None):
    require(isinstance(actual, dict), 'Missing actual short-distance tissue subsurface profile')
    require(actual.get('asset') == SUBSURFACE_ASSET, 'Wrong actual Phase 9 subsurface profile asset')
    for key in ('profile_shading_model', 'burley', 'mean_free_path_enabled'):
        require(actual.get(key) is True, 'Subsurface profile feature is not actually enabled: '+key)
    for key, expected in SUBSURFACE_SETTINGS.items():
        close(actual.get(key), expected, 'actual_subsurface_profile.'+key)
    if authored is not None:
        require(isinstance(authored, dict) and
                authored.get('schema') == 'endoforge.phase9.subsurface-profile.v1',
                'Missing authored Phase 9 subsurface profile')
        for key, expected in SUBSURFACE_SETTINGS.items():
            close(authored.get(key), expected, 'scene.phase9_material_profile.'+key)
            close(actual.get(key), authored[key], 'scene/actual subsurface profile.'+key)
    return actual


def audit_appearance(appearance, expected=None):
    require(isinstance(appearance, dict) and appearance.get('schema') == 'endoforge.phase9.appearance.v1',
            'Missing actual Phase 9 appearance record')
    require(appearance.get('phase') == 9 and appearance.get('mechanics_phase') == 6,
            'Appearance must distinguish Phase 9 presentation from Phase 6 mechanics')
    require(appearance.get('dynamic_position_algorithm') == 'smooth_bounded_pn_triangle_v1',
            'Missing actual Phase9 smooth bounded PN position contract')
    require(appearance.get('diagnostic_neutral_grey') is False,
            'Diagnostic grey organ overrides cannot be used as authored-material acceptance')
    require(appearance.get('dynamic_uv_algorithm') == ALGORITHM, 'Missing actual periodic material-UV convention')
    require(appearance.get('spatial_postprocess_applied') is False and
            appearance.get('world_position_offset_applied') is False,
            'Untracked image warp or material displacement invalidates geometry labels')
    labels = appearance.get('geometric_labels', '').lower()
    require('geometric normals exclude' in labels and 'normal-map' in labels and 'pinhole' in labels,
            'Geometric/shading-normal and projection conventions must be explicit')
    for key, path in ASSETS.items():
        require(appearance.get(key) == path, 'Unexpected Phase 9 material asset: '+key)
    subsurface = audit_subsurface_profile(appearance.get('actual_subsurface_profile'))
    instrument = appearance.get('instrument_material_parameters')
    require(isinstance(instrument, dict) and instrument.get('revision') == 'brushed-steel-v2',
            'Missing actual versioned instrument parameters')
    for key, value in {'SteelRoughness': .36, 'SteelAnisotropy': .4, 'SteelMetallic': 1,
                       'SteelBaseColor': [.62, .65, .68]}.items():
        close(instrument.get(key), value, 'instrument.'+key)
    shaders = appearance.get('material_shader_checks')
    require(isinstance(shaders, list) and len(shaders) == 3 and
            {s.get('asset') for s in shaders} == set(ASSETS.values()),
            'Missing actual compiled shader-map checks for all three Phase 9 materials')
    for shader in shaders:
        for key in ('resource_exists', 'compilation_finished', 'shader_map_valid', 'shader_map_complete', 'passed'):
            require(shader.get(key) is True, 'Invalid/fallback Phase 9 material: '+str(shader.get('asset'))+'.'+key)
        available = shader.get('compile_error_inspection_available')
        require(type(available) is bool, 'Missing compile-error inspection scope')
        require(shader.get('compile_errors_empty') is (True if available else None),
                'Shader compile errors or invalid packaged compile-error claim')
        completion = ('Editor compiler finished; complete actual-platform shader map required' if available else
                      'No runtime compiler; loaded complete cooked shader map required')
        require(shader.get('completion_evidence') == completion,
                'Shader completion scope must distinguish editor compilation from loaded cooked shaders')
    profile = appearance.get('authored_profile')
    require(isinstance(profile, dict) and profile.get('schema') == 'endoforge.phase9.render_profile.v1'
            and isinstance(profile.get('id'), str) and profile['id'].strip(), 'Missing versioned render profile')
    actual = appearance.get('actual_settings')
    require(isinstance(actual, dict), 'Missing actual render settings')
    require(actual.get('manual_exposure') is True and actual.get('physical_camera_exposure') is False,
            'Uncontrolled exposure')
    for key in ('motion_blur', 'chromatic_aberration'):
        require(number(actual.get(key), key) == 0, 'Unexpected imaging effect: '+key)
    limits = {'light_intensity_cd': (.005, 2), 'light_source_radius_cm': (.01, 1),
              'exposure_bias': (-3, 3), 'vignette': (0, .25), 'bloom': (0, .1)}
    for key, (lo, hi) in limits.items():
        value = number(actual.get(key), key)
        require(lo <= value <= hi, 'Appearance outside declared common profile limits: '+key)
        close(value, profile.get(key), key)
    color = actual.get('light_color_linear')
    require(isinstance(color, list) and len(color) == 3 and
            all(.1 <= number(v, 'light_color_linear') <= 1 for v in color), 'Invalid actual light color')
    # UE light color is quantized through its stored color representation.
    close(color, profile.get('light_color_linear'), 'light_color_linear', .01)
    for key in ('lumen_scene_quality', 'lumen_scene_detail',
                'lumen_final_gather_quality', 'lumen_reflection_quality'):
        require(number(actual.get(key), key) >= 4, 'Lumen quality below inherited verified setting: '+key)
    require(0 < number(actual.get('horizontal_fov_degrees'), 'horizontal_fov_degrees') < 180,
            'Invalid actual horizontal FOV')
    close(actual.get('light_relative_position_cm'), [0, .12, .05], 'camera-relative light position')
    for key, value in {'light_inner_cone_degrees': 32, 'light_outer_cone_degrees': 52,
                       'light_shadow_bias': .05, 'light_contact_shadow_length_cm': .35}.items():
        close(actual.get(key), value, key)
    if expected is not None:
        close(appearance, expected, 'appearance consistency')
    return {'profile_id': profile['id'], 'projection': 'undistorted pinhole',
            'geometric_normals_exclude_normal_maps': True,
            'material_shader_checks': shaders,
            'instrument_material_parameters': instrument,
            'actual_subsurface_profile': subsurface,
            'spatial_postprocess_applied': False, 'world_position_offset_applied': False,
            'actual_settings': actual}


def audit_manifest(manifest_path, asset_dir=None):
    manifest_path = Path(manifest_path).resolve()
    manifest = read(manifest_path)
    require(manifest.get('phase') == 9 and manifest.get('mechanics_phase') == 6,
            'Visual manifest must identify Phase 9 with inherited mechanics')
    require(manifest.get('hash_algorithm') == 'SHA1', 'Unexpected asset identity algorithm')
    summary = audit_appearance(manifest.get('appearance'))
    audit_source(manifest.get('dynamic_uv_source'))
    authored = manifest.get('authored_materials')
    applied = manifest.get('applied_materials')
    require(isinstance(authored, dict) and len(authored) >= 7, 'Missing authored tissue materials')
    require(isinstance(applied, list) and len(applied) >= 7, 'Missing actual per-component material parameters')
    by_name = {m['name']: m for m in authored.values()}
    require(len(by_name) == len(authored), 'Repeated authored material name')
    seen = set()
    components = set()
    for material in applied:
        name, component = material.get('authored_name'), material.get('component')
        require(name in by_name and isinstance(component, str) and component,
                'Unrecognized applied tissue material/component')
        require(component not in components, 'Repeated applied-material component')
        components.add(component); seen.add(name); source = by_name[name]
        require(material.get('material_asset') == ASSETS['anatomy_material_asset'], 'Wrong actual tissue shader')
        close(material.get('texture_address_u'), {key:'TA_Wrap' for key in ('BaseTexture','NormalTexture','RoughnessTexture')},
              component+'.actual texture U sampler')
        parameters = {'Roughness': source['roughness'], 'Metallic': source['metallic'],
                      'Specular': source['specular'], 'SubsurfaceOpacity': source['subsurface_opacity'],
                      'TextureWeight': 1, 'NormalWeight': source['normal_strength'], 'RoughnessWeight': 1,
                      'RoughnessScale': source.get('roughness_scale', 1),
                      'RoughnessBias': source.get('roughness_bias', 0), 'BaseColor': [1, 1, 1],
                      'BaseColorGain': source.get('base_color_gain', [1, 1, 1]),
                      'SubsurfaceColor': source['subsurface_color']}
        for key, value in parameters.items():
            close(material.get(key), value, component+'.'+key)
    require(seen == set(by_name), 'Not every authored tissue material is represented in actual applied records')
    hashes = manifest.get('asset_file_hashes')
    require(isinstance(hashes, dict) and len(hashes) >= 23 and
            all(k in hashes for k in ('scene.json', 'physics-mesh.json')), 'Incomplete visual asset identities')
    for name in by_name.values():
        for key in ('base_color_texture', 'roughness_texture', 'normal_texture'):
            require(name.get(key) in hashes, 'Texture omitted from manifest: '+str(name.get(key)))
    if asset_dir is not None:
        asset_dir = Path(asset_dir).resolve()
        for name, expected in hashes.items():
            actual_file = resolve_child(asset_dir, name)
            require(hashlib.sha1(actual_file.read_bytes()).hexdigest() == expected.lower(),
                    'Actual asset bytes differ from visual manifest: '+name)
        scene = read(asset_dir/'scene.json')
        require(scene.get('phase') == 9, 'Wrong authored scene phase')
        close(manifest['appearance']['authored_profile'], scene.get('phase9_render'), 'scene render profile')
        audit_subsurface_profile(manifest['appearance'].get('actual_subsurface_profile'),
                                 scene.get('phase9_material_profile'))
        close(authored, scene.get('material_sets'), 'scene authored material sets')
        audit_source(manifest.get('dynamic_uv_source'), scene['dynamic_surface']['uvs'], asset_dir/'physics-mesh.json')
    summary.update({'manifest_sha256': sha(manifest_path),
                    'manifest_sha1': hashlib.sha1(manifest_path.read_bytes()).hexdigest(),
                    'applied_components': len(applied), 'tissue_material_names': sorted(seen),
                    'asset_hashes': len(hashes), 'asset_bytes_verified': asset_dir is not None,
                    'dynamic_uv_source_asset_verified': asset_dir is not None,
                    'instrument_scope': 'Material identities and actual v2 steel parameters verified; this is not an optical calibration of metal or insulation.'})
    return manifest, summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        _, metrics = audit_manifest(args.manifest, args.assets)
        report = {'phase': 9, 'schema': 'endoforge.phase9.appearance-audit.v1', 'passed': True,
                  'metrics': metrics, 'clinical_review': 'pending',
                  'scope': 'Parameter, asset identity and label-semantics validation; no automated aesthetic judgement.'}
    except (ValueError, KeyError, TypeError, OSError) as error:
        report = {'phase': 9, 'schema': 'endoforge.phase9.appearance-audit.v1', 'passed': False, 'error': str(error)}
    report['audit_script_sha256'] = sha(__file__)
    report['uv_audit_script_sha256'] = sha(Path(__file__).with_name('audit_uv.py'))
    write_new(args.output, report)
    print(json.dumps(report))
    raise SystemExit(0 if report['passed'] else 1)
