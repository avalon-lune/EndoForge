# Phase 5: authored local gallbladder scene

This milestone replaces the technical specimen view with an original, editable
gallbladder, hepatic support and local abdominal working field. It connects the
new anatomy to native deformation, liver-bed attachment, two friction graspers,
guarded action replay and small synchronized stereo exports. Suturing is deferred.

Only the final delivery receipts establish completed acceptance. Diagnostic
trials under `tmp/` include deliberately retained failures and are not release
evidence. Phase 1–4 deliveries and the separate Phase 4 collision correction
remain immutable; the preservation audit also covers the teacher's source files.

## Anatomy and reference use

`Assets/Phase5/EndoForge_Anatomy.blend` is newly authored in Blender 5.2.2 LTS.
`Scripts/BlenderPhase5/build_assets.py` creates its editable objects, UVs,
materials, original texture maps, runtime mesh definition and preview. The
teacher's two anatomy atlases informed relationships and proportions; the
CholecSeg8K reference frames informed color, vessels, wetness and surrounding
fat. No third-party mesh or photographic pixels are copied into the new assets.

The local scene deliberately simplifies hepatic lobes, duct and arterial
landmarks and surrounding anatomy. The cavity is an open local working field,
not a complete abdomen or intestinal lumen. The two research briefs require
different downstream datasets: a gallbladder scene does not satisfy the
intestinal-lumen brief. Detailed anatomy and operative orientation need separate
tutor/clinician review.

## Mechanics and coordinate contract

Native coordinates are metres and UE world coordinates are centimetres, related
by multiplication by 100 without a hidden anatomical coordinate conversion.
X is the simulation lateral axis; Y runs from fundus toward neck; Z points away
from the hepatic support. These are not patient DICOM axes.

The authored gallbladder middle surface has 266 vertices and 528 triangles. Two
offset layers form a 1.1 mm wall with 532 physical nodes and 1,584 tetrahedra.
Large-displacement corotational tetrahedral FEM uses the existing native SOFA
implicit/contact pipeline. The neck material constraint is fixed. Thirty-one
back-side material vertices connect to fixed liver-bed anchors through springs
with their actual initial rest lengths; these attachment springs represent the
bed connection, not an artificial grasper attraction. The visual connection
membrane follows the corresponding outer-wall/anchor boundaries. Every fixed
anchor is bound to an actual hepatic triangle with explicit barycentric weights;
the loader independently reconstructs this position before accepting the asset.

The liver is a fixed, closed contact mesh with a locally refined hepatic bed. Its
visible surface uses the same coordinates and topology. The two Phase 5 instrument ports
are on their corresponding sides of the operative field; both tools are native
friction graspers. A UI closure latch preserves a command, not an unbreakable
attachment. Unequal or excessive traction can cause slipping and require opening
and regrasping. There is no Phase 5 organ cutting or suturing path.

The native Phase 5 intersection adapter preserves SOFA's point, edge and face
tests and constraint responses. Jaw proximity uses the established 1.5 mm alarm
and 0.45 mm contact offset. Liver proximity starts at 0.8 mm and expands to at
least `0.45 mm + maximum observed tissue speed × substep duration + 0.15 mm`.
The broad phase covers the larger envelope. This reduces unnecessary resting
contacts near the 0.95 mm bed gap; the policy and actual envelope are recorded.
It is a sampled velocity margin, not a proof of continuous collision detection.

The constitutive and attachment parameters are engineering settings. There is no
calibrated bile pressure, fluid model or biological force prediction. Lumen-volume
change is measured separately from tetrahedral wall-volume health. Self-contact,
general instrument/instrument, instrument/liver and background-cavity response
are not implemented by the tissue contact solver. The tested trajectories are
also geometrically audited for inter-jaw and liver/jaw overlap; this is finite
coverage, not a universal contact guarantee.

## Identity, replay and display

Phase 5 uses `--phase5` natively and `-LapPhase5` in UE. The distribution launcher
selects port 47327. Default legacy protocol 4 and explicit protocol 3 remain
separate compatibility paths.

`physics-mesh.json` has an immutable byte fingerprint in protocol 5, together
with model/version and the complete physical configuration. FNV-1a is used for
runtime identity and is not an authenticity claim; SHA-256 is used for delivery
receipts. Recording import checks the model, fingerprint, material settings and
commands before replacing the usable recording. Different anatomy or incompatible
configuration must be rejected. Native and UE state identities, topology and
material vertex identities remain associated with the rendered state.

