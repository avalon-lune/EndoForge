# EndoForge roadmap

The immediate research direction is controllable endoscopic image sequences with corresponding geometry and deformation state. Physical interaction supports that goal; a complete surgical training curriculum and clinically calibrated force prediction are separate longer-term objectives. The order below reflects that direction and is not a delivery-date commitment.

Author and maintainer: **Avalon**. As of 24 October 2026, the local **Phase 6 r2 engineering delivery has passed**; [STATUS](STATUS.md) distinguishes that result from unfinished appearance, calibration and specialized datasets. [MILESTONES](MILESTONES.md) gives the stage-by-stage implementation history.

## Phase 4 — deformation, curved specimens, replay and traceability

The current source extends the verified Phase 3 interaction to configurable flat and curved thin specimens, simulation-step action recordings, guarded replay, and physical/render/camera state capture. Suturing is deferred.

The [Phase 4 specification](PHASE4.md) defines the acceptance gates: meaningful stable manipulation, 600 simulated seconds of continuous prescribed actions for each shape, five repeated sequences with no more than 0.5 mm node RMS deviation, contact/health records, independent snapshot geometry/projection checks, exact-binary packaged and relocated testing, and preservation of all earlier delivery files.

Passing those gates establishes a reusable engineering deformation foundation. It does not prove that the curved technical specimen is a gallbladder, that a material is biologically accurate, or that every possible organ interaction has been solved. Actual test receipts determine whether a build is complete.

## Preserved foundation — Phase 4 collision correction

Before anatomy work, revisit the curved straight-retreat defect and expand angle, speed and trajectory coverage with raw surface geometry checks. The [collision-fix specification](PHASE4-COLLISION-FIX.md) adds these gates while retaining every existing Phase 4 acceptance requirement. The corrected distribution is separate; all Phase 1–4 deliveries remain preserved. A successful finite matrix establishes only its measured operating range.

## Phase 5 — localized gallbladder and cavity scene

Select one camera-visible local scene and one or two target actions using the research output requirements and real reference videos. Build only the anatomy needed for that view and motion. Specify anatomical connections and fixed regions before committing the visual asset, because attachments strongly affect the deformation.

Completion requires a coherent scale, geometry/physics binding, appropriate camera/light/material behavior, and credible movement under the selected action. Add tissue-to-tissue or self-contact only where the scene needs it. High visual polygon counts do not improve the resolution of the underlying physical model.

The [Phase 5 implementation](PHASE5.md) adds original editable Blender anatomy, a closed thin-wall gallbladder, compliant liver-bed attachment, two friction graspers, guarded replay and short stereo/geometry exports. Its native, independent geometry, packaged and relocated test receipts determine acceptance. These engineering checks remain separate from anatomical review and experimental tissue calibration. The existing mesh-edge cutting stays in the legacy specimen modes.

## Phase 6 — shared interaction, rendering and output foundation

The current delivery improves manual response/target bounds, observation space,
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

## Next — specialized scenes and paired dataset workflows

Basic stereo RGB, camera parameters, depth, geometric normals, object IDs, masks and physical state already exist. Agree on each project's additional output fields, scene, variation and ingestion requirements before extending the exporter. Candidate additions include temporal tissue trajectories, richer visibility and task-specific image decomposition. Their inclusion follows the downstream research contract, not a blanket promise to export everything. The tutor's original reference documents remain local and are not republished here.

Each image must identify the physical state and camera that produced it. A video and an independently sampled physics CSV are not automatically synchronized ground truth. Handle resets, duplicated render frames, cut-induced identity changes and occlusion explicitly. Export provenance, parameters, actions and timebase so samples can be regenerated and checked.

Acceptance includes ingestion by the intended research code, numerical/image correspondence checks and a small reviewed dataset before large-scale generation. Scene, action, material and appearance variations should then be expanded according to measured coverage needs.

## Preserved earlier milestones

Phase 1 established the external physics bridge and keyboard/mouse grasp–traction–release loop. Phase 2 replaced assisted attachment with native friction contact on a thick tetrahedral tissue pad and improved procedural instrument geometry. [Phase 2 evidence](verification/phase2-summary.json) belongs to that historical package.

Phase 3 added two tools and physical cutting of a thin tetrahedral specimen. Cutting changes material connectivity and generates real cut sidewalls, retaining element rest volumes, mass and motion. Its [specification](PHASE3.md) describes the 5 mm edge discretization and exclusions; its [verification summary](verification/phase3-summary.json) identifies tested binaries. Packages in `output/Phase1/`, `output/Phase2/` and `output/Phase3/` remain preserved.

## Deferred mechanics and calibration

Needle handling, puncture, physical thread, sliding through tissue and knots are a separate future milestone. A visual spline or an unexplained fixed attachment cannot establish suturing. Full-organ remeshing/dissection, bleeding, electrocautery and force-feedback hardware also need their own requirements and verification.

If force research becomes a deliverable, define the predicted quantity first and obtain appropriate measurements. Contact impulse magnitudes are not measured handle force, biological damage or a validated tissue parameter. Calibration requires documented parameter fitting, uncertainty and checks against independent measurements.

Clinician review, anatomical review, usability, skill-assessment validity and learning effectiveness are distinct from software regression. Hardware haptics requires a dedicated stability and timing design; the tissue solver is not a ready-made high-rate haptic loop.

## Completion discipline

A milestone needs an explained implementation, reproducible tests, reviewed captures, playable output and explicit limitations. Editor, packaged, extracted-package and clean-machine/clean-checkout checks provide different evidence and should be reported separately. Record exact code/configuration/binary hashes and retain failed trials as diagnostics rather than accepted delivery evidence.
