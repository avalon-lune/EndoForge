# Open, run and inspect Phase 9

Author and maintainer: **Avalon**. Current Phase9 is an engineering-verified
review candidate; human visual approval remains pending. Read [the scope and
limits](PHASE9.md) before evaluating it.

The local review package is not hosted by this source synchronization. If you
have the delivered package, open `output/Phase9/EndoForge-Phase9-review-final01/` and
double-click `StartTrainer.cmd`. Read its `TESTING.zh-CN.md` and open
`Evidence/visual_gallery.html` for the focused review and unchanged UE captures.
The package includes its native runtime; UE Editor/Blender/Python are not needed.

The complete editable workspace project remains
`Prototype/LapTrainer/LapTrainer.uproject`. From the workspace root, use two
PowerShell terminals:

```powershell
# Terminal A: keep matching physics running.
& .\Scripts\StartPhase9Development.ps1 -Mode Physics
# Terminal B: full editor, then normal Play.
& .\Scripts\StartPhase9Development.ps1 -Mode Editor -EngineRoot 'E:/UE_5.7'
```

This selects UE `-LapPhase9`, the compatible native `--phase6` solver, explicit
`Assets/Phase9` geometry and matching development port 47391. Opening the project
alone does not select this milestone or start physics. The same helper supports
`-Mode Preview` and `-DryRun`. The original Blender scene is in `Assets/Phase9`.
The source included in the delivery is inspection source, not a self-contained
clean-machine authoring/cook distribution. Previous recordings retain their
corresponding earlier model and execution configuration.

For a GitHub source checkout, install the [build prerequisites](BUILDING.md), run
`git lfs install` and `git lfs pull`, then build the native runtime and editor
module. The repository contains authored UE assets; it does not contain UE,
the SDK installation, compiled executables or the local trainer ZIP.

## Phase 9 controls and code map

Wait for healthy connected physics. Press `2` or `3` for the left/right approach
preset, `C` to select an instrument, and `F` to toggle its jaws. Arrows or right
mouse dragging move the tip; `Ctrl` enables precision movement, and
`Ctrl + wheel` requests a 0.2 mm height pulse. `W/S` changes height, `T/G`
insertion, `Q/E` roll. Middle-button drag orbits the view; `PageUp/PageDown`
changes distance and `Home` restores it. `R` resets, `F5` records, `F6` replays,
`F7` snapshots, `F10` quits. A liver-blocked jaw may require retraction before
opening. Read the [focused visual checklist](../Scripts/TESTING-Phase9.zh-CN.md).

The current runtime mechanics are in `Physics/Phase3Model.h`, with Phase9 FEM and
output auditing in `Phase9FEM.h` and `Phase9OutputAudit.h`. UE uses
`Phase6Interaction.cpp`, the shared scene/bridge and `Phase9Rendering.cpp` for
the current presentation. The [output contract](../Physics/README-Phase9-Output.md)
defines velocities, signed reactions and validity. Model authoring is in
`Assets/Phase9` and `Scripts/BlenderPhase9`.

# Preserved Phase8 startup

Author/maintainer: **Avalon**. The full UE editor, standalone preview and packaged trainer are separate entry points.

## Prepare a source checkout

Use Windows x64 and the validated UE 5.7.4 / Visual Studio 2022 C++ setup. Install Git LFS and run `git lfs pull` for UE assets. UE is installed separately. Follow [BUILDING](BUILDING.md) to fetch pinned native dependencies and build the physics executable and UE editor module. Compiled executables and SDKs are excluded from source publication.

## Open the editable UE project

`Prototype/LapTrainer/LapTrainer.uproject` opens the full project. Double-clicking alone does not start SOFA or select Phase 8: the scene chooses its milestone from launch arguments. From the repository root, use two PowerShell terminals:

