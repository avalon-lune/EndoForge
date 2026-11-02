# EndoForge Phase 9 development and authoring

Author and maintainer: Avalon. These entry points select the current Phase9
assets explicitly. They do not build, import or qualify anything automatically.
The changed physical mesh requires fresh qualification; Phase8 acceptance and
native inheritance receipts do not qualify Phase9.

| Endpoint | Assets / selector | Default TCP port |
| --- | --- | --- |
| Native development | `--phase6 --mesh Assets/Phase9/physics-mesh.json` | `47391` |
| UE editor / preview | `-LapPhase9 -LapAnatomyDir=<absolute Assets/Phase9>` | `47391` |
| Packaged launcher | `-LapPhase9`, explicit package `Assets/Phase9` | `47411` |

The compatible native `--phase6` entry point identifies the solver and protocol.
It loads the named Phase9 mesh. UE materials and meshes use `/Game/Phase9`;
earlier phase roots keep their existing selectors and behavior.

Run all commands below from the repository root. Every launcher supports
`-DryRun`, which prints its command without starting a process.

Author the scene with `Scripts/BlenderPhase9/build_assets.py` using the project's
Blender installation. Build `LapTrainerEditor` separately after C++ changes.
Close this project in Unreal Editor, then explicitly import its authored assets:

```powershell
& .\Prototype\LapTrainer\Scripts\ImportPhase9Assets.ps1 -EngineRoot 'E:/UE_5.7'
```

The importer writes a fresh `tmp/phase9/imports/<run>/` directory. Its receipt
binds the inputs, compiled material statistics and actual imported LOD0 position,
triangle, UV and authored-normal checks. It also compares earlier Content and
Assets before and after the import. These are authoring diagnostics; physical,
runtime shader-map, visual and delivery checks remain separate.

The importer reads `phase9_material_profile` from `scene.json` and creates the
three Phase9 runtime materials plus `M_Phase9DiagnosticGrey`. The grey material
has constant base color `(0.45, 0.45, 0.45)`, roughness `0.65` and specular `0.25`,
with no textures, normal map or subsurface scattering. It is excluded from the
three authored-material statistics and is used only when explicitly requested.

For interactive work, use separate PowerShell terminals:

```powershell
& .\Scripts\StartPhase9Development.ps1 -Mode Physics
& .\Scripts\StartPhase9Development.ps1 -Mode Editor -EngineRoot 'E:/UE_5.7'
```

Keep the physics terminal open and use normal in-process Play in the editor.
`-Mode Preview` starts the game directly. Supply the same `-PhysicsPort` on both
commands when choosing a different port. `-SessionDirectory` must be fresh so
that existing recordings are preserved. There is no fallback to an earlier
phase's packaged runtime or acceptance receipt.

Run bounded authoring diagnostics after building and importing:

```powershell
# Native-backed organ shape inspection with grey organ materials.
& .\Prototype\LapTrainer\Scripts\DiagnosePhase9Editor.ps1 `
    -RunName 'Phase9-Grey-01' -SkipDataset -ShapeReview `
    -ExtraUnrealArguments @('-LapPhase9Grey')

# Authored materials and actual UE viewport footage.
& .\Prototype\LapTrainer\Scripts\DiagnosePhase9Editor.ps1 `
    -RunName 'Phase9-Materials-01' -Video -ShapeReview
```

Each invocation requires a new run name and writes under
`Prototype/LapTrainer/Saved/<run>/`. Both examples use the real native process
and the normal diagnostic sequence. Grey inspection does not replace visual
review of authored materials. The script always passes `-LapDiagnostic`; its
timing and footage are diagnostic evidence, not acceptance performance.
`-ExtraUnrealArguments` passes additional diagnostic switches without changing
the default selector or asset paths. No existing service is stopped when a port
is occupied. Cleanup targets only processes launched by that invocation.

For a separately prepared package, use its fresh package root:

```powershell
& .\Scripts\StartPhase9.ps1 -PackageRoot 'E:/path/to/Phase9Package'
```

The package needs `Physics/LapPhysics.exe`,
`LapTrainer/Binaries/Win64/LapTrainer.exe`, cooked Phase9 content, and the full
`Assets/Phase9` directory. When distributing this launcher at the package root,
copy `Phase7ProcessPolicy.ps1` beside it. Package assembly, archive sealing and
final delivery qualification are separate steps.
