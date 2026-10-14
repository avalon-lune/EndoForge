# Phase 3: bimanual manipulation and physical cutting

EndoForge Phase 3 targets a thin training membrane, with one grasper and one scissors controlled through the ordinary UE input path. UE renders and handles input; the external native service owns tissue deformation, cutting and instrument state. The internal UE project and executable remain `LapTrainer`.

This milestone is an engineering prototype. It is not a clinically calibrated organ model, a validated assessment of surgical skill, or a haptic simulator. The material, contact and cutting parameters need physical measurements and clinician review before they can support those claims.

## Interaction contract

`C` selects the grasper or scissors. With the grasper selected, `F` toggles persistent grasper closure, allowing the grasper to hold tissue while the operator moves the scissors. With the scissors selected, `F` can release an already closed grasper; it cannot close the parked grasper. Holding `Space` closes the active instrument; releasing it reopens that instrument unless the grasper remains latched. `Esc` releases both tools. On selection change, the previously active instrument parks at its achieved position. The native service rejects inactive motion and closing commands, while allowing release. Each motion is constrained by its trocar setup.

The other existing motion keys remain: arrows or right-mouse motion in the camera-relative horizontal plane, W/S for height, T/G for insertion, Q/E for axial roll, Ctrl for fine movement and Shift for faster commands. `1` and `2` reset to their respective presets; `3` places the scissors at its ready position without resetting tissue; `R` restores intact tissue. `Tab` changes the camera view.

## Physical cutting contract

Cutting changes the load-bearing tissue representation in the native service. The resulting tissue positions and topology are returned together, so UE renders the same surviving connections used by the physical model. The implementation must not report successful cutting solely because a material mask, pre-recorded animation or hidden patch changes the image.

Cut initiation is gated by a closing scissors action and blade proximity to tissue. Opening scissors, moving without closing, and closing away from tissue must not cut. Repeated cuts modify the current topology; reset restores the original topology and releases instruments. Detached tissue remains part of the simulation.

The spatial resolution of the cut is limited by the physical mesh. This scope is deliberately the training membrane; it does not claim arbitrary sub-element remeshing of volumetric organs. Exact discretization, solver parameters and cutting gates are defined in `Physics/Phase3Model.h` and checked by its numerical regression.

### Discretization and constitutive model

The 120 × 80 × 1.5 mm sheet starts with 850 physical nodes, 2,304 tetrahedra and 1,696 exterior triangles. Its 425-point center grid has 5 mm spacing and 768 triangles. Each triangle is extruded into a prism with top and bottom material nodes and a consistent three-tetrahedron tessellation. SOFA's large-deformation `TetrahedronFEMForceField` uses Young's modulus 25,000 Pa and Poisson ratio 0.35. Density is 1,000 kg/m³; lumped nodal masses are assembled from tetrahedron rest volumes, giving total mass 0.0144 kg. Both layers of the rear row are fixed. Gravity is disabled, so detached pieces may recoil or move under contact but do not fall under gravity. This homogeneous engineering material does not describe biological anisotropy, viscoelasticity, heterogeneous layers, vascular structures or failure energy.

The scene uses `FreeMotionAnimationLoop`, implicit Euler integration, sparse LDL factorization and Lagrangian friction constraints. Each accepted physics update advances a 1/30 s simulation interval. It first attempts one step; if numerical, element-quality or force checks reject that candidate, it restores the previous state and retries the interval with two and then four substeps. These increments are 1/30, 1/60 or 1/120 s, not a claim of achieved wall-clock update rates; rendering runs separately. Rayleigh stiffness and mass damping settings are 0.015 and 8.0; these are numerical settings rather than measured viscoelastic parameters. The contact solver allows 80 iterations with tolerance 1e-6. A 0.01 diagonal compliance regularization stabilizes opposing thin-layer contact constraints; its finite softness is part of this engineering approximation.

