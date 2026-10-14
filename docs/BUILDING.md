# Building EndoForge — Phase 3

The current UE client uses Phase 3 protocol and the native service defaults to the thin-membrane model. `LapTrainer` remains the technical UE project/executable name. Downloaded dependencies, generated runtime files and delivery packages are excluded from Git.

A build on another clean machine has not been independently verified. Actual binary hashes and local test results are recorded by the release workflow; these instructions do not promise byte-identical builds.

## Prerequisites

| Requirement | Baseline / purpose |
|---|---|
| Windows x64 | Current supported build and runtime platform; the renderer uses DirectX 11 |
| Git and Git LFS | `.uasset` and `.umap` files are LFS objects |
| Unreal Engine 5.7.4 | Installed separately through Epic's supported distribution; not included in this repository |
| Visual Studio 2022 with Desktop development with C++ | MSVC v143 x64 compiler, Windows SDK, `vswhere`, and `dumpbin` |
| Validated physics toolchain | MSVC 19.38.33145.0 and Windows SDK 10.0.22621.0; build scripts select the available VS 2022 installation rather than forcing these exact versions |
| Validated UE toolchain | MSVC toolchain 14.44.35226 and Windows SDK 10.0.22621.0, selected by UnrealBuildTool |
| PowerShell and `curl.exe` | Windows build/download scripts; the baseline uses Windows PowerShell 5.1 |
| Python 3.10 or newer | Standard-library-only TCP tests and release finalizer; not needed to run the trainer |

CMake 4.4.4, SOFA 26.06.00, Eigen 3.4.0, Boost 1.87.0, and nlohmann/json 3.11.3 are fetched by the dependency script. UE's Python asset script uses the Python runtime bundled with the editor. Blender and SofaPython3 are not required.

Run the following commands from the **repository root**, in PowerShell. Replace the engine path with your own installation:

```powershell
$EngineRoot = 'C:/Program Files/Epic Games/UE_5.7'
git lfs install
git lfs pull
```

The `.uproject` associates with UE 5.7; use the tested 5.7.4 installation for this baseline. Each UE build/run script accepts `-EngineRoot`. The scripts' existing fallback path is a development-machine convenience, not an installation requirement.

## Build and verify

```powershell
& .\Physics\download-dependencies.ps1
& .\Physics\build.ps1
& .\Physics\RunPhase3Regression.ps1
& .\Prototype\LapTrainer\Scripts\Build.ps1 -EngineRoot $EngineRoot -Target Editor
& .\Scripts\RunPhase3Protocol.ps1 -EngineRoot $EngineRoot
& .\Scripts\RunPhase3Integration.ps1 -EngineRoot $EngineRoot
```

The downloader uses the pinned manifest in `Physics/dependencies.json`. Already verified downloads in `ThirdParty/` are reused. The build stages the executable and its DLL dependencies into `Physics/runtime/`, with dependency notices, SOFA configuration and source/executable hash metadata. Staging alone does not mark tests as passed; the regression wrapper creates actual native and TCP evidence.

The committed `.umap` and `.uasset` files are Git LFS assets. Asset regeneration is optional: `Prototype/LapTrainer/Scripts/GenerateAssets.ps1` regenerates the map/materials after an editor build and may change those binaries. It does not refine the physical tissue mesh.

For manual development, run `Physics/runtime/LapPhysics.exe` in one terminal and `Prototype/LapTrainer/Scripts/RunEditor.ps1 -EngineRoot $EngineRoot -Game` in another. Phase 3 uses localhost port 47323. Stop the manual service before running wrappers that start their own service on that port; wrappers report occupied ports rather than killing unrelated processes.

## Package and relocate

```powershell
& .\Prototype\LapTrainer\Scripts\Package.ps1 -EngineRoot $EngineRoot *> .\tmp\phase3-package.log
& .\Scripts\AssemblePhase3.ps1
& .\Scripts\TestPhase3Package.ps1 -RunName 'phase3-packaged-YOUR-RUN'
python .\Scripts\finalize_phase3.py --run-directory '.\output\verification\phase3-packaged-YOUR-RUN' --package-log '.\tmp\phase3-package.log' --validate-only
# Repeat the finalizer command without --validate-only after validation.
& .\Scripts\TestPhase3Archive.ps1
```

Create the `tmp` directory before redirecting a log into it if it does not exist. Each verification run needs a fresh name. Use `--protocol-directory` on the finalizer to include an independent UE protocol automation receipt. The editor module and packaged game have different hashes and separate evidence.

The assembled application is `output/Phase3/EndoForge/StartTrainer.cmd`. The finalizer writes `output/Phase3/EndoForge_Phase3_Win64.zip`, its hash sidecar, curated verification evidence and a per-file manifest. The archive test extracts into a new directory, verifies every listed file and repeats packaged input acceptance. Its receipt is stored beside the original ZIP.

Existing Phase 3 output is not replaced without `AssemblePhase3.ps1 -Replace`; replacement is constrained to a checked child directory of `output/Phase3/`. Phase 1 and Phase 2 delivery directories are preserved. The runtime package includes prerequisites and required native libraries; users do not need the UE editor, Python, Blender or full SOFA SDK.

See [PHASE3.md](PHASE3.md) for physical scope, required evidence and test interpretation, and [README-Phase3.md](../Scripts/README-Phase3.md) for Chinese user instructions.

## Earlier baseline

The historical [Phase 2 build guide](BUILDING-PHASE2.md) applies to commit `8045a66` and its single-grasper UE source. The current native service retains `--phase2` for legacy diagnostics, but the current UE client requires protocol 3. Rebuilding Phase 2 as a complete application requires its matching historical source; mixing the current client with the old server is unsupported. Preserved packaged deliveries can be run independently.
