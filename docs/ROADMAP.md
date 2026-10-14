# EndoForge roadmap

EndoForge aims to become a laparoscopic skills simulation environment in which tissue, instruments and training tasks behave consistently enough to support structured evaluation. The immediate development strategy is to complete small, verifiable physical interactions before combining them into more complex procedures.

This document separates delivered work from planned work. It is a technical direction, not a delivery schedule or a claim of clinical validation. Team size, hardware, clinical partners and available calibration data will determine the eventual scope and timing.

## Delivered locally: Phase 3 — two instruments and membrane cutting

The current source implements a keyboard/mouse grasper and scissors acting on a thin training membrane. Each tool retains its own target, closure, roll and trocar-constrained actual pose. The grasper can remain deliberately closed while the selected scissors performs repeated cuts.

Physical cutting splits material connectivity along selected in-plane mesh edges through a thin tetrahedral layer, retaining element volumes, material mass and pre-cut motion. Elastic and contact structures are rebuilt on that topology; the complete current mesh and both tools are accepted atomically by UE. The render surface uses linear bindings with no artificial connection across duplicated cut nodes. Extended incisions can separate tissue components.

The [Phase 3 specification](PHASE3.md) records the actual constitutive model, cut resolution, closing/contact gates, numerical protections and exclusions. This remains a discrete engineering model of a thin training specimen. It does not establish arbitrary volumetric organ cutting, biological fracture energy, clinically measured cutting forces or validated training effectiveness.

The [local verification summary](verification/phase3-summary.json) records successful native, TCP, packaged and extracted-package checks.

Acceptance consists of a reproducible hold–tension–cut–release exercise, physical mass/connectivity and disconnected-response tests, inactive-tool/air-cut rejection, reset, protocol robustness, UE input/render checks and packaged/relocated testing. Actual receipts, rather than this roadmap, determine whether any particular build completed those checks. Local deliverables and evidence are placed in `output/Phase3/` and `output/verification/`.

## Preserved earlier milestones

Phase 1 established the external physics bridge and keyboard/mouse grasp–traction–release loop. Its proximity-assisted grasp was superseded by native contact mechanics in Phase 2.

Phase 2 implements one grasper acting on a 120 × 80 × 12 mm pad, using a 351-node, 1,152-tetrahedron corotational FEM model, native friction contact, bounded instrument motion and detailed procedural geometry. Its [verification summary](verification/phase2-summary.json) belongs to that historical delivery. Existing `output/Phase1/` and `output/Phase2/` packages are preserved; the current thin-membrane client is a later source revision.

## Cutting refinements beyond this milestone

Finer incision geometry requires a justified resolution/performance budget or a more general sub-element remeshing strategy. Future work should examine membrane self-contact, more faithful bypass-scissor geometry, force-calibrated fracture behavior, general organ remeshing and biological material data. Each change needs renewed convergence, contact and topology validation. Visual smoothness alone is not physical resolution.

Full-organ dissection, bleeding and thermal energy effects remain outside the delivered training-membrane scope. The next major interaction milestone is needle and thread mechanics, developed independently before combining it with cut-edge approximation.

## Suturing: needle and thread mechanics — planned

**Goal:** pass a needle through a controlled specimen and use a physical thread to approximate and retain the tissue edges.

This is a separate mechanics milestone. It needs a needle contact/puncture model, a thread representation with stretch and bend behavior, thread–instrument and thread–tissue interaction, and stable handling of multiple contact states. A rendered spline connecting two points is not sufficient to establish suture behavior.

Develop the exercise in increasing difficulty: needle handling, controlled entry/exit, thread passage, tissue-edge approximation, then loop and knot behavior where justified by the chosen model. Acceptance should examine puncture events, thread tension, contact/sliding, recovery after releasing a tool, repeatability and numerical stability. Knot security and tissue injury would require additional models and physical validation; neither follows automatically from a visually plausible knot.

