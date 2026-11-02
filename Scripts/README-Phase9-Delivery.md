# EndoForge Phase 9 — visual review candidate

Author and maintainer: Avalon. This package is prepared for direct visual and
interactive review. `review-candidate.json` identifies the tested build and
evidence. Human visual approval remains pending until the reviewer supplies it;
engineering checks do not establish clinical validity.

Extract the complete package and double-click `StartTrainer.cmd`. UE Editor,
Blender, Python and physical instrument hardware are not needed for packaged
use. Wait for scene/physics readiness before interaction. The configured renderer
uses DX12, SM6, Lumen and hardware ray tracing.

Press 2/3 for the left/right approach preset; C selects the active instrument.
Arrow keys or right-mouse dragging move it; W/S changes height, T/G changes
insertion, Q/E changes roll, and Ctrl enables precision movement. Ctrl+wheel
requests a 0.2 mm height change. F toggles jaw closure; Space closes temporarily.
Middle-mouse dragging changes the view; PageUp/PageDown changes distance and
Home restores it. R/1 resets; F5 starts/stops recording; F6 replays; F7 saves a
frozen state; F10 exits. A physically blocked jaw opening may require retraction
before release. Playback enforces the current model and execution identity.

Phase 9 revises the physical wall and its attached display surface, original
organ appearance, support-weighted liver-bed attachment and output definitions.
The display is reconstructed from current physical nodes with a recorded
0.12 mm bound. It is also the geometry used for image/depth/normal labels.
Fine normal maps affect shading, not the exported geometric normal.

New live-state fields provide solver node velocities and signed world-coordinate
per-jaw contact reactions in newtons. These describe the last accepted substep;
they are distinct from the older sum of individual contact-force magnitudes.
Read `Source/Physics/README-Phase9-Output.md` for indexing, sign, sampling and
invalid-state behavior. These are not calibrated handle-force measurements.

The source and editable Blender scene are supplied for inspection. The working
UE project in the development workspace remains the primary editable project;
source inclusion alone is not a promise of a clean rebuild on another machine.
Required third-party software and license notices are retained separately from
the original anatomy. Teacher reference images and third-party anatomy archives
are not redistributed here.

The liver is static. Surrounding cavity/fat and duct/artery landmarks do not
implement general soft-tissue contact or dissection. The hollow wall has no
luminal fluid-pressure model, identified biological parameters or clinical
calibration. Suturing, full-shaft/general self-contact, force-feedback hardware
and the two research branches' specialized outputs are outside this delivery.
Four internal stereo frames test coordinate/state correspondence; they are not
a research dataset. Earlier phase deliveries remain independently preserved.

Use `TESTING.zh-CN.md` for the focused visual review checklist. Record the view,
tool, action and screenshot when reporting a remaining shape or contact defect.
Open `Evidence/visual_gallery.html` for actual UE before/after and neutral-grey
views. The grey views expose remaining distal curvature bands for review; they
are not a claim that every surface defect has been eliminated.
