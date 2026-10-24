# Phase 6: shared interaction, visual and data foundation

Phase 6 is the common foundation before the two research projects diverge. Its
acceptance definition is `Scripts/Phase6/acceptance-spec.json`. Nothing in this
document establishes a completed test; the sealed final delivery receipt does.
No project-specific highlight dataset, intestinal scene, suturing or clinical
material calibration is included.

## Preservation and identities

`tmp/phase6/preserved-baseline.json` inventories every current file under
`output/Phase1`, `Phase2`, `Phase3`, `Phase4`, `Phase4-CollisionFix`, `Phase5`, and
`source`. The immutable baseline contains 2,314 files / 17,999,245,815 bytes and
has SHA-256 `6dd67c3cadd62949b1ee3282c3a69f3a19aa9e4a69e0e1169e709cd59bc2bf5a`.
This includes the newly supplied intestinal reference package. Existing temporary
verification runs are not part of that baseline. Additions to the user's source
directory after this baseline must be disclosed; no script silently blesses a
changed baseline.

Source, build inputs, anatomy, packaged game and native physics binaries are
hashed together after successful compilation. The final ZIP is sealed once,
extracted into a fresh directory, launched, and audited there. Candidate and
fresh-extraction evidence must bind to the same binaries and assets.

## Input and simulation

The end-to-end local measurement is PlayerController input event -> native
accepted state -> state received in UE. It is not hardware motion-to-photon.
The required P95 is at most 150 ms, target lead at most 1 mm, and travel after
input release at most 1 mm. Raw keyboard and mouse samples for both instruments
are retained. Workspace paths include approach, contact, traction and withdrawal.
Contact checks cover finite recorded trajectories and interpolated intermediate
states, not proof of continuous collision prevention everywhere.

The public Phase 6 ready presets (`2`/`3`) sample a material-bound target once
from the currently accepted deformed tissue state. The original outer-surface
triangle and barycentric point locate the same material region while preserving
the authored world-space tip-to-surface offset. That target stays fixed for the
approach; keyboard/mouse commands and contact friction determine subsequent
movement and gripping. `phase6-ready-targets.json` records the selected binding
and evaluated target for inspection. This is an input-placement feature, not a
new tissue law or an automatic grasp constraint.

The 1080p display gate is mean >=30 FPS (target 60); physical simulated-time to
wall-time progression is independently >=0.95. Export freezes are excluded and
acceptance workloads must not compete. Report native step mean/P95, render-frame
P95, and available GPU timings rather than hiding CPU delays behind display FPS.

Normal play and acceptance share the same visible scene-preparation gate before
instrument controls become available. The actual initial viewport renders with
the requested ray-tracing material pipeline while shader/PSO work drains. Readiness
requires at least 120 stable actual viewport draws over two seconds and a completed RHI submission
fence; preparation fails after 90 seconds. This covers the initial viewport, not
every unseen later view or export mode. The runtime audit requires successful
startup, zero pending work and matching readiness counters in the UE log.

Startup duration and counters are retained separately in `phase6-runtime.json`.
Interactive performance measurement begins at readiness and retains subsequent
slow frames and solver samples under the stated live/export/replay timing scopes.
Readiness does not depend on achieving a favorable FPS, and samples are not chosen
after observing their speed. Later export and feature-comparison captures retain
their own preparation and temporal-history checks.

## Visual and rendering evidence

Original editable assets need improved silhouette, instrument structure, tissue
materials and working-space presentation. The physical unit scale is preserved.
Dense rendering geometry and physics geometry have an explicit audited binding;
the visual surface cannot be detached from actual contact without disclosure.
RGB and auxiliary labels use the same actual rendered triangle geometry.

D3D12, SM6, Lumen GI/reflections, hardware RT, and close-up high-quality shadows
must be proved from runtime settings and initialization logs. Five controlled
images hold physics state, camera and exposure fixed: full features, a repeated
full capture, GI off, reflections off, and shadows off. Their numeric differences
are compared with repeat-capture temporal noise. Neither configuration toggles nor
different screenshot hashes alone prove an effective feature.
The proof SceneCapture must explicitly request hardware ray tracing and the
engine's SceneCapture override must not disable it; global viewport ray-tracing
settings alone do not establish the capture path.

## Physics and common data

The existing gallbladder protocol can remain version 5 while the runtime milestone
is Phase 6; this compatibility does not allow old execution reports to stand in
for new tests. Bind all reports to actual current binaries and assets. Five fresh
process replays require <=0.5 mm node RMS and matching grasp/release events. Report
maximum node and force deviations even when the RMS gate passes.

Phase 6 enables the existing SparseLDL solver's `parallelInverseProduct` with
four threads for independent inverse-product row calculations. The serial path
remains the default in earlier phases. This changes execution scheduling, while
material parameters, time step, contact thresholds and the solved equations stay
fixed. Differential replay and the full fresh-binary native suite remain required;
timings from a diagnostic alone cannot establish packaged real-time performance.

