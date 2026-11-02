# Phase 8 — shared foundation before the research branches

Author and maintainer: Avalon. This document defines the milestone contract.
Acceptance is established only by the identity-bound final verification receipt
under `output/Phase8/`; this scope document alone is not a passing result.

The goal is a usable, visually credible and reproducible common scene from which
Project 1 and Project 2 can begin their separate implementations. This milestone
does not produce either specialized dataset. The proposed three 100–300-frame
sequences and downstream teammate-reader integration were explicitly removed
from scope on 28 October 2026.

## Fixed predecessor and scope

The accepted Phase 7 archive is
`output/Phase7/EndoForge-Phase7-Windows-20261026-r1.zip`, SHA-256
`6a998be9dcd04dbfe4707d5abf0bc8e14991b359a6e7bfa04dedeabcc70e0e60`.
Its delivery includes source and editable assets. Do not overwrite it, earlier
deliveries, original reference images, or earlier milestone content.

Work starts with source/reference analysis, then a representative gallbladder,
hepatic-bed and instrument area, followed by scene integration and verification.
Original material fields and model edits are authored in Blender; actual UE
captures establish appearance. Reference models and photographs are references,
not redistributed artwork. The local reference corpus remains read-only.

## Gates

1. Record primary-source case studies and specific adopted/rejected techniques.
2. Improve close-up anatomy presentation: smooth continuous silhouettes,
   believable neck/landmark transitions, differentiated surrounding tissue and
   instrument surfaces. Inspect overview, organ close-up, jaw contact, dual
   traction and additional oblique views. No pass from polygon count alone.
3. Reduce uniform plastic shading through coordinated albedo, mesoscopic and
   microscopic normals, regional roughness, measured-scale scattering settings
   and controlled lighting. These are synthetic authoring parameters, not
   calibrated tissue optics. Check both still and moving images.
4. Preserve or improve ordinary keyboard/mouse handling and working space.
   Exercise both tools, precision/default/fast movement, stop/reverse,
   grasp/traction/release/reset and representative approach/retraction paths.
   Disclose unsupported collision pairs rather than claiming universal collision.
5. Keep physical identity, visible geometry, material-point bindings and existing
   output semantics consistent. Normal maps are shading normals, not geometric
   truth. Any actual mechanical/contact surface change requires corresponding
   new physical qualification. Unchanged physics may inherit identified native
   evidence, but the integrated runtime must be tested afresh.
6. Existing recording/replay/snapshot and small alignment smoke checks remain
   regression tests. No new research sequence deliverable or teammate ingestion
   gate is required. Preserve strict replay validation.
7. At 1920×1080 retain mean >=55 FPS, frame P95 <=25 ms, local input P95 <=150 ms
   and live physics/wall >=0.95. Measure with no competing acceptance workloads.
   Retain actual Lumen, hardware RT and near-shadow evidence.
8. Freeze source/assets/configuration identities; package to `output/Phase8/`;
   verify archive integrity and a fresh extraction launch. Preserve Phases 1–7.
   Record exact results, limitations and startup instructions before acceptance.

## Branch boundary

Project 1 begins its stereo/specular/curvature/tracking-specific output work only
after this base is accepted. Project 2 begins its colon scene, endoscope motion
and temporal correspondence work separately. A colon is a new anatomical and
interaction problem, not a gallbladder texture variant. Surgical-image optics
and postprocessing profiles remain separate from the common geometry/material
base and must transform labels consistently when spatial processing is added.

No suturing, completed organ dissection, calibrated handle force, full deformable
liver or universal self-contact is implied. Engineering visual review and
supervisor/anatomy review are recorded separately. Never mark the milestone
complete solely because its old engineering tests still pass.

## Selected implementation

Candidate 03 supplies original 4K gallbladder/liver color maps, 2K roughness and
normal maps, irregular hierarchical vascular fields, revised capsule variation
and curved closed non-contact neck landmarks. The installed UE 5.7 Subsurface
Profile uses a short mean-free-path setting and separable scattering. Its actual
loaded parameters and shader validity are recorded; tissue optics are not
measured biological constants. Geometry labels exclude normal-map relief.

The physical gallbladder/liver, attachment and native solver are byte-identical
to the qualified Phase7 inputs. New exact-identity inheritance evidence binds
that native qualification. Phase8 still requires new integrated interaction,
replay, render, contact, four-frame alignment and package/extraction tests.
Do not describe the inherited 35-case suite as a new Phase8 execution.

Use `Scripts/StartPhase8Development.ps1 -Mode Physics`, then `-Mode Editor` to
open the complete editable UE project with the matching Phase8 scene. Use the
delivery's `StartTrainer.cmd` for the packaged application. Port 47351 is the
development default; the compatible native mode remains `--phase6`.

See [branch responsibilities](PHASE8-BRANCH-BOUNDARY.md),
[reference analysis](PHASE8-CASE-STUDIES.md), and the delivered Chinese testing
guide. The accepted geometry is an idealized gallbladder scene, not a colon
scene, clinical model, complete abdominal reconstruction or final surgical-image
photorealism. Those limits are explicit at the development branch point.
