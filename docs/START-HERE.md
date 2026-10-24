# Open, run and inspect Phase 6

Author/maintainer: **Avalon**. The full UE editor, standalone preview and packaged trainer are separate entry points.

## Prepare a source checkout

Use Windows x64 and the validated UE 5.7.4 / Visual Studio 2022 C++ setup. Install Git LFS and run `git lfs pull` for UE assets. UE is installed separately. Follow [BUILDING](BUILDING.md) to fetch pinned native dependencies and build the physics executable and UE editor module. Compiled executables and SDKs are excluded from source publication.

## Open the editable UE project

`Prototype/LapTrainer/LapTrainer.uproject` opens the full project. Double-clicking alone does not start SOFA or select Phase 6: the scene chooses its milestone from launch arguments. From the repository root, use two PowerShell terminals:

```powershell
# Terminal A: native physics service; keep running while testing.
& .\Scripts\StartPhase6Development.ps1 -Mode Physics
# Terminal B: full editor with Phase 6 arguments, then click Play.
& .\Scripts\StartPhase6Development.ps1 -Mode Editor -EngineRoot 'E:/UE_5.7'
# Optional standalone game preview through the editor executable:
& .\Scripts\StartPhase6Development.ps1 -Mode Preview -EngineRoot 'E:/UE_5.7'
```

The helper selects UE `-LapPhase6`, native `--phase6`, matching port `47329`, absolute asset/mesh paths and D3D12. Absolute native paths matter because the service changes its working directory to its runtime folder. UE displays accepted SOFA geometry rather than applying a second Chaos tissue simulation.

Use normal Play within the editor process. A separate standalone Play process may need the same additional launch parameters in UE settings. Restarting the native service between separate play sessions gives a clean baseline. Close/stop the game before stopping the native terminal, and finish recording before shutdown. The helper refuses to start a second service on an occupied port.

`-DryRun` prints executable/arguments without launching. Publication validation of this new helper is a syntax/argument check, not a claim of an additional full interactive editor-session acceptance run.

## Run the local package

Fully extract the accepted r2 ZIP and double-click `StartTrainer.cmd`. Its launcher starts the included physics service and manages shutdown. UE editor, Blender, Python and physical instruments are not needed. Phase 6 needs compatible DX12/SM6 hardware ray tracing; recorded performance used an RTX 5080, and other hardware requires measurement.

The approximately 4.05 GB r2 ZIP remains a local delivery, not a GitHub Release supplied by this sync. See [its identity and results](verification/phase6-summary.json).

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
- `Physics/Phase3Model.h`: shared mechanics; `Phase6ToolCollision.h`: static-liver jaw admission.
- `Assets/Phase6/EndoForge_Anatomy.blend`, `Scripts/BlenderPhase6`: editable modeling and authoring.

Read [STATUS](STATUS.md) before interpreting images, forces or sample exports as medical ground truth or a finished research deliverable.
