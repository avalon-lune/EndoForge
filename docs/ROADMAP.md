# EndoForge roadmap

The immediate research direction is controllable endoscopic image sequences with corresponding geometry and deformation state. Physical interaction supports that goal; a complete surgical training curriculum and clinically calibrated force prediction are separate longer-term objectives. The order below reflects that direction and is not a delivery-date commitment.

Author and maintainer: **Avalon**. As of 2 November 2026, **Phase9 has completed local engineering verification and packaging and is ready for human visual/interaction review**. [Exact results](verification/phase9-summary.json) and [STATUS](STATUS.md) retain the scope and limitations. Phase9 has fresh native qualification for its changed mesh. Four internal alignment frames are regressions; specialized branch development remains separate. [MILESTONES](MILESTONES.md) preserves all nine stages.

## Phase 4 — deformation, curved specimens, replay and traceability

The Phase4 source extended verified Phase3 interaction to configurable flat/curved thin specimens, simulation-step recordings, guarded replay, and physical/render/camera state capture. Suturing remained deferred.

The [Phase 4 specification](PHASE4.md) defines the acceptance gates: meaningful stable manipulation, 600 simulated seconds of continuous prescribed actions for each shape, five repeated sequences with no more than 0.5 mm node RMS deviation, contact/health records, independent snapshot geometry/projection checks, exact-binary packaged and relocated testing, and preservation of all earlier delivery files.

Passing those gates establishes a reusable engineering deformation foundation. It does not prove that the curved technical specimen is a gallbladder, that a material is biologically accurate, or that every possible organ interaction has been solved. Actual test receipts determine whether a build is complete.

## Preserved foundation — Phase 4 collision correction

The preserved Phase4 collision correction revisited the curved straight-retreat defect and expanded angle/speed/trajectory coverage with raw surface geometry checks. The [collision-fix specification](PHASE4-COLLISION-FIX.md) retained the Phase4 requirements. The earlier distributions remain preserved; the finite matrix establishes only its measured operating range.

## Phase 5 — localized gallbladder and cavity scene

Select one camera-visible local scene and one or two target actions using the research output requirements and real reference videos. Build only the anatomy needed for that view and motion. Specify anatomical connections and fixed regions before committing the visual asset, because attachments strongly affect the deformation.

Completion requires a coherent scale, geometry/physics binding, appropriate camera/light/material behavior, and credible movement under the selected action. Add tissue-to-tissue or self-contact only where the scene needs it. High visual polygon counts do not improve the resolution of the underlying physical model.

The [Phase 5 implementation](PHASE5.md) adds original editable Blender anatomy, a closed thin-wall gallbladder, compliant liver-bed attachment, two friction graspers, guarded replay and short stereo/geometry exports. Its native, independent geometry, packaged and relocated test receipts determine acceptance. These engineering checks remain separate from anatomical review and experimental tissue calibration. The existing mesh-edge cutting stays in the legacy specimen modes.

## Phase 6 — shared interaction, rendering and output foundation

The preserved Phase 6 delivery improves manual response/target bounds, observation space,
bound display geometry and original materials. Actual Lumen GI/reflections,
hardware ray tracing and near-contact shadows are verified with controlled
captures. Sustained grip, adaptive contact solving, static-liver jaw admission,
guarded replay and image/geometry correspondence have recorded engineering tests.
The [technical scope](PHASE6.md) and [public result summary](verification/phase6-summary.json)
identify the finite tested operating range and accepted r2 binaries.

Visual work is not finished. Refine anatomy, tissue color/translucency, vascular
detail and surface appearance with supervisor review. Preserve the audited
physical/display relationship and repeat affected tests after changes. This is
the shared platform before project-specific development; the current gallbladder
scene does not substitute for an intestinal/colonoscopy scene.

## Phase 7 — shared anatomy and appearance revision

The [accepted common-foundation revision](PHASE7.md) smooths and requalifies the physical/display liver, refines original materials and display UVs, retains bounded attachment geometry, and verifies actual packaged image/state correspondence. [Recorded results](verification/phase7-summary.json) bind the Phase7 runtime, assets and fresh-extracted checks. Both the former frame-pacing/progression shortfall and the transient SOFA thread-field recording mismatch are covered by the accepted execution configuration and strict replay tests.

