# Phase 4 collision correction and expanded contact verification

This patch revisits the Phase 4 grasper/specimen contact boundary. It preserves every existing file in `output/Phase1/` through `output/Phase4/` and delivers separately under `output/Phase4-CollisionFix/`. Gallbladder/cavity modeling and suturing are deferred.

The final native, protocol, compatibility and packaged interaction runs below passed on the recorded binaries. ZIP relocation is checked after archive creation; its separate receipt identifies the actual archive SHA-256 and is not written back into that archive.

## Contact implementation

The tissue surface and both instruments' jaw surfaces now expose triangle, line and point collision features together. Adding edge-edge contact closes the gap left by only testing mesh points against triangle faces: a jaw can intersect a triangle interior even while the tissue's 5 mm-spaced nodes remain outside.

`LocalMinDistance.useLMDFilters` is set to `false`. In the installed SOFA implementation this enables the built-in point/edge/face normal-cone validity tests. The previous `true` setting assumed separate LMD filter objects, which this generated graph does not supply, and bypassed those internal feature tests. Filtering artificial/back-facing feature contacts is necessary for oblique approach; merely adding more line contacts without valid feature normals is insufficient.

The collision child state is explicitly synchronized with its parent after restoring physical positions/velocities during graph creation, and after adaptive retry or rollback. SOFA's collision pass can run before its normal current-position mapping propagation. Restoring only the parent therefore left the mapped collision surface at rest or at a failed trial pose when the next contact detection began. This was particularly visible after a cut rebuilt the topology: tissue geometry had been restored, but its collision representation did not yet represent the same state. The mapped free-position/free-velocity buffers are allocated before the first animation step, and `MechanicalOperations.propagateXAndV` propagates both current and free states before that detection pass. A dedicated regression observes a real blade-induced topology change and compares all four parent/mapped vectors immediately, before another animation could conceal the defect; maximum error must be at most `1e-10` in the corresponding SI coordinate/velocity values.

Latched-jaw closure feedback retains its original `GripClosureLoadN = 0.03 N` aggregate contact-load threshold and the original two longitudinal jaw segments. The feedback value is an engineering controller setting, not a tissue material constant, measured handle force, clinical recommendation or calibrated grasping force. Dual-tool cutting hold is restored through correct mapped-state synchronization rather than stronger closing feedback; the complete cutting/contact regression must verify that behavior.

The solver still resolves native unilateral contact and Coulomb friction. There is no attractive grasp spring, tissue-node projection, hidden path rerouting, or additional speed cap in this correction. The 1/30-second accepted timestep, inherited adaptive substeps, contact distance, friction and material parameters retain their prior values. Requested input and actual instrument poses are both recorded so such changes could not be hidden by a request-only test.

## Test interpretation and coverage

The fixed matrix contains 19 exercises: the original curved straight-return failure; flat and curved straight, diagonal, elbow, tangent, out-and-back and vertical paths; controlled straight-return speeds at 6, 12 and 18 mm/s; and curved straight returns with approach azimuths of −30°, 0° and +30°. Rolls cover 60°, 75°, 90°, 105° and 120°. This is a declared combination matrix, not every possible Cartesian combination. Native command segmentation rounds segment duration to whole simulation steps, so measured command speeds can be slightly below their nominal rate.

The delivery audit checks the actual roll during closing and traction (within 0.5°), verifies that commanded movement reaches at least 90% of its specified rate without exceeding it, and requires meaningful actual travel, lift and endpoint arrival. The original straight regression keeps its direct home target; actual tip positions must stay within 0.1 mm of that direct segment and advance monotonically. Stalling, stopping short, silently returning along a raised curve, or changing only the test labels cannot pass these gates.

The historical 75° probe forced a particular slip outcome. With corrected contact generation, a successful 75° grasp may instead remain stable. The probe now accepts either actual holding or measured slip, while still requiring initial bilateral contact, more than 2 mm of deformation during the lift, reopening/reorientation and regrasp without reset, finite/healthy state, the unchanged penetration bound and final release. This deliberately changes the expected physical outcome; it does not remove traction, recovery or contact-quality checks. Its old assertion name is retained for compatibility and the report records which outcome occurred.

The Phase 3 compatibility input exercise follows persistent material-face identities across cuts. Its previous fixed world-space sweep did not follow the changed material surface after the first incision. The updated keyboard-driven sequence lifts clear, moves outside the free front edge, lowers to insertion height, enters with the jaws open, then closes. It retains all 17 original assertions, including two real cuts while the grasper holds, release and reset. This corrects the test's approach geometry for the changed contact model; it does not reimplement cutting, establish arbitrary insertion-angle support, or inject native cut events or tissue geometry.

Whole-triangle depth is the maximum, over a tissue triangle, of its inward minimum distance to the six jaw-box faces. The independent Python auditor finds that value through polygon/eroded-box intersection and bisection, rather than relying on the native summary. It additionally tests quarter-, half- and three-quarter interpolated states between accepted outputs, with interpolated orthonormal jaw frames. This is a tunnelling screen, not continuous-time proof of every SOFA internal substep.

