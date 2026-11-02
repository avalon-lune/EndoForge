# Phase 7 reference and visual review guide

Project author and maintainer: **Avalon**. Phase 7 develops the common anatomy,
material and rendering foundation before the two research projects diverge.
This guide records engineering observations from the supplied references; it is
not clinician approval, calibrated tissue optics or a patient-specific model.

## Reference roles

| Local reference | Appropriate use | Limits |
|---|---|---|
| `source/ref/ref/Cholecyst_CholecSeg8K_VID35_seg8k.zip` | Gallbladder/liver-bed appearance, liver capsule, local wet highlights and surrounding fat | RGB frames do not uniquely determine albedo, roughness, lamp intensity or camera calibration |
| `source/ref/ref/Cholecyst_CholecSeg8K_VID52_seg8k.zip` | Wider cavity context, traction, instrument appearance and near-axis endoscope lighting | Circular field of view and compression are acquisition characteristics, not anatomy |
| `source/full_male_anatomy_blender_anim_rigged_v1.6.3/` | Asymmetric liver outline, inferior surface and gallbladder relationship | Atlas appearance and inspection materials are not surgical photorealism or a physical tissue model |
| `source/Z-Anatomy-extracted/Z-Anatomy/Startup.blend` | Organ arrangement, gallbladder neck/body silhouette, diaphragm and omentum context | Saved base meshes include coarse surfaces and open boundaries; anatomy labels do not prove an existing usable cavity surface |

The local image inventory contains 240 VID35 and 800 VID52 RGB frames at
854 × 480. The review sampled both archives, including full-resolution frames
35/780, 35/1131, 52/320 and 52/2985. Those frame identifiers are provenance for
the visual discussion, not independent patient cases or a clinical evaluation.
Reference images and third-party meshes are not redistributed with EndoForge.
Original modelling and procedural texture authoring must remain separate from
the reference material.

## Visual targets

- **Gallbladder:** the supplied images include pale ivory, yellow-grey and pink
  tissue. Uniform green is not a required realism target. Use restrained,
  irregular colour variation, fine tapering vessels with soft edges, and wet
  surface detail. Avoid uniform opaque plastic, painted wire-like vessels,
  coarse pebble texture and highlights baked into the albedo.
- **Liver:** use a muted burgundy/plum appearance, subtle irregular pale capsule
  markings, and fine wet specular variation. Large planar highlights should not
  reveal a coarse display surface. Atlas liver shape is asymmetric, with a
  tapering left region and a distinct inferior surface, rather than a generic
  smooth plate.
- **Fat and cavity:** vary lobule size and arrangement; the reference fat is
  predominantly yellow/cream with pink-orange septa. Avoid a regular dark orange
  cobblestone ring. Cavity lining, fat and liver need different surface detail
  and spatial roles.
- **Liver bed:** preserve the actual attachment mechanics while improving the
  continuous fibrous/serosal appearance at the visible transition. A sharp
  pasted-on outline is not a satisfactory substitute for an attached surface.
- **Instruments:** distinguish metal from insulation and resolve the jaw tips at
  close range. Fine machining/roughness must remain stable under motion. Added
  visible geometry must agree with geometry exports and its collision scope.

Preserving a physical mesh byte-for-byte limits how far its displayed outline
may change. Smooth display normals, bound surface refinement and shading detail
are not evidence of a new anatomical volume. Any material change to physical
shape or attachment locations requires a new identity and corresponding
mechanical/contact validation.

## Lighting and imaging

The reference look depends on a light near the viewing axis, local curvature and
wet microstructure together. Use recorded camera-relative illumination and
controlled exposure when comparing changes. A broad glossy highlight cannot be
fixed solely by increasing polygon count; over-darkening the entire scene also
hides relevant structure.

The common scene should remain readable in overview, organ close-up, dual
traction and jaw-contact views. Strong vignette, circular cropping, sensor noise,
motion blur and compression are optional later acquisition profiles. They must
not conceal geometric defects or be described as evidence of physical realism.
The supplied RGB images do not establish calibrated numerical material or device
parameters; chosen parameters must be labelled as synthetic engineering values.

## Shared data requirements

The two local requirement documents establish common constraints that apply
before implementing their specialized outputs:

1. RGB, geometry, depth and object labels use the same accepted scene state,
   camera and explicit pixel-coordinate convention.
2. Normal maps modify **shading normals**. Exported **geometric normals** must keep
   their geometric meaning; extra texture detail is not additional measured
   geometry.
3. Highlights originate in geometry, lighting and the material model. A white
   RGB region or a Lumen feature comparison is not automatically a specular
   ground-truth pass.
4. Record geometry/appearance versions, texture hashes, material parameters,
   camera/light configuration, colour pipeline and applicable random seeds.
   Texture variants do not count as independently sourced anatomical models.
5. Preserve material-point identity through deformation, replay and snapshots.
   Include all relevant visible geometry in matching data exports.
6. Future distortion, crop and resampling need corresponding label transforms
   and explicit mappings. Exposure motion blur needs an exposure-time sampling
   convention rather than an unexplained single-frame truth claim.

This stage does not claim delivery of the specialized stereo highlight dataset,
colon scene suite, curvature labels, specular decomposition or tracking outputs.

## Review and acceptance evidence

Compare actual UE runtime and packaged captures with Phase 6 in the four views
above; record camera/exposure changes if the views are not exactly matched.
Inspect movement as well as still images for cracks, apparent penetration,
texture sliding, unstable reflections, shadow flicker and temporal trails.
Use independent geometry/data audits and exact-package checks alongside visual
inspection. A Blender preview alone does not validate the UE result.

Engineering checks and visual comparison can document improvement and remaining
defects. Supervisor/clinician review of anatomical suitability and teaching
realism remains a separate, pending decision.
