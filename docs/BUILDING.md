# Building EndoForge — Phase 6 and preserved earlier phases

The current Phase 6 scene selects protocol 5 with UE `-LapPhase6`, native `--phase6`, assets under `Assets/Phase6` and matching port 47329. The native default remains protocol 4 for technical specimens. `LapTrainer` remains the internal UE project name. Dependencies, generated runtimes and deliveries are excluded from Git. The sections below preserve earlier workflows under explicit historical headings.

A build on another clean machine has not been independently verified. Actual binary hashes and local test results are recorded by the release workflow; these instructions do not promise byte-identical builds.

The [Phase 6 source/asset inventory](verification/phase6-source-assets.json) retains the 173 input hashes from the accepted r2 build receipt. Git attributes preserve authored bytes for these inputs: automatic CRLF/LF conversion would invalidate asset fingerprints even without changing JSON values. Documentation and the new development launcher are publication additions, outside that original build inventory. Hydrate Git LFS before comparing UE asset hashes.

## Prerequisites

| Requirement | Baseline / purpose |
|---|---|
| Windows x64 | Phase 6 uses DirectX 12 / SM6 with hardware ray tracing; earlier rendering paths are historical |
| Git and Git LFS | `.uasset` and `.umap` files are LFS objects |
| Unreal Engine 5.7.4 | Installed separately through Epic's supported distribution; not included in this repository |
| Visual Studio 2022 with Desktop development with C++ | MSVC v143 x64 compiler, Windows SDK, `vswhere`, and `dumpbin` |
| Validated physics toolchain | MSVC 19.38.33145.0 and Windows SDK 10.0.22621.0; build scripts select the available VS 2022 installation rather than forcing these exact versions |
| Validated UE toolchain | MSVC toolchain 14.44.35226 and Windows SDK 10.0.22621.0, selected by UnrealBuildTool |
| PowerShell and `curl.exe` | Windows build/download scripts; the baseline uses Windows PowerShell 5.1 |
| Python 3.11 or newer | Standard-library TCP tests and SHA-256 release tooling; NumPy/Pillow for the independent geometry/image audits; not needed to run the trainer |

CMake 4.4.4, SOFA 26.06.00, Eigen 3.4.0, Boost 1.87.0, and nlohmann/json 3.11.3 are fetched by the dependency script. UE's Python asset script uses the Python runtime bundled with the editor. Reauthoring Phase 5 anatomy uses Blender 5.2.2 LTS; the existing exported assets can be used without Blender. Independent liver-contact and stereo-data audits use Python with NumPy and Pillow. SofaPython3 is not required.

Run the following commands from the **repository root**, in PowerShell. Replace the engine path with your own installation:

```powershell
$EngineRoot = 'C:/Program Files/Epic Games/UE_5.7'
git lfs install
git lfs pull
```

The `.uproject` associates with UE 5.7; use the tested 5.7.4 installation for this baseline. Each UE build/run script accepts `-EngineRoot`. The scripts' existing fallback path is a development-machine convenience, not an installation requirement.

## Current Phase 6 build and development

```powershell
& .\Physics\download-dependencies.ps1
& .\Physics\build.ps1
& .\Prototype\LapTrainer\Scripts\Build.ps1 -EngineRoot $EngineRoot -Target Editor
# Separate terminals; the editor command opens the full project, not a cooked EXE.
& .\Scripts\StartPhase6Development.ps1 -Mode Physics
& .\Scripts\StartPhase6Development.ps1 -Mode Editor -EngineRoot $EngineRoot
```

See [START-HERE](START-HERE.md) for Play/preview behavior and port/shutdown details.
The current editable Blender model, FBX exports, textures and physical/visual JSON
are under `Assets/Phase6`; its generators also read original Phase 5 assets.
Do not regenerate assets just to open the checked-in project. Regeneration changes
identities and requires dependent validation.

For a complete editor input/data exercise, after building:

```powershell
& .\Prototype\LapTrainer\Scripts\TestPhase6Editor.ps1 -EngineRoot $EngineRoot -RunName 'Phase6-YOUR-RUN' -Acceptance
```

