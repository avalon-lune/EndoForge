# Phase 7: reference-informed common visual foundation

Project author and maintainer: Avalon. This milestone improves the shared local
gallbladder scene before specialized Project 1/2 development. The acceptance
specification is `Scripts/Phase7/acceptance-spec.json`; this document alone does
not establish completion. Anatomy and teaching suitability require supervisor
review separately from engineering tests.

## Fixed predecessor

Phase 6 r2 is fixed at Git tag `phase6-r2-accepted-20261024`, commit
`3e5d0e6df5257818d952d792c720c0a08f03543c`. Its accepted local archive and raw evidence
remain unchanged. The Phase 7 preservation baseline inventories 4,745 files /
40,136,818,630 bytes under prior deliveries, original Phase 5/6 assets and supplied
references. Its SHA-256 is
`76da150dcd52e0b017e59ebaf55549ee031a78405bd2294541a1d6ce0373bdb5`.

## Shared appearance and geometry

The [reference guide](PHASE7-REFERENCE-GUIDE.md) distinguishes actual laparoscopic
appearance from anatomical atlas geometry. Pale gallbladder tissue is present in
the supplied imagery; changing it uniformly green would not solve the observed
plastic appearance. The targets are irregular tissue structure, organ-specific
surface variation, natural wet highlights, smooth macro shading, subtle vessels
and a more credible layered cavity/fat environment.

Original Phase 7 models and textures belong in `Assets/Phase7`; editable authoring
scripts belong in `Scripts/BlenderPhase7`. Imports use `/Game/Phase7` and never
regenerate earlier phase assets. Physical coordinates stay in metres. Display
surface bindings remain explicit and bounded, with geometric normals and
material shading normals distinguished in exported data. Additional visible
geometry must appear in depth, IDs and geometry records.

The gallbladder FEM remains the Phase 6 mechanical formulation. Visible liver
creases require actual physical liver surface smoothing with a matching display
surface and new native qualification. Display refinement is not a claim of a
patient-specific organ, new material calibration or fully deformable liver. Noncontact cavity and fat
modeling must remain clear of the tested surgical workspace. Unsupported contact
pairs remain explicit limitations.

The frozen Phase 7 liver candidate has 7,432 physical vertices and 14,860
triangles. Its continuous macro shape removes the former equatorial jump; the
operative bed uses a smooth field constrained by the retained 31 attachment
points and the previously usable neck region. All original gallbladder FEM,
material and instrument rig values are retained. The physical asset SHA-256 is
`9405cfab1fb00e36290b242579d8ce4f085f6fa4505228aee72f723770a0de38`.
Rest-state whole-triangle gallbladder clearance is 0.511 mm; static validity and
historical trajectory clearance are preflight evidence, not a replacement for
new dynamic qualification.

The attachment display is a continuous, endpoint-bound visualization of the
spring envelope. Its actual triangles are exported as object 500 and remain
within 0.12 mm of the original ruled patches over their complete surfaces.
This visualization is not an additional membrane FEM or a calibrated attachment
tissue model. Display geometry, geometric normal labels and material shading
remain separate records.

The current Phase 7 native candidate uses a deeper collision search hierarchy
(depth 12) and SOFA's parallel free-motion/collision-detection loop for the
compatible assembly path. All triangle, edge and point collision features,
material values, constraint tolerances and motion guards are retained. The
constraint response waits for both tasks. Execution metadata records requested
thread settings and the effective shared scheduler after graph initialization;
the development machine currently reports eight shared workers. This is an
execution change requiring fresh physical regression, not inherited acceptance.
Its execution configuration participates in strict action-recording validation.
Older recordings without that configuration must be played with their preserved
older delivery; fresh Phase 7 recordings are required for this candidate.

## Rendering and reproducibility

The current common presentation uses a near-axis endoscope illuminator, fixed
exposure, organ-specific PBR materials and the established DX12/SM6 Lumen/HWRT
pipeline. It is not yet a calibrated camera/device profile. Strong lens distortion,
noise, compression, motion blur and project-specific imaging variants are deferred.

The scene carries a versioned appearance profile. Actual camera/light settings,
applied material parameters and texture identities enter the visual manifest and
sample metadata. Normal maps do not become geometric-normal ground truth.
All paired RGB/depth/normal/ID captures retain one frozen state and camera.

