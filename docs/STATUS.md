# Current review candidate — Phase9

Author and maintainer: **Avalon**. Engineering verification and fresh ZIP
extraction/run completed on **2 November 2026**. Human visual approval remains
pending. See [Phase9 changes, startup, measurements and limits](PHASE9.md) and
[the exact engineering summary](verification/phase9-summary.json).

The conspicuous lower contour is smoother; some grey-view curvature bands remain.
Physical parameters/handle forces are not calibrated biological measurements.
The full earlier deliveries are preserved. This update does not publish a release.

# Preserved status — Phase8

Author and maintainer: **Avalon (avalon-lune)**. Local engineering delivery verified on **28 October 2026**.

Fresh-extracted 1920x1080 measurements: **59.31 FPS**, **17.303 ms frame P95**, **84.14 ms local input P95**, and **0.9729 simulated seconds per live wall second**.

Engineering-only; appearance remains synthetic and clinical/anatomy review remains pending. The exact accepted Phase7 35-case native qualification is inherited, not rerun as Phase8. Four frozen stereo frames are internal alignment regressions. No specialized Project1/Project2 branch development, research sequences or teammate-reader integration is delivered. The final preservation check covers **5,984** files.

Archive: EndoForge-Phase8-Windows-20261028-r1.zip, 1.23 GB (1,234,516,248 bytes). SHA-256: f575a6de3b02f709dc304c7774372b58bc0df1347c806eb4b742a06fbcbfd392. Authority: output/Phase8/phase8-final-verification.json; [selected exact results](verification/phase8-summary.json). This update does not publish a runtime release.

Anatomy is idealized; liver/cavity structures are mainly static. Duct/artery shapes are simplified non-contact orientation landmarks; attachment rendering visualizes constraints. Tissue/force calibration, dissection, suturing, full-shaft/general self-contact and universal collision support are not claimed.

Run StartTrainer.cmd and read TESTING.zh-CN.md. For source/editor use, see [Phase8 startup](START-HERE.md). Earlier recordings remain with their corresponding deliveries under strict configuration validation.

## Preserved Phase7 status

Author and maintainer: **Avalon (avalon-lune)**. Local delivery verified on **26 October 2026**.

Phase 7 has passed the scoped common-foundation engineering gates, including an actual packaged run and a fresh ZIP extraction/run. The current scene has a newly smoothed physical/display liver, revised original tissue and metal materials, finer cavity detail, corrected display UVs and a continuous bound attachment display. The accepted gallbladder FEM, friction grasping and paired image/geometry workflow remain the basis.

Fresh-extracted performance was **59.65 FPS**, with **16.842 ms** frame P95 and **0.9757** simulated seconds per live wall second. Full 35-case native regression, 15 sustained-grip cases, 50 repeated cycles, five fresh-process replays, independent geometry checks and 24 stereo frames passed. All **4,745** prior-delivery/reference files and the preserved UE content matched the baseline. See [the preserved Phase7 metrics and identities](verification/phase7-summary.json).

Local archive: `EndoForge-Phase7-Windows-20261026-r1.zip`. SHA-256: `6a998be9dcd04dbfe4707d5abf0bc8e14991b359a6e7bfa04dedeabcc70e0e60`. The final delivery receipt is stored beside the archive under `output/Phase7/`. This local update does not publish a GitHub release.

**Appearance remains synthetic.** The smoother surfaces, regional colour, vessels and lighting are engineering improvements; they do not achieve real surgical-image photorealism or establish anatomical validity. The gallbladder is idealized; liver and cavity remain primarily static. Straight duct/artery landmarks are not complete functional anatomy, and the pale attachment layer visualizes the spring envelope rather than a membrane FEM. Tissue/force calibration, clinical review, full-shaft/general self-contact, dissection, suturing and specialized Project 1/2 datasets remain unfinished or outside this milestone.

