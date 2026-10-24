# Phase 6 native interaction and FEM assembly

`LapPhysics.exe --phase6` serves the anatomy model on port `47329` using protocol
5. It loads `runtime/assets/phase6.json` by default. `--mesh` may select an
explicit validated asset. The geometry, material law, mass, time step and native
Coulomb contact response remain those of the accepted Phase 5 wall model.

## Responsive commands

Each tool may supply three optional Boolean fields:

- `hold_tip`: resolve the positional target to the current native position at
  receipt. This cancels pending travel without moving back to a delayed display
  position.
- `hold_roll`: similarly hold the current native roll.
- `bounded_target`: limit a manual target to 1 mm ahead of the current native
  position and 4 degrees ahead in roll. Explicit approach presets omit this
  limit and retain the existing position-control semantics.

The 18 mm/s and 60 degrees/s native simulation-time rate limits are unchanged.
The UE input implementation uses 5/12/18 mm/s for precision/default/fast motion,
normalizes diagonal key motion, limits accumulated mouse travel, cancels stale
targets on direction reversal, and sends hold when manual input ends. Pose
presentation remains based on the accepted native state.

The effective resolved position commands are recorded for replay. Wall-clock
input timing and delayed feedback are not recomputed during replay. States
include `last_command_seq` and `applied_command_seq` to measure receipt of an
accepted response; these values do not measure hardware motion-to-photon delay.

## Mechanical grasp latch

Phase 6 acquires a grasp after both inner faces have contact and each carries at
least 0.03 N of computed normal contact load. It then locks that jaw angle until
an explicit opening command. This is an engineering acquisition criterion, not
clinical tissue-force calibration or a continuously regulated force target.
FEM contact and Coulomb friction determine retention; no tissue attachment is
added. Existing nine-step contact-loss release remains. The recording config uses
`grasp_controller_implementation: phase6-bilateral-load-latch-v1` and binds all
solver, motion-guard and acquisition parameters. Older configs are rejected.

A physical output frame can use 1/2/4/8/16 substeps. Each accepted substep limits
node travel to the authored wall thickness and contact solver residual to 1e-5.
Rejected steps rebuild the contact graph from saved x/v before retry, clearing
failed-solve mappings and solver caches. The unchanged 30 Hz command/output clock and immutable
FEM material are independent of this adaptive integration. Invalid motion or
exhausted retries cannot become normal accepted output. Runtime speed must still
pass isolated packaged acceptance.

Phase 6 uses SOFA's NNCG contact solver and zero additional contact-compliance
regularization. The previous 0.01 numerical regularization allowed slow friction
creep despite persistent bilateral contact; retained-deformation tests now cover
that failure. A successful finer substep count is retained for eight output
frames before trying a coarser count. All residual, geometry and force gates
still apply, and the adaptive schedule resets for recording/replay.

## Equivalent stiffness assembly

`Phase6FEM` derives from SOFA's `TetrahedronFEMForceField<Vec3d>`. SOFA still
computes forces, corotational rotations, strain-displacement matrices, material
stiffness and damping, and all direct solves and contact constraints. Only
`buildStiffnessMatrix` is specialized. It evaluates

`diag(R,R,R,R) K diag(Rᵀ,Rᵀ,Rᵀ,Rᵀ)`

as sixteen 3-by-3 block products rather than two dense 12-by-12 products full
of known zero multiplications. All sixteen coupling blocks are assembled in the
original element/node order. Nothing is frozen, decimated or replaced with a
different time step. Phase 3/4/5 entry points keep the original SOFA component.

The configuration reports
`assembly_implementation: phase6-equivalent-block-rotation-v1`, so recordings
cannot silently cross between implementations. `--phase6-baseline-assembly`
retains the stock component for explicit comparison. Source for the referenced
SOFA implementation remains in the distributed SOFA source archive and SDK,
under its existing LGPL notices.

Phase 6 also enables SOFA's built-in `parallelInverseProduct` with four worker
threads for the constraint compliance product `J M^-1 J^T`. Independent rows and
matrix entries run concurrently; each entry keeps its original dot-product
order, with synchronization between the lower, diagonal and upper phases.
The constraint count, 80-iteration limit, tolerance, friction and regularization
remain unchanged. Phase 3/4/5 and `--phase6-baseline-assembly` retain serial
compliance execution.

## Validation

- `--self-test-phase6 --report <file>` exercises production parsing, manual
  bounds, current-pose hold, tool switching, presets and resolved-command replay.
- `--profile-phase6` with that test records SOFA internal timing.
- `--profile-recording <actions.json> --profile-phase6 --report <file>` replays
  existing effective actions without network pacing or state restoration and
  profiles resulting steps 944--1076 (the Diagnostic06 loaded right approach).
  It exports every step's nodes and tool/contact values to `<file>.states.jsonl`.
  `compare_phase6_recorded_profiles.py` compares these files with a predeclared
  `1e-12 m` node-distance tolerance and exact equality for every other field;
  exact numerical equality is reported separately. `--reference-recorded`
  compares against an original native recording journal, skipping its initial
  step-zero row. Profiling elapsed wall time is offline diagnostic time, not a
  replacement for the combined interactive simulation/wall measurement.
- `--phase6 --self-test-phase5 --probe-options <file> --report <file>` reuses
  accepted grasp/traction/release paths. The option `assembly_compare: true`
  compares all 144 entries of every element stiffness matrix against the stock
  SOFA implementation at each scenario stage, including deformed states.
- `test_phase6_latency.py --output <new-folder>` measures real localhost command
  to accepted-state response and stopping travel. Packaged UE input tests are
  separately required for UI response and combined rendering/physics progress.
- `run_phase6_regression.py --output <new-folder>` runs the controller test,
  nine-case 2 mm traction matrix, same-process/fresh-process replay, 50-cycle
  endurance, rejected assets and legacy Phase 3/4 native/socket regressions.
- `run_phase6_long_hold.py --output <new-folder>` records 60 seconds of stationary
  grasp and 60 seconds after traction, then retracts while closed and releases.
  It tests the actual failed packaged left pose, its mirrored right pose, all
  six independent `+/-0.1 mm` axis perturbations for each tool, and dual 2 mm
  traction. Single-tool 1 mm traction must add and retain at least 0.5 mm of node
  displacement from the pre-lift state; dual 2 mm traction requires 1.5 mm.
  Every hold step must retain the physical grip and the latched angle. Existing
  regression defaults and their deformation criteria remain unchanged.

Numerical fidelity is engineering evidence, not clinical calibration. Physical
grip remains frictional and may slip under excessive differential traction.
All contact and timing claims must retain their tested scope and measured load.
