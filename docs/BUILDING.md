# Building EndoForge — Phase 2 baseline

EndoForge contains the UE project, its authored/generated project assets, the native SOFA service, and development scripts. The technical project/executable paths retain the name `LapTrainer`. External SDKs, compiled programs, packaged distributions, training sessions, and local test output are excluded from Git.

The baseline was built and tested on its original Windows development machine. A fresh-clone build on a second machine has **not** been independently verified. The instructions below follow the checked-in script interfaces; they do not claim byte-identical executable reproduction.

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

## Download and build the physics service

```powershell
& .\Physics\download-dependencies.ps1
& .\Physics\build.ps1
```

The downloader reads [`Physics/dependencies.json`](../Physics/dependencies.json), creates `ThirdParty/`, verifies each pinned download's SHA-256, and extracts the SDK/tool/header packages. The separately downloaded nlohmann/json and Tight Inclusion notices are also hash-pinned in the manifest. A hash mismatch stops the download workflow; it is not silently accepted.

The build produces `Physics/runtime/LapPhysics.exe`. Runtime staging follows SDK DLL dependencies and copies the required libraries, notices, and `etc/sofa.ini` into `Physics/runtime/`. It generates `build-info.json` from the selected CMake compiler/SDK metadata and the current executable/source hashes, marking protocol verification as not yet run. Do not copy only the EXE. The corresponding SOFA source archive is downloaded alongside the SDK for later distribution. See [third-party components](THIRD_PARTY.md).

`Physics/build.ps1` uses the Visual Studio 2022 CMake generator. Runtime staging locates an installed x64 `dumpbin.exe` through `vswhere`; it reports a missing C++ installation explicitly. A new compiler or SDK combination needs fresh testing.

## Build and run UE

```powershell
& .\Prototype\LapTrainer\Scripts\Build.ps1 -EngineRoot $EngineRoot -Target Editor
```

The map and materials are committed through LFS, so asset generation is normally optional. To regenerate them from the checked-in procedural material/map script after building the editor module:

```powershell
& .\Prototype\LapTrainer\Scripts\GenerateAssets.ps1 -EngineRoot $EngineRoot
```

This writes `/Game/Maps/TrainingMap` and the project materials under `Content/`. Regeneration may change those binary assets; review changes before committing them. It does not change the physical mesh, contact model, or FEM parameters.

For a manual development run, start the physics service in a separate PowerShell terminal:

```powershell
Push-Location .\Physics\runtime
try { & .\LapPhysics.exe --port 47322 }
finally { Pop-Location }
```

Then launch the game from another terminal at the repository root:

```powershell
& .\Prototype\LapTrainer\Scripts\RunEditor.ps1 -EngineRoot $EngineRoot -Game
```

The UE bridge uses `127.0.0.1:47322`. Only one Phase 2 client can use that service at a time. Close the game and stop the manually started service when finished. The separately assembled package has a launcher that manages this lifecycle automatically. Controls and model limitations are documented in the root README and [`Physics/README.md`](../Physics/README.md).

## Run the existing checks

Do not leave a manual Phase 2 service running when starting the TCP or UE integration tests. Those tests start and stop their own process.

### Native numerical and TCP regression

Run the wrapper after every physics build:

```powershell
& .\Physics\RunRegression.ps1
# If Python is not on PATH:
# & .\Physics\RunRegression.ps1 -Python 'C:/path/to/python.exe'
```

It checks that port 47322 is free, verifies staged source/executable hashes, executes both real tests, records fresh executable hashes and UTC timestamps, and sets `build-info.json`'s `tested_protocol` to `2` only after both tests pass. Results are `Physics/runtime/phase2-physics-test-results.json` and `phase2-network-test-results.json`. It rejects executable changes during the test run.

The numerical test covers the FEM/contact scenario, force-unit balance, slip/release, recovery, reset, and protection behavior. The TCP test exercises the actual protocol, watchdog, malformed commands, reconnection, jaw poses, and grasp/traction scenario. Inspect `passed`, the individual checks, and model/performance metrics. These are software checks, not biological material validation.

### Individual diagnostic commands