Full delivery additionally requires the native 35-case suite, guard/network/replay
tests, independent geometry/image audits, exact-binary packaging and fresh archive
execution. [PHASE6](PHASE6.md) and `Scripts/Phase6/acceptance-spec.json` define the
gates. `Scripts/Phase6/validate_native_candidate.py` coordinates native/audit work;
`freeze_ue_validation.py` binds an editor build and successful integration to the
native suite; `build_receipt.py`, `assemble.py`, `collect_evidence.py`, `archive.py`
and `final_delivery_receipt.py` form the delivery chain. Consult each script's
`--help` and use fresh run directories. Some acceptance commands intentionally
require locally generated evidence and preservation baselines; a source checkout
is not a copy of the original workstation's complete test history.

The published r2 result is a completed local build, not a guarantee that a newly
compiled binary or modified asset inherits those results. The publication-only
development helper has separate syntax/argument validation. No additional runtime
acceptance is inferred from documentation changes.

## Historical Phase 5 build, test and package

Run the dependency downloader and native build below, then build the UE editor.
The anatomy mesh is loaded from `Assets/Phase5/physics-mesh.json`; changing it
invalidates dependent physics, replay and rendered-data receipts.

```powershell
& .\Physics\download-dependencies.ps1
& .\Physics\build.ps1
& .\Prototype\LapTrainer\Scripts\Build.ps1 -EngineRoot $EngineRoot -Target Editor
& .\Prototype\LapTrainer\Scripts\TestPhase5Editor.ps1 -EngineRoot $EngineRoot -RunName 'Phase5-YOUR-RUN'
# Basic native exercise; the full delivery also needs matrix/endurance/repeat/network tests.
& .\Physics\runtime\LapPhysics.exe --self-test-phase5 --mesh .\Assets\Phase5\physics-mesh.json --report .\tmp\phase5-native-YOUR-RUN.json
```

The release workflow uses fresh destinations and never replaces Phase 1–4.
Use Python 3.11 or later for the hashing/assembly scripts and the NumPy/Pillow
environment for `audit_dataset.py` and `audit_liver_contact.py`.

```powershell
& .\Prototype\LapTrainer\Scripts\Package.ps1 -EngineRoot $EngineRoot -OutputDirectory .\tmp\phase5-uat-YOUR-RUN *> .\tmp\phase5-uat-YOUR-RUN.log
python .\Scripts\Phase5\build_receipt.py --root . --ue-package .\tmp\phase5-uat-YOUR-RUN\Windows --package-log .\tmp\phase5-uat-YOUR-RUN.log --output .\tmp\phase5-build-YOUR-RUN.json
python .\Scripts\Phase5\assemble.py --root . --ue-package .\tmp\phase5-uat-YOUR-RUN\Windows --build-receipt .\tmp\phase5-build-YOUR-RUN.json --output .\output\verification\phase5-candidate-YOUR-RUN
& .\Scripts\TestPhase5Package.ps1 -PackageRoot .\output\verification\phase5-candidate-YOUR-RUN -RunName 'phase5-input-YOUR-RUN'
```

Successful build and input reports are necessary but not sufficient. Independently
audit actual captured snapshots, stereo data, whole-face jaw contact, the connected
liver bed and preservation of old deliveries. Seal the complete evidence-bearing
package with `Scripts/Phase5/archive.py`, create a fresh ZIP, extract and verify
its manifest, then repeat the packaged input and independent geometry/data audits.
See [PHASE5.md](PHASE5.md), `Scripts/Phase5/acceptance-spec.json`, and the final
delivery's verification index for exact identities and executed coverage.

The editable Blender scene and generators are under `Assets/Phase5` and
`Scripts/BlenderPhase5`. The playable package does not require any authoring tools.
The copied `Source/` directory keeps the repository layout; fetch dependencies
there before rebuilding. A SOFA source archive is supplied for license/source
availability and is not a substitute for the compiler, SDK or UE installation.

## Historical Phase 4 build and verify