Launch the delivered application with `StartTrainer.cmd`; the package contains a Chinese manual test guide. For the complete editable UE project and matching native service, follow [Phase 7 startup](PHASE7.md#open-and-inspect-this-milestone). New execution settings participate in strict replay validation: recordings from earlier versions should use their preserved deliveries, and differing effective thread configurations may be rejected.

## Preserved Phase 6 status

The following describes the earlier r2 delivery and its history; Phase 7 results are stated above.

Author and maintainer: **Avalon (avalon-lune)**. Reviewed on **24 October 2026**.


I have completed a locally tested engineering foundation for endoscopic interaction and paired image/geometry research. Its current scene is a gallbladder manipulated by two friction graspers. Completed implementation and unfinished visual, physical and research work are separated below for supervisor review.

### Completed and verified locally

- Editable UE project and original Blender gallbladder, liver and local abdominal assets.
- Gallbladder wall FEM, neck constraints, compliant liver-bed attachment and physical friction grasping.
- Bimanual approach, grasp, traction, release, bounded manual input and jaw admission against the static liver.
- More detailed bound display/instrument geometry, original materials/textures and observation controls.
- Actual Lumen GI/reflection, hardware ray tracing and near-contact shadow comparisons.
- Step-based action recording, guarded replay, state identity and matching frozen snapshots.
- Basic stereo RGB/geometry export, including camera-Z depth, geometric normals, IDs, masks and cameras.
- Native, sustained-grip and endurance tests; packaged run; fresh ZIP extraction/run; independent geometry/data audits.

Accepted archive: `EndoForge-Phase6-Windows-20261024-r2.zip`. SHA-256: `268b726e1e1c21d722a4a7f47628aa8f48824846499fa619369b4b316d23caa9`. [Public metrics](verification/phase6-summary.json) summarize the local receipt. Raw evidence remains in the local delivery; this source sync does not claim a hosted runtime release.

### Modeling and appearance are not final

The scene has editable geometry, not only rendered images. The gallbladder deforms; liver and cavity are primarily static. Duct/artery shapes are orientation landmarks, not functional surgical targets. The port layout is an engineering rig, not clinical placement guidance.

Current images remain synthetic. Tissue color, translucency, wetness variation, small vessels, anatomical proportions and some highlighted surfaces need refinement. Published captures show the actual result without retouching. Advanced rendering and higher polygon counts do not establish photographic or anatomical realism. Anatomy review is pending.

### Physics boundaries

- Material parameters and force outputs are not calibrated to biological measurements or clinical safety thresholds.
- Strong/asymmetric traction can slip. Closure latches after bilateral load acquisition; tissue is not pinned to the tool.
- Rigid-liver jaw blocking is geometric admission, not measured reaction force.
- Full-shaft collision, general instrument–instrument response, general self-contact, deformable liver and full organ interaction remain incomplete or absent.
- No fluid/bile/blood, electrosurgery, anatomical dissection, organ cutting or suturing is delivered in this scene.
- Legacy Phase 3/4 cutting is a thin-specimen mesh-edge operation, not completed organ surgery.
- Geometry checks cover declared finite paths and sampled intermediate states, not arbitrary-motion collision freedom.

### Output and validation boundaries

The preserved Phase6 build's two short stereo sequences establish an export foundation; they are **not** either research project's finished dataset. Task-specific fields, intestinal scenes, timebase/frame-rate contracts, appearance variation, occlusion handling, scale and downstream ingestion need separate implementation and acceptance.

Geometric normals differ from material normal maps; camera-Z depth in millimetres differs from ray distance; modeled contact loads differ from handle forces. Replay is tolerance-based, not a blanket bit-identical cross-machine guarantee.

Software acceptance does not replace manual usability, supervisor/clinician review, tissue calibration or educational/clinical validation. A complete independent rebuild on a different clean machine remains unverified. Source checkout/file-integrity checks are a narrower, separately reported claim.

### Phase 6 r2 correction

The first 24 October candidate passed its initial package run but failed fresh-extraction acceptance: the right lift ended at approximately 2.166773 mm versus the intended 2 mm and the unchanged 0.12 mm endpoint tolerance. Tissue health remained valid; the exact-lift test advanced before in-flight movement settled.

r2 uses ordinary Ctrl+wheel 0.2 mm finite pulses, waits for applied-command and settled-position acknowledgement, then switches tools. It does not inject tissue motion or loosen endpoint/retained-deformation gates. Ordinary keyboard/mouse response is also tested by separate foundation trials. New editor, packaged and fresh-extracted runs measured approximately 2.000 mm per tool and passed. Native mechanics and its accepted binary were unchanged by this test-driver correction.

The unaccepted ZIP is preserved and marked locally. Only r2 is the accepted Phase6 delivery. Earlier solver/contact/liver-guard changes and coverage are explained in [PHASE6](PHASE6.md).

### Historical Phase6 next-work note

1. Supervisor review and a recorded manual usability/anatomy assessment.
2. Visual/anatomical refinement while preserving physical/display correspondence.
3. Separate scene/output contracts and implementations for the two research projects.
4. Measured tissue calibration if biological force accuracy becomes a required output.

The earlier Phase6 source synchronization added documentation, evidence and a launcher around its accepted simulation. That historical publication did not rewrite the preserved r2 ZIP or establish another accepted runtime.