## Anatomy, imaging and visual fidelity — planned

**Goal:** move from standardized pads to selected anatomical training scenes while retaining traceable geometry and mechanics.

The initial priority is a coherent training scene: calibrated scale, appropriate instrument proportions, endoscope-like viewing, useful lighting, and materials that preserve visibility of contact and deformation. Anatomical detail should be added to support a defined exercise rather than only to increase asset complexity.

Possible later inputs include segmentation and mesh preparation from medical imaging, external modeling tools, and clinician-reviewed anatomy. Tools such as 3D Slicer or MITK may support a future preparation pipeline; they are not integrated dependencies of the present runtime. Any clinical image use would require an appropriate data source, permissions and handling process. No patient-data workflow is implemented now.

Mechanical additions may include distinct tissue layers, more suitable constitutive laws, anisotropy, viscoelasticity, self-contact and selected organ attachments. Each addition must be justified by the target task and available measurements. More render vertices do not establish a more accurate tissue model.

Completion criteria should cover anatomical review, mesh quality, contact consistency, target viewing conditions and a validated link between the chosen material model and the exercise. Broad claims of general surgical realism remain out of scope until that evidence exists.

## Calibration and clinical evaluation — required before clinical claims

**Goal:** connect model behavior to measurements and assess whether the resulting exercises are useful to their intended users.

Work should begin with an agreed use case and measurable quantities. Candidate measurements include force–displacement curves, compression and relaxation behavior, instrument geometry and jaw kinematics, friction/slip under controlled loading, and cutting or puncture behavior where those features exist. Parameters should be fitted with documented uncertainty, and checked on measurements that were not used in fitting.

Clinician review should shape the task, instrument handling, visual cues and failure cases. Training metrics need their own evaluation: movement efficiency, completion time and contact exposure can be logged, but a numerical score is not automatically a valid assessment of surgical skill. Reliability, usability and learning-effectiveness studies are distinct from software regression tests.

Potential hardware support includes tracked or encoded instrument handles, camera calibration and optional haptics. These require explicit coordinate calibration, latency and failure handling. Force feedback additionally needs a dedicated stability and update-rate design; the current 30 Hz tissue solver is not a ready-made haptic servo loop.

No current numerical protection threshold should be presented as a clinical safety limit or injury threshold. Any future deployment claims must match the intended use and the evidence actually obtained.

## Engineering work across milestones

| Area | Direction and completion evidence |
|---|---|
| Reproducible builds | Verify a clean public checkout on a separate Windows environment; record toolchain versions, dependency hashes and generated assets |
| Testing | Keep native physics, protocol, UE input and packaged-launch tests distinct; fail on unhealthy or malformed state history, not only on process exit |
| Performance | Measure end-to-end latency and solver/render budgets under representative contact and topology loads; report hardware and resolution with results |
| Numerical quality | Extend mesh-quality, contact, force-balance and convergence checks for each new physical feature; record rejected steps and protective stops |
| Rendering | Bind all visible deformable geometry to the authoritative model and quantify any deliberate surface offsets |
| Telemetry | Preserve metric definitions, units, reset identifiers and test provenance; distinguish model predictions from measured physical values |
| Usability | Evaluate camera views, control switching, recovery from errors and clear contact/slip cues with intended users |
| Distribution | Maintain dependency notices, corresponding-source handling, asset provenance and explicit project licensing before offering broader reuse terms |

## How a milestone is considered complete

A milestone needs a playable exercise, an explained physical model, reproducible acceptance tests, reviewed screenshots or recordings, and a documented list of remaining limitations. A passing editor run is followed by packaged testing; relocation and a clean-machine/clean-checkout check provide different evidence and should be reported separately.

The current [README](../README.md), [Phase 3 specification](PHASE3.md) and [build guide](BUILDING.md) describe the implementation. Future milestones remain hypotheses to validate through physical measurements, software tests and user evaluation.
