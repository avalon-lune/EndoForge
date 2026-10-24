"""Create project-owned procedural training assets using the Unreal Python API.

Run only after compiling the LapTrainerEditor C++ target. The level remains
minimal because TrainingGameMode creates the interactive scene at runtime.
Surface detail changes shading only: no displacement, WPO or collision offset.
"""
import unreal
import json
from pathlib import Path

TOOLS = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
ASSETS = unreal.EditorAssetLibrary

# Compact deterministic value noise, evaluated in the material's UV reference
# coordinates. This needs no textures or external downloads and follows the pad
# as its physical mesh deforms. It is visual surface finish, not anatomy data.
NOISE = r"""
struct LapNoise {
    float hash(float2 p) {
        return frac(sin(dot(p, float2(127.1, 311.7))) * 43758.5453);
    }
    float value(float2 p) {
        float2 i = floor(p);
        float2 f = frac(p);
        float2 u = f * f * (3.0 - 2.0 * f);
        return lerp(lerp(hash(i), hash(i + float2(1, 0)), u.x),
                    lerp(hash(i + float2(0, 1)), hash(i + float2(1, 1)), u.x), u.y);
    }
};
LapNoise noise;
"""

TISSUE_COLOR = NOISE + r"""
float coarse = noise.value(UV * float2(5.0, 4.0));
float medium = noise.value(UV * float2(23.0, 17.0) + 9.4);
float phase = UV.x * 470.0 + 3.0 * sin(UV.y * 16.0);
float aa = 1.0 - smoothstep(0.4, 2.5, fwidth(phase));
float fiber = sin(phase) * aa;
float shade = 1.0 + 0.12 * (coarse - 0.5) + 0.055 * (medium - 0.5);
return float3(0.57, 0.165, 0.205) * shade + float3(0.009, 0.006, 0.006) * fiber;
"""

TISSUE_ROUGHNESS = NOISE + r"""
float film = noise.value(UV * float2(9.0, 7.0));
float fine = noise.value(UV * 83.0);
return 0.245 + 0.065 * film + 0.012 * (fine - 0.5);
"""

TISSUE_NORMAL = r"""
float phase = UV.x * 470.0 + 3.0 * sin(UV.y * 16.0);
float phase2 = UV.y * 570.0 + 1.6 * sin(UV.x * 21.0);
float aa1 = 1.0 - smoothstep(0.4, 2.5, fwidth(phase));
float aa2 = 1.0 - smoothstep(0.4, 2.5, fwidth(phase2));
return normalize(float3(0.018 * cos(phase) * aa1,
                        0.009 * cos(phase2) * aa2, 1.0));
"""

STEEL_ROUGHNESS = NOISE + r"""
float phase = UV.y * 760.0;
float aa = 1.0 - smoothstep(0.4, 2.5, fwidth(phase));
float brush = sin(phase) * aa;
return 0.27 + 0.027 * brush + 0.024 * (noise.value(UV * float2(13, 80)) - 0.5);
"""

STEEL_NORMAL = r"""
float phase = UV.y * 760.0;
float aa = 1.0 - smoothstep(0.4, 2.5, fwidth(phase));
return normalize(float3(0.0, 0.004 * cos(phase) * aa, 1.0));
"""

POLYMER_ROUGHNESS = NOISE + r"""
return 0.42 + 0.075 * noise.value(UV * 72.0);
"""


def expression(material, expression_type, x=0, y=0):
    return MEL.create_material_expression(material, expression_type, x, y)


def scalar(material, value, x, y):
    node = expression(material, unreal.MaterialExpressionConstant, x, y)
    node.set_editor_property("r", value)
    return node


def color(material, rgb, x, y):
    node = expression(material, unreal.MaterialExpressionConstant3Vector, x, y)
    node.set_editor_property("constant", unreal.LinearColor(*rgb, 1.0))
    return node


def custom_uv(material, code, output_type, description, x, y):
    uv = expression(material, unreal.MaterialExpressionTextureCoordinate, x - 250, y)
    uv.set_editor_property("coordinate_index", 0)
    node = expression(material, unreal.MaterialExpressionCustom, x, y)
    node.set_editor_property("code", code)
    node.set_editor_property("output_type", output_type)
    node.set_editor_property("description", description)
    input_uv = unreal.CustomInput()
    input_uv.set_editor_property("input_name", "UV")
    node.set_editor_property("inputs", [input_uv])
    if not MEL.connect_material_expressions(uv, "", node, "UV"):
        raise RuntimeError("Could not connect UV input for " + description)
    return node


