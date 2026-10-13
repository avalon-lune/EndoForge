"""Create project-owned procedural training assets using the Unreal Python API.

Run only after compiling the LapTrainerEditor C++ target. The level remains
minimal because TrainingGameMode creates the interactive scene at runtime.
Surface detail changes shading only: no displacement, WPO or collision offset.
"""
import unreal

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


def main():
    ASSETS.make_directory("/Game/Maps")
    ASSETS.make_directory("/Game/Materials")
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
