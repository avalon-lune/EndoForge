"""Create only Phase8 materials and imported meshes using the Unreal Python API.

Run only after compiling the LapTrainerEditor C++ target. The level remains
minimal because TrainingGameMode creates the interactive scene at runtime.
Surface detail changes shading only: no displacement, WPO or collision offset.
"""
import unreal
import gc
import json
from pathlib import Path

MEL = unreal.MaterialEditingLibrary
ASSETS = unreal.EditorAssetLibrary


def asset_tools():
    # Keep UObject wrappers local to operations so no tool instance survives
    # into editor teardown when this module is executed through runpy.
    return unreal.AssetToolsHelpers.get_asset_tools()


def connect(source, output_name, destination, input_name):
    if not MEL.connect_material_expressions(source, output_name, destination, input_name):
        available = MEL.get_material_expression_input_names(destination)
        raise RuntimeError("Material graph connection failed: " + str(destination.get_class().get_name()) +
                           " input=" + repr(input_name) + " available=" + repr(available))
    return True


def connect_property(source, output_name, material_property):
    if not MEL.connect_material_property(source, output_name, material_property):
        raise RuntimeError("Material output connection failed: " + str(material_property))
    return True

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
return 0.014 * brush + 0.022 * (noise.value(UV * float2(13, 80)) - 0.5);
"""

STEEL_NORMAL = r"""
float phase = UV.y * 760.0;
float aa = 1.0 - smoothstep(0.4, 2.5, fwidth(phase));
return normalize(float3(0.0, 0.0015 * cos(phase) * aa, 1.0));
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
    if not connect(uv, "", node, "UV"):
        raise RuntimeError("Could not connect UV input for " + description)
    return node


