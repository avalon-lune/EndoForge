# EndoForge Phase 8 — shared foundation

Author and maintainer: Avalon. The supplied verification records and the final
receipt beside the ZIP establish which engineering checks passed and identify
the exact archive. This guide describes operation and limits, not clinical
validation. See `TESTING.zh-CN.md` for the Chinese manual test guide.

Extract the complete package, then run StartTrainer.cmd. A complete Windows
package supplies the native physics runtime and its required libraries; UE
Editor, Blender and Python are not needed for ordinary packaged use. The scene
requires a GPU/driver supporting the configured DX12/SM6 hardware ray tracing.

Wait for scene preparation. Press 2 or 3 to approach the left or right grasp
position; C switches instruments. Arrow keys or right-mouse dragging move the
active tool, W/S or the wheel changes height, and Ctrl enables fine movement.
Ctrl+wheel requests a 0.2 mm move. F toggles closure; Space closes temporarily.
T/G move along the instrument axis and Q/E rotate it. Middle-mouse dragging
changes the view; PageUp/PageDown changes distance; Home restores the view.
R/1 resets, F5 records, F6 replays, F7 saves a frozen snapshot and F10
exits. End recording before closing; retract before retrying a blocked release.
Replay retains strict physical/execution configuration checks.

The common foundation uses synthetic engineering anatomy. Attachment rendering
visualizes constraints; ducts and vessels remain orientation landmarks. Liver
and cavity structures are mainly static. No clinical force/material calibration,
complete dissection, suturing or universal collision support is claimed. Shading
normals and geometric labels remain separate.

The unchanged native runtime and physical inputs are identified against the
accepted freshly executed Phase 7 qualification. Phase 8 does not claim a new
35-case native execution. Integrated interaction, rendering, replay and package
verification require their own fresh records.

Four frozen stereo frames are internal correspondence regressions at rest,
single traction, dual traction and release. They are not research sequences, a
Project 1/2 dataset deliverable or a downstream teammate-reader acceptance gate.
Earlier accepted deliveries retain their own verification records.

The editable project is `Source/Prototype/LapTrainer/LapTrainer.uproject`.
From `Source/`, start `Scripts/StartPhase8Development.ps1 -Mode Physics`, then
`-Mode Editor` in another terminal. The helper verifies and reuses the packaged
native runtime; UE 5.7.4 and the C++ build environment are required for editing.
Original Blender assets are under `Assets/Phase8/`; source authoring dependencies
are retained under `Source/Assets/Phase5` through `Source/Assets/Phase8`.
No claim of a clean rebuild on another machine is implied by source inclusion.

Read `Source/docs/PHASE8-BRANCH-BOUNDARY.md` before starting either research
branch. Specialized highlight/curvature/tracking outputs and the colon/endoscope
scene remain separate work. This common scene improves synthetic tissue
appearance but does not claim real-surgical-image photorealism.