Live progression is measured from paired wall/native observations made after
each ordinary transport poll. Polls that receive no new native state still count
their elapsed wall time. Raw observations, segment endpoints and explicit
startup/export/replay boundaries are exported and independently reconstructed.
Frame rate is measured separately. The 0.95 simulated-seconds-per-wall-second
threshold is this project's interactive engineering target, not a clinical
certification standard; it does not establish calibrated tissue mechanics.

Phase 7 launchers explicitly honor existing timer-resolution requests only in
their newly launched endpoint processes. Windows 11 can otherwise ignore those
requests for invisible windows, causing background validation frame pacing to
differ from visible interaction. The helper verifies process identity and records
API readback; it changes neither global timers nor other applications' priority
or power policy. See Microsoft's [process timer policy documentation](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setprocessinformation).

Periodic gallbladder UV coordinates are unwrapped within each physical face
before display interpolation; polar vertices use that face's neighbouring chart.
The authored UV table and actual display bindings accompany Phase 7 exports so
the mapping can be checked independently. This corrects compressed texture bands
without changing the accepted native physical surface.

## Required engineering checks

- The revised physical liver requires a newly executed full 35-case native suite,
  collision guard, latency and independent geometry checks. Unchanged solver
  source does not permit inheriting acceptance for a changed physical mesh.
  An isolated workspace stages the new physical asset under legacy Phase 6
  test paths so the established test logic runs unchanged; provenance records
  the Phase 7 candidate hash and all actual test inputs.
- Current UE editor, packaged and fresh-extracted binaries must execute the full
  input, dual-grasp traction, release, replay, snapshot and 24-frame stereo exercise.
- Independently audit the actual presented trajectories, whole-face contact,
  liver relation and rendered geometry/label correspondence.
- At 1920×1080, measure mean at least 55 FPS, frame P95 at most 25 ms, local input
  P95 at most 150 ms and live physical progression at least 0.95 simulated seconds
  per wall second. The target is a stable 60 FPS. Export freezes have separately
  recorded scope; diagnostic video capture cannot count as isolated performance.
- Verify actual Lumen GI/reflections, hardware RT and shadows with settings,
  initialization logs and fixed-state feature comparisons against repeat noise.
- Review actual overview, organ close-up, jaw contact and dual-traction images,
  compare them to Phase 6 and the references, and retain findings including defects.
  A screenshot checksum or higher triangle count alone cannot pass appearance.
- Seal a new archive, verify CRC and hashes, extract into a fresh location and
  repeat interaction/data/runtime audits before writing the final receipt.
- Bind the actual cooked UE content, runtime DLLs, native configuration and
  physical assets to the build and execution receipts. The new package's legacy
  native `phase6.json` path explicitly carries the qualified Phase 7 asset for
  the compatible solver; earlier deliveries and root runtime assets are preserved.

The output destination is `output/Phase7/`. Previous delivery folders remain
preserved. No suturing, colon-specific workflow, specular-decomposition dataset,
clinical force validity or completed Project 1/2 dataset is claimed.

## Open and inspect this milestone

The packaged application starts with `StartTrainer.cmd`. For source development,
build the native runtime and UE editor module using [BUILDING](BUILDING.md), then
run these commands from the source root in two terminals:

```powershell
& .\Scripts\StartPhase7Development.ps1 -Mode Physics
& .\Scripts\StartPhase7Development.ps1 -Mode Editor -EngineRoot 'E:/UE_5.7'
```

Keep the first terminal running and use normal in-process Play in the editor.
`-Mode Preview` starts the same scene as a standalone editor preview. The helper
selects UE `-LapPhase7`, the matching `Assets/Phase7` directory and port `47331`.
Native `--phase6` is intentional: Phase 7 reuses the compatible solver and
protocol 5 with the explicitly supplied, newly qualified physical asset.

The editable original model is `Assets/Phase7/EndoForge_Anatomy.blend`. Only the
Phase 7 authoring/import tools should regenerate this milestone's assets; older
assets and accepted deliveries are preserved. Blender renders are authoring
previews. Actual UE captures and the independent reports establish the declared
engineering checks. The pale attachment strip, simplified duct/artery landmarks
and remaining synthetic tissue appearance still need anatomical/artistic review.