## Historical defect and acceptance boundary

The original curved interior straight retreat reached approximately 0.4928 mm of sampled physical-node penetration into a jaw box. The old acceptance route returned along the elevated arch and avoided that crossing. That route restriction was a documented limitation, not a repair of general collision handling. The original failed straight retreat must remain a regression case with its intended motion intact.

The inherited node-depth tolerance remains 0.15 mm. Independent surface geometry checks complement node sampling; mesh vertices alone cannot establish that the interiors of 5 mm triangles are clear. Report surface sampling/intersection definitions, thresholds, maximum depth, affected frames, command/actual tool motion and operating range explicitly. Do not equate a finite path matrix with continuous collision detection or arbitrary-motion guarantees.

## Acceptance and evidence

The final native executable SHA-256 is `0644da8a53bc7b7e8aaec45d6be7176ef8e8e6c471e58d8ba19f4f48f11f1a6a`; the packaged game SHA-256 is `311daa219d814df34812c48c875a90ac4711d9103103352e6512c24276fb9509`. The successful native regression wrapper refreshed `build-info.json` with tested protocols 3 and 4. The measured final results are:

| Gate | Recorded result |
|---|---|
| Native core and repeated actions | 46/46; five repeats per specimen, maximum node RMS 0 m; one real cut observed by the immediate four-vector mapping check, maximum error 0 |
| Flat and curved continuous endurance | 9/9 each; 600 simulated seconds, 18,000 accepted steps and 60 grip cycles each; zero protection events and zero measured node depth |
| Collision matrix and independent geometry | 19/19; 7,406 output frames including initial states and 22,161 inter-frame samples; all four maximum node/surface/output/interpolation depth metrics 0 m |
| Phase 4 TCP and UE protocol | 20/20 TCP assertions; atomic snapshot protocol automation passed |
| Phase 3 compatibility | 19/19 native, 19/19 TCP, 17/17 UE input; atomic topology protocol automation passed; two keyboard-driven cuts with retained grip |
| Packaged Phase 4 input | 22/22; actual curved direct-retreat travel 39.308546987 mm, presented node depth 0 mm and zero protection events; 12 normal screenshots and three frozen screenshot/state pairs |
| Supplemental curved configuration | 8/8; 251 received states, 71 held states, 12.032252 mm maximum displacement, 100 fixed nodes with zero measured drift and zero protection events |

The packaged session contained 726 telemetry rows and measured physics-step P95 of 40.6328 ms while native regression processes were also running. This is a local acceptance measurement, not an isolated performance benchmark or a hard real-time guarantee. Recorded zero depth applies to the stated finite cases and geometry definition; it does not prove collision-free arbitrary motion. Full raw evidence is distributed in `Verification/`, with archive relocation recorded separately beside the ZIP.

The correction retains every applicable original [Phase 4 acceptance gate](PHASE4.md): both 600-second continuous endurance runs, five repeated trajectories per specimen, cutting compatibility, persisted TCP replay, atomic UE protocol handling, packaged input and frozen snapshot correspondence, ZIP integrity and fresh extraction/launch. All receipts must refer to the exact delivered binary and source/configuration hashes.

One supplemental configuration is checked separately: the curved preset with two fixed rear rows and Young modulus 30,000 Pa. Its actual TCP grasp/lift/release test must retain all eight assertions, fixed-node stability and zero protection events, with the final executable and test-script hashes. The report, exact input and runtime log are retained under `Verification/supplemental-configuration/`. This single short manipulation exercise does not establish arbitrary parameter combinations or a separate 600-second endurance result for that configuration.

Additional collision evidence must include the original curved straight retreat plus declared angle, speed and path coverage for both specimens, and raw per-step mesh/tool geometry. Failed trials remain diagnostic artifacts; only a complete successful matrix from the final binary may enter delivery acceptance. The finalizer independently checks the prescribed coverage, raw evidence, geometry audit and provenance before producing the ZIP.

An old-release comparison is retained separately in `Verification/diagnostics/legacy-collision/`: 329 received states, with step 1 explicitly missing, measured approximately 0.479091 mm node depth and 0.700000 mm whole-triangle depth. The original published approximately 0.4928 mm figure belongs to its earlier diagnostic run. These observations use the preserved executable and include raw state/actions, original reproduction script, current audit scripts and their SHA-256 chain. They demonstrate the old failure and the value of surface checks; their incomplete receive history is never substituted for the new matrix's complete accepted-step evidence.

The pre-patch preservation baseline is `tmp/phase4-collision-fix/preserved-baseline.json`: 824 files / 4,684,530,187 bytes across Phase 1–4, SHA-256 `13eef137e823b7f75631171c6eb38dccc304fd07edc1c93439d9a299c982c616`. Finalization checks both exact file membership and every file's size/hash. The original deliveries are not edited or re-tested in place.

## Delivery commands

Run the native matrix from the repository root in a **fresh** verification directory. The native CLI writes geometry and assertions; the following PowerShell records the exact executable/source identity and exit code before the independent auditor hashes the matrix. Do not add or change report fields after the audit without rerunning that audit.