```powershell
# Terminal A: native physics service; keep running while testing.
& .\Scripts\StartPhase8Development.ps1 -Mode Physics
# Terminal B: full editor with Phase 8 arguments, then click Play.
& .\Scripts\StartPhase8Development.ps1 -Mode Editor -EngineRoot 'E:/UE_5.7'
# Optional standalone game preview through the editor executable:
& .\Scripts\StartPhase8Development.ps1 -Mode Preview -EngineRoot 'E:/UE_5.7'
```

The helper selects UE `-LapPhase8`, the compatible native `--phase6` solver, matching port `47351`, absolute asset/mesh paths and D3D12. Absolute native paths matter because the service changes its working directory to its runtime folder. UE displays accepted SOFA geometry rather than applying a second Chaos tissue simulation.

Use normal Play within the editor process. A separate standalone Play process may need the same additional launch parameters in UE settings. Restarting the native service between separate play sessions gives a clean baseline. Close/stop the game before stopping the native terminal, and finish recording before shutdown. The helper refuses to start a second service on an occupied port.

`-DryRun` prints executable/arguments without launching. The delivered Source/ launcher can reuse the exact sibling packaged physics runtime after checking its executable and mesh identities. A full clean-machine editor rebuild is a separate, unverified claim.

## Run the local package

Fully extract the Phase8 delivery ZIP and double-click `StartTrainer.cmd`. Its launcher starts the included physics service and manages shutdown. UE editor, Blender, Python and physical instruments are not needed. Phase8 needs compatible DX12/SM6 hardware ray tracing; recorded performance used an RTX 5080, and other hardware requires measurement.

Phase8 delivery identity and results are recorded in the final receipt beside its ZIP under `output/Phase8/`. Until that receipt passes, a candidate is not accepted. The accepted Phase7 archive remains preserved; see [its historical results](verification/phase7-summary.json). The package includes `TESTING.zh-CN.md`; prior deliveries stay in their original phase folders. Old recordings require the corresponding old package; differing effective execution configurations can be rejected by strict replay checks.

## Controls

Wait for preparation and healthy connected physics. Press `2`, wait for left approach, then `F` to close. Use `3` for right approach and `C` to select a tool. Each `F` toggles that tool's closure; friction determines holding and slip.

| Input | Action |
|---|---|
| Arrows / right-button drag | Camera-relative tip movement |
| W / S; wheel | Vertical movement |
| Ctrl / Shift | Fine / faster input |
| Ctrl + wheel | Finite 0.2 mm vertical target pulse |
| T / G; Q / E | Shaft-axis movement; roll |
| F / Space | Closure latch / temporary closure |
| C; 2 / 3 | Select tool; left / right approach |
| R / 1 | Reset |
| Middle-button drag; PageUp / PageDown; Home | Orbit; distance; restore observation |
| Tab / H | View / help |
| F5 / F6 / F7 | Record / replay / frozen snapshot |
| Esc / F10 | Release controls and request opening / quit |

Recording begins from reset; replay locks live motion and checks model/configuration identities. Static-liver blocking can prevent opening until retraction; it is geometric blocking, not measured reaction force. A numerical health stop requires reset and log inspection.

## Code reading map

- `TrainingScene.cpp`, `Phase6Interaction.cpp`: controller input and observation.
- `Phase5Scene.cpp`: shared anatomy scene, basic stereo outputs and input exercises.
- `Phase6Rendering.cpp`: display binding, feature captures and runtime metrics.
- `SimulationBridge.cpp`: validated state/command transport.
- `Phase7Progression.cpp`, `Phase7ProgressionClock.h`: paired native/wall progression records, distinct from display FPS.
- `Physics/Phase3Model.h`: shared mechanics; `Phase6ToolCollision.h`: static-liver jaw admission.
- `Assets/Phase8/EndoForge_Anatomy.blend`, `Scripts/BlenderPhase8`: editable modeling and authoring.

Read [STATUS](STATUS.md) before interpreting images, forces or sample exports as medical ground truth or a finished research deliverable.
