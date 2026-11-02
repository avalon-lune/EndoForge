# Phase 9 historical review tools

These sixteen scripts preserve the exact helpers and final orchestration recipes
for the local Phase9 engineering review sealed on 2 November 2026. The
[manifest](manifest.json) records each original workspace-relative path, published
copy, byte count and SHA-256. These copies are publication documentation outside
the 533-file frozen build input inventory. Local attributes preserve their mixed
line endings.

The recipes expect their original directory depth, fixed local tool installations
and existing evidence under `tmp/phase9` and `output/Phase9`. Execution requires
restoring the manifest's original locations and the matching local evidence.
Several recipes also require fresh output directories. Preserve these historical
copies when adapting a separate new run.

Raw state traces, SDKs, compiled runtimes, delivery archives, reference documents
and private media are not included. See the [public engineering summary](../phase9-summary.json)
and [source identity inventory](../phase9-source-assets.json). Recorded passes
apply to the tested local binaries. These recipes do not establish a fresh
checkout build, a new test run, human visual approval or clinical validation.
