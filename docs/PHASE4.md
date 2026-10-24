# Phase 4 — reproducible deformation and geometry states

This document describes the original Phase 4 baseline. The separate [collision correction](PHASE4-COLLISION-FIX.md) extends its contact tests and preserves the original delivery. Its final receipts and measured limits govern the corrected build; the historical route restriction below must not be mistaken for evidence that the original defect was fixed.

Phase 4 prepares EndoForge for a localized gallbladder/endoscopic scene and, later, paired synthetic video and geometry datasets. It extends the existing grasper/scissors mechanics with configurable flat and curved specimens, fixed-step action recording/replay, and traceable physical/render states. Suturing is outside this milestone.

This is an engineering specimen workflow. Stable deformation and repeatable software output do not establish biological material accuracy, anatomical fidelity, clinical effectiveness or calibrated contact force. The next step after the acceptance gates is anatomy-specific modeling and attachment/contact adaptation.

## Runtime boundary

UE 5.7.4 renders the authoritative native SOFA 26.06.00 state and handles keyboard/mouse input. The native service defaults to protocol 4 on `127.0.0.1:47325`. Metres are used for physics and centimetres in UE. The Phase 3 source compatibility path uses native `--phase3` and UE `-LapPhase3`; earlier delivery folders remain unchanged.

The physical foundation remains a thin tetrahedral volume with corotational FEM and frictional jaw contact. The grasper has no attractive attachment spring. Scissors alter material connectivity on selected physical mesh edges. The inherited 5 mm mesh scale does not become finer when the displayed surface is subdivided. See [Phase 3](PHASE3.md) for the foundation and inherited exclusions.

`Physics/configs/flat.json` and `curved.json` are versioned specimen configurations; copies reside beside the packaged native executable. Runtime options include `--specimen flat|curved`, `--config PATH` and `--session-dir PATH`. The full accepted configuration is part of the recording provenance. The curved specimen is a technical shape for testing shape/attachment replacement, not an anatomical gallbladder.

The supplied presets have a 120 × 80 mm planform, 1.5 mm thickness, 25 × 17 middle-surface grid, 850 initial volume nodes and 2,304 tetrahedra. The curved middle surface rises by a 12 mm sine profile along its length; thickness is extruded along its local normal. Default material parameters remain 25 kPa Young’s modulus, 0.35 Poisson ratio and 1,000 kg/m³ density, with the rear node row fixed in both layers. One to three fixed rows are configurable within the validated parser bounds; mesh counts remain fixed in this milestone.

Grip is contact-dependent. The oblique 75° roll probe on the flat sheet checks initial bilateral contact, detected slip under the lift, then reopening/reorientation to 90° and successful regrasp without reset. The corresponding curved probe holds in that defined setup. These are test scenarios, not a guarantee that every orientation retains tissue.

The contact gate is **0.15 mm sampled physical-node depth inside a jaw box**. It does not bound triangle crossing between 5 mm mesh nodes or prove that all continuous surfaces are intersection-free. Endurance uses sixty 300-step grasp–lift–release cycles per specimen without resetting the tissue between cycles. The independent CSV audit requires every cycle to contain simultaneous holding and more than 2 mm deformation during lift steps 90–179, and no holding from step 210 onward after the opening transient; an initial grasp alone cannot satisfy the cycle. Native records include both the maximum sampled depth and the time for which it is positive.

### Validated movement envelope

The curved interior probe uses a surface-aware approach and retreat: enter at the free front edge, follow the arch to the interior grasp point, grasp and lift by 4 mm, fully open while maintaining the lifted height, then reverse along the raised curved route to the front edge before returning home. The 450-state path validation measured zero sampled physical-node penetration. Final acceptance checks the complete evidence against the delivered executable and retains the 0.15 mm engineering threshold; this individual trajectory does not establish general collision coverage.

A diagnostic straight-line retreat from the curved interior to the home pose crossed beneath the arched sheet and reached approximately **0.4928 mm** sampled node penetration. Grasping and lifting had succeeded; the return route caused the failure. The accepted path avoids that crossing. This is a documented operating envelope, not a general collision guarantee or a repair of arbitrary-path collision limitations. The edge, interior, corner and oblique probes describe specific positions, rolls and trajectories; manually dragging a tool straight through the specimen is outside the demonstrated bounds.

For ordinary use, fully open the jaws before retreat and move clear of the local tissue surface. When inside the curved specimen, retrace the raised approach route toward its free edge rather than taking a shortcut through the arch. Additional arbitrary trajectory, tissue self-contact and continuous triangle collision coverage would require separate work.

## Recording and state identity

