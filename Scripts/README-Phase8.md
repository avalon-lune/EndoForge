# EndoForge Phase 8 — development entry points

Author and maintainer: Avalon. Acceptance of this common foundation is recorded
in the final verification receipt beside the Phase8 delivery archive. See
[PHASE8.md](../docs/PHASE8.md) for scope and verification requirements.

After the native runtime, UE editor module and Phase 8 assets have been prepared,
run these commands from the repository root in separate PowerShell terminals:

```powershell
& .\Scripts\StartPhase8Development.ps1 -Mode Physics
& .\Scripts\StartPhase8Development.ps1 -Mode Editor -EngineRoot 'E:/UE_5.7'
```

Keep the physics terminal running and use normal in-process Play in the editor.
`-Mode Preview` starts a standalone editor preview. Both endpoints use port
`47351`; set the same `-PhysicsPort` on both commands if another port is needed.
The native `--phase6` mode is intentional: the compatible solver loads the
explicit `Assets/Phase8/physics-mesh.json`. The editor selects `-LapPhase8`.
The launcher supports `-DryRun` to print its command without starting a process.

Wait for scene preparation. Press `2` or `3` to approach the left or right grasp
position; `C` switches the active instrument. Arrow keys or right-mouse dragging
move it, `W/S` or the wheel adjusts height, and `Ctrl` enables fine movement.
`Ctrl+wheel` requests a 0.2 mm move. `F` toggles jaw closure; `Space` closes
temporarily. `T/G` move along the instrument axis; `Q/E` rotate it.

Middle-mouse dragging changes the view; `PageUp/PageDown` changes distance and
`Home` restores the view. `R/1` resets, `F5` records, `F6` replays, `F7` saves a
frozen snapshot, and `F10` exits. End recording before closing. Strict replay
requires matching physical and execution configuration. Retract before retrying
release when collision protection blocks jaw opening.

This is synthetic engineering anatomy. The attachment display visualizes
constraints; ducts and vessels remain orientation landmarks. Liver and cavity
structures are mainly static. No clinical material/force calibration, completed
dissection, suturing, universal contact support or specialized Project 1/2
dataset is claimed. Material normals describe shading; geometric labels remain
separate. Earlier accepted deliveries remain the reference for their own results.
