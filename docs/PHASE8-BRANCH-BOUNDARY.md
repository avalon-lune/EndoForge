# Phase8 common base and subsequent research branches

Author and maintainer: Avalon. This is an implementation boundary, not a claim
that either research dataset or clinical simulator is complete. The final
Phase8 verification receipt determines whether this base is accepted.

## Shared components to retain

- Original editable Blender assets and reproducible asset authoring; a UE scene
  with differentiated wet tissue, metal and surrounding anatomy materials.
- Keyboard/mouse control of two instruments, accepted native tissue deformation,
  contact/friction grasping, liver-bed attachment and explicit collision scope.
- D3D12/SM6, Lumen GI/reflections, hardware RT, near shadows and a recorded common
  illumination profile. Optical effects are separated from physical geometry.
- Recorded per-step commands, strict configuration-aware replay, accepted native
  state, stable material-node identities and dynamic display bindings.
- Frozen stereo RGB, camera-Z depth in millimetres, geometric world normals,
  object IDs, validity masks, actual display triangles, cameras and identities.
  Four internal alignment frames are regression checks, not a research dataset.

## What the branches add

| Direction | Starts from this base | Work that belongs to the branch |
|---|---|---|
| Project1: stereo endoscopic highlights | Shared renderer, materials, paired cameras, geometry and state records | Linear HDR and specular/no-specular decomposition, curvature definitions, highlight/occlusion masks, instances and tracks, controlled appearance variations and project-specific acceptance |
| Project2: colon sequences | Shared camera/state/version conventions, geometry export, replay and rendering infrastructure | Colon anatomy and folds, endoscope front geometry/motion, physical gap definitions, long trajectories, temporal material-point correspondence, revisits, visibility and project-specific imaging cases |

A gallbladder texture cannot substitute for a colon model. Neither branch should
reimplement transport, state identity or output coordinate conventions merely
because its anatomy and research fields differ. Branch-specific physical changes
need new model/version identities and their own qualification.

## Imaging direction versus research direction

The realistic common scene is the base. A surgical-camera appearance profile can
later add device-specific response, noise, tone mapping and lens effects to that
same base. This is separate from the Project1/Project2 split. Any spatial warp
must transform coordinates and validity consistently; exposure or temporal
effects need recorded sampling semantics. No such new effects are hidden in
Phase8 RGB.

## Stable conventions and limitations

Native coordinates use metres; UE/exported mesh coordinates use centimetres.
Image depth is camera-axis Z in millimetres, not ray distance. Geometric normals
exclude the material normal map. Existing `phase5`/`phase7` schema and filename
labels remain where the format/algorithm is unchanged; numeric `phase:8` and the
appearance/model hashes identify the current milestone.

The unchanged qualified FEM is a 532-node, 1,584-tetrahedron gallbladder wall;
display detail is distinct from physical resolution. The liver is static, the
attachment display represents the spring envelope, and duct/artery landmarks
have no functional mechanics. Full-shaft collision, general self-contact,
calibrated force/tissue optics, organ dissection, suturing, biological validity
and specialist approval are not supplied by this engineering acceptance.

Teacher requirements remain in the local `source` folder. Original reference
photos and third-party anatomy collections are not redistributed with the
authored Phase8 assets.
