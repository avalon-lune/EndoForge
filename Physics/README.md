# LapPhysics — phase 2 SOFA contact service

Native C++ application using the unmodified official SOFA 26.06.00 Win64 libraries. All tissue vertices are evolved by SOFA FEM; UE displays returned geometry and jaw poses. The phase 1 package is retained separately. No Python, SofaPython3, Qt, Blender, proprietary bridge, or cloud service is needed at runtime.

## Build and run

Run `runtime/LapPhysics.exe`; it listens on localhost `127.0.0.1:47322`. `--port 47323` selects another port. The service supports reconnection. Build with `download-dependencies.ps1` then `build.ps1`, using installed Visual Studio 2022 x64 and Windows SDK. The verified compiler is MSVC 19.38.33145.0, SDK 10.0.22621.0. Runtime staging discovers Visual Studio through `vswhere` and uses its latest available x64 `dumpbin`, failing explicitly if unavailable.

Package the entire runtime directory, including its 37 DLLs, executable, `etc/sofa.ini`, licenses, build metadata, and phase 2 acceptance reports. Phase 2 uses port 47322 so it can coexist with an unchanged phase 1 service on 47321. Exact selected files are in `runtime-manifest.txt`. The full 219 MB SDK is not required by users. Microsoft x64 Visual C++ runtime is a prerequisite; the UE package supplies its standard prerequisite installer.

Corresponding SOFA source is `ThirdParty/SOFA/sofa-v26.06.00-source.zip` in the development workspace, and `Source/Dependencies/sofa-v26.06.00-source.zip` in a delivered package. Both paths are relative to their respective roots. Keep that archive and notices with redistribution. `dependencies.json` and `dependency-hashes.json` pin sources, versions, URLs and SHA-256. Users can rebuild/replace the dynamically linked SOFA libraries. No GPL SofaUE5-Renderer code is used.

## Physical model

| Quantity | Implemented value |
|---|---|
| Specimen | 120 × 80 × 12 mm; XY centered, initial Z 0…12 mm |
| Physical mesh | 13 × 9 × 3 = 351 nodes, 1,152 tetrahedra, 544 boundary triangles |
| Fixation | Entire Y = +40 mm rear edge, 39 nodes |
| Constitutive law | Homogeneous isotropic corotational linear elasticity, SOFA TetrahedronFEMForceField `method=large` |
| Material | E = 3,500 Pa; Poisson ratio 0.35; total mass 0.1152 kg |
| Gravity | Zero; this specimen isolates tool-induced dynamics |
| Damping | Rayleigh stiffness 0.025, mass 1.0; numerical coefficients, not identified tissue viscoelasticity |
| Integration | FreeMotionAnimationLoop, EulerImplicitSolver, fixed **1/30 s** |
| Linear solve | SparseLDLSolver with 3 × 3 block sparse matrix |
| Contact solve | BlockGaussSeidelConstraintSolver, maximum 500 iterations, tolerance 1e-7 |
| Jaw contact | Native SOFA FrictionContactConstraint, Coulomb coefficient 0.65 |
| Detection | Triangle/line/point surface models, LocalMinDistance: alarm 1.5 mm, contact offset 0.4 mm |
| Tray support | Static triangle-plane FrictionContactConstraint at Z = −4.3 mm, XY halfsize 137.5 × 107.5 mm, friction 0.65 |
| Tool speeds | Translation ≤20 mm/s, roll ≤80°/s, closing halfangle 35°/s, opening 60°/s |

Material and friction parameters are engineering demonstration choices. They were not measured on biological tissue. No anatomical data, patient data, clinical force threshold, injury prediction or training-effectiveness validation is represented. A 663-node refinement trial had greater local compression and higher cost; it was not selected. Render subdivision increases surface smoothness, not the physical discretization accuracy.

The moving jaws are prescribed kinematic surfaces. Their position and **free velocity** drive the SOFA constraint solve; tissue deformation, contact resistance and sliding arise from FEM plus Coulomb contact. There are no proximity capture springs in phase 2. Closing is stopped only after opposing inner faces both contact tissue and aggregate jaw load exceeds 0.5 N. This is an engineering clamp controller, not a force-controlled physical handle. While held, the halfangle stays at the contact-supported value. Continued traction can slide the material out of the jaws. Loss for over 0.2 s releases the grip, and reopening is required before recapture. Both jaws touching the same top face does not qualify as opposing inner contact.