Action recordings describe commands applied at simulation steps. Replay starts from the recording's initial configuration and state; live tool movement is excluded during replay. Capturing visual frames independently of the simulation clock is not sufficient for reproducible geometry data.

Native recordings contain `actions.json`, `states.jsonl` and `metadata.json` under an owned session directory. UE also records presented state identity and camera state. Frozen snapshot JSON and PNG files allow geometry-to-screen validation. The native record, the rendered state and the camera are separate facts and are labeled as such; a repeated rendered frame must not be represented as a new physical step.

Material identity is distinct from a node's current array index. Cutting duplicates nodes and changes topology; topology versions and material ancestry must survive that operation. A reset starts a new identity epoch rather than pretending that its new step zero continues the previous tissue trajectory.

## Acceptance gates

All gates require real successful receipts from the exact delivered binaries. Missing evidence is a failure, and documentation is not a substitute for running the tests.

| Gate | Required evidence |
|---|---|
| Grasp/traction/release | Flat and curved specimens, meaningful grip and displacement, clean release and reset |
| Stability | At least 600 simulated seconds per specimen in continuous prescribed action cycles; finite states, valid elements, zero terminal safety stops |
| Repeatability | Five runs per specimen; matching discrete events and node-position RMS deviation at most 0.5 mm for the non-cutting sequence |
| Contact quality | Explicit penetration metric/definition, measured maximum and duration; model-scale tolerance recorded with results |
| Cut compatibility | Existing Phase 3 connectivity, mass, release, protocol and input checks remain applicable |
| State traceability | Monotonic identities within epochs, explicit resets/topology changes and saved configuration/actions |
| Render correspondence | Independently reconstruct bound render vertices and project using the saved matrix; compare to engine projection within 1 pixel |
| Delivery | Editor/protocol, actual packaged launch, ZIP integrity and extracted-package launch; exact source/config/binary SHA-256 provenance |
| Preservation | Compare all existing Phase 1–3 files against the pre-Phase-4 size/SHA-256 baseline |

The endurance duration is simulation time, not wall-clock duration and not a fixed rendering rate. Solver timing, adaptive retries and end-to-end latency must be reported separately. Data generation can run slower than real time while preserving the correct simulation clock. The native regression wrapper runs core and the two endurance processes concurrently; its reported solver timings include that local contention. The final packaged-session CSV was captured while native regression workloads also ran on this machine. Its timing is an observation of that acceptance run, not an isolated performance benchmark or hard real-time guarantee.

## Build and verification

Use the installed Windows x64 UE and MSVC toolchain described in [BUILDING](BUILDING.md). Native dependencies remain under `ThirdParty/`; no Blender, physical instrument or cloud service is needed to test the packaged specimen.

```powershell
& .\Physics\build.ps1
& .\Physics\RunPhase4Regression.ps1
& .\Prototype\LapTrainer\Scripts\Build.ps1 -EngineRoot E:/UE_5.7 -Target Editor
& .\Scripts\RunPhase4Protocol.ps1
& .\Scripts\RunPhase4Integration.ps1
& .\Prototype\LapTrainer\Scripts\Package.ps1 -EngineRoot E:/UE_5.7
& .\Scripts\WritePhase4BuildReceipt.ps1 -PackageLog <saved-successful-UAT-log>
& .\Scripts\AssemblePhase4.ps1
& .\Scripts\TestPhase4Package.ps1
python .\Scripts\finalize_phase4.py --run-directory <packaged-run> --package-log <UAT-log> --protocol-directory <protocol-run> --legacy-input-directory <phase3-compatibility-run>
& .\Scripts\TestPhase4Archive.ps1
```

The independent snapshot audit has reusable corruption tests in `Scripts/test_phase4_snapshot.py`; delivery gates have negative tests in `Scripts/test_phase4_delivery.py`. These synthetic unit fixtures are not runtime acceptance evidence.

Use fresh verification run names. Assembly with `-Replace` may replace only its generated child directory beneath `output/Phase4/`. The ZIP relocation receipt is generated after the archive and stored alongside it, so the archive hash remains stable.

## Remaining scene-specific work

A gallbladder scene still needs geometry/physical bindings, anatomical attachments, camera/material reference matching, and any organ-to-organ or self-contact required by its chosen motion. Full volumetric organ dissection, puncture, thread, knots, bleeding, electrocautery and physical force feedback are excluded. Dataset labels and export formats require the research output specification; recording the necessary state is preparation, not a completed research dataset.

The package's `Verification/verification-summary.json` and underlying reports state what a particular build passed. Unrun tests and failed trials must not be labeled as accepted results.