def make_material(name, rgb, roughness=0.4, metallic=0.0, vertex=False,
                  tissue=False, steel=False, polymer=False):
    asset_path = "/Game/Phase8/Materials/" + name
    material = ASSETS.load_asset(asset_path) if ASSETS.does_asset_exist(asset_path) else None
    if material is None:
        material = asset_tools().create_asset(name, "/Game/Phase8/Materials", unreal.Material, unreal.MaterialFactoryNew())
    if material is None:
        raise RuntimeError("Could not create material " + name)
    MEL.delete_all_material_expressions(material)
    material.set_editor_property("two_sided", True)
    material.set_editor_property("tangent_space_normal", True)
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_SUBSURFACE if tissue else unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    if tissue:
        base = custom_uv(material, TISSUE_COLOR, unreal.CustomMaterialOutputType.CMOT_FLOAT3,
                         "Subtle training-pad color and surface fibers", -650, -180)
    elif steel:
        base = expression(material, unreal.MaterialExpressionVectorParameter, -600, -160)
        base.set_editor_property("parameter_name", "SteelBaseColor")
        base.set_editor_property("default_value", unreal.LinearColor(*rgb, 1.0))
    else:
        base = color(material, rgb, -600, -160)
    if vertex:
        vertex_node = expression(material, unreal.MaterialExpressionVertexColor, -600, -340)
        multiply = expression(material, unreal.MaterialExpressionMultiply, -280, -160)
        connect(base, "", multiply, "A")
        connect(vertex_node, "RGB", multiply, "B")
        base = multiply
    connect_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    roughness_node = scalar(material, roughness, -260, 10)
    normal_node = None
    if tissue:
        roughness_node = custom_uv(material, TISSUE_ROUGHNESS, unreal.CustomMaterialOutputType.CMOT_FLOAT1,
                                   "Thin wet surface finish", -650, 100)
        normal_node = custom_uv(material, TISSUE_NORMAL, unreal.CustomMaterialOutputType.CMOT_FLOAT3,
                                "Micro-normal only: no physical displacement", -650, 350)
    elif steel:
        brushing = custom_uv(material, STEEL_ROUGHNESS, unreal.CustomMaterialOutputType.CMOT_FLOAT1,
                             "Fine stainless-steel brushing variation", -950, 100)
        finish = expression(material, unreal.MaterialExpressionScalarParameter, -950, 20)
        finish.set_editor_property("parameter_name", "SteelRoughness")
        finish.set_editor_property("default_value", .36)
        roughness_node = expression(material, unreal.MaterialExpressionAdd, -480, 100)
        connect(finish, "", roughness_node, "A")
        connect(brushing, "", roughness_node, "B")
        anisotropy = expression(material, unreal.MaterialExpressionScalarParameter, -480, 530)
        anisotropy.set_editor_property("parameter_name", "SteelAnisotropy")
        anisotropy.set_editor_property("default_value", .4)
        connect_property(anisotropy, "", unreal.MaterialProperty.MP_ANISOTROPY)
        normal_node = custom_uv(material, STEEL_NORMAL, unreal.CustomMaterialOutputType.CMOT_FLOAT3,
                                "Very low-amplitude steel micro-normal", -650, 350)
    elif polymer:
        roughness_node = custom_uv(material, POLYMER_ROUGHNESS, unreal.CustomMaterialOutputType.CMOT_FLOAT1,
                                   "Soft molded-polymer surface finish", -650, 100)
    connect_property(roughness_node, "", unreal.MaterialProperty.MP_ROUGHNESS)
    if normal_node is not None:
        connect_property(normal_node, "", unreal.MaterialProperty.MP_NORMAL)
    if steel:
        metal = expression(material, unreal.MaterialExpressionScalarParameter, -260, 600)
        metal.set_editor_property("parameter_name", "SteelMetallic")
        metal.set_editor_property("default_value", metallic)
    else:
        metal = scalar(material, metallic, -260, 100)
    connect_property(metal, "", unreal.MaterialProperty.MP_METALLIC)
    connect_property(scalar(material, 0.38 if tissue else 0.4, -260, 200), "", unreal.MaterialProperty.MP_SPECULAR)
    if tissue:
        connect_property(color(material, (0.38, 0.075, 0.065), -260, 550), "", unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
        connect_property(scalar(material, 0.85, -260, 410), "", unreal.MaterialProperty.MP_OPACITY)
    MEL.recompile_material(material)
    ASSETS.save_loaded_asset(material)
    unreal.log("LAPTRAINER_ASSET " + asset_path)


def make_anatomy_material(phase8=False):
    name = "M_AnatomyPhase8" if phase8 else "M_Anatomy"
    path = "/Game/Phase8/Materials/" + name
    material = ASSETS.load_asset(path) if ASSETS.does_asset_exist(path) else asset_tools().create_asset(name, "/Game/Phase8/Materials", unreal.Material, unreal.MaterialFactoryNew())
    MEL.delete_all_material_expressions(material)
    material.set_editor_property("two_sided", True)
    material.set_editor_property("tangent_space_normal", True)
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_SUBSURFACE_PROFILE if phase8 else unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    if phase8:
        profile_path = "/Game/Phase8/Materials/SP_TissuePhase8"
        profile = ASSETS.load_asset(profile_path)
        if profile is None:
            profile = asset_tools().create_asset("SP_TissuePhase8", "/Game/Phase8/Materials", unreal.SubsurfaceProfile, unreal.SubsurfaceProfileFactory())
        scene = json.loads((Path(__file__).resolve().parents[3] / "Assets/Phase8/scene.json").read_text(encoding="utf8"))
        authored = scene["phase8_material_profile"]
        settings = profile.get_editor_property("settings")
        for prop, value in [("enable_burley", True), ("enable_mean_free_path", True),
                            ("world_unit_scale", authored["world_unit_scale"]),
                            ("mean_free_path_distance", authored["mean_free_path_distance_cm"]),
                            ("roughness0", authored["roughness0"]),
                            ("roughness1", authored["roughness1"]),
                            ("lobe_mix", authored["lobe_mix"]), ("ior", 1.38)]:
            settings.set_editor_property(prop, value)
        settings.set_editor_property("mean_free_path_color", unreal.LinearColor(*authored["mean_free_path_color"], 1))
        settings.set_editor_property("surface_albedo", unreal.LinearColor(.28, .16, .12, 1))
        settings.set_editor_property("tint", unreal.LinearColor(1, 1, 1, 1))
        settings.set_editor_property("implementation", unreal.SubsurfaceImplementationTechniqueHint.SIH_SEPARABLE)
        profile.set_editor_property("settings", settings)
        ASSETS.save_loaded_asset(profile)
        material.set_editor_property("subsurface_profile", profile)
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
    connect(base, "", mix, "A")
    connect(tex, "RGB", mix, "B")
    connect(weight, "", mix, "Alpha")
    gain = expression(material, unreal.MaterialExpressionVectorParameter, -350, -400)
    gain.set_editor_property("parameter_name", "BaseColorGain")
    gain.set_editor_property("default_value", unreal.LinearColor(1, 1, 1, 1))
    tinted = expression(material, unreal.MaterialExpressionMultiply, -100, -200)
    connect(mix, "", tinted, "A")
    connect(gain, "", tinted, "B")
    connect_property(tinted, "", unreal.MaterialProperty.MP_BASE_COLOR)
    for name, value, prop, y in [("Roughness", .3, unreal.MaterialProperty.MP_ROUGHNESS, 100), ("Metallic", 0, unreal.MaterialProperty.MP_METALLIC, 200)]:
        node = expression(material, unreal.MaterialExpressionScalarParameter, -400, y)
        node.set_editor_property("parameter_name", name)
        node.set_editor_property("default_value", value)
        connect_property(node, "", prop)
    phase = "Phase8" if phase8 else "Phase5"
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
        asset_tools().import_asset_tasks([task])
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
        connect(weightnode, "", blend, "Alpha")
        if label == "Normal":
            decode = expression(material, unreal.MaterialExpressionMultiply, -750, 450)
            connect(texnode, "RGB", decode, "A")
            connect(scalar(material, 2, -950, 600), "", decode, "B")
            offset = expression(material, unreal.MaterialExpressionSubtract, -500, 450)
            connect(decode, "", offset, "A")
            connect(scalar(material, 1, -750, 600), "", offset, "B")
            connect(color(material, (0, 0, 1), -500, 600), "", blend, "A")
            handed = expression(material, unreal.MaterialExpressionMultiply, -350, 500)
            connect(offset, "", handed, "A")
            connect(color(material, (1, -1, 1), -500, 700), "", handed, "B")
            connect(handed, "", blend, "B")
            connect_property(blend, "", unreal.MaterialProperty.MP_NORMAL)
        else:
            fallback = expression(material, unreal.MaterialExpressionScalarParameter, -500, 850)
            fallback.set_editor_property("parameter_name", "Roughness")
            fallback.set_editor_property("default_value", .3)
            connect(fallback, "", blend, "A")
            connect(texnode, "R", blend, "B")
            rough_scale = expression(material, unreal.MaterialExpressionScalarParameter, -100, 850)
            rough_scale.set_editor_property("parameter_name", "RoughnessScale")
            rough_scale.set_editor_property("default_value", 1.0)
            rough_bias = expression(material, unreal.MaterialExpressionScalarParameter, -100, 1000)
            rough_bias.set_editor_property("parameter_name", "RoughnessBias")
            rough_bias.set_editor_property("default_value", 0.0)
            scaled = expression(material, unreal.MaterialExpressionMultiply, 150, 750)
            connect(blend, "", scaled, "A")
            connect(rough_scale, "", scaled, "B")
            biased = expression(material, unreal.MaterialExpressionAdd, 350, 750)
            connect(scaled, "", biased, "A")
            connect(rough_bias, "", biased, "B")
            bounded = expression(material, unreal.MaterialExpressionClamp, 550, 750)
            bounded.set_editor_property("min_default", 0.08)
            bounded.set_editor_property("max_default", 0.8)
            connect(biased, "", bounded, MEL.get_material_expression_input_names(bounded)[0])
            connect_property(bounded, "", unreal.MaterialProperty.MP_ROUGHNESS)
    if phase8:
        # SSS and the low-roughness wet microfacet lobe are implemented in the
        # actual UE material. This is not a Blender-only clear-coat preview.
        specular = expression(material, unreal.MaterialExpressionScalarParameter, -300, 300)
        specular.set_editor_property("parameter_name", "Specular")
        specular.set_editor_property("default_value", .32)
        connect_property(specular, "", unreal.MaterialProperty.MP_SPECULAR)
        subsurface = expression(material, unreal.MaterialExpressionVectorParameter, -300, 1100)
        subsurface.set_editor_property("parameter_name", "SubsurfaceColor")
        subsurface.set_editor_property("default_value", unreal.LinearColor(.38, .13, .08, 1))
        connect_property(subsurface, "", unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
        opacity = expression(material, unreal.MaterialExpressionScalarParameter, -300, 1250)
        opacity.set_editor_property("parameter_name", "SubsurfaceOpacity")
        opacity.set_editor_property("default_value", .93)
        connect_property(opacity, "", unreal.MaterialProperty.MP_OPACITY)
    else:
        connect_property(scalar(material, .45, -300, 300), "", unreal.MaterialProperty.MP_SPECULAR)
    MEL.recompile_material(material)
    ASSETS.save_loaded_asset(material)


def import_phase8_static_meshes():
    """Create actual static-mesh Lumen cards, preserving full-resolution LOD0.

    FBX vertices are authored in centimetres with Y pre-mirrored to compensate
    legacy UE's unconditional handedness conversion. Scene/unit conversion is
    disabled and the final actual LOD0 XYZ is checked by the geometry audit.
    Nanite is intentionally not enabled: reference depth must match actual LOD0.
    """
    root = Path(__file__).resolve().parents[3] / "Assets" / "Phase8"
    source = json.loads((root / "scene.json").read_text(encoding="utf8"))
    mesh_editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    imported = []
    for obj in source["static_objects"]:
        if "fbx_file" not in obj:
            continue
        asset_path = obj["static_mesh_asset"].split(".")[0]
        if asset_path != "/Game/Phase8/Meshes/SM_" + str(obj["id"]):
            raise RuntimeError("Refusing to replace an asset outside generated Phase8 meshes")
        # Legacy FBX atomic reimport retains prior coordinate settings even when
        # a fresh FbxImportUI is attached to an AssetImportTask. Rebuild only our
        # seven reproducible Phase8 derived meshes; no earlier-phase assets.
        if ASSETS.does_asset_exist(asset_path) and not ASSETS.delete_asset(asset_path):
            raise RuntimeError("Could not replace generated Phase8 mesh " + asset_path)
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", str(root / obj["fbx_file"]))
        task.set_editor_property("destination_path", "/Game/Phase8/Meshes")
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
        asset_tools().import_asset_tasks([task])
        asset_path = obj["static_mesh_asset"].split(".")[0]
        mesh = ASSETS.load_asset(asset_path)
        if not isinstance(mesh, unreal.StaticMesh):
            raise RuntimeError("Phase8 FBX did not produce static mesh: " + asset_path)
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
        mesh.set_material(0, ASSETS.load_asset("/Game/Phase8/Materials/M_AnatomyPhase8"))
        ASSETS.save_loaded_asset(mesh)
        imported.append({"id": obj["id"], "asset": asset_path,
                         "render_vertices": mesh_editor.get_number_verts(mesh, 0),
                         "lumen_cards_max": 32, "nanite_enabled": False,
                         "coordinate_conversion": "scene/unit disabled; explicit FBX Y pre-mirror compensates legacy converter, source cm and identity node scale"})
        unreal.log("LAP_PHASE6_STATIC_MESH " + asset_path)
    evidence = Path(__file__).resolve().parents[3] / "tmp" / "phase8"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "static-mesh-import.json").write_text(json.dumps(imported, indent=2), encoding="utf8")


def verify_compiled_material_statistics():
    """Finish actual-platform compilation after graph construction, before success.

    Temporary disconnected expressions can emit warnings while graphs are built.
    This final compiled evidence is separate from the stricter C++ runtime
    shader-map/fallback gate and fresh-process reload validation.
    """
    records = []
    for name in ("M_AnatomyPhase8", "M_MetalPhase8", "M_InsulationPhase8"):
        path = "/Game/Phase8/Materials/" + name
        material = ASSETS.load_asset(path)
        if not isinstance(material, unreal.Material):
            raise RuntimeError("Missing generated material: " + path)
        statistics = MEL.get_statistics(material)  # Internally FinishCompilation().
        fields = ("num_vertex_shader_instructions", "num_pixel_shader_instructions", "num_samplers")
        values = {key: int(statistics.get_editor_property(key)) for key in fields}
        passed = values["num_vertex_shader_instructions"] > 0 and values["num_pixel_shader_instructions"] > 0
        records.append({"asset": path, "statistics": values, "compiled_instructions_available": passed})
        if not passed:
            raise RuntimeError("Final compiled shader instructions unavailable: " + path)
        ASSETS.save_loaded_asset(material)
        del statistics, material
    evidence = Path(__file__).resolve().parents[3] / "tmp" / "phase8"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "material-import-verification.json").write_text(json.dumps({
        "schema": "endoforge.phase8.material-import.v1", "passed": True, "materials": records,
        "scope": "Final compiled instruction evidence; fresh reload and runtime shader-map validation are required separately."
    }, indent=2), encoding="utf8")


def main():
    # Scoped paths are deliberate: no Phase1-7 assets or map are regenerated.
    ASSETS.make_directory("/Game/Phase8/Materials")
    make_anatomy_material(phase8=True)
    make_material("M_MetalPhase8", (0.62, 0.65, 0.68), metallic=1.0, steel=True)
    make_material("M_InsulationPhase8", (0.009, 0.012, 0.016), polymer=True)
    verify_compiled_material_statistics()
    import_phase8_static_meshes()
    ASSETS.save_directory("/Game/Phase8", only_if_is_dirty=False, recursive=True)
    unreal.log("LAPTRAINER_PHASE8_ASSETS_SUCCESS")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        unreal.log_error("LAPTRAINER_PHASE8_ASSETS_FAILED")
        raise
    finally:
        gc.collect()