The tray uses the same native constraint contact solver with a static two-triangle plane. It is included in the measured support-penetration audit. Jaw surfaces use a 0.4 mm constraint separation envelope; visible surfaces may show a small gap. Full instrument shaft collision, tissue self-collision, cutting, suture/thread contact, tissue failure, fluid/blood simulation, hyperelasticity and near-incompressibility are outside this implementation. Only the two jaw collision envelopes are validated here. Keyboard input is not force-feedback hardware.

## Exact jaw geometry and coordinate convention

SI metres throughout. Pivot = (0.12, −0.14, 0.15). Tool axis points from tip to pivot. Base side = normalized cross(tool axis, world Z), with world Y fallback near vertical. Positive roll rotates this side around tool axis by the right-hand rule. Width = normalized cross(tool axis, rolled side).

Each jaw is an OBB of length 14.5 mm, width 2.5 mm, thickness 1.4 mm. It has five length segments for collision (24 vertices and 44 triangles); segmentation preserves the exact box envelope. Halfangle ranges from 40° open to 2° requested closed. Common hinge = tip + tool axis × 14.5 mm. Index 0 is −Side; index 1 is +Side. Each hinge is offset by sign × Side × 0.825 mm. Forward = −tool axis × cos(angle) + sign × Side × sin(angle); center = hinge + Forward × 7.25 mm. Pose local X = Forward, Y = Width, Z = normalized cross(X,Y). Inner faces are index 0 local +Z and index 1 local −Z. The UE meshes follow the returned poses, rather than recomputing them from input.

Workspace limiting first clamps X ±90 mm, Y −70…+65 mm, Z −5…+90 mm, then projects to pivot insertion distance 120…300 mm and a 32° cone about the pivot-to-(0,0,12 mm) reference. The last projection can slightly change a prior box-clamped coordinate. Roll is normalized every step. UE uses the same projection order.

## Stability and telemetry meaning

`contact_force_n` and its compatibility alias `force_n` are **sum of individual jaw-contact force magnitudes**, Σ||F_i||. They are neither the tool net force nor one jaw's clamp force. Each friction contact has three multiplier rows. EulerImplicitSolver solves velocity increment with mass-unit system A; constraint compliance is dt × J A⁻¹ Jᵀ, so the multiplier is an impulse and reported N = multiplier / dt. The two jaws' constraint-Jacobian row indices select only their contact multipliers; tray-only constraints are excluded from the displayed jaw load. The independent force check constructs Jᵀλ/dt at FEM nodes and compares all contact nodal forces with FEM internal forces at a quasistatic hold, including rear-boundary reaction (the tested lifted state has no tray contact). It does not use the mapped `getLambda()` vector, which in this scene accumulates mapped contributions more than once.

`slip_distance_m` tracks fixed material points: at capture, each inner contact is projected to a boundary triangle, its barycentric weights are retained, and subsequent movement in the jaw's local tangential X/Y plane is measured. The reported value is the maximum offset since capture, not cumulative path length or an experimentally identified coefficient. Above 2 mm the state is marked `slipping`; the native contact solver determines the motion.

`penetration_m` is an independent geometric sample maximum: 40 points on the jaw boundaries are tested against the closed deformed tissue surface with ray-parity containment and nearest-triangle distance; tissue boundary vertices and triangle centroids are also tested inside both OBBs. Zero means no overlap at these samples, not a proof of zero continuous triangle intersection. `floor_penetration_m` is deepest tissue-node indentation below −4.3 mm. `min_tet_volume_ratio` is the minimum signed deformed/rest tetrahedron volume ratio among accepted coordinates.

After each candidate SOFA step, a >2 N aggregate contact load, >2 mm sampled overlap, or volume ratio <0.08 causes rollback to the prior tissue state and tool pose. Contact overload releases and opens the jaws; the operator must open to continue translation. A quality-only violation stops the solver and requests reset. The count `safety_stops` and `rejected_min_tet_volume_ratio` record rejected candidates, including potential negative volumes; these events are not hidden as healthy accepted geometry. A finite displacement above 150 mm or nonfinite position also stops operation. Thresholds are numerical safeguards, not clinical tissue-damage thresholds. An additional held travel limit is 55 mm.