def make_material(name, rgb, roughness=0.4, metallic=0.0, vertex=False,
                  tissue=False, steel=False, polymer=False):
    asset_path = "/Game/Materials/" + name
    material = ASSETS.load_asset(asset_path) if ASSETS.does_asset_exist(asset_path) else None
    if material is None:
        material = TOOLS.create_asset(name, "/Game/Materials", unreal.Material, unreal.MaterialFactoryNew())
    if material is None:
        raise RuntimeError("Could not create material " + name)
    MEL.delete_all_material_expressions(material)
    material.set_editor_property("two_sided", True)
    material.set_editor_property("tangent_space_normal", True)
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_SUBSURFACE if tissue else unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    if tissue:
        base = custom_uv(material, TISSUE_COLOR, unreal.CustomMaterialOutputType.CMOT_FLOAT3,
                         "Subtle training-pad color and surface fibers", -650, -180)
    else:
        base = color(material, rgb, -600, -160)
    if vertex:
        vertex_node = expression(material, unreal.MaterialExpressionVertexColor, -600, -340)
        multiply = expression(material, unreal.MaterialExpressionMultiply, -280, -160)
        MEL.connect_material_expressions(base, "", multiply, "A")
        MEL.connect_material_expressions(vertex_node, "RGB", multiply, "B")
        base = multiply
    MEL.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    roughness_node = scalar(material, roughness, -260, 10)
    normal_node = None
    if tissue:
        roughness_node = custom_uv(material, TISSUE_ROUGHNESS, unreal.CustomMaterialOutputType.CMOT_FLOAT1,
                                   "Thin wet surface finish", -650, 100)
        normal_node = custom_uv(material, TISSUE_NORMAL, unreal.CustomMaterialOutputType.CMOT_FLOAT3,
                                "Micro-normal only: no physical displacement", -650, 350)
    elif steel:
        roughness_node = custom_uv(material, STEEL_ROUGHNESS, unreal.CustomMaterialOutputType.CMOT_FLOAT1,
                                   "Fine stainless-steel brushing", -650, 100)
        normal_node = custom_uv(material, STEEL_NORMAL, unreal.CustomMaterialOutputType.CMOT_FLOAT3,
                                "Very low-amplitude steel micro-normal", -650, 350)
    elif polymer:
        roughness_node = custom_uv(material, POLYMER_ROUGHNESS, unreal.CustomMaterialOutputType.CMOT_FLOAT1,
                                   "Soft molded-polymer surface finish", -650, 100)
    MEL.connect_material_property(roughness_node, "", unreal.MaterialProperty.MP_ROUGHNESS)
    if normal_node is not None:
        MEL.connect_material_property(normal_node, "", unreal.MaterialProperty.MP_NORMAL)
    MEL.connect_material_property(scalar(material, metallic, -260, 100), "", unreal.MaterialProperty.MP_METALLIC)
    MEL.connect_material_property(scalar(material, 0.38 if tissue else 0.4, -260, 200), "", unreal.MaterialProperty.MP_SPECULAR)
    if tissue:
        MEL.connect_material_property(color(material, (0.38, 0.075, 0.065), -260, 550), "", unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
        MEL.connect_material_property(scalar(material, 0.85, -260, 410), "", unreal.MaterialProperty.MP_OPACITY)
    MEL.recompile_material(material)
    ASSETS.save_loaded_asset(material)
    unreal.log("LAPTRAINER_ASSET " + asset_path)


def make_anatomy_material(phase6=False):
    name = "M_AnatomyPhase6" if phase6 else "M_Anatomy"
    path = "/Game/Materials/" + name
    material = ASSETS.load_asset(path) if ASSETS.does_asset_exist(path) else TOOLS.create_asset(name, "/Game/Materials", unreal.Material, unreal.MaterialFactoryNew())
    MEL.delete_all_material_expressions(material)
    material.set_editor_property("two_sided", True)
    material.set_editor_property("tangent_space_normal", True)
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_SUBSURFACE if phase6 else unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    base = expression(material, unreal.MaterialExpressionVectorParameter, -800, -150)
    base.set_editor_property("parameter_name", "BaseColor")
    base.set_editor_property("default_value", unreal.LinearColor(.4, .32, .13, 1))
    tex = expression(material, unreal.MaterialExpressionTextureSampleParameter2D, -800, -400)
    tex.set_editor_property("parameter_name", "BaseTexture")
    tex.set_editor_property("texture", ASSETS.load_asset("/Engine/EngineResources/WhiteSquareTexture"))
    weight = expression(material, unreal.MaterialExpressionScalarParameter, -800, 0)
    weight.set_editor_property("parameter_name", "TextureWeight")
    weight.set_editor_property("default_value", 0)
    mix = expression(material, unreal.MaterialExpressionLinearInterpolate, -350, -200)
    MEL.connect_material_expressions(base, "", mix, "A")
    MEL.connect_material_expressions(tex, "RGB", mix, "B")
    MEL.connect_material_expressions(weight, "", mix, "Alpha")
    MEL.connect_material_property(mix, "", unreal.MaterialProperty.MP_BASE_COLOR)
    for name, value, prop, y in [("Roughness", .3, unreal.MaterialProperty.MP_ROUGHNESS, 100), ("Metallic", 0, unreal.MaterialProperty.MP_METALLIC, 200)]:
        node = expression(material, unreal.MaterialExpressionScalarParameter, -400, y)
        node.set_editor_property("parameter_name", name)
        node.set_editor_property("default_value", value)
        MEL.connect_material_property(node, "", prop)
    phase = "Phase6" if phase6 else "Phase5"
    texture_root = Path(__file__).resolve().parents[3] / "Assets" / phase / "textures"
    normal_nodes = {}
    for label, suffix in [("Normal", "normal"), ("Roughness", "roughness")]:
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", str(texture_root / ("GallbladderSerosa_" + suffix + ".png")))
        task.set_editor_property("destination_path", "/Game/" + phase + "/Textures")
        task.set_editor_property("destination_name", "T_AnatomyDefault" + label)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("save", True)
        TOOLS.import_asset_tasks([task])
        texture = ASSETS.load_asset("/Game/" + phase + "/Textures/T_AnatomyDefault" + label)
        texture.set_editor_property("srgb", False)
        texture.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
        ASSETS.save_loaded_asset(texture)
        texnode = expression(material, unreal.MaterialExpressionTextureSampleParameter2D, -1100, 450 if label == "Normal" else 750)
        texnode.set_editor_property("parameter_name", label + "Texture")
        texnode.set_editor_property("texture", texture)
        texnode.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        weightnode = expression(material, unreal.MaterialExpressionScalarParameter, -800, 850)
        weightnode.set_editor_property("parameter_name", label + "Weight")
        weightnode.set_editor_property("default_value", 0)
        blend = expression(material, unreal.MaterialExpressionLinearInterpolate, -250, 450 if label == "Normal" else 750)
        MEL.connect_material_expressions(weightnode, "", blend, "Alpha")
        if label == "Normal":
            decode = expression(material, unreal.MaterialExpressionMultiply, -750, 450)
            MEL.connect_material_expressions(texnode, "RGB", decode, "A")
            MEL.connect_material_expressions(scalar(material, 2, -950, 600), "", decode, "B")
            offset = expression(material, unreal.MaterialExpressionSubtract, -500, 450)
            MEL.connect_material_expressions(decode, "", offset, "A")
            MEL.connect_material_expressions(scalar(material, 1, -750, 600), "", offset, "B")
            MEL.connect_material_expressions(color(material, (0, 0, 1), -500, 600), "", blend, "A")
            handed = expression(material, unreal.MaterialExpressionMultiply, -350, 500)
            MEL.connect_material_expressions(offset, "", handed, "A")
            MEL.connect_material_expressions(color(material, (1, -1, 1), -500, 700), "", handed, "B")
            MEL.connect_material_expressions(handed, "", blend, "B")
            MEL.connect_material_property(blend, "", unreal.MaterialProperty.MP_NORMAL)
        else:
            fallback = expression(material, unreal.MaterialExpressionScalarParameter, -500, 850)
            fallback.set_editor_property("parameter_name", "Roughness")
            fallback.set_editor_property("default_value", .3)
            MEL.connect_material_expressions(fallback, "", blend, "A")
            MEL.connect_material_expressions(texnode, "R", blend, "B")
            MEL.connect_material_property(blend, "", unreal.MaterialProperty.MP_ROUGHNESS)
    if phase6:
        # SSS and the low-roughness wet microfacet lobe are implemented in the
        # actual UE material. This is not a Blender-only clear-coat preview.
        specular = expression(material, unreal.MaterialExpressionScalarParameter, -300, 300)
        specular.set_editor_property("parameter_name", "Specular")
        specular.set_editor_property("default_value", .32)
        MEL.connect_material_property(specular, "", unreal.MaterialProperty.MP_SPECULAR)
        subsurface = expression(material, unreal.MaterialExpressionVectorParameter, -300, 1100)
        subsurface.set_editor_property("parameter_name", "SubsurfaceColor")
        subsurface.set_editor_property("default_value", unreal.LinearColor(.38, .13, .08, 1))
        MEL.connect_material_property(subsurface, "", unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
        opacity = expression(material, unreal.MaterialExpressionScalarParameter, -300, 1250)
        opacity.set_editor_property("parameter_name", "SubsurfaceOpacity")
        opacity.set_editor_property("default_value", .93)
        MEL.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY)
    else:
        MEL.connect_material_property(scalar(material, .45, -300, 300), "", unreal.MaterialProperty.MP_SPECULAR)
    MEL.recompile_material(material)
    ASSETS.save_loaded_asset(material)


def import_phase6_static_meshes():
    """Create actual static-mesh Lumen cards, preserving full-resolution LOD0.

    FBX vertices are authored in centimetres with Y pre-mirrored to compensate
    legacy UE's unconditional handedness conversion. Scene/unit conversion is
    disabled and the final actual LOD0 XYZ is checked by the geometry audit.
    Nanite is intentionally not enabled: reference depth must match actual LOD0.
    """
    root = Path(__file__).resolve().parents[3] / "Assets" / "Phase6"
    source = json.loads((root / "scene.json").read_text(encoding="utf8"))
    mesh_editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    imported = []
    for obj in source["static_objects"]:
        if "fbx_file" not in obj:
            continue
        asset_path = obj["static_mesh_asset"].split(".")[0]
        if asset_path != "/Game/Phase6/Meshes/SM_" + str(obj["id"]):
            raise RuntimeError("Refusing to replace an asset outside generated Phase6 meshes")
        # Legacy FBX atomic reimport retains prior coordinate settings even when
        # a fresh FbxImportUI is attached to an AssetImportTask. Rebuild only our
        # seven reproducible Phase6 derived meshes; no earlier-phase assets.
        if ASSETS.does_asset_exist(asset_path) and not ASSETS.delete_asset(asset_path):
            raise RuntimeError("Could not replace generated Phase6 mesh " + asset_path)
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", str(root / obj["fbx_file"]))
        task.set_editor_property("destination_path", "/Game/Phase6/Meshes")
        task.set_editor_property("destination_name", "SM_" + str(obj["id"]))
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("replace_existing_settings", True)
        task.set_editor_property("save", True)
        task.set_editor_property("factory", unreal.FbxFactory())
        options = unreal.FbxImportUI()
        options.set_editor_property("import_mesh", True)
        options.set_editor_property("import_as_skeletal", False)
        options.set_editor_property("import_animations", False)
        options.set_editor_property("import_materials", False)
        options.set_editor_property("import_textures", False)
        options.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
        settings = options.get_editor_property("static_mesh_import_data")
        settings.set_editor_property("convert_scene", False)
        settings.set_editor_property("convert_scene_unit", False)
        settings.set_editor_property("force_front_x_axis", False)
        settings.set_editor_property("import_uniform_scale", 1.0)
        settings.set_editor_property("import_translation", unreal.Vector(0, 0, 0))
        settings.set_editor_property("import_rotation", unreal.Rotator(0, 0, 0))
        settings.set_editor_property("remove_degenerates", False)
        settings.set_editor_property("auto_generate_collision", False)
        settings.set_editor_property("combine_meshes", True)
        settings.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS)
        task.set_editor_property("options", options)
        TOOLS.import_asset_tasks([task])
        asset_path = obj["static_mesh_asset"].split(".")[0]
        mesh = ASSETS.load_asset(asset_path)
        if not isinstance(mesh, unreal.StaticMesh):
            raise RuntimeError("Phase6 FBX did not produce static mesh: " + asset_path)
        mesh.set_editor_property("allow_cpu_access", True)
        mesh.set_editor_property("support_ray_tracing", True)
        nanite = mesh.get_editor_property("nanite_settings")
        nanite.set_editor_property("enabled", False)
        mesh.set_editor_property("nanite_settings", nanite)
        build = mesh_editor.get_lod_build_settings(mesh, 0)
        build.set_editor_property("recompute_normals", False)
        build.set_editor_property("recompute_tangents", False)
        build.set_editor_property("remove_degenerates", False)
        build.set_editor_property("use_full_precision_u_vs", True)
        build.set_editor_property("use_high_precision_tangent_basis", True)
        build.set_editor_property("max_lumen_mesh_cards", 32)
        build.set_editor_property("distance_field_resolution_scale", 2.0)
        build.set_editor_property("generate_distance_field_as_if_two_sided", obj["id"] in (300, 301, 310, 311))
        mesh_editor.set_lod_build_settings(mesh, 0, build)
        mesh.set_material(0, ASSETS.load_asset("/Game/Materials/M_AnatomyPhase6"))
        ASSETS.save_loaded_asset(mesh)
        imported.append({"id": obj["id"], "asset": asset_path,
                         "render_vertices": mesh_editor.get_number_verts(mesh, 0),
                         "lumen_cards_max": 32, "nanite_enabled": False,
                         "coordinate_conversion": "scene/unit disabled; explicit FBX Y pre-mirror compensates legacy converter, source cm and identity node scale"})
        unreal.log("LAP_PHASE6_STATIC_MESH " + asset_path)
    evidence = Path(__file__).resolve().parents[3] / "tmp" / "phase6"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "static-mesh-import.json").write_text(json.dumps(imported, indent=2), encoding="utf8")


