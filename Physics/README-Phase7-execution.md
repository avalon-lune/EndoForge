# Phase 7 execution and recording compatibility

The dense Phase 7 liver retains its complete physical mesh and all triangle,
edge, and point collision features. The optimized native path uses a collision
BVH depth of 12 and SOFA's existing parallel execution of free motion and
collision detection. Contact response and constraint solving start after the
free-motion task has joined. Material properties, contact distances, friction,
NNCG tolerances, rigid-motion admission, and the physical asset are unchanged by
these scheduling changes.

Both changes are conditional on the existing `phase6Assembly` configuration.
The Phase 1–5 paths and `--phase6-baseline-assembly` retain their original
collision depth and sequential animation-loop setup. Previous packaged
deliveries remain separate; the current executable is a new build requiring
fresh qualification.

## Execution provenance

The exported `config.execution_settings` identifies
`phase7-dense-liver-cpu-v1`. It records the selected depth, parallel flags, and
requested thread settings. `observed_runtime` is captured after each graph
initialization by reading the effective algorithm flags and the existing shared
task-scheduler registry. Reading the registry does not instantiate, initialize,
or resize a scheduler. Mutable component `nbThreads` Data are recorded separately
in top-level `execution_diagnostics` on hello/state messages and in the native
log; they are not part of strict replay configuration.

The animation loop retains its tested default thread request of `0`; the
linear solver retains its request of `4` and `parallelInverseProduct=true`.
SOFA's first initializer controls the shared pool, so those component requests
are not reliable substitutes for its actual thread count. The initialization
smoke check on this workstation reported eight effective shared threads. This
is an observation, not a hardcoded eight-thread setting. Record the effective
count on every deployment. Performance gains must not be attributed entirely
to task overlap when shared-pool initialization can also affect compliance
assembly.

SOFA can rewrite the first initializing component's raw `nbThreads` Data from
zero to eight, while a later graph retains zero because the existing shared
pool is already initialized. This is an initialization-history observation,
not a different eight-thread execution configuration. The requested values
and actual scheduler type/count remain in `config.execution_settings`; the raw
observations remain visible in `execution_diagnostics`. Recording and replay
therefore retain strict equality of effective configuration across process
restarts without treating initialization history as a physical setting.

## Replay compatibility

Anatomy action recordings retain the existing strict configuration comparison.
The new execution settings, including the observed scheduler configuration,
are part of that comparison. Historical action files without those settings,
or records from a different execution configuration, are rejected rather than
silently replayed as equivalent. Use the corresponding earlier delivery for
earlier records, or make a fresh recording with this build.

A deliberately converted historical action sequence may be used as a
separately identified engineering comparison fixture. Such a conversion must
preserve the original file, disclose the configuration replacement and both
input hashes, and must not be described as successful unmodified replay.
Production replay validation must not ignore or remove configuration fields.

## Validation scope

The isolated scheduling experiments demonstrated improved recorded and UE
performance without changing the physical asset. The deeper BVH changed some
contact enumeration and resulting numerical trajectories relative to the old
depth-eight build, so the earlier physics qualification cannot be inherited.
The adopted source and executable require fresh native regression, motion
guard, interaction, replay, data, and packaged performance acceptance.
Diagnostic benchmark success alone is not a delivery acceptance result.

The canonical Windows build uses MSVC toolset `14.38.33130`
(`cl 19.38.33145.0`) and Windows SDK `10.0.22621.0`. Preserve the prior runtime
before rebuilding and retain source, executable, asset, and compiler identities
with the new qualification evidence.