Replay is evaluated at a declared numerical tolerance, not as a bit-for-bit
guarantee across processes. The original criterion is five runs with maximum
per-frame node RMS error at most 0.5 mm and identical grasp/release events.
Fresh-process contact trajectories can differ through floating-point accumulation;
the delivery reports include the measured RMS and worst individual-node error.
The SOFA matrix assembly contains address-ordered force-field containers, a
plausible source of changed accumulation order. This source-level observation
does not establish that it is the sole cause of every replay difference.

The UE scene checks the local physical asset and visual/physical binding before
displaying a healthy organ. Instruments follow actual returned jaw/pivot poses.
Dynamic rendering is barycentrically bound to physical boundary triangles;
additional triangles do not increase physical contact resolution. Normal-map
detail is a shading effect and must not be exported as geometric curvature.

## Small stereo exports

The automated UE exercise exports two short sequences with at least 12 distinct
accepted states each, at 640×512 pixels per eye and 5 mm baseline. Both eyes and
all image channels use the same frozen displayed state. The native service can
continue under its heartbeat while presentation is frozen; subsequent accepted
states remain separate. Export time is not counted as interactive performance.

Each frame includes actual world-space render geometry, native state, camera
intrinsics and extrinsics, RGB, float32 camera Z depth in millimetres, independently
rasterized geometric depth, world geometric normals, object IDs and a validity
mask. Pixels use a top-left origin and centers at `(x+0.5,y+0.5)`. This pinhole
sample has no distortion, motion blur or temporal AA. UE's clockwise front-face
convention defines outward geometric normals with `cross(C-A,B-A)`; shading
vertex normals and tangent normal textures are distinct data.

The independent Python auditor compares GPU depth against geometry over the
declared valid region, then uses ray/triangle intersections to check stratified
samples of depth, visible object identity and geometric normals. It checks actual
dimensions, units, camera basis, stereo separation, distinct state IDs and model
fingerprint. The validity mask excludes background and silhouette discontinuities
independently of the measured error; the report includes coverage.

These exports establish interface readiness, not completion of either research
dataset. Specular separation, no-specular counterpart images, HDR decomposition,
material-point tracks, curvature, refracted paths, motion exposure, calibrated
optics and larger coverage remain separate work.

## Acceptance and reproduction

The intended gates are machine-readable in
`Scripts/Phase5/acceptance-spec.json`. They include actual two-tool input,
release/recovery, multiple approach rolls/speeds/paths, straight retreat, at least
600 simulated seconds and 30 continuous cycles, five replays within 0.5 mm node
RMS with identical grasp/release events, malformed
and incompatible-record rejection, and legacy native/network checks.

`audit_contact.py` independently checks physical nodes and entire triangle faces
against actual jaw boxes, with intermediate output samples, inter-tool jaw SAT
checks and liver boundary/containment checks. Its 0.15 mm threshold is a stated
engineering criterion. It does not prove continuous collision freedom or cover
every shaft/background contact.

`TestPhase5Package.ps1` launches the real packaged game and drives its normal
PlayerController input path. Independent snapshot and dataset audits follow.
The final ZIP is extracted to a fresh directory, its manifest is verified and
the same packaged acceptance exercise is rerun. The final report records exact
native/game/asset identities and measured display/physics timing, including the
simulation-to-wall-time ratio.

Example tools from the repository root:

```powershell
& 'E:/Software/Blender/blender.exe' --background --factory-startup --disable-autoexec --python-exit-code 1 --python Scripts/BlenderPhase5/build_assets.py
& 'E:/Software/Blender/blender.exe' --background --factory-startup --disable-autoexec --python-exit-code 1 --python Scripts/BlenderPhase5/verify_blend.py
python Scripts/BlenderPhase5/audit_assets.py
python Scripts/Phase5/audit_geometry.py --mesh Assets/Phase5/physics-mesh.json --output tmp/phase5/geometry-audit.json
& .\Physics\build.ps1
& .\Prototype\LapTrainer\Scripts\Build.ps1 -EngineRoot E:/UE_5.7 -Target Editor
```

Blender's default generation preserves the existing physical JSON; explicit
`-- --rebuild-physics` invalidates dependent tests and requires complete
revalidation. The packaged `Source/` preserves the repository's relative layout,
including `Prototype/LapTrainer`, `Physics`, `Scripts`, `Assets/Phase5` and `docs`.
Rebuilding still requires the toolchain and dependencies described in
`BUILDING.md`; the playable package does not.