The images remain synthetic. Supervisor review should guide further vascular/translucent detail, anatomical proportions, instrument appearance and camera response. Additional realism must preserve geometry/physics/data correspondence and rerun affected checks. Project 1 and Project 2 specialized scenes and outputs have not started in this milestone.

## Phase 8 — common foundation before branching

The current [Phase8 contract](PHASE8.md) adds reference-guided original appearance and neck-landmark refinement while keeping accepted physical identity, controls, replay and geometric outputs consistent. It removes research-sequence delivery and teammate-reader integration from this common milestone. Four internal paired states remain regression checks only. [The branch boundary](PHASE8-BRANCH-BOUNDARY.md) separates the two projects and the later surgical-camera appearance profile. Acceptance requires the exact local delivery receipt, not this roadmap.

## Phase 9 — revised organ surface and physical output

The [Phase9 revision](PHASE9.md) addresses the conspicuous gallbladder contour
corners with a revised physical wall and bound display, regional appearance and
support-weighted attachment. Actual node velocities and signed jaw contact
reactions have explicit definitions. Fresh native, independent geometry,
packaged and extracted-package checks passed. Grey near views still contain
shallow curvature bands; human visual approval is the current stopping point.

Review organ proportions, residual faceting, plastic appearance and deformation
under single/bilateral traction. Record remaining defects by view and action,
then rerun the affected engineering checks after changes. The common baseline
has not become a calibrated biological model merely because these checks pass.

## After shared-base review — specialized scenes and paired dataset workflows

[Current branch responsibilities](BRANCH-BOUNDARY.md) supersede the Phase8-era
physical counts while retaining the separation between the two research aims.

Basic stereo RGB, camera parameters, depth, geometric normals, object IDs, masks and physical state already exist. Agree on each project's additional output fields, scene, variation and ingestion requirements before extending the exporter. Candidate additions include temporal tissue trajectories, richer visibility and task-specific image decomposition. Their inclusion follows the downstream research contract, not a blanket promise to export everything. The tutor's original reference documents remain local and are not republished here.

Each image must identify the physical state and camera that produced it. A video and an independently sampled physics CSV are not automatically synchronized ground truth. Handle resets, duplicated render frames, cut-induced identity changes and occlusion explicitly. Export provenance, parameters, actions and timebase so samples can be regenerated and checked.

Each later research branch may include ingestion by its intended research code in its own acceptance, numerical/image correspondence checks and a small reviewed dataset before large-scale generation. Scene, action, material and appearance variations should then be expanded according to measured coverage needs.

## Preserved earlier milestones

Phase 1 established the external physics bridge and keyboard/mouse grasp–traction–release loop. Phase 2 replaced assisted attachment with native friction contact on a thick tetrahedral tissue pad and improved procedural instrument geometry. [Phase 2 evidence](verification/phase2-summary.json) belongs to that historical package.

Phase 3 added two tools and physical cutting of a thin tetrahedral specimen. Cutting changes material connectivity and generates real cut sidewalls, retaining element rest volumes, mass and motion. Its [specification](PHASE3.md) describes the 5 mm edge discretization and exclusions; its [verification summary](verification/phase3-summary.json) identifies tested binaries. Packages in `output/Phase1/`, `output/Phase2/` and `output/Phase3/` remain preserved.

## Deferred mechanics and calibration

Needle handling, puncture, physical thread, sliding through tissue and knots are a separate future milestone. A visual spline or an unexplained fixed attachment cannot establish suturing. Full-organ remeshing/dissection, bleeding, electrocautery and force-feedback hardware also need their own requirements and verification.

If force research becomes a deliverable, define the predicted quantity first and obtain appropriate measurements. Contact impulse magnitudes are not measured handle force, biological damage or a validated tissue parameter. Calibration requires documented parameter fitting, uncertainty and checks against independent measurements.

Clinician review, anatomical review, usability, skill-assessment validity and learning effectiveness are distinct from software regression. Hardware haptics requires a dedicated stability and timing design; the tissue solver is not a ready-made high-rate haptic loop.

## Completion discipline

A milestone needs an explained implementation, reproducible tests, reviewed captures, playable output and explicit limitations. Editor, packaged, extracted-package and clean-machine/clean-checkout checks provide different evidence and should be reported separately. Record exact code/configuration/binary hashes and retain failed trials as diagnostics rather than accepted delivery evidence.
