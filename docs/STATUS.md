# Current status — Phase 6 r2

Author and maintainer: **Avalon (avalon-lune)**. Reviewed on **24 October 2026**.

I have completed a locally tested engineering foundation for endoscopic interaction and paired image/geometry research. Its current scene is a gallbladder manipulated by two friction graspers. Completed implementation and unfinished visual, physical and research work are separated below for supervisor review.

## Completed and verified locally

- Editable UE project and original Blender gallbladder, liver and local abdominal assets.
- Gallbladder wall FEM, neck constraints, compliant liver-bed attachment and physical friction grasping.
- Bimanual approach, grasp, traction, release, bounded manual input and jaw admission against the static liver.
- More detailed bound display/instrument geometry, original materials/textures and observation controls.
- Actual Lumen GI/reflection, hardware ray tracing and near-contact shadow comparisons.
- Step-based action recording, guarded replay, state identity and matching frozen snapshots.
- Basic stereo RGB/geometry export, including camera-Z depth, geometric normals, IDs, masks and cameras.
- Native, sustained-grip and endurance tests; packaged run; fresh ZIP extraction/run; independent geometry/data audits.

Accepted archive: `EndoForge-Phase6-Windows-20261024-r2.zip`. SHA-256: `268b726e1e1c21d722a4a7f47628aa8f48824846499fa619369b4b316d23caa9`. [Public metrics](verification/phase6-summary.json) summarize the local receipt. Raw evidence remains in the local delivery; this source sync does not claim a hosted runtime release.

## Modeling and appearance are not final

The scene has editable geometry, not only rendered images. The gallbladder deforms; liver and cavity are primarily static. Duct/artery shapes are orientation landmarks, not functional surgical targets. The port layout is an engineering rig, not clinical placement guidance.

Current images remain synthetic. Tissue color, translucency, wetness variation, small vessels, anatomical proportions and some highlighted surfaces need refinement. Published captures show the actual result without retouching. Advanced rendering and higher polygon counts do not establish photographic or anatomical realism. Anatomy review is pending.

## Physics boundaries

- Material parameters and force outputs are not calibrated to biological measurements or clinical safety thresholds.
- Strong/asymmetric traction can slip. Closure latches after bilateral load acquisition; tissue is not pinned to the tool.
- Rigid-liver jaw blocking is geometric admission, not measured reaction force.
- Full-shaft collision, general instrument–instrument response, general self-contact, deformable liver and full organ interaction remain incomplete or absent.
- No fluid/bile/blood, electrosurgery, anatomical dissection, organ cutting or suturing is delivered in this scene.
- Legacy Phase 3/4 cutting is a thin-specimen mesh-edge operation, not completed organ surgery.
- Geometry checks cover declared finite paths and sampled intermediate states, not arbitrary-motion collision freedom.

## Output and validation boundaries

Two short stereo sequences establish an export foundation; they are **not** either research project's finished dataset. Task-specific fields, intestinal scenes, timebase/frame-rate contracts, appearance variation, occlusion handling, scale and downstream ingestion need separate implementation and acceptance.

Geometric normals differ from material normal maps; camera-Z depth in millimetres differs from ray distance; modeled contact loads differ from handle forces. Replay is tolerance-based, not a blanket bit-identical cross-machine guarantee.

Software acceptance does not replace manual usability, supervisor/clinician review, tissue calibration or educational/clinical validation. A complete independent rebuild on a different clean machine remains unverified. Source checkout/file-integrity checks are a narrower, separately reported claim.

## Phase 6 r2 correction

The first 24 October candidate passed its initial package run but failed fresh-extraction acceptance: the right lift ended at approximately 2.166773 mm versus the intended 2 mm and the unchanged 0.12 mm endpoint tolerance. Tissue health remained valid; the exact-lift test advanced before in-flight movement settled.

r2 uses ordinary Ctrl+wheel 0.2 mm finite pulses, waits for applied-command and settled-position acknowledgement, then switches tools. It does not inject tissue motion or loosen endpoint/retained-deformation gates. Ordinary keyboard/mouse response is also tested by separate foundation trials. New editor, packaged and fresh-extracted runs measured approximately 2.000 mm per tool and passed. Native mechanics and its accepted binary were unchanged by this test-driver correction.

The unaccepted ZIP is preserved and marked locally. Only r2 is the current accepted delivery. Earlier solver/contact/liver-guard changes and coverage are explained in [PHASE6](PHASE6.md).

## Next work

1. Supervisor review and a recorded manual usability/anatomy assessment.
2. Visual/anatomical refinement while preserving physical/display correspondence.
3. Separate scene/output contracts and implementations for the two research projects.
4. Measured tissue calibration if biological force accuracy becomes a required output.

This source synchronization adds documentation, selected evidence and a development launch helper around the accepted simulation. It does not rewrite the preserved r2 ZIP or claim a newly accepted runtime merely because documentation changed.