```powershell
$MatrixRoot = [IO.Path]::GetFullPath('output/verification/phase4-collision-YOUR-RUN')
if (Test-Path -LiteralPath $MatrixRoot) { throw 'Choose a fresh verification directory.' }
$NativeExe = [IO.Path]::GetFullPath('Physics/runtime/LapPhysics.exe')
$NativeBuild = Get-Content -LiteralPath 'Physics/runtime/build-info.json' -Raw | ConvertFrom-Json
$NativeHash = (Get-FileHash -LiteralPath $NativeExe -Algorithm SHA256).Hash.ToLowerInvariant()
if ($NativeBuild.executable_sha256 -ne $NativeHash) { throw 'Staged executable metadata differs.' }
function Assert-MatrixSources {
    foreach ($Entry in $NativeBuild.source_files_sha256.PSObject.Properties) {
        $SourcePath = Join-Path 'Physics' $Entry.Name
        if ((Get-FileHash -LiteralPath $SourcePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Entry.Value) {
            throw "Source changed after native staging: $($Entry.Name)"
        }
    }
}
Assert-MatrixSources
New-Item -ItemType Directory -Path $MatrixRoot | Out-Null
$MatrixReport = Join-Path $MatrixRoot 'phase4-collision-matrix.json'
$MatrixStarted = [DateTime]::UtcNow.ToString('o')
& $NativeExe --collision-test --report $MatrixReport *> (Join-Path $MatrixRoot 'native-matrix.log')
$NativeExit = $LASTEXITCODE
Assert-MatrixSources
if ((Get-FileHash -LiteralPath $NativeExe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $NativeHash) { throw 'Executable changed during matrix.' }
$Matrix = Get-Content -LiteralPath $MatrixReport -Raw | ConvertFrom-Json
$Matrix | Add-Member -NotePropertyName executable_sha256 -NotePropertyValue $NativeHash -Force
$Matrix | Add-Member -NotePropertyName source_files_sha256 -NotePropertyValue $NativeBuild.source_files_sha256 -Force
$Matrix | Add-Member -NotePropertyName native_exit_code -NotePropertyValue $NativeExit -Force
$Matrix | Add-Member -NotePropertyName tested_at_utc -NotePropertyValue $MatrixStarted -Force
$Matrix | ConvertTo-Json -Depth 32 | Set-Content -LiteralPath $MatrixReport -Encoding UTF8
if ($NativeExit -ne 0 -or $Matrix.passed -ne $true -or $Matrix.filter -or @($Matrix.cases).Count -ne 19) { throw 'Complete native collision matrix failed.' }
python .\Scripts\audit_phase4_collision_geometry.py --matrix $MatrixReport --output (Join-Path $MatrixRoot 'collision-geometry-audit.json')
if ($LASTEXITCODE -ne 0) { throw 'Independent collision geometry audit failed.' }
```

After rebuilding and collecting successful fresh native, protocol, compatibility and packaged-run evidence:

```powershell
python .\Physics\test_phase4_configuration.py
# Require its eight passing checks and the current staged executable hash.
& .\Scripts\WritePhase4BuildReceipt.ps1 -PackageLog <successful-UAT-log>
& .\Scripts\AssemblePhase4CollisionFix.ps1
& .\Scripts\TestPhase4Package.ps1 -PackageRoot '.\output\Phase4-CollisionFix\EndoForge' -RunName <fresh-name>
python .\Scripts\finalize_phase4_collision_fix.py --run-directory <packaged-run> --package-log <UAT-log> --protocol-directory <phase4-protocol-run> --legacy-input-directory <phase3-input-run> --legacy-protocol-directory <phase3-protocol-run> --collision-report <collision-matrix-report> --validate-only
# Repeat without --validate-only only after every gate succeeds.
& .\Scripts\TestPhase4CollisionFixArchive.ps1 -RunName <fresh-relocation-name>
```

The wrappers reuse the original implementation while constraining the destination to the new output root. `-Replace`, when explicitly used, can replace only the new generated distribution. The old output root is rejected by the collision-fix variant. Dependencies remain pinned under the project; no Blender, UE upgrade or physical instrument is required.

## Limits

This remains an engineering membrane simulation with mesh-edge cutting, not calibrated biological tissue, validated clinical training or an anatomy-specific model. Report measured correction behavior and any limiter/servo consequences on motion. Preserve the distinction between requested input, actual instrument pose and deformed tissue state. Self-contact, tissue-organ contact and true anatomical attachments require separate requirements and tests.

Existing `endoforge.actions.v1` recordings can be loaded into this runtime, but that format does not reject a different physics-model version. Changing contact generation can change the geometry and forces produced by the same old commands. Reproducing an old trajectory exactly requires its corresponding original package/executable; loading those commands into the corrected model is a new computation, not evidence of cross-version equivalence. Within-build replay remains subject to the complete repeatability gates.

Instrument-to-instrument collision, instrument-shaft collision and tissue self-contact are not implemented by this patch. Its surface checks concern the exported tissue surface against the two instruments' jaw boxes. Neither the test range nor the solver contact-load feedback establishes clinical tissue safety.