Both instruments have two kinematic jaw envelopes, each 14.5 × 2.5 × 1.4 mm and divided into two length segments. Both the tissue surface and jaw envelopes use triangle and point collision models, without line-edge models. A static triangular tray sits underneath. Native Coulomb friction coefficient is 0.8, alarm distance is 1.5 mm, and contact separation offset is 0.45 mm. Grasping is recognized from opposing inner-jaw contacts. A latched grasper can adjust closure when the computed contact load relaxes. Continuing traction can lose friction contact, after which opening is required before regrasping. There is no attractive distance spring that substitutes for physical grasp contact. Preset commands approach their target with bounded tool motion after reset, rather than teleporting collision geometry into the sheet.

The displayed force is the sum of contact-constraint magnitudes assigned to that instrument, converted from the final accepted substep's impulse to average force by dividing by that substep's actual duration. It is not a vector net reaction, whole-update time average or calibrated jaw clamp force. Penetration is sampled at material nodes against jaw envelopes; it is not a continuous global collision bound. Both quantities are engineering diagnostics.

### Cut resolution and topology transfer

For each actively selected scissors closing stroke, native contact on an inner blade supplies actual tissue contact points. Previously intact interior mesh edges can become candidates only when their deformed midpoint is within 3.6 mm of such a contact point and lies inside the finite closing region. This region uses a 12 mm center segment, a 7 mm radial wedge envelope and an axial range from −2 to +14 mm relative to the tip. Candidate material edges accumulate within the current closing stroke. Once the blade half-angle reaches 18°, the service resolves this candidate graph into one nonbranching incision path: it selects the contacted component with the greatest span along the blade axis and uses the shortest path between its extreme vertices, with rest-edge length as the cost. Every path edge must have been seeded by native contact during that same stroke. This avoids cutting all incident edges around each touched triangle.

One stroke produces at most one topology update; reopening beyond 28° rearms cutting. The scissors stop at an 8° half-angle to avoid fully pinching opposing collision envelopes together. Multiple strokes can extend an incision or intersect previous incisions; only their resulting physical connectivity determines whether a piece has separated.

The contact requirement prevents distant proximity-only cutting, but the 3.6 mm edge snap and 7 mm wedge deliberately account for the coarse 5 mm mesh. The cut is therefore mesh-edge based and quantized; it does not precisely follow the visible sharpened blade edge or model fracture toughness, cutting resistance or thermal effects. The HUD's cut-stroke count is the number of committed batches, not the number of separated edges.

Each selected edge separates corresponding material vertex fans through both thickness layers. The existing tetrahedra and their rest shapes remain; positions and velocities transfer from the existing material state. Nodal mass is redistributed from unchanged tetrahedron rest volumes. The exposed tetrahedron boundary supplies the new cut sidewalls. The native scene, elasticity and contact structures are reconstructed for the new topology. The old SOFA graph remains alive until the replacement graph has been initialized. If construction throws an exception, the old mesh, graph, tools, contacts and cut counters are restored, the protection counter increases, and no partial topology revision is published. This is a construction-failure rollback, not a claim that every arbitrary cut is mechanically valid. Simulation steps also check finite values, signed tetrahedron volume, surface area and force limits. If all adaptive attempts fail, protection rolls back the interval, clears grasp state and requests open tools. Invalid numerical or element-quality results also freeze the model at its last accepted pose until reset, so physical jaw opening does not continue in that unhealthy state. Adaptive retries are recorded separately from safety stops. Regular exercise acceptance requires zero safety stops, including events before a reset.

Crack tips can remain connected; a spanning cut or closed loop can create independent components. The reported cut length is the sum of selected edges in their rest configuration, not the mouse path length. A topology rebuild can cause a longer simulation step. Fixed simulation steps do not guarantee wall-clock real-time performance; the measurements in the delivered reports apply to the tested machine and scenario. Steps taking longer than 33.3 ms reduce the achieved update rate and add interaction latency.

UE displays the physical volume's exterior triangle surface, including the top, bottom and newly exposed cut sidewalls. Subdivision uses linear barycentric bindings; cut boundaries do not share interpolation across duplicated physical nodes. Render refinement adds no physical degrees of freedom and does not increase the 5 mm cut resolution.

