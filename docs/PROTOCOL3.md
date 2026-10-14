# Local Phase 3 protocol

The UE client connects to the native SOFA service at `127.0.0.1:47323`. Records are UTF-8 JSON objects terminated by a newline. The listener is local only. Phase 3 requires protocol `3`; a Phase 2 service is not compatible with the new client.

## Commands

Every command carries `type: "command"`, a sequence number `seq`, an integer `reset_id`, `paused`, `active_tool` (0 or 1), and exactly two entries in `tools`:

```json
{
  "type": "command",
  "seq": 1,
  "reset_id": 0,
  "paused": false,
  "active_tool": 0,
  "tools": [
    {"tip_m": [-0.022, -0.047, 0.006], "closed": 0, "roll_deg": 90},
    {"tip_m": [0.022, -0.047, 0.006], "closed": 0, "roll_deg": 90}
  ]
}
```

Tool 0 is the grasper and tool 1 is the scissors. Both targets are transmitted every tick. The inactive instrument retains its actual pose and existing closure; explicit opening is always accepted, while new closure and motion require selecting that instrument. This allows a deliberately latched grasper to keep holding while scissors are selected. Selecting a tool does not transfer its position to the other tool. The physics service applies its own motion limits; command positions are not authoritative actual poses.

## Accepted state

The service begins with `type: "hello"`, `protocol: 3`, `units: "m"`, `vertices` and `triangles`. Subsequent `state` records contain complete current geometry, not a partial topology patch. Vertex indices can change after cutting or reset.

| Field | Meaning |
|---|---|
| `vertices`, `triangles` | Physical positions in metres and triples of zero-based vertex indices |
| `topology_revision` | Revision of the physical mesh connectivity |
| `cut_count` | Number of successful cutting transactions (one can sever several mesh edges) |
| `cut_edge_count` | Number of distinct severed mesh edges |
| `component_count` | Number of connected tissue components |
| `cut_length_m` | Cumulative cut length, in metres |
| `reset_id` | Acknowledged reset |
| `healthy` | Numerical health flag |
| `step_ms` | Physics step computation time in milliseconds |
| `max_displacement_m` | Maximum displacement from material rest positions |
| `tools` | Two actual instrument states, in grasper/scissors order |

Each tool state provides `tip_m`, `roll_deg`, `jaw_open_fraction`, `grasping`, `force_n`, `contact_count`, `contact_force_n`, `penetration_m`, `slip_distance_m`, `grip_state` and two `jaw_poses`. Each jaw frame contains `center_m` and unit world vectors `axis`, `side`, `normal`, forming a right-handed orthonormal frame.

The UE bridge converts metres to centimetres for rendering and millimetres for penetration/slip displays. Forces are engineering model outputs, not measured forces or clinical safety thresholds. Their mechanical definitions are documented with the model in [PHASE3.md](PHASE3.md).

## Transaction and freshness rules

The bridge validates the complete mesh, counters and both tools before committing a state. An invalid second instrument therefore cannot update the first instrument or the tissue. Invalid data does not refresh the input watchdog. A connectivity change requires a different topology revision; a topology rollback requires a changed reset identifier.

The bridge accepts up to 10,000 vertices and 20,000 triangles, checks triangle index ranges and repeated indices, and verifies all jaw frames. It rejects non-finite coordinates or telemetry. TCP input buffering is bounded to 4 MiB. Partially sent commands finish before a new command is queued, preserving JSON record boundaries.

Closure is permitted only after a healthy, fresh state with the requested reset acknowledgement. The service separately handles command timeout/disconnection. The UI clears deliberate holds on connection loss and reset. Neither stale data nor a visible retained mesh proves that live physics is running.

`EndoForge.Phase3.AtomicTopologyProtocol` is an Unreal automation test for malformed geometry, malformed second-tool telemetry, an actual connectivity/vertex-count transaction, stale pre-cut geometry, reset and watchdog freshness. It is separate from native SOFA and normal PlayerController input acceptance.

`safety_stops` is a nonnegative integer in every state. UE retains the highest observed count across resets and reconnects, logs it in the session CSV, and fails ordinary interaction acceptance if any protection was observed, including force-limit stops that keep `healthy=true`.
