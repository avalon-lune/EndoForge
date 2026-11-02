# Phase 8 — case studies and look-development decisions

Author: Avalon. Reviewed 28 October 2026. These are primary-source references,
not licenses to redistribute source models or images.

## Relevant successful work

**SuFIA-BC / ORBIT-Surgical**
https://orbit-surgical.github.io/sufia-bc/

The authors describe a surgical digital-twin pipeline from CT segmentation to
mesh conversion, mesh cleaning/refinement, texturing and scene assembly. Its
organ presentation and tissue-retraction context are relevant comparisons.
Adopt the ordered geometry–material–scene workflow and multi-view review. Do not
import their success claims as validation of EndoForge, replace SOFA with their
simulator, or equate photorealistic anatomy with validated deformable mechanics.

**Epic Digital Humans / Photorealistic Character**
https://dev.epicgames.com/documentation/en-us/unreal-engine/digital-humans?application_version=4.27
https://dev.epicgames.com/documentation/unreal-engine/photorealistic-character?application_version=4.27

These production examples combine detailed color, roughness, specularity,
scattering and normal information. The useful principle is coordinated detail
at several spatial scales, including variation beneath the surface, rather than
a uniform glossy material. Skin is not gallbladder tissue: transfer the method,
not skin colors, scattering distances, anatomical detail or asset textures.

**Epic Subsurface Profile implementation**
https://dev.epicgames.com/documentation/en-us/unreal-engine/subsurface-profile-shading-model-in-unreal-engine

The documented profile provides scattering-distance control and dual specular
lobes. Screen-space and temporal dependencies require actual renderer testing.
Evaluate a short-distance tissue profile against the previous simple subsurface
shader. Do not assume a stronger scattering effect is more realistic. Confirm
the installed UE 5.7 implementation rather than copying newer API expectations.

## Local reference observations

Viewed original teacher frames `seg8k_video35_000780.png` and
`seg8k_video52_000320.png` from the supplied CholecSeg8K archives. Their appearance
differs across cases: pale gray/cream gallbladder, pink and green-gray variation,
irregular branching vessels; muted burgundy liver with capsule markings and
broken wet highlights; unequal yellow fat lobules and pink connective septa.
The near-axis light matters. RGB photographs alone do not identify optical
constants, albedo or roughness numerically. Do not bake observed highlights into
the base color or claim a patient-specific reconstruction.

## Diagnosis of the actual Phase 7 close-up

The shape is already smooth at this view, but the surface reads as opaque plastic:
broad uniform color, almost invisible micro-normal relief, sparse faint vessels,
one broad wet highlight. The duct and artery read as separate straight rods;
the narrow attachment strip reads as a pasted-on band. Instrument faces are
excessively dark. Simply adding triangles cannot correct those material and
connection problems.

## Initial implementation decisions, subject to actual UE review

- Preserve the qualified physical gallbladder/liver/attachment contract initially;
  improve bounded display and non-contact neck landmarks without pretending
  these landmarks have surgical mechanics. If the physical shape must change,
  issue a new identity and requalify it.
- Author new multiscale original color, branching vascular, fine connective and
  wetness fields. Fine relief stays shading-only, with explicit physical scale.
- Test short-distance scattering and two wet-surface reflection scales. Separate
  albedo and roughness. Keep fixed exposure for meaningful comparisons.
- Keep dynamic texture coordinates attached to material points. Avoid camera-
  facing overlays, hidden displacement, aggressive vignette or image-generation
  postprocessing as a substitute for runtime geometry/material quality.
- Start with the organ–bed–instrument area. Inspect actual UE close-ups before
  extending the method, then test moving shading and ordinary controls.

## First actual UE comparison (candidate 01)

The first close-up and oblique captures passed scoped interaction checks, but
failed the visual review: long repeated vascular lines, overly large pigment
patches, a dark liver and noisy scattering at shadow boundaries. This candidate
was rejected; diagnostic performance is not final acceptance evidence.

Candidate 02 replaces the lines with an original hierarchical branching field,
reduces color saturation and pole concentration, and lightens the hepatic
capsule. The profile uses UE 5.7's separable implementation because the adaptive
filtered importance-sampling implementation produced unstable grain in the
fixed-state capture path. Scattering distance and dual-lobe settings remain
explicit synthetic values. This choice must be checked in actual runtime stills,
motion and the four internal alignment captures before acceptance.

## Candidate 03 selection

Actual UE diagnostic04 captures were inspected at the workspace, organ, jaw
contact and dual-traction views, with additional oblique/attachment views.
Increasing vascular curvature and taper hierarchy avoids the earlier straight
hairline appearance. Softer capsule markings and varied micro-normal response
break the broad liver highlight. The actual loaded profile, separable mode,
material parameters and complete shader maps passed the appearance identity
audit. Scattering no longer shows the earlier colored grain in these captures.

This is an engineering improvement suitable for testing the common research
base, not a photographic reconstruction. Vessel layouts remain synthetic,
background fat is simplified, and orientation landmarks do not represent a
complete biliary tree. The idealized gallbladder and static liver remain visible
limits. Relative comparisons use different authored lighting/materials and are
not calibrated image-quality measurements. Clinical/anatomy approval is pending.
The final package, motion, contact and data checks remain separately required;
this look-development note is not final branch-readiness acceptance.
