"""Validate exact Phase 4 binaries and real test evidence, then create the ZIP.

This does not build, run tests, or invent missing results. Relocation testing is
separate because its receipt refers to the SHA-256 of this completed archive.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import stat
import struct
import sys
import uuid
import zipfile
from verify_phase4_snapshot import audit_snapshot

ROOT = Path(__file__).resolve().parents[1]



def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    require(path.is_file(), f"Missing evidence: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    require(isinstance(value, dict), f"Expected JSON object: {path}")
    return value


def no_reparse(path: Path) -> None:
    for entry in (path, *path.parents):
        if entry.exists() or entry.is_symlink():
            attrs = entry.lstat()
            require(not entry.is_symlink() and not (getattr(attrs, "st_file_attributes", 0)
                    & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)),
                    f"Junction or symbolic link is not permitted: {entry}")


def report(path: Path, executable_hash: str | None = None, checks: bool = True, expected_phase: int = 4) -> dict:
    value = read_json(path)
    require(value.get("phase") == expected_phase and value.get("passed") is True,
            f"Expected successful Phase {expected_phase} evidence: {path}")
    require(value.get("experimental") is not True and not value.get("failure")
            and not value.get("failures"), f"Report has unresolved failures: {path}")
    if "native_exit_code" in value:
        require(value["native_exit_code"] == 0, f"Native process did not exit successfully: {path}")
    if checks:
        assertions = value.get("checks")
        require(isinstance(assertions, dict) and bool(assertions)
                and all(item is True for item in assertions.values()),
                f"Every check must be present and true: {path}")
    if executable_hash:
        require(str(value.get("executable_sha256", "")).lower() == executable_hash,
                f"Report belongs to a different physics executable: {path}")
    return value


def png_size(path: Path) -> tuple[int, int]:
    require(path.is_file() and path.stat().st_size > 10000, f"Missing screenshot: {path}")
    with path.open("rb") as stream:
        header = stream.read(24)
    require(header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR", f"Invalid PNG: {path}")
    width, height = struct.unpack(">II", header[16:24])
    require(width >= 640 and height >= 360, f"Screenshot too small: {path}")
    return width, height


def check_preserved(baseline_path: Path, phases: tuple[str, ...] = ("Phase1", "Phase2", "Phase3")) -> dict:
    baseline = read_json(baseline_path)
    entries = baseline.get("files", [])
    require(bool(entries), "Previous-phase baseline is empty")
    counts = {name: 0 for name in phases}
    seen = set()
    for entry in entries:
        relative = Path(entry["path"])
        require(not relative.is_absolute() and len(relative.parts) > 2 and
                relative.parts[0] == "output" and relative.parts[1] in counts,
                "Baseline must contain only the required preserved output phases")
        path = (ROOT / relative).resolve()
        require(path.is_relative_to((ROOT / "output" / relative.parts[1]).resolve()), "Unsafe baseline path")
        require(str(relative) not in seen, "Duplicate preservation baseline path")
        seen.add(str(relative))
        require(path.is_file() and path.stat().st_size == entry["size"] and sha256(path) == entry["sha256"],
                f"Previous-phase file changed or disappeared: {relative}")
        counts[relative.parts[1]] += 1
    require(all(counts.values()), "Preservation baseline must cover every required previous phase")
    actual = {str(path.relative_to(ROOT)) for name in phases
              for path in (ROOT / "output" / name).rglob("*") if path.is_file()}
    require(actual == seen, "Preserved output file set differs from its baseline")
    return {"phase": 4, "passed": True, "baseline_sha256": sha256(baseline_path),
            "verified_files": len(entries), "counts": counts,
            "checked_at_utc": datetime.now(timezone.utc).isoformat()}


def validate_source_set(source_hashes: dict, package: Path) -> None:
    require(isinstance(source_hashes, dict) and len(source_hashes) >= 10, "Missing UE source provenance")
    for name, digest in source_hashes.items():
        prefix = "Prototype/LapTrainer/"
        require(name.startswith(prefix), "Invalid UE source receipt path")
        relative = Path(name[len(prefix):])
        require(not relative.is_absolute() and ".." not in relative.parts, "Unsafe UE source path")
        source = package / "Source/LapTrainer" / relative
        require(source.is_file() and sha256(source) == digest.lower(), f"UE packaged source differs: {name}")
    ue_root = package / "Source/LapTrainer"
    actual = {"Prototype/LapTrainer/LapTrainer.uproject"}
    for folder in ("Source", "Config", "Content"):
        actual.update("Prototype/LapTrainer/" + p.relative_to(ue_root).as_posix()
                      for p in (ue_root / folder).rglob("*") if p.is_file())
    require(actual == set(source_hashes), "UE source receipt does not cover exactly the shipped build inputs")


def validate_repeats(native: dict) -> None:
    specimens = native.get("specimens", [])
    require(len(specimens) == 2 and {item.get("specimen") for item in specimens} == {"flat", "curved"},
            "Repeatability evidence must cover both specimens")
    for item in specimens:
        repeats = item.get("repeats", [])
        require(len(repeats) >= 5, "At least five repeats required per specimen")
        require(len({r.get("repeat") for r in repeats}) == len(repeats), "Duplicate repeat identifiers")
        for repeat in repeats:
            rms = repeat.get("max_frame_node_rms_m")
            require(repeat.get("completed") is True and repeat.get("same_discrete_events") is True and
                    isinstance(repeat.get("steps"), int) and repeat["steps"] >= 300 and
                    isinstance(rms, (int, float)) and math.isfinite(rms) and 0 <= rms <= 0.0005,
                    "Incomplete repeat, mismatched events, or RMS > 0.5 mm")
        m = item.get("metrics", {})
        require(m.get("all_healthy") is True and m.get("all_finite") is True and
                m.get("gripped_steps", 0) > 0 and m.get("max_displacement_m", 0) > 0.002,
                "Repeat reference must contain healthy actual grip and meaningful traction")
    if "cut_replays" in native:
        cuts = native["cut_replays"]
        require(len(cuts) >= 5 and len({r.get("repeat") for r in cuts}) == len(cuts), "Incomplete cut replay repetitions")
        for replay in cuts:
            rms = replay.get("max_frame_node_rms_m")
            require(replay.get("completed") is True and replay.get("same_discrete_events") is True and
                    replay.get("steps", 0) > 0 and isinstance(rms, (int, float)) and math.isfinite(rms) and
                    0 <= rms <= .0005, "Cut replay geometry, topology events or node identity differs")


def validate_endurance(value: dict, specimen: str, path: Path) -> tuple[Path, dict]:
    require(value.get("kind") == "continuous_endurance" and value.get("specimen") == specimen,
            "Endurance report kind or specimen mismatch")
    m = value.get("metrics", {})
    require(m.get("all_healthy") is True and m.get("all_finite") is True and
            m.get("safety_stops") == 0 and m.get("reset_count_during_test") == 0,
            "Endurance contains invalid states, safety stops, or resets")
    require(m.get("accepted_steps", 0) >= 18000 and m.get("simulated_seconds", 0) >= 600 - 1e-7,
            "Endurance must cover at least 600 simulated seconds / 18000 steps per specimen")
    cycles = value.get("cycles", [])
    require(len(cycles) >= 60 and all(c.get("gripped") is True and c.get("safety_stops") == 0 for c in cycles),
            "Every continuous 10-second exercise cycle must actually grip")
    require(m.get("cycles_with_grip") == len(cycles), "Gripped cycle count differs from raw cycle records")
    require(isinstance(m.get("max_sampled_penetration_m"), (int, float)) and
            0 <= m["max_sampled_penetration_m"] <= m.get("sampled_penetration_tolerance_m", -1) <= 0.00015,
            "Sampled node penetration exceeds 0.15 mm engineering tolerance")
    history = path.with_name(path.stem + "-states.csv")
    require(history.is_file(), f"Missing raw endurance history: {history}")
    with history.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == m["accepted_steps"], "Raw endurance history count differs")
    previous_time, previous_step, previous_state, epoch = 0.0, 0, -1, None
    peak_penetration, max_step_ms = 0.0, 0.0
    cycle_observations = {}
    for row in rows:
        require(row.get("healthy") == "1" and row.get("safety_stops") == "0", "Unhealthy endurance row")
        numbers = {key: float(row[key]) for key in ("time_s", "min_tet_volume_ratio", "min_triangle_area_ratio",
                   "max_displacement_m", "max_sampled_penetration_m", "step_ms")}
        require(all(math.isfinite(n) for n in numbers.values()), "Nonfinite endurance state")
        step, state = int(row["step_index"]), int(row["state_id"])
        if epoch is None:
            epoch = int(row["simulation_id"])
        require(int(row["simulation_id"]) == epoch, "Endurance changes simulation epoch")
        require(step == previous_step + 1 and state > previous_state and numbers["time_s"] > previous_time,
                "Endurance history is not continuous and monotonic")
        require(abs(numbers["time_s"] - step / 30.0) < 0.001, "Endurance timebase differs from step history")
        require(numbers["min_tet_volume_ratio"] > 0 and numbers["min_triangle_area_ratio"] > 0,
                "Endurance history contains invalid elements")
        require(row.get("grasping") in ("0", "1"), "Missing explicit endurance grip state")
        cycle, phase = divmod(step - 1, 300)
        observed = cycle_observations.setdefault(cycle, {"cycle": cycle, "lift_gripped_steps": 0,
            "lift_gripped_deformed_steps": 0, "lift_max_displacement_m": 0.0, "late_release_gripped_steps": 0})
        if 90 <= phase <= 179:
            observed["lift_max_displacement_m"] = max(observed["lift_max_displacement_m"], numbers["max_displacement_m"])
            if row["grasping"] == "1":
                observed["lift_gripped_steps"] += 1
                if numbers["max_displacement_m"] > .002:
                    observed["lift_gripped_deformed_steps"] += 1
        if phase >= 210 and row["grasping"] == "1":
            observed["late_release_gripped_steps"] += 1
        peak_penetration = max(peak_penetration, numbers["max_sampled_penetration_m"])
        max_step_ms = max(max_step_ms, numbers["step_ms"])
        previous_time, previous_step, previous_state = numbers["time_s"], step, state
    require(abs(peak_penetration - m["max_sampled_penetration_m"]) < 1e-6,
            "Raw penetration history differs from summary")
    require(previous_time >= 600 - 0.001, "Raw endurance history is shorter than 600 seconds")
    complete_cycles = [observation for cycle, observation in sorted(cycle_observations.items())
                       if (cycle + 1) * 300 <= len(rows)]
    require(len(complete_cycles) >= 60, "Missing complete raw exercise cycles")
    require(all(item["lift_gripped_deformed_steps"] > 0 for item in complete_cycles),
            "An endurance cycle lost meaningful grip/traction during its lift phase")
    require(all(item["late_release_gripped_steps"] == 0 for item in complete_cycles),
            "An endurance cycle remained gripping after the opening transient")
    return history, {"passed": True, "rows": len(rows), "simulated_seconds": previous_time,
                     "peak_sampled_penetration_m": peak_penetration, "max_step_ms": max_step_ms,
                     "complete_cycles": len(complete_cycles),
                     "min_lift_gripped_steps_per_cycle": min(item["lift_gripped_steps"] for item in complete_cycles),
                     "min_lift_gripped_deformed_steps_per_cycle": min(item["lift_gripped_deformed_steps"] for item in complete_cycles),
                     "late_release_gripped_steps": sum(item["late_release_gripped_steps"] for item in complete_cycles),
                     "cycles": complete_cycles,
                     "history_sha256": sha256(history)}


def validate_recordings(run: Path, metadata_paths: list[Path] | None = None,
                        require_presented: bool = True) -> list[dict]:
    summaries = []
    if metadata_paths is None:
        metadata_paths = sorted((run / "native-sessions").rglob("*-metadata.json"))
    for metadata_path in metadata_paths:
        metadata = read_json(metadata_path)
        require(metadata.get("schema") == "endoforge.session.v1", "Invalid native session metadata")
        paths = []
        for field in ("actions_file", "states_file"):
            name = metadata.get(field, "")
            require(isinstance(name, str) and Path(name).name == name and bool(name), "Unsafe recording filename")
            paths.append(metadata_path.parent / name)
        actions_path, states_path = paths
        actions = read_json(actions_path)
        steps = actions.get("steps", [])
        require(actions.get("schema") == "endoforge.actions.v1" and bool(steps) and
                abs(actions.get("dt_s", 0) - 1/30) < 1e-12 and
                actions.get("config") == metadata.get("config") and
                len(steps) == metadata.get("accepted_steps"), "Incomplete or mismatched action recording")
        require(abs(metadata.get("duration_s", -1) - len(steps)/30) < 1e-6,
                "Native recording duration differs from accepted action count")
        require(metadata.get("initial_state_included") is True, "Native recording omits initial state")
        count, epoch, previous_state = 0, None, -1
        with states_path.open(encoding="utf-8-sig") as stream:
            for line in stream:
                state = json.loads(line)
                require(state.get("schema") == "endoforge.physics-state.v1" and state.get("protocol") == 4,
                        "Native recording has invalid state schema")
                if epoch is None:
                    epoch = state.get("simulation_id")
                require(state.get("simulation_id") == epoch and state.get("state_id", -1) > previous_state,
                        "Native recording has stale state identity or unannounced reset")
                require(state.get("session", {}).get("step_index") == count and
                        abs(state.get("time", -1) - count/30) < 1e-6, "Native record timebase mismatch")
                require(state.get("healthy") is True and state.get("safety_stops") == 0 and
                        state.get("config") == actions["config"], "Native record is unhealthy or changes configuration")
                vertices = state.get("vertices", [])
                ids = state.get("node_ids", [])
                require(bool(vertices) and len(vertices) == len(ids) == len(set(ids)), "Invalid recorded node identity")
                require(all(isinstance(v, list) and len(v) == 3 and all(isinstance(n, (int, float)) and
                            math.isfinite(n) for n in v) for v in vertices), "Invalid recorded physical vertices")
                previous_state = state["state_id"]
                count += 1
        require(count == len(steps) + 1, "Native state history must include every accepted step and the initial state")
        summaries.append({"metadata": metadata_path.relative_to(run).as_posix(), "passed": True,
                          "accepted_steps": len(steps), "states": count, "config": actions["config"],
                          "actions_sha256": sha256(actions_path), "states_sha256": sha256(states_path)})
    require(bool(summaries), "Packaged run did not produce a complete native action/state recording")
    if not require_presented:
        return summaries
    presented = list(run.rglob("*presented-states*.jsonl"))
    require(len(presented) == 1, "Expected one UE presented-state history")
    count = 0
    previous_state = -1
    with presented[0].open(encoding="utf-8-sig") as stream:
        for line in stream:
            value = json.loads(line)
            state = value.get("native_state", {})
            require(value.get("record_kind") == "presented_state" and state.get("protocol") == 4 and
                    state.get("healthy") is True and state.get("safety_stops") == 0,
                    "Unhealthy or malformed presented-state record")
            require(state.get("state_id", -1) >= previous_state, "Presented native state identity moved backwards")
            require(bool(value.get("camera", {}).get("view_projection_matrix")), "Presented state lacks actual camera matrix")
            require(value.get("render_topology_revision") == state.get("topology_revision"),
                    "Displayed geometry topology differs from native state")
            previous_state = state["state_id"]
            count += 1
    require(count >= 20, "Presented-state history is incomplete")
    return summaries


def collect_network_recordings(network: dict, report_path: Path) -> tuple[list[tuple[Path, str]], list[dict]]:
    """Curate only takes identified by the final TCP report, never old diagnostic takes."""
    metrics = network.get("metrics", {})
    persisted = network.get("persisted_replay", {})
    require(metrics.get("safety_stops") == 0, "TCP session contains numerical protection events")
    for section, field in ((metrics, "replay_final_rms_m"), (persisted, "max_received_frame_node_rms_m")):
        rms = section.get(field)
        require(isinstance(rms, (float, int)) and math.isfinite(rms) and 0 <= rms <= .0005,
                "TCP saved-input or fresh-process replay exceeds 0.5 mm RMS")
    require(persisted.get("steps", 0) >= 130 and persisted.get("matched_received_steps", 0) >= 20,
            "Fresh-process disk replay lacks meaningful trajectory coverage")
    runtime = report_path.resolve().parent
    evidence, audits = [], []
    for section, state_key, count_key in ((metrics, "snapshot_file", "recorded_steps"),
                                          (persisted, "states_file", "steps")):
        action_name, state_name = section.get("actions_file"), section.get(state_key)
        require(isinstance(action_name, str) and isinstance(state_name, str), "Missing TCP recording paths")
        actions, states = Path(action_name).resolve(), Path(state_name).resolve()
        require(actions.is_relative_to(runtime) and states.is_relative_to(runtime) and
                actions.parent == states.parent and actions.name.endswith("-actions.json"),
                "TCP recording paths must stay within the report's runtime directory")
        stem = actions.name.removesuffix("-actions.json")
        metadata = actions.with_name(stem + "-metadata.json")
        require(states.name == stem + "-states.jsonl", "TCP action/state take identifiers differ")
        for path in (actions, states, metadata):
            no_reparse(path)
        meta = read_json(metadata)
        require(meta.get("actions_file") == actions.name and meta.get("states_file") == states.name,
                "TCP metadata does not identify the reported action/state pair")
        audit = validate_recordings(runtime, [metadata], require_presented=False)[0]
        require(audit["accepted_steps"] == section.get(count_key), "TCP report and recorded action counts differ")
        audits.append(audit)
        evidence.extend((path, "network-sessions/" + path.name) for path in (actions, states, metadata))
    return evidence, audits


def delivery_paths(collision_fix: bool, package: Path | None, baseline: Path | None) -> tuple[Path, Path, Path, str]:
    phase_root = ROOT / "output" / ("Phase4-CollisionFix" if collision_fix else "Phase4")
    package = package or phase_root / "EndoForge"
    no_reparse(package)
    require(package.resolve() != phase_root.resolve() and package.resolve().is_relative_to(phase_root.resolve()),
            f"Destination must be a child of {phase_root}; prior deliveries are preserved")
    baseline = baseline or ROOT / "tmp" / ("phase4-collision-fix" if collision_fix else "phase4") / "preserved-baseline.json"
    archive_name = "EndoForge_Phase4_CollisionFix_Win64.zip" if collision_fix else "EndoForge_Phase4_Win64.zip"
    return phase_root, package.resolve(), baseline, archive_name


def retain_acceptance_checks(current: dict, baseline_report: Path) -> None:
    previous = read_json(baseline_report)
    previous_checks = previous.get("checks", {})
    require(bool(previous_checks) and all(item is True for item in previous_checks.values()),
            f"Invalid preserved acceptance reference: {baseline_report}")
    require(all(current.get("checks", {}).get(name) is True for name in previous_checks),
            f"Collision correction must retain every original acceptance assertion: {baseline_report.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--collision-fix", action="store_true", help="New collision-fix output; preserve original Phase 1–4 deliveries")
    parser.add_argument("--collision-report", type=Path)
    parser.add_argument("--legacy-collision-diagnostic", type=Path,
                        default=ROOT / "tmp/phase4-collision-fix/baseline")
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--physics-report", type=Path, default=ROOT / "Physics/runtime/phase4-physics-test-results.json")
    parser.add_argument("--network-report", type=Path, default=ROOT / "Physics/runtime/phase4-network-test-results.json")
    parser.add_argument("--package-log", type=Path, required=True)
    parser.add_argument("--protocol-directory", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--endurance-flat", type=Path, default=ROOT / "Physics/runtime/phase4-endurance-flat.json")
    parser.add_argument("--endurance-curved", type=Path, default=ROOT / "Physics/runtime/phase4-endurance-curved.json")
    parser.add_argument("--legacy-input-directory", type=Path, required=True)
    parser.add_argument("--legacy-protocol-directory", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    phase_root, package, baseline_path, archive_name = delivery_paths(args.collision_fix, args.package, args.baseline)
    require(args.collision_fix or args.collision_report is None, "Collision evidence requires --collision-fix")
    if args.collision_fix:
        require(args.legacy_protocol_directory is not None, "Collision-fix delivery requires Phase 3 protocol regression")
    require(package.is_dir(), "Assemble the Phase 4 package first")
    for item in package.rglob("*"):
        no_reparse(item)
    run = args.run_directory.resolve()
    require(run.is_dir() and not run.is_relative_to(package), "Keep packaged-run evidence outside the deliverable")
    physics_exe = package / "Physics/LapPhysics.exe"
    game_exe = package / "LapTrainer/Binaries/Win64/LapTrainer.exe"
    for path in (physics_exe, game_exe, package / "StartTrainer.cmd", package / "StartTrainer.ps1",
                 package / "Source/Physics/Phase4Session.h", package / "Source/docs/PHASE4.md",
                 package / "Physics/etc/sofa.ini", package / "Physics/licenses/TIGHT-INCLUSION-MIT.txt",
                 package / "Source/Dependencies/sofa-v26.06.00-source.zip"):
        require(path.is_file(), f"Missing packaged file: {path}")
    for path in (package / "README.md", package / "Source/docs/PHASE4.md"):
        require(path.is_file() and "PHASE4_DOCUMENTATION_PENDING_MODEL_SYNC" not in path.read_text(encoding="utf-8-sig"),
                f"Model documentation must be synchronized before finalization: {path}")
    physics_hash, game_hash = sha256(physics_exe), sha256(game_exe)
    build = read_json(package / "Physics/build-info.json")
    require(build.get("phase") == 4 and build.get("protocol") == 4 and build.get("tested_protocol") == 4,
            "Physics build metadata must describe tested Phase 4 protocol 4")
    require(build.get("executable_sha256", "").lower() == physics_hash, "Physics build metadata hash differs")
    sources = build.get("source_files_sha256", {})
    require("Phase4Session.h" in sources and "Phase4Tests.h" in sources and "Phase3Model.h" in sources and "main.cpp" in sources, "Missing physics source provenance")
    for name, digest in sources.items():
        require(not Path(name).is_absolute() and ".." not in Path(name).parts, f"Invalid source filename: {name}")
        source = package / "Source/Physics" / name
        require(source.is_file() and sha256(source) == digest.lower(), f"Packaged source differs: {source}")
    for name in ("flat.json", "curved.json"):
        source = package / "Source/Physics/configs" / name
        runtime_config = package / "Physics/configs" / name
        require(source.is_file() and runtime_config.is_file() and sha256(source) == sha256(runtime_config),
                f"Native runtime and corresponding-source configurations differ: {name}")
    if args.collision_fix:
        for folder in ("Physics", "Scripts", "docs"):
            shipped_root = package / "Source" / folder
            require(shipped_root.is_dir(), f"Missing corresponding delivery tools: {folder}")
            for shipped in shipped_root.rglob("*"):
                if shipped.is_file():
                    source = ROOT / folder / shipped.relative_to(shipped_root)
                    require(source.is_file() and sha256(source) == sha256(shipped),
                            f"Packaged source/script/document differs from reviewed source: {shipped}")
        require(sha256(package / "README.md") == sha256(ROOT / "Scripts/README-Phase4-CollisionFix.md"),
                "Packaged user instructions differ from reviewed collision-fix source")
    ue_build = read_json(package / "phase4-build-receipt.json")
    require(ue_build.get("phase") == 4 and ue_build.get("game_exe_sha256") == game_hash,
            "UE build receipt belongs to another game executable")
    require(ue_build.get("package_log_sha256") == sha256(args.package_log), "UAT log differs from build receipt")
    validate_source_set(ue_build.get("source_files_sha256"), package)
    preservation = check_preserved(baseline_path, ("Phase1", "Phase2", "Phase3", "Phase4") if args.collision_fix else ("Phase1", "Phase2", "Phase3"))
    legacy_physics_path = ROOT / "Physics/runtime/phase3-physics-test-results.json"
    legacy_network_path = ROOT / "Physics/runtime/phase3-network-test-results.json"
    legacy_physics = report(legacy_physics_path, physics_hash, expected_phase=3)
    legacy_network = report(legacy_network_path, physics_hash, expected_phase=3)
    legacy_input_path = args.legacy_input_directory / "phase3-input-test.json"
    legacy_inputs = report(legacy_input_path, expected_phase=3)
    legacy_receipt_path = args.legacy_input_directory / "integration-result.json"
    legacy_receipt = report(legacy_receipt_path, checks=False, expected_phase=3)
    require(legacy_receipt.get("physics_exe_sha256") == physics_hash and
            legacy_receipt.get("module_sha256") == ue_build.get("editor_module_sha256") and
            legacy_receipt.get("source_files_sha256") == ue_build.get("source_files_sha256"),
            "Phase 3 compatibility input regression uses stale binaries or sources")
    require(legacy_inputs.get("metrics", {}).get("safety_stop_count") == 0 and
            legacy_receipt.get("physics_errors") == 0 and legacy_receipt.get("engine_protocol_or_fatal_errors") == 0,
            "Phase 3 compatibility regression has protection or runtime errors")
    physics = report(args.physics_report, physics_hash)
    network = report(args.network_report, physics_hash)
    collision_audit, collision_evidence, legacy_collision_diagnostic = None, [], None
    supplemental_configuration = None
    if args.collision_fix:
        from verify_phase4_collision import validate_collision_report, collect_legacy_collision_diagnostic
        require(physics.get("checks", {}).get("physical_cut_collision_surface_synced_before_next_step") is True,
                "Collision correction requires immediate post-cut mapped-state regression")
        mapping = physics.get("cut_mapping_audit", {})
        require(type(mapping.get("observed_topology_changes")) is int and mapping["observed_topology_changes"] > 0,
                "Mapped-state regression must observe a real physical topology change")
        mapping_error = mapping.get("max_position_or_velocity_error")
        require(type(mapping_error) in (int, float) and math.isfinite(mapping_error) and 0 <= mapping_error <= 1e-10
                and mapping.get("tolerance") == 1e-10,
                "Physical/collision x, v, xfree or vfree differs after cut and before the next simulation step")
        collision_path = args.collision_report or ROOT / "Physics/runtime/phase4-collision-matrix.json"
        collision_audit, collision_evidence = validate_collision_report(collision_path, physics_hash, sources)
        legacy_collision_diagnostic, diagnostic_evidence = collect_legacy_collision_diagnostic(args.legacy_collision_diagnostic)
        collision_evidence += diagnostic_evidence
        configuration_report = ROOT / "Physics/runtime/phase4-configuration-test-results.json"
        configuration_input = configuration_report.with_name("phase4-configuration-test-input.json")
        supplemental_configuration = report(configuration_report, physics_hash)
        expected_configuration = read_json(ROOT / "Physics/configs/curved.json")
        expected_configuration.update(fixed_rows=2, young_modulus_pa=30000)
        require(supplemental_configuration.get("kind") == "supplemental_configuration" and
                supplemental_configuration.get("config") == expected_configuration == read_json(configuration_input),
                "Supplemental configuration must identify the selected two-row, 30,000 Pa curved specimen")
        require(supplemental_configuration.get("test_script_sha256") ==
                sha256(ROOT / "Physics/test_phase4_configuration.py"),
                "Supplemental configuration test script differs from its receipt")
        expected_configuration_checks = {
            "effective_configuration_matches_file", "two_rows_identified_in_both_layers",
            "modified_configuration_bilateral_grasp", "modified_configuration_transfers_traction",
            "fixed_nodes_remain_fixed_during_manipulation", "released_after_manipulation",
            "all_received_states_finite_and_healthy", "clean_disconnect_exit"}
        require(set(supplemental_configuration["checks"]) == expected_configuration_checks,
                "Supplemental configuration exercise must retain all eight assertions")
        config_metrics = supplemental_configuration.get("metrics", {})
        config_fixed_error = config_metrics.get("max_fixed_node_error_m")
        config_displacement = config_metrics.get("max_displacement_m")
        require(config_metrics.get("fixed_physical_nodes") == 100 and config_metrics.get("safety_stops") == 0 and
                type(config_metrics.get("received_states")) is int and config_metrics["received_states"] >= 200 and
                type(config_metrics.get("gripped_states")) is int and config_metrics["gripped_states"] > 0 and
                type(config_fixed_error) in (int, float) and math.isfinite(config_fixed_error) and 0 <= config_fixed_error < 1e-9 and
                type(config_displacement) in (int, float) and math.isfinite(config_displacement) and config_displacement > .002,
                "Supplemental configuration lacks healthy fixed-row grasp/traction evidence")
        collision_evidence += [(path, "supplemental-configuration/" + path.name) for path in
                               (configuration_report, configuration_input,
                                configuration_report.with_name("phase4-configuration-test.log"))]
        for required in (package / "Source/docs/PHASE4-COLLISION-FIX.md", package / "README.md"):
            require(required.is_file() and "COLLISION_FIX_DOCUMENTATION_PENDING" not in required.read_text(encoding="utf-8-sig"),
                    f"Collision documentation must match the measured final implementation: {required}")
    network_evidence, network_recording_audits = collect_network_recordings(network, args.network_report)
    endurance = {"flat": report(args.endurance_flat, physics_hash),
                 "curved": report(args.endurance_curved, physics_hash)}
    validate_repeats(physics)
    endurance_histories, endurance_audits = [], {}
    for name, path in (("flat", args.endurance_flat), ("curved", args.endurance_curved)):
        history, audit = validate_endurance(endurance[name], name, path)
        endurance_histories.append(history)
        endurance_audits[name] = audit
    inputs = report(run / "phase4-input-test.json")
    if args.collision_fix:
        previous_verification = ROOT / "output/Phase4/EndoForge/Verification"
        for current, previous_name in (
                (physics, "phase4-physics-test-results.json"),
                (network, "phase4-network-test-results.json"),
                (inputs, "phase4-input-test.json"),
                (legacy_physics, "legacy-phase3/phase3-physics-test-results.json"),
                (legacy_network, "legacy-phase3/phase3-network-test-results.json"),
                (legacy_inputs, "legacy-phase3/phase3-input-test.json")):
            retain_acceptance_checks(current, previous_verification / previous_name)
        require(inputs.get("report_version") == 2, "Collision-fix package requires expanded UE input report version 2")
        for name in ("curved_interior_grasp_traction_release", "curved_direct_retreat_reaches_home",
                     "curved_direct_retreat_presented_node_depth_bounded"):
            require(inputs.get("checks", {}).get(name) is True, f"Missing collision-fix UE acceptance: {name}")
        depth = inputs.get("metrics", {}).get("collision_presented_node_depth_max_mm")
        travel = inputs.get("metrics", {}).get("curved_direct_retreat_travel_mm")
        require(isinstance(depth, (int, float)) and math.isfinite(depth) and 0 <= depth <= .15,
                "Presented-state jaw node depth exceeds 0.15 mm or is missing")
        require(isinstance(travel, (int, float)) and math.isfinite(travel) and travel > 20,
                "Curved straight retreat must actually move more than 20 mm")
    require(inputs.get("metrics", {}).get("safety_stop_count") == 0,
            "UE input acceptance must prove the regular exercise had no protection events")
    for metric, maximum in (("max_projection_error_px", 1.0), ("max_render_binding_error_mm", 0.001)):
        value = inputs.get("metrics", {}).get(metric)
        require(isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= maximum,
                f"Missing or excessive input acceptance metric: {metric}")
    receipt = report(run / "phase4-packaged-run.json", checks=False)
    require(receipt.get("run_kind") == "packaged" and receipt.get("game_exit_code") == 0 and receipt.get("native_exit_code") == 0, "Missing packaged acceptance or verified native graceful exit")
    require(receipt.get("physics_exe_sha256") == physics_hash and receipt.get("game_exe_sha256") == game_hash,
            "Packaged acceptance binary hashes differ")
    require(receipt.get("engine_protocol_or_fatal_errors") == 0 and receipt.get("physics_errors") == 0,
            "Packaged run logged runtime errors")
    require(receipt.get("telemetry_safety_stops") == 0, "Packaged run must verify zero numerical protection events")
    game_log = run / "unreal.log"
    require(game_log.is_file() and "LAP_PHASE4_TEST complete passed=1 directory=" in
            game_log.read_text(encoding="utf-8-sig", errors="replace"), "UE did not save a successful test")
    require(args.package_log.is_file() and "BUILD SUCCESSFUL" in
            args.package_log.read_text(encoding="utf-8-sig", errors="replace"), "Missing successful UAT build log")
    screenshots = sorted(path.name for path in run.glob("phase4_*.png"))
    require(len(screenshots) >= (12 if args.collision_fix else 7), "Missing complete Phase 4 screenshot sequence")
    screenshot_dimensions = {name: png_size(run / name) for name in screenshots}
    evidence = [(args.physics_report, "phase4-physics-test-results.json"),
                (args.network_report, "phase4-network-test-results.json"),
                (args.endurance_flat, "phase4-endurance-flat.json"),
                (args.endurance_curved, "phase4-endurance-curved.json"),
                (run / "phase4-input-test.json", "phase4-input-test.json"),
                (run / "phase4-packaged-run.json", "phase4-packaged-run.json"),
                (game_log, "phase4-packaged-unreal.log"), (args.package_log, "phase4-package.log")]
    evidence += [(run / name, name) for name in screenshots]
    evidence += network_evidence
    evidence += collision_evidence
    evidence += [(path, path.name) for path in endurance_histories]
    evidence += [(path, "legacy-phase3/" + path.name) for path in
                 (legacy_physics_path, legacy_network_path, legacy_input_path, legacy_receipt_path)]
    for name in ("unreal.log", "physics.stdout.log", "physics.stderr.log"):
        evidence.append((args.legacy_input_directory / name, "legacy-phase3/" + name))
    evidence += [(path, "legacy-phase3/" + path.name) for path in args.legacy_input_directory.glob("phase3_*.png")]
    legacy_protocol = None
    if args.legacy_protocol_directory:
        legacy_protocol = report(args.legacy_protocol_directory / "protocol-result.json", checks=False, expected_phase=3)
        require(legacy_protocol.get("module_sha256") == ue_build.get("editor_module_sha256"),
                "Optional Phase 3 protocol evidence belongs to another editor module")
        legacy_index = read_json(args.legacy_protocol_directory / "index.json")
        matches = [t for t in legacy_index.get("tests", []) if t.get("fullTestPath") == "EndoForge.Phase3.AtomicTopologyProtocol"]
        require(legacy_index.get("failed") == 0 and len(matches) == 1 and
                matches[0].get("state") == "Success" and matches[0].get("errors") == 0,
                "Optional Phase 3 atomic topology protocol did not pass")
        for name in ("protocol-result.json", "index.json", "unreal.log"):
            evidence.append((args.legacy_protocol_directory / name, "legacy-phase3/protocol-" + name))
    for name in ("physics.stdout.log", "physics.stderr.log", "launcher.stdout.log", "launcher.stderr.log"):
        evidence.append((run / name, "phase4-" + name))
    protocol = None
    if args.protocol_directory:
        protocol = report(args.protocol_directory / "protocol-result.json", checks=False)
        module_hash = protocol.get("module_sha256", "")
        require(len(module_hash) == 64 and all(c in "0123456789abcdef" for c in module_hash.lower()),
                "Editor protocol evidence must identify its tested module SHA-256")
        require(module_hash == ue_build.get("editor_module_sha256"), "Protocol test used another editor module")
        require(protocol.get("source_files_sha256") == ue_build.get("source_files_sha256"),
                "Protocol and post-UAT build source hashes differ")
        index = read_json(args.protocol_directory / "index.json")
        require(index.get("failed") == 0 and index.get("succeeded", 0) + index.get("succeededWithWarnings", 0) == 1,
                "Editor protocol automation did not report exactly one successful test")
        matching = [test for test in index.get("tests", [])
                    if test.get("fullTestPath") == "EndoForge.Phase4.AtomicSnapshotProtocol"]
        require(len(matching) == 1 and matching[0].get("state") == "Success" and matching[0].get("errors") == 0,
                "Missing successful atomic topology protocol test")
        evidence += [(args.protocol_directory / "protocol-result.json", "phase4-editor-protocol-result.json"),
                     (args.protocol_directory / "index.json", "phase4-editor-protocol-index.json")]
    snapshot_paths = []
    for candidate in run.rglob("*.json"):
        if candidate.name in {"phase4-input-test.json", "phase4-packaged-run.json"}:
            continue
        value = json.loads(candidate.read_text(encoding="utf-8-sig"))
        if isinstance(value, dict) and "native_state" in value and ("render_vertices_cm" in value or "render_bindings" in value):
            snapshot_paths.append(candidate)
    require(bool(snapshot_paths), "No independently auditable frozen UE snapshot")
    snapshot_audits = [audit_snapshot(path) for path in snapshot_paths]
    recording_audits = validate_recordings(run)
    require(all(item.get("screenshot") for item in snapshot_audits), "Every frozen snapshot needs its corresponding PNG")
    require(inputs.get("metrics", {}).get("snapshots_saved") == len(snapshot_paths),
            "Frozen snapshot count differs from UE report")
    for path in snapshot_paths:
        relative = path.relative_to(run).as_posix()
        evidence.append((path, relative))
        screenshot = path.parent / (read_json(path).get("screenshot") or read_json(path).get("screenshot_file"))
        evidence.append((screenshot, screenshot.relative_to(run).as_posix()))
    for path in (run / "native-sessions").rglob("*"):
        if path.is_file():
            evidence.append((path, path.relative_to(run).as_posix()))
    for path in run.rglob("*presented-states*.jsonl"):
        evidence.append((path, path.relative_to(run).as_posix()))
    # A snapshot can also be one of the normal acceptance screenshots.
    evidence = list({name: (path, name) for path, name in evidence}.values())
    telemetry = list(run.glob("phase4-session-*.csv"))
    require(len(telemetry) == 1, "Expected exactly one controlled telemetry CSV")
    with telemetry[0].open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) >= 100 and len(rows) == receipt.get("telemetry_samples"),
            "CSV sample count must match the packaged receipt")
    require(all(row.get("healthy") == "1" and row.get("safety_stops") == "0" for row in rows),
            "Raw telemetry contains unhealthy states, missing protection counters, or protection events")
    require(all(row.get("solve_ms") for row in rows), "Telemetry lacks solve durations")
    solve_times = sorted(float(row["solve_ms"]) for row in rows)
    require(all(math.isfinite(value) and value >= 0 for value in solve_times),
            "Telemetry contains invalid solve durations")
    p95 = solve_times[math.ceil(len(solve_times) * 0.95) - 1]
    require(isinstance(receipt.get("telemetry_physics_step_p95_ms"), (int, float)) and
            abs(p95 - receipt["telemetry_physics_step_p95_ms"]) < 1e-6,
            "Raw telemetry timing differs from the packaged receipt")
    evidence += [(path, path.name) for path in telemetry]
    for path, _ in evidence:
        require(path.is_file(), f"Missing evidence: {path}")
    for path in (package / "Physics").rglob("*"):
        if path.is_file():
            require(path.suffix.lower() != ".json" or path.name == "build-info.json" or path.parent.name == "configs", f"Uncurated runtime report: {path}")
            require(path.suffix.lower() != ".log", f"Uncurated runtime log: {path}")
    validation = {"validated": True, "phase": 4, "delivery_variant": "collision-fix" if args.collision_fix else "original", "package": str(package), "physics_exe_sha256": physics_hash,
                  "game_exe_sha256": game_hash, "evidence_files": len(evidence), "screenshots": len(screenshots)}
    if args.validate_only:
        print(json.dumps(validation, ensure_ascii=False, indent=2))
        return
    staging = phase_root / (".verification-staging-" + uuid.uuid4().hex)
    staging.mkdir()
    try:
        for path, name in evidence:
            (staging / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, staging / name)
        summary = {**validation, "assembled_at_utc": datetime.now(timezone.utc).isoformat(),
                   "native_checks": physics["checks"], "network_checks": network["checks"], "input_checks": inputs["checks"],
                   "physics_model": physics.get("model", {}),
                   "physics_metrics": physics.get("metrics", {}), "input_metrics": inputs.get("metrics", {}),
                   "editor_protocol_evidence": protocol,
                   "endurance": endurance, "endurance_history_audits": endurance_audits, "snapshot_audits": snapshot_audits,
                   "recording_audits": recording_audits,
                   "network_recording_audits": network_recording_audits,
                   "collision_matrix_audit": collision_audit,
                   "legacy_collision_diagnostic": legacy_collision_diagnostic,
                   "supplemental_configuration": supplemental_configuration,
                   "phase3_compatibility": {"physics_checks": legacy_physics["checks"],
                       "network_checks": legacy_network["checks"], "input_checks": legacy_inputs["checks"],
                       "receipt": legacy_receipt, "optional_protocol_receipt": legacy_protocol},
                   "previous_phases_preserved": preservation,
                   "telemetry_samples": receipt.get("telemetry_samples"),
                   "telemetry_physics_step_p95_ms": receipt.get("telemetry_physics_step_p95_ms"),
                   "telemetry_timing_context": "Measured local packaged acceptance session without isolated scheduling/workload control; not an isolated performance benchmark or hard real-time guarantee.",
                   "screenshot_dimensions": screenshot_dimensions,
                   "evidence": [{"path": name, "sha256": sha256(staging / name)} for _, name in evidence],
                   "limitations": ["Training membrane, not calibrated biological tissue or validated clinical training.",
                       "Automated UE PlayerController input is not physical mouse/keyboard or clinician usability testing.",
                       "Local Windows machine performance only; no hard real-time or haptic guarantee.",
                       ("See Source/docs/PHASE4-COLLISION-FIX.md for the 19-case range, sampled inter-frame audit and retained exclusions."
                        if args.collision_fix else "See Source/docs/PHASE4.md for specimen, replay, contact metric and dataset preparation boundaries.")]
                       + (["Finite collision matrix and interpolation samples are not arbitrary-motion or continuous-time guarantees; tool-tool, shaft and tissue self-contact remain excluded.",
                           "Old actions can load but exact historical trajectories require their original package/binary; cross-version recomputation can change geometry and forces.",
                           "The retained 0.03 N aggregate contact-load closure feedback threshold is an uncalibrated engineering setting, not clinical grasping force."] if args.collision_fix else [])}
        (staging / "verification-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (staging / "previous-phases-preserved.json").write_text(json.dumps(preservation, indent=2), encoding="utf-8")
        if args.collision_fix:
            (staging / "diagnostics/legacy-collision/README.md").write_text(
                "# 旧版碰撞失败对照（非验收通过证据）\n\n"
                "此处保留原 Phase4 程序的失败复现、动作、接收到的原始状态及实际脚本。"
                f"接收到 {legacy_collision_diagnostic['received_frames']} 条状态；缺失步为 "
                f"{', '.join(map(str, legacy_collision_diagnostic['missing_steps'])) or '无'}。"
                "接收到的离散状态不代表全部内部连续轨迹，不能用来替代新版本验收。"
                "独立几何测量显示旧版节点及三角面穿入超过 0.15 mm。\n\n"
                "`reproduce_phase4_collision_baseline-original.py` 是当时执行复现的原脚本；"
                "当前 `reproduce_phase4_collision_baseline.py --audit-only --outdir .` 可重新审查保存的旧状态，"
                "并依赖同目录的 `audit_phase4_collision_geometry.py`。原执行、重审及输入文件的 SHA-256 记录在 JSON 中。\n\n"
                "修复版通过证据位于 `Verification/collision/`，要求全部规定 case 的每个接受步，不能用此诊断代替。\n",
                encoding="utf-8")
        (staging / "验证记录.md").write_text(
            "# 第四阶段交付验证记录\n\n"
            "本目录保留最终独立打包程序的实际验收记录。原生物理、TCP 协议和 UE 正常输入路径的测试均核对了最终程序 SHA-256。\n\n"
            "- `phase4-physics-test-results.json`：平面／曲面抓持牵拉释放、配置、状态身份与五次动作回放比较。\n"
            "- `phase4-endurance-flat.json`、`phase4-endurance-curved.json` 及对应 `-states.csv`：各600秒模拟时间的连续循环及逐步健康、单元和接触记录。\n"
            "- `phase4-network-test-results.json`：真实本机 TCP、录制／回放控制、身份与错误消息检查。\n"
            "- `phase4-input-test.json`、`phase4-packaged-run.json`：UE 正常输入路径的双试件操作、录制回放、快照和保护次数检查。\n"
            "- `phase4-package.log`：Windows 打包日志。\n"
            "- `phase4_*.png`：平面／曲面的准备、抓持、牵拉、释放、回放等实际画面。\n"
            "- `phase4-snapshot-*.json/png`：冻结的物理状态、显示网格、绑定、相机与对应截图；独立投影审查结果见汇总JSON。\n"
            "- `native-sessions/`、`phase4-presented-states.jsonl`：原生动作与逐步状态、UE实际展示状态。\n"
            "- `network-sessions/`：最终 TCP 测试中明确引用的两组录制，包含断线保存和新进程磁盘回放的动作、完整状态与元数据。\n"
            "- `legacy-phase3/`：当前程序兼容模式的第三阶段物理、TCP和UE输入回归证据。\n"
            f"- `previous-phases-preserved.json`：既有阶段的 {preservation['verified_files']} 个文件及完整文件集合的大小与 SHA256 核验。\n"
            "- `phase4-session-acceptance.csv`：本次运行的受控会话数据。\n\n"
            f"本次会话记录 {receipt.get('telemetry_samples')} 条；物理求解步耗时 P95 为 "
            f"{receipt.get('telemetry_physics_step_p95_ms')} ms。这是本机验收会话的实际测量，未控制独占调度与背景负载，并非独占机器的性能基准或硬实时保证。"
            "具体通过条件、原始测量值与模型边界见 JSON 及 `Source/docs/PHASE4.md`。\n\n"
            "输入测试经过 UE PlayerController 和正常交互代码，不代表实体键鼠手感验收或医生评审。"
            "材料、接触和剪切参数未经真实组织标定；当前结果不能证明临床训练有效性。\n\n"
            f"ZIP 解压到新目录的独立运行测试在压缩包完成后进行，其报告位于 `output/{phase_root.name}/archive-relocation-verification.json`，不写回 ZIP。\n"
            + ("\n修复版额外门槛：`collision/` 保存不同角度、速度、路径及原曲面直线撤回的真实报告和逐步证据；独立审查见 `verification-summary.json` 的 `collision_matrix_audit`。`supplemental-configuration/` 仅验证曲面、固定后两排、杨氏模量 30,000 Pa 这一补充配置的 TCP 抓持／牵拉／释放，不代表任意配置或其600秒耐久已验证。`diagnostics/legacy-collision/` 单独保留旧版预期失败对照（有缺帧，不计为通过证据）。范围与限制见 `Source/docs/PHASE4-COLLISION-FIX.md`。\n" if args.collision_fix else ""),
            encoding="utf-8")
        verify = package / "Verification"
        if verify.exists():
            no_reparse(verify)
            shutil.rmtree(verify)
        staging.replace(verify)
    finally:
        if staging.exists():
            no_reparse(staging)
            shutil.rmtree(staging)
    for path in sorted(package.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        relative = path.relative_to(package)
        disposable = relative.parts[0] != "Verification" and (path.suffix.lower() == ".pdb" or
                     any(part.lower() in ("saved", "logs", "sessions") for part in relative.parts))
        if path.exists() and disposable:
            no_reparse(path)
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    (package / "Logs").mkdir(exist_ok=True)
    files = sorted(path for path in package.rglob("*") if path.is_file() and path.name != "package-manifest.json")
    manifest_path = package / "package-manifest.json"
    manifest_path.write_text(json.dumps([{"path": path.relative_to(package).as_posix(), "bytes": path.stat().st_size,
                           "sha256": sha256(path)} for path in files], ensure_ascii=False, indent=2), encoding="utf-8")
    files.append(manifest_path)
    zip_path = phase_root / archive_name
    temporary = zip_path.with_suffix(".zip.partial")
    no_reparse(zip_path)
    no_reparse(temporary)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=5, allowZip64=True) as archive:
            for path in files:
                archive.write(path, "EndoForge/" + path.relative_to(package).as_posix())
        with zipfile.ZipFile(temporary) as archive:
            invalid = archive.testzip()
            require(invalid is None, f"ZIP CRC failure: {invalid}")
        temporary.replace(zip_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    digest = sha256(zip_path)
    (phase_root / "previous-phases-preserved.json").write_text(json.dumps(preservation, indent=2), encoding="utf-8")
    sidecar = zip_path.with_suffix(".zip.sha256")
    no_reparse(sidecar)
    sidecar.write_text(f"{digest}  {zip_path.name}\n", encoding="ascii")
    print(json.dumps({**validation, "zip": str(zip_path), "sha256": digest, "zip_crc_passed": True,
                      "files": len(files), "zip_bytes": zip_path.stat().st_size}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(f"Phase 4 finalization failed: {error}", file=sys.stderr)
        sys.exit(1)
