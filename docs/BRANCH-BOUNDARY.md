# Common foundation and research branch responsibilities

Author and maintainer: **Avalon**. Updated 2 November 2026 for Phase9. The current
engineering candidate is ready for human visual/interaction review; neither
research specialization has been implemented or delivered by this milestone.

## Shared foundation

Retain the UE/native transport, accepted-state identity, units, timebase, strict
replay, original asset workflow, renderer, camera conventions and geometric
export contract. The current gallbladder scene demonstrates physical interaction
and the relationship between displayed geometry and data.

Phase9 uses 724 physical wall nodes and 2,160 tetrahedra, with a separate
92,160-triangle display and a recorded 0.12 mm reconstruction bound. It supplies
actual node velocities and signed per-jaw contact reactions. The liver is static,
the wall has no luminal fluid-pressure model, and tissue/force parameters remain
uncalibrated. Display density is not FEM resolution or evidence of biological validity.

The current review should check remaining contour/curvature bands, anatomy,
material appearance and manipulation. Engineering test success is recorded
separately from this human judgement. A new model or changed physical parameters
need new identities and affected validation; old recordings retain their old build.

## Project-specific work after the common review

| Direction | Reuse | Additional implementation |
|---|---|---|
| Project1: stereo endoscopic highlight/image research | Paired cameras, renderer, original material workflow, state and geometric labels | Define and implement HDR/specular decomposition, masks, curvature, visibility, instances/tracks and controlled scene variations against its research contract |
| Project2: colon/endoscope sequences | Camera/state/version conventions, physical/display binding, recording, rendering and export infrastructure | Author colon anatomy and folds; implement relevant endoscope motion/geometry, physical gaps, temporal material-point correspondence, revisits, visibility and longer trajectories |

The current gallbladder does not substitute for a colon scene. These rows are
planned responsibilities, not claims that the named outputs already exist.
Each branch will establish its own operating range and output acceptance.

## Imaging profile is a separate choice

The realistic common scene can later receive a surgical-camera appearance profile:
device response, tone mapping, lens distortion, noise or temporal effects. This
does not define the Project1/Project2 split. Spatial transformations must update
coordinates and validity consistently; temporal effects need explicit sampling.
No new camera-effects profile is claimed as part of Phase9.

Native coordinates are metres, UE coordinates centimetres, and image depth is
camera-axis Z in millimetres. Geometric normals exclude material normal maps.
Four stereo frames in Phase9 are internal correspondence checks, not a research
dataset or a teammate-reader integration deliverable. Tutor requirements and
original reference media remain local. See [physical outputs](../Physics/README-Phase9-Output.md),
[current results](verification/phase9-summary.json) and the preserved
[Phase8 boundary](PHASE8-BRANCH-BOUNDARY.md) for historical context.