The Phase 6 grasper closes until each inner face supports at least 0.03 N of
computed normal contact load, then locks that measured angle. The threshold is
an engineering acquisition criterion, not clinical calibration. Retention and
slip remain physical contact/friction; there is no force servo or tissue pin.
The config binds this latch and the adaptive contact solver. A rejected solve
rebuilds contact caches from saved mechanical state before refining the time
step. Accepted substeps limit node travel to wall thickness and solver residual
to 1e-5. These safeguards do not replace independent penetration, deformation,
replay or real-time acceptance. Previous delivery files remain unchanged.
Final native acceptance requires all twenty
existing regression cases plus fifteen sustained-grip cases: both nominal single
grasps, independent +/-0.1 mm X/Y/Z offsets for each tool, and 2 mm dual traction.
Each additional case holds the initial grasp for 60 simulated seconds, applies
1 mm single-tool or 2 mm dual-tool traction, holds for another 60 seconds, retracts
while closed, and releases. Retained deformation must increase by at least 0.5 mm
for single-tool or 1.5 mm for dual-tool traction from the pre-lift state.

Phase 6 uses SOFA's NNCG contact solver and zero additional contact-compliance
regularization. The previous 0.01 numerical regularization allowed slow friction
creep despite persistent bilateral contact; retained-deformation tests now cover
that failure. A successful finer substep count is retained for eight output
frames before trying a coarser count. All residual, geometry and force gates
still apply, and the adaptive schedule resets for recording/replay.

Every additional native state is retained and independently checked for grip,
the declared fixed latch and angular-rate limits during holding/traction/retraction,
contact counters, finite total and bilateral normal force
and geometry, healthy state, positive elements and the native node-penetration
bound. Contact-loss grace samples are disclosed according to the unchanged native
grip-loss policy. Whole-face/interpolated contact and closed-liver geometry audits
additionally cover the three nominal long-hold traces; the twelve offset traces
are not claimed as independently swept whole-surface geometry. The full nine-case
operating matrix and endurance geometry audits remain required for the new binary.
At most two offline long-hold cases may run together; their timings do not count
as isolated interactive throughput or input-latency acceptance.

Two sequences with at least 12 states each provide synchronized 640x512 stereo
RGB, camera Z depth in mm, world geometric normals, IDs, validity, exact rendered
geometry, cameras and model/state identities. Independent ray intersections
validate depth, normal and ID labels. Validity rules and temporal/image processing
are explicit; normal maps are not geometric curvature ground truth.

The anatomy remains a local gallbladder scene. It is not a full abdomen or colon.
Tutor anatomy review and real-material experiments remain distinct from software
verification. Unsupported collision pairs and numerical limitations are listed
in the delivered report rather than inferred from unrelated successful tests.

## Reproducible delivery sequence

1. Preserve prior artifacts before editing; validate new assets and source.
2. Run `freeze_ue_validation.py prepare` before the final editor build. Its
   `protocol` mode executes the atomic snapshot test with an owned headless UE
   process. After the full editor input/data exercise passes, `seal` verifies the
   unchanged source/assets, module identity, protocol log and lifecycle evidence.
   `--native-suite` selects the exact native evidence directory. Explicit
   `--allow-pending-native-suite` may prepare a future suite path for an isolated
   UE run first; preparation makes no native pass claim, and `seal` still requires
   that suite to pass with the frozen binary and anatomy asset.
3. Package with UAT; `build_receipt.py` requires successful UAT and matching freeze.
4. `assemble.py` writes a fresh `output/Phase6/` or `output/verification/` candidate.
5. `TestPhase6Package.ps1` executes actual controller input in the packaged build.
6. Audit native paths, replay, endurance, input/runtime, data and visual geometry.
7. Collect only passing evidence, seal the manifest, create and CRC-check ZIP.
8. Extract to a fresh directory, rerun actual input/data/runtime checks, reverify
   preservation and create the separate final receipt beside the ZIP.

No failed report is rewritten as successful; diagnostic trials remain separate.
For a changed native candidate, `validate_native_candidate.py native` runs the
existing twenty cases, fifteen additional long holds and latency test into a fresh directory, with legacy socket
ports and raw outputs isolated. Its separate `audits` stage checks all matrix and
endurance and three representative long-hold trajectories with unchanged geometric kernels. Prior binary reports
are retained and cannot satisfy the new candidate's gates.
An interrupted native suite may reuse already passing reports only after checking
their checkpoint hashes and the exact executable hash. The Phase 6 resume helper
runs only the missing final legacy socket case with isolated port/output paths;
it retains the test source, isolation mapping and raw session evidence.