def main():
    if "-LapPhase6AssetsOnly" in unreal.SystemLibrary.get_command_line():
        make_anatomy_material(phase6=True)
        import_phase6_static_meshes()
        ASSETS.save_directory("/Game/Phase6", only_if_is_dirty=False, recursive=True)
        ASSETS.save_asset("/Game/Materials/M_AnatomyPhase6", only_if_is_dirty=False)
        unreal.log("LAPTRAINER_PHASE6_ASSETS_SUCCESS")
        return
    ASSETS.make_directory("/Game/Maps")
    ASSETS.make_directory("/Game/Materials")
    make_anatomy_material()
    phase6_source = Path(__file__).resolve().parents[3] / "Assets" / "Phase6" / "scene.json"
    if phase6_source.exists():
        make_anatomy_material(phase6=True)
        import_phase6_static_meshes()
    make_material("M_Tissue", (0.57, 0.165, 0.205), vertex=True, tissue=True)
    make_material("M_Metal", (0.59, 0.61, 0.64), metallic=0.88, steel=True)
    make_material("M_Instrument", (0.59, 0.61, 0.64), metallic=0.88, steel=True)
    make_material("M_Dark", (0.017, 0.022, 0.028), roughness=0.6, polymer=True)
    make_material("M_Table", (0.035, 0.077, 0.091), roughness=0.62)
    make_material("M_Accent", (0.035, 0.31, 0.34), roughness=0.38, metallic=0.05)
    make_material("M_Insulation", (0.012, 0.018, 0.022), polymer=True)
    make_material("M_Tray", (0.49, 0.52, 0.55), metallic=0.8, steel=True)
    make_material("M_PadBacking", (0.055, 0.095, 0.11), roughness=0.72)
    map_path = "/Game/Maps/TrainingMap"
    subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if ASSETS.does_asset_exist(map_path):
        if not subsystem.load_level(map_path):
            raise RuntimeError("Could not load existing training level")
    else:
        if not subsystem.new_level(map_path):
            raise RuntimeError("Could not create training level")
    if not subsystem.save_current_level():
        raise RuntimeError("Could not save training level")
    ASSETS.save_directory("/Game", only_if_is_dirty=False, recursive=True)
    unreal.log("LAPTRAINER_ASSETS_SUCCESS")


try:
    main()
except Exception:
    unreal.log_error("LAPTRAINER_ASSETS_FAILED")
    raise