There is no membrane self-collision, full shaft collision or instrument-to-instrument collision in this milestone. The two jaw pairs use the same collision group to avoid resolving kinematic tool-to-tool contact as deformable tissue response. Suturing and general volumetric organ cutting require a separate model extension.

## Protocol and lifecycle

Phase 3 uses protocol 3 on local TCP port 47323. The packaged launcher starts a private native process, verifies the listening socket belongs to it, then starts the UE game. It stops that native process when the game ends. Occupied ports are reported; unrelated user processes are left running.

The bridge validates the dynamic mesh and instrument state before use. A topology change must update the physical positions, triangle connectivity, constraints and UE surface as one accepted state. Invalid state or missing control must stop unsafe motion and release instruments according to the native watchdog/protection rules. Contact and force estimates are model outputs rather than calibrated instrument measurements.

## Build and test workflow

Use the repository root as the working directory. Existing downloads in `ThirdParty/` are reused. Building and packaging use UE 5.7.4, Windows x64 and DirectX 11.

```powershell
& .\Physics\build.ps1
& .\Physics\RunPhase3Regression.ps1
& .\Prototype\LapTrainer\Scripts\Build.ps1 -EngineRoot 'E:/UE_5.7' -Target Editor
& .\Scripts\RunPhase3Protocol.ps1 -EngineRoot 'E:/UE_5.7'
& .\Scripts\RunPhase3Integration.ps1 -EngineRoot 'E:/UE_5.7'
& .\Prototype\LapTrainer\Scripts\Package.ps1 -EngineRoot 'E:/UE_5.7'
& .\Scripts\AssemblePhase3.ps1
& .\Scripts\TestPhase3Package.ps1
```

Use a successful UAT package log and the exact packaged-run directory with the finalizer:

```powershell
python .\Scripts\finalize_phase3.py --run-directory '.\output\verification\phase3-packaged-YOUR-RUN' --package-log '.\path\to\successful-uat.log' --validate-only
# After validation, run the same command without --validate-only.
& .\Scripts\TestPhase3Archive.ps1
```

`AssemblePhase3.ps1` permits only a child directory of `output/Phase3/` as destination. The default is `output/Phase3/EndoForge`. Existing output requires explicit `-Replace`; the script never uses Phase 1 or Phase 2 as its destination. The finalizer creates `output/Phase3/EndoForge_Phase3_Win64.zip` and its SHA-256 sidecar. `TestPhase3Archive.ps1` extracts that completed archive to a fresh directory, checks every manifest hash, and repeats the packaged input test. Its receipt stays beside the archive rather than changing the archive being tested.

Add `--protocol-directory <phase3-protocol-run>` to retain the independent editor automation report. Its module SHA-256 identifies the tested UE editor module, separately from the delivered game executable. Intentional invalid-packet warnings are part of that rejection test and are retained in its report; ordinary packaged input acceptance must have no invalid protocol messages.

## Evidence and acceptance

The native and real TCP reports must identify Phase 3, contain successful individual assertions, and match the SHA-256 of the delivered native executable. Runtime build metadata must also match the included physical source. The UE packaged-run receipt records both binary hashes, runtime error counts, session CSV sample count and measured solver-step timing. The input report must confirm zero safety stops, and every accepted CSV row must have `healthy=1` and `safety_stops=0`; a protection-assisted route cannot pass as regular interaction.

The input test is invoked with `-LapPhase3Test -LapAutoExit -LapCaptureDir <directory>`. It uses normal UE PlayerController input events, checks returned physical state, and captures ready, grasp, traction, cut, separation, release and reset views. The strict finalizer checks the raw evidence; it does not create passing results when a test is absent or failed. Test results and performance metrics belong in `Verification/` after a successful run, not in source-code claims written before testing.

Automated software input does not establish physical mouse/keyboard feel, accessibility, clinician usability or educational effectiveness. Those require user trials. Mesh resolution, simplified instrument collision, materials and contact behavior also limit transfer to biological tissue. Suturing, knots, energy instruments, bleeding, anatomical reconstruction and hardware force feedback are outside this milestone.