```powershell
& .\Physics\download-dependencies.ps1
& .\Physics\build.ps1
& .\Physics\RunPhase4Regression.ps1
& .\Prototype\LapTrainer\Scripts\Build.ps1 -EngineRoot $EngineRoot -Target Editor
& .\Scripts\RunPhase4Protocol.ps1 -EngineRoot $EngineRoot
& .\Scripts\RunPhase4Integration.ps1 -EngineRoot $EngineRoot
```

The downloader uses the pinned manifest in `Physics/dependencies.json`. Already verified downloads in `ThirdParty/` are reused. The build stages the executable and its DLL dependencies into `Physics/runtime/`, with dependency notices, SOFA configuration and source/executable hash metadata. Staging alone does not mark tests as passed; the regression wrapper creates actual native and TCP evidence.

The committed `.umap` and `.uasset` files are Git LFS assets. Asset regeneration is optional: `Prototype/LapTrainer/Scripts/GenerateAssets.ps1` regenerates the map/materials after an editor build and may change those binaries. It does not refine the physical tissue mesh.

For manual development, run `Physics/runtime/LapPhysics.exe` in one terminal and `Prototype/LapTrainer/Scripts/RunEditor.ps1 -EngineRoot $EngineRoot -Game` in another. Phase 4 uses localhost port 47325. Stop the manual service before running wrappers that start their own service on that port; wrappers report occupied ports rather than killing unrelated processes.

## Historical Phase 4 package and relocate

For the current collision correction, use the [separate collision-fix workflow](PHASE4-COLLISION-FIX.md#delivery-commands). It writes only to `output/Phase4-CollisionFix/` and preserves the original Phase 1–4 deliveries. The commands below document the original Phase 4 workflow and must not be used to overwrite that preserved delivery during the correction.

```powershell
& .\Prototype\LapTrainer\Scripts\Package.ps1 -EngineRoot $EngineRoot *> .\tmp\phase4-package.log
& .\Scripts\WritePhase4BuildReceipt.ps1 -PackageLog .\tmp\phase4-package.log
& .\Scripts\AssemblePhase4.ps1
& .\Scripts\TestPhase4Package.ps1 -RunName 'phase4-packaged-YOUR-RUN'
python .\Scripts\finalize_phase4.py --run-directory '.\output\verification\phase4-packaged-YOUR-RUN' --package-log '.\tmp\phase4-package.log' --protocol-directory '<protocol-run-directory>' --legacy-input-directory '<phase3-compatibility-run>' --validate-only
# Repeat the finalizer command without --validate-only after validation.
& .\Scripts\TestPhase4Archive.ps1
```

Create the `tmp` directory before redirecting a log into it if it does not exist. Each verification run needs a fresh name. `--protocol-directory` is required by the finalizer for independent UE protocol automation provenance; it must match the editor module captured after UAT. The editor module and packaged game have different hashes and separate evidence.

The assembled application is `output/Phase4/EndoForge/StartTrainer.cmd`. The finalizer writes `output/Phase4/EndoForge_Phase4_Win64.zip`, its hash sidecar, curated verification evidence and a per-file manifest. The archive test extracts into a new directory, verifies every listed file and repeats packaged input acceptance. Its receipt is stored beside the original ZIP.

Existing Phase 4 output is not replaced without `AssemblePhase4.ps1 -Replace`; replacement is constrained to a checked child directory of `output/Phase4/`. Phase 1, Phase 2 and Phase 3 delivery directories are preserved against the pre-development SHA-256 baseline. The runtime package includes prerequisites and required native libraries; users do not need the UE editor, Python, Blender or full SOFA SDK.

See [PHASE4.md](PHASE4.md) for physical scope, required evidence and test interpretation, and [README-Phase4.md](../Scripts/README-Phase4.md) for Chinese user instructions.

## Earlier baseline

The historical [Phase 2 build guide](BUILDING-PHASE2.md) applies to commit `8045a66` and its single-grasper UE source. The current native service retains `--phase2` for legacy diagnostics, and `--phase3`/UE `-LapPhase3` for the previous thin-specimen protocol. UE without an explicit phase flag uses protocol 4; the Phase 5 launcher supplies its explicit flag. Rebuilding Phase 2 as a complete application requires its matching historical source; mixing the current client with the old server is unsupported. Preserved packaged deliveries can be run independently.
