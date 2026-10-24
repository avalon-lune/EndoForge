# EndoForge protocol 4 and recording formats

The default native service listens on `127.0.0.1:47325`. Messages are UTF-8 JSON objects separated by newlines, over one local TCP session. Physics units are metres, seconds, kilograms and Newtons; UE display positions are native positions multiplied by 100 (centimetres). This is a local engineering API, not a network service for untrusted remote clients.

Protocol 4 extends the [protocol 3](PROTOCOL3.md) geometry/tool state with configuration, state identity and recording/replay control. Explicit native `--phase3` and UE `-LapPhase3` retain the preceding compatibility path. Do not connect a protocol-3 client to the protocol-4 default port.

## Command

The existing command contains `type: "command"`, `reset_id`, `paused`, `active_tool` (0 or 1), and exactly two `tools`, each with `tip_m`, `roll_deg`, and `closed`. Protocol 4 additionally permits:

| Field | Meaning |
|---|---|
| `specimen` | `flat` or `curved`; a change is applied with a new reset identifier |
| `session_action` | Empty, `record_start`, `record_stop`, `replay_last`, or `replay_stop` |
| `action_id` | Nonnegative exactly representable integer, monotonically increasing for new session actions |
| `seq` | Optional command sequence identifier |

`record_start` and `replay_last` require a new `reset_id`. Session action identifiers prevent retransmission from repeating the same action. Invalid fields reject the command before mutation. Live tool commands cannot change an active or completed replay. `replay_stop` releases tools and returns to ordinary input; reset also ends the current replay/recording.

Recordings begin from a defined reset configuration, rather than silently recording from an unknown deformed state. A native recording stores the commands that were actually applied at accepted simulation steps, not wall-clock keyboard event times. One accepted outer step advances 1/30 s; adaptive solver substeps are internal to that step.

## Returned state

Native geometry, topology and both tool states form one accepted snapshot. Added fields include:

| Field | Meaning |
|---|---|
| `protocol` | Integer 4 |
| `specimen`, `config` | Selected shape name and complete accepted physical configuration |
| `simulation_id` | Reset/configuration epoch within the native process |
| `state_id` | Monotonic native state identifier within that process |
| `node_ids` | Unique persistent node identity for the current epoch; not an array index |
| `material_node_ids` | Original material identity, including layer identity |
| `parent_node_ids` | Previous node ancestor when a split creates a new identity; -1 if no parent |
| `session` | Mode, acknowledged action ID, accepted step index, replay length, recorded step count, action filename and error |
| `total_mass_kg`, `thickness_m` | Current specimen metadata |

The inherited `topology_revision` identifies geometry connectivity changes. Array indices and material identities serve different purposes: cut nodes can share original material ancestry while moving independently. State IDs are not wall-clock frame numbers; several rendered frames can use the same accepted native state. Across service restarts, pair IDs with the owned session/run provenance rather than treating numeric IDs as globally unique.

UE validates the whole message before committing it. Invalid identity arrays, stale revisions/epochs, malformed tool frames or incomplete geometry must not partly update the rendered specimen. Health and protection histories remain part of acceptance even after a later healthy state.

## Native files

The launcher creates an owned directory under `Sessions/` and passes it with `--session-dir`. A recording produces timestamped `session-...-actions.json`, `session-...-states.jsonl` and `session-...-metadata.json`; `last-session.json` identifies the latest completed take.

A loaded take is limited to 180,000 steps (100 simulated minutes). `StartTrainer.ps1 -ReplayRecording PATH` copies an existing completed action record into a new owned session directory; F6 then replays it using the saved configuration.

`endoforge.actions.v1` contains `dt_s`, `config` and the ordered `steps` command array. A recorded step may also contain `clear_stroke_edges: [bool, bool]`: this preserves a tool-switch or reopening transition that cleared the candidate cutting stroke between two simulation steps, even if several commands arrived in that interval. Replay applies that logical transition before the effective step command; it does not inject recorded geometry or tool poses. `endoforge.session.v1` metadata records accepted step count, duration, configuration, corresponding filenames and the force definition. A state file includes the initial state plus each accepted recorded step. Its `endoforge.physics-state.v1` rows additionally include rest vertices, velocities, tetrahedra, fixed indices and cut material edges.

The physical contact-load quantity is the sum of contact impulse magnitudes divided by the accepted final substep duration. It is not a measured handle force, biological stress ground truth or clinical injury limit.

## UE presented-state and frozen-snapshot files

`phase4-presented-states.jsonl` stores records with `record_kind: "presented_state"`, the accepted `native_state`, camera, rendered vertex count and topology revision. It records the native state displayed by the scene, not every off-screen native step.

F7 creates `phase4-snapshot-NNN.json` and a matching PNG. During capture the scene holds the displayed state. The JSON contains:

- `native_state` and capture identity;
- `render_vertices_cm`, `render_triangles`, and `render_bindings` with physical `nodes` and barycentric `weights`;
- `camera` with position/basis, FOV, viewport, actual view rectangle and view-projection matrix;
- `projected_samples` with render vertex indices and UE PlayerController screen coordinates;
- `screenshot` and actual screenshot dimensions.

UE world axes are +X forward, +Y right and +Z up; image coordinates start at the top left. The recorded view rectangle is needed for constrained viewports. This renderer does not model calibrated lens distortion. Any nominal pinhole intrinsics are descriptive; validation uses the saved actual projection matrix and engine-projected samples.

`Scripts/verify_phase4_snapshot.py` independently reconstructs the bound visible geometry and projects saved vertices through that matrix. It requires at most 1 pixel deviation from the engine projection, valid identities/topology and a matching image size. This establishes geometric state correspondence, not pixel-perfect semantic segmentation or anatomical validity.

## Delivery provenance

Native build metadata identifies executable and source/config hashes; regression reports identify the exact tested executable. A post-UAT receipt captures packaged game, editor module and UE source hashes. The delivery finalizer rejects mismatched evidence, incomplete endurance/replay gates and failed snapshot audits, then writes the per-file manifest and ZIP SHA-256. A fresh extracted-package run is verified afterward without modifying the completed archive.