`step_ms` includes the actual SOFA animation, pose updates and audits, excluding JSON, TCP, UE rendering and scheduling sleep. `sofa_animate_ms` and `contact_audit_ms` allow profiling. Physics is nominal 30 Hz, with UE rendering independent; no hard real-time or haptic-frequency claim is made. The final local regression measured step P95 29.532 ms and maximum 47.989 ms, including the stress-protection test. Ordinary rendering is decoupled, and transient steps can exceed the 33.33 ms budget. Results can change with CPU load.

## Protocol 2

Newline-delimited UTF-8 JSON over nonblocking localhost TCP, one client. At most 64 command lines per physics step, maximum line size 4,096 bytes and bounded input queue. Oversized input disconnects. Every connection resets scene and reset_id to zero.

`hello`: protocol 2, units `m`, vertices, triangles, solver, dt, material_validated:false, node_count, tet_count, grasp_model, pivot_m.

`command`: type `command`, optional nonnegative integer seq, tip_m three finite numbers, closed finite number clamped 0…1, reset_id integer 0…2,147,483,647, paused boolean, optional finite roll_deg. A complete command is validated before any mutation. Unknown types and malformed packets do not refresh the watchdog. A new reset_id resets the scene; when the same command is open, its validated tip/roll becomes the initial pose immediately. Presets must use clear starting positions.

`state`: frame, reset_id, time, vertices, grasping, force_n, step_ms, max_displacement_m, healthy, message, actual tip_m, roll_deg, two jaw_poses (center_m/axis/side/normal), actual jaw_angle_deg, jaw_open_fraction=(angle−2)/38, contact_count, jaw_contact_counts, contact_force_n, penetration_m, grip_state, slip_distance_m, min_tet_volume_ratio, floor_penetration_m, safety_stops, rejected_min_tet_volume_ratio and profiling fields. State is sent each physics step when the output buffer is available. Grip states include open, contact, holding, slipping, released and limit.

No accepted command for 0.5 s stops translation and opens/releases the jaws. Disconnect also releases. Physics can continue after client disconnection. Roll uses the shortest angular path. Pause suspends solver and tool pose integration.

## Reproducible operation and acceptance

Safe front-edge preset: reset open at tip (0, −0.052, 0.006) m, roll 90°. Advance to (0, −0.037, 0.006), wait at least 1 s; close and wait 1.6 s. The validated case stops near a 6.17° halfangle with opposed contact. Move to (0.003, −0.038, 0.014) and wait 1.2 s for an 8 mm lift with continued grip. Pull farther to (0.005, −0.040, 0.022) for 1.8 s to demonstrate slip and release. Open and withdraw for recovery. Top-pressure preset starts (0, −0.015, 0.025), roll 0; move down to Z = 0.006 with open jaws.

Run `runtime/LapPhysics.exe --self-test phase2-physics-test-results.json` for numerical acceptance; run `test_network.py` for actual socket acceptance (requires the port free). Reports are `runtime/phase2-physics-test-results.json` and `runtime/phase2-network-test-results.json`; require phase:2, experimental:false, passed:true and the matching executable hash. Tests cover rest, top pressure, same-side no-grip, bilateral capture, 8 mm traction, independent static force balance, tracked slip, release recovery, ten resets, extreme compression protection/rollback, RCM limits, volume/penetration/fixed-edge audits, malformed commands, atomic rejection, watchdog, normalized roll, jaw orthogonality, reconnect and oversized packets. Final accepted results: 8.04 mm lift with continued grip; tracked slip 8.59 mm before release; recovery residual 0.0666 mm after withdrawal; minimum accepted regular-operation volume ratio 0.29256; zero sampled jaw overlap and zero measured tray-node penetration; quasistatic relative nodal residual 0.221%. The deliberately severe compression case rejects a candidate volume ratio 0.03557 and stops safely, retaining a positive accepted mesh. Numerical checks are software verification, not tissue validation. UE integration and packaging are tested separately by the project.

## Licenses and provenance

Official SOFA source and SDK use tag v26.06.00, commit 7c18e95d5c5f2839079892c69e7d89a313c79603. Selected core/components: LGPL-2.1-or-later; tinyxml2: zlib; bundled Tight Inclusion DLL: MIT; Boost headers: BSL-1.0; Eigen headers: MPL-2.0; nlohmann/json: MIT. Notices are retained under runtime/licenses. CMake 4.4.4 is build-only and its distribution notices are retained under ThirdParty. Additional SDK plugins with other licenses are not automatically staged. `build-info.json` identifies the exact executable and source hashes.