To run just the numerical executable while developing:

```powershell
Push-Location .\Physics\runtime
try {
    & .\LapPhysics.exe --self-test phase2-physics-test-results.json
    if ($LASTEXITCODE -ne 0) { throw 'Physics regression failed.' }
}
finally { Pop-Location }
```

To run just the real TCP test:

```powershell
python .\Physics\test_network.py
```

The raw native executable does not append its own executable/source hashes or UTC timestamp. Use `RunRegression.ps1`, rather than these individual commands, to create complete native release evidence. The TCP Python script does record its own executable hash.

### UE input/contact integration

```powershell
& .\Scripts\RunPhase2Integration.ps1 -EngineRoot $EngineRoot
```

The script creates a fresh timestamped directory under `output/verification/`, starts SOFA and UE, then checks the generated `phase2-input-test.json` and screenshots. The test injects UE PlayerController input events consumed by the normal input code. It is not a physical mouse/keyboard or physician usability test. `-LapPhase2Test` is the Phase 2 acceptance mode; the retained Phase 1 AutoDemo/KeyTest modes are not Phase 2 acceptance criteria.

## Create a local Windows test package

```powershell
& .\Prototype\LapTrainer\Scripts\Package.ps1 -EngineRoot $EngineRoot
& .\Scripts\AssemblePhase2.ps1
& .\output\Phase2\LapTrainer\StartTrainer.cmd
```

The UE archive defaults to `Prototype/Packages/Windows`; the assembled package is `output/Phase2/LapTrainer`. The assembler copies the physics DLLs, `etc` configuration, licenses, project source, and corresponding SOFA source archive. It excludes probes, ordinary test logs/reports, generated caches, and PDBs. It fails if the output directory already contains files unless explicitly passed `-Replace`, which replaces only the validated generated Phase 2 destination. Existing Phase 1 output is separate.

The packaged launcher starts its own hidden physics process, verifies the listening socket belongs to that process, launches UE, and stops only its own physics process afterward. An occupied Phase 2 port is reported; unrelated processes are not killed. UE's prerequisite installer is included by the packaging script. End users do not need UE, Python, or the full SOFA SDK.

For a new packaged acceptance run:

```powershell
& .\Scripts\TestPhase2Package.ps1
```

It creates a new `output/verification/phase2-packaged-*` directory with a packaged-run receipt, binary hashes, input/contact results, screenshots, logs, and a selected session CSV.

## Release provenance is a separate step

An ordinary build generates build metadata but **does not claim that tests passed**. `RunRegression.ps1` creates the native verification evidence; UE integration and packaged acceptance are separate checks. Generated metadata and test output are intentionally excluded from Git.

Before using the strict `Scripts/finalize_phase2.py` release finalizer:

1. Build and run `RunRegression.ps1` against that exact build. The scripts record the actual compiler, SDK, SOFA provenance, executable hash, timestamps, and hashes of `main.cpp`, `Phase2Model.h`, `CMakeLists.txt`, and `test_network.py`. Do not reuse metadata from a previous binary.
2. Build/package UE and retain the successful UAT log. Assemble the distribution with the current, tested physics metadata. If the output directory was already assembled before a rebuild or test, explicitly reassemble it.
3. Run `TestPhase2Package.ps1` against that assembled package. It writes the packaged-run receipt, input results, screenshots, selected telemetry, and logs, and checks that its binaries did not change during the run.
4. Pass those exact files to the finalizer. Begin with `--validate-only`; then omit that option to collect evidence, strip generated sessions/logs, generate the manifest, create the ZIP, check ZIP CRCs, and write its SHA-256 sidecar. Any executable change requires new matching evidence.

Example after the above release steps, using your actual paths:

```powershell
python .\Scripts\finalize_phase2.py `
    --run-directory '.\output\verification\phase2-packaged-YOUR-RUN' `
    --package-log '.\path\to\your-successful-uat.log' `
    --validate-only
```

The finalizer checks that native tests and the packaged run refer to the delivered executables, and that packaged physics source matches the recorded source hashes. It does not run missing tests or turn old evidence into new evidence. A fresh-machine CI build remains follow-up work.
