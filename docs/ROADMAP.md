# EndoForge roadmap

EndoForge aims to become a laparoscopic skills simulation environment in which tissue, instruments and training tasks behave consistently enough to support structured evaluation. The immediate development strategy is to complete small, verifiable physical interactions before combining them into more complex procedures.

This document separates delivered work from planned work. It is a technical direction, not a delivery schedule or a claim of clinical validation. Team size, hardware, clinical partners and available calibration data will determine the eventual scope and timing.

## Current baseline: Phase 2 implemented

The current source implements one virtual grasper acting on a 120 × 80 × 12 mm training pad. SOFA advances a 351-node, 1,152-tetrahedron corotational FEM model and resolves native frictional contacts between the tissue, prescribed jaws and tray. A contact-supported closing controller, opposing-contact grasp detection and tracked material-point slip complement the constraint solve. Physics targets 30 Hz; UE renders and handles keyboard/mouse input separately.

The visual model includes separate beveled and serrated jaws, hinge hardware, shaft and insulation. Tissue rendering is bound to the physical surface with a bounded smoothing offset. The scene offers four views, actual-versus-commanded tool feedback, interaction-state indicators and session telemetry.

Local acceptance covers numerical behavior, network robustness, the normal UE keyboard path, a packaged application and a relocated package. The [Phase 2 verification summary](verification/phase2-summary.json) records accepted results. Current evidence includes sustained traction, opening-induced release, natural slip, reset, motion limits, solver health and sampled penetration checks. These are engineering checks. Material constants and contact parameters have not been identified from measured tissue or instrument data.

The earlier Phase 1 established the UE/SOFA transport and basic interaction loop. Its proximity-based grabbing mechanism is superseded in the current Phase 2 interaction path; its older automation modes are not current acceptance criteria.

## Phase 3: two instruments and thin-membrane cutting — planned next

**Goal:** hold and tension a thin specimen with one instrument while a second instrument makes a physically represented cut, with clear visual and mechanical consequences.

The first cutting task should use a purpose-designed thin membrane rather than claiming arbitrary cutting through the current volumetric pad. Its constitutive model, thickness representation and topology updates must be chosen and tested together. A tool crossing a texture or hiding triangles is insufficient: the cut must alter mechanical connectivity and expose the resulting free edges.

Proposed work:

- Add a second independent instrument, per-tool control state, trocar constraints and actual returned poses.
- Define usable keyboard/mouse switching or coordinated control before introducing physical input hardware.
- Implement the membrane model and instrument contact, then a cutting rule tied to the active cutting geometry and physical state.
- Update topology, constraints, collision surfaces and UE render bindings together; retain deterministic reset and replay inputs.
- Preserve a tensioned specimen across partial cuts and complete separation, with bounded solver cost and explicit failure reporting.

Completion requires a reproducible hold–tension–cut–release exercise. Tests should demonstrate that a cut changes connectivity, separated regions respond independently, inactive tools do not cut, render and collision surfaces remain consistent, and reset returns to the original specimen. Repeated cuts, boundary cuts, contact during topology changes and overload cases need their own regression coverage. The appropriate timestep and mesh resolution remain design decisions until measured.

Full-organ dissection, bleeding, thermal energy effects and general volumetric remeshing are outside this first cutting milestone.

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

The sequence above deliberately leaves implementation choices open where experiments are still needed. The current [README](../README.md), [physics reference](../Physics/README.md) and [build guide](BUILDING.md) describe what exists today; this roadmap describes work that remains.
