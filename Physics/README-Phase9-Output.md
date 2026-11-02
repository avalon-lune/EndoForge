# Phase9 native physics output v1

The anatomy asset opts in with this exact tag:

```json
"phase9_physics_output": {"schema": "endoforge.phase9-physics-output.v1"}
```

The loader rejects unsupported nonempty tags. An absent, null, or empty tag keeps
the previous output contract. A model's numeric version alone does not enable
Phase9 output. No solver, material, mesh, collision or grasp-control setting is
selected by this tag.

The Phase4Session hello, live states and recorded snapshots include
`output_schema: "endoforge.phase9-physics-output.v1"`. Existing protocol,
`endoforge.physics-state.v1` snapshot schema and action schema stay unchanged.
The hello, initial recording snapshot and session metadata contain
`physics_output_definition` with units, indexing, sign and sampling scope.

## Node velocity

`velocities_m_s[i]` is the actual SOFA tissue MechanicalObject velocity in world
XYZ, in metres per second. Its index matches `vertices[i]` and `node_ids[i]` in
the same state. It is the current solver velocity, including the restored
velocity after a rejected trial. It is not a finite difference of rendered
positions. Legacy snapshots already carried this array; Phase9 also publishes
it in every live state and the hello.

## Tool contact reaction

Each tool entry has these additional fields:

| Field | Meaning |
| --- | --- |
| `contact_force_sample_valid` | Whether a successful solve supplies the sample. |
| `contact_force_sample_duration_s` | Duration `h` of the final accepted substep, in seconds; null without a valid sample. |
| `jaw_contact_resultants_on_tool_n[j]` | World XYZ contact reaction on jaw `j`, in newtons; indexing matches `jaw_poses`. |
| `contact_resultant_on_tool_n` | Sum of the two jaw reaction vectors, in newtons. |
| `contact_resultant_magnitude_n` | Euclidean magnitude of that resultant, in newtons. |
| `contact_force_sum_magnitudes_n` | Explicitly named alias of the unchanged legacy scalar `contact_force_n` / `force_n`. |

For each jaw, the vector is reconstructed from its native mapped constraint
Jacobian and the solver's `d_constraintForces` impulse multipliers:

```text
F_jaw = sum_rows sum_columns J_jaw[row,column] * lambda[row] / h
F_tool = F_jaw[0] + F_jaw[1]
```

This includes normal and both tangential Coulomb components with their native
signs. The result is the reaction **on the tool**, in world coordinates. The
mapped `getLambda()` storage is not used. The jaw Jacobian selects tool/tissue
contacts, excluding liver-only tissue contacts. The prescribed rigid-liver
motion guard has no modeled reaction force to report. Shaft, tool/tool and
handle-actuation forces are also outside this output.

The legacy scalar remains the sum of individual contact-force magnitudes:
`sum_contacts sqrt(lambda_n^2 + lambda_t1^2 + lambda_t2^2) / h`, with each
contact triple selected once across both jaws. Opposing jaw reactions can
cancel in `contact_resultant_on_tool_n` while this scalar stays positive. None
of these values is a clinically calibrated clamp or handle force.

The vectors and scalar describe the **last accepted substep**, not an average
over the complete output frame. A successful solve without contact publishes
valid zero vectors. Before the first successful solve and after a rejected
step, `contact_force_sample_valid` is false; the resultant and duration fields
are null, and the per-jaw array is `[null, null]`. Rejected trial impulses are
never published as an accepted vector. A paused state retains the sample at
the unchanged simulation time. The legacy scalar retains its previous
initialization and rejection-clearing behavior.

## Native audit helper

Include `Phase9OutputAudit.h` after `Phase4Session.h` and call
`phase9AuditPhysicsOutput(session, session.state())` at real solver states. The
returned JSON has `passed`, `errors`, tolerances and per-tool metrics. It checks
live velocity/ID ordering, legacy aliases, accepted-substep duration, null and
zero sample behavior, and each jaw's action/reaction against the opposite
**unprojected collision-surface Jacobian** restricted to the jaw's rows. SOFA
projects fixed-neck columns out of the parent tissue Jacobian; those contacts
still contribute a reaction on the tool. The audit independently reconstructs
each surface row from the projected parent plus its fixed-node contributions,
using the same strict numerical tolerance. The fixed contribution is reported
explicitly. It reports absent contact
rows separately from zero-impulse and active rows. An actual untagged live state
is checked for absence of the new fields.

The fixture must observe `metrics.contact_reaction_reference_exercised: true`
to qualify its contact-force check; a successful no-contact audit alone does
not exercise the force reference.

`testPhase5` applies this audit only for tagged assets, beginning at the initial
state and continuing through its actual ticks and any requested replays. It
writes `<report-stem>-phase9-output-audit.jsonl` beside the ordinary state trace.
The report retains its existing phase label, adds `milestone: 9`, summarizes
initial invalid, accepted noncontact and nonzero-contact coverage, and requires
every audit to pass with at least one nonzero contact reference exercised.
Existing motion, health and numerical acceptance gates remain in effect.
Untagged runs do not create an audit file.

Force comparisons allow `1e-9 N + 1e-8 * max(vector magnitudes)` for native
double-precision summation and mapping order, including cancellation. Copied
velocities allow `1e-12 m/s + 1e-10 * max(velocity magnitudes)`; duration allows
`1e-12 s`. These are numerical comparison tolerances, not calibration bounds.
The helper does not create contact or synthesize fixture states. Run contact,
traction, rejection and untagged cases in the caller's native fixture.

## Attachment distribution under mesh refinement

A Phase9-tagged anatomy asset may specify `attachment_vertex_weights`, an
array of positive finite dimensionless values in the same order as
`attachment_vertex_ids`, anchor positions and anchor bindings. An absent array
means all weights are 1, preserving earlier assets. A supplied array requires
the exact Phase9 output tag and a length matching the attachment list.

For attachment index `i`, the actual native spring uses stiffness
`2 N/m * weight[i]` and damping `0.02 N*s/m * weight[i]`. The published
`attachment_elastic_force_n` uses the same effective stiffness and remains a
sum of the absolute elastic spring loads; it excludes damping. The attachment
loop appends `bedNodes[i]` while resolving `attachment_vertex_ids[i]`, so the
native spring, anchor and reported load share the same index. The unchanged
base constants are not a claim of biological calibration.

The Phase9 mesh generator distributes weights by lumped patch area and
normalizes their sum to 31, the earlier attachment count. This preserves the
aggregate nominal stiffness and damping when the patch is refined. It is a
numerical distribution policy, not an identified biological material or
attachment law. The loader validates individual weights; it does not
renormalize them. The asset source and its fingerprint preserve the authored
values for recording identity and reproducibility.
