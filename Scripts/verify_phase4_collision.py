"""Delivery audit for collision matrix coverage, raw histories and provenance.

The geometric depth algorithm lives in audit_phase4_collision_geometry.py;
this module verifies its evidence chain and independently audits motion/state
history. Neither a success flag nor a filtered matrix can pass on its own.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from finalize_phase4 import ROOT, no_reparse, read_json, require, sha256


CASE_SPECS = {"curved_straight_regression": ("curved", "legacy_straight", 90., .018, 0., True)}
for _shape in ("flat", "curved"):
    for _suffix, _path, _roll, _speed, _azimuth, _grip in (
            ("straight_90_fast", "straight", 90., .018, 0., True),
            ("diagonal_75_slow", "diagonal", 75., .006, -30., False),
            ("elbow_105_medium", "elbow", 105., .012, 30., False),
            ("tangent_60_fast", "tangent", 60., .018, -30., False),
            ("reverse_120_medium", "reverse", 120., .012, 30., False),
            ("vertical_90_slow", "vertical", 90., .006, 0., True)):
        CASE_SPECS[_shape + "_" + _suffix] = (_shape, _path, _roll, _speed, _azimuth, _grip)
    for _suffix, _speed in (("slow", .006), ("medium", .012)):
        CASE_SPECS[_shape + "_straight_90_" + _suffix] = (_shape, "straight", 90., _speed, 0., True)
for _side, _azimuth in (("left", -30.), ("right", 30.)):
    CASE_SPECS["curved_straight_90_approach_" + _side] = ("curved", "straight", 90., .018, _azimuth, True)


def number(value, label: str) -> float:
    require(type(value) in (int, float) and math.isfinite(value), f"Non-finite or missing {label}")
    return float(value)


def vec(value, label: str) -> list[float]:
    require(isinstance(value, list) and len(value) == 3, f"Expected 3-vector: {label}")
    return [number(item, label) for item in value]


def same(actual: float, reported, label: str, tolerance=1e-8) -> None:
    require(abs(actual - number(reported, label)) <= tolerance, f"Raw collision history differs from {label}")


def finite_tree(value) -> None:
    if isinstance(value, dict):
        for item in value.values():
            finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            finite_tree(item)
    elif type(value) in (int, float):
        require(math.isfinite(value), "Collision history contains a non-finite number")


def audit_trajectory(path: Path, case: dict) -> dict:
    """Recompute state/motion metrics from every recorded frame, including failures."""
    no_reparse(path)
    with path.open(encoding="utf-8-sig") as stream:
        header = json.loads(next(stream))
        require(header.get("type") == "mesh" and header.get("case_id") == case["id"], "Collision mesh header mismatch")
        finite_tree(header)
        dt = number(header.get("dt_s"), "dt_s")
        same(dt, 1/30, "fixed simulation timestep")
        half = vec(header.get("jaw_half_extents_m"), "jaw half-extents")
        for actual, expected in zip(half, (.00725, .00125, .0007)):
            same(actual, expected, "physical jaw half-extents", 1e-12)
        rest = header.get("rest_vertices", [])
        require(len(rest) >= 4 and bool(header.get("triangles")), "Collision history has no physical surface")
        for point in rest:
            vec(point, "rest vertex")
        for face in header["triangles"]:
            require(len(face) == 3 and all(type(i) is int and 0 <= i < len(rest) for i in face), "Invalid collision triangle")
        frames = 0
        travel = node_peak = surface_peak = displacement = actual_lift = 0.
        min_volume = min_area = 1.
        contacts = grips = traction_grips = slips = 0
        previous_tip = traction_start = final_command = None
        start_time = final_time = 0.
        phases = set()
        regression_retreat_commands = []
        regression_retreat_tips = []
        regression_retreat_start = None
        previous_command = None
        requested_speed_peak = actual_speed_peak = max_roll_error = 0.
        for line in stream:
            require(bool(line.strip()), "Blank/missing collision history frame")
            frame = json.loads(line)
            finite_tree(frame)
            require(frame.get("type") == "collision_frame" and frame.get("frame") == frames - 1
                    and frame.get("step_index") == frames, "Collision frames are stale, skipped or out of order")
            require(frame.get("healthy") is True and frame.get("safety_stops") == 0, "Collision history has unhealthy/protected states")
            final_time = number(frame.get("time_s"), "time_s")
            if frames == 0:
                start_time = final_time
            same(final_time - start_time, frames * dt, "simulation step time", 1e-6)
            vertices = frame.get("vertices", [])
            require(len(vertices) == len(rest), "Collision history topology count changed")
            for point in vertices:
                vec(point, "current vertex")
            tip = vec(frame.get("actual_tip_m"), "actual tool tip")
            final_command = vec(frame.get("command_tip_m"), "command tool tip")
            same(number(frame.get("command_roll_deg"), "command roll"), case["roll_deg"], "case roll")
            tools = frame.get("tools", [])
            require(len(tools) == 2, "Collision history must contain both instruments")
            require(tip == tools[0].get("tip_m"), "Actual collision tip differs from tool state")
            for tool in tools:
                vec(tool.get("tip_m"), "tool tip")
                require(type(tool.get("grasping")) is bool and isinstance(tool.get("jaw_poses"), list)
                        and len(tool["jaw_poses"]) == 2, "Incomplete grasp/jaw state")
                for pose in tool["jaw_poses"]:
                    for key in ("center_m", "axis", "side", "normal"):
                        vec(pose.get(key), "jaw " + key)
            volume = number(frame.get("min_tet_volume_ratio"), "tetrahedron volume")
            area = number(frame.get("min_triangle_area_ratio"), "triangle area")
            require(volume > 0 and area > 0, "Invalid elements in collision history")
            phase = frame.get("phase")
            phases.add(phase)
            if frames:
                travel += math.dist(tip, previous_tip)
                actual_speed_peak = max(actual_speed_peak, math.dist(tip, previous_tip) / dt)
                if phase in ("close", "traction", "traction_hold"):
                    roll_error = abs(number(tools[0].get("roll_deg"), "actual roll") - case["roll_deg"])
                    max_roll_error = max(max_roll_error, roll_error)
                    require(roll_error <= .5, "Collision case requested a roll that the actual instrument did not reach")
                if case["id"] != "curved_straight_regression" and phase in (
                        "traction", "straight_withdraw", "final_withdraw", "elbow_turn", "tangent_withdraw",
                        "reverse_out", "reverse_back", "vertical_withdraw"):
                    requested_speed = math.dist(final_command, previous_command) / dt
                    require(requested_speed <= case["command_speed_m_s"] + 1e-8, "Collision command exceeded declared motion speed")
                    requested_speed_peak = max(requested_speed_peak, requested_speed)
                node_peak = max(node_peak, *(number(t.get("penetration_m"), "native node depth") for t in tools))
                surface_peak = max(surface_peak, number(frame.get("surface_depth_m"), "native surface depth"))
                displacement = max(displacement, number(frame.get("max_displacement_m"), "maximum deformation"))
                min_volume, min_area = min(min_volume, volume), min(min_area, area)
                contacts += tools[0].get("contact_count", 0) > 0
                grips += tools[0]["grasping"]
                slips += tools[0].get("grip_state") == "slipping"
                if phase == "close":
                    traction_start = tip
                if phase in ("traction", "traction_hold"):
                    require(traction_start is not None, "Traction without preceding closure")
                    actual_lift = max(actual_lift, tip[2] - traction_start[2])
                    traction_grips += tools[0]["grasping"]
                if phase in ("straight_withdraw", "withdraw_settle"):
                    require(tools[0]["grasping"] is False, "Hidden grip after release")
                if case["id"] == "curved_straight_regression" and phase == "straight_withdraw":
                    if regression_retreat_start is None:
                        regression_retreat_start = previous_tip
                    regression_retreat_commands.append(final_command)
                    regression_retreat_tips.append(tip)
            previous_tip = tip
            previous_command = final_command
            frames += 1
    require(frames >= 201 and frames == case.get("frame_count"), "Collision history is short or count differs")
    require({"initial", "approach", "close", "traction", "release"}.issubset(phases), "Collision exercise is incomplete")
    require(tools[0]["grasping"] is False, "Final collision state retains a hidden grasp")
    endpoint = math.dist(previous_tip, final_command)
    require(travel >= .025 and endpoint <= .0015 and actual_lift >= .0025,
            "Collision case avoided interaction by stalling, failing to lift or missing its endpoint")
    require(contacts > 0 and 0 <= node_peak <= .00015 and 0 <= surface_peak <= .00015,
            "Collision raw contact/depth gate failed")
    if case["expected_grip"]:
        require(grips > 0 and traction_grips > 0 and displacement > .002, "Required grip/traction did not occur")
    if case["id"] == "curved_straight_regression":
        require(len(regression_retreat_commands) >= 60 and
                all(math.dist(point, [-.022, -.047, .006]) < 1e-10 for point in regression_retreat_commands),
                "Original curved retreat must target home directly; a raised detour cannot replace the regression")
        route = [end - start for start, end in zip(regression_retreat_start, [-.022, -.047, .006])]
        route_length_squared = sum(value*value for value in route)
        require(route_length_squared > .025**2, "Original curved direct retreat is too short")
        progress, max_deviation = -1e-8, 0.
        for point in regression_retreat_tips:
            offset = [actual-start for actual, start in zip(point, regression_retreat_start)]
            next_progress = sum(a*b for a,b in zip(offset, route))/route_length_squared
            deviation = math.sqrt(sum((a-next_progress*b)**2 for a,b in zip(offset, route)))
            require(next_progress >= progress - 1e-8 and 0 <= next_progress <= 1+1e-8 and deviation <= .0001,
                    "Actual curved withdrawal backtracked or detoured off the original direct line")
            progress, max_deviation = next_progress, max(max_deviation, deviation)
    else:
        require(requested_speed_peak >= .9*case["command_speed_m_s"], "Collision speed variant never reached its declared command rate")
        max_deviation = None
    metrics = {"accepted_steps": frames-1, "simulated_seconds": final_time-start_time,
               "max_node_depth_m": node_peak, "max_surface_depth_m": surface_peak,
               "max_displacement_m": displacement, "min_tet_volume_ratio": min_volume,
               "min_triangle_area_ratio": min_area, "tool_travel_m": travel,
               "withdrawal_endpoint_error_m": endpoint, "actual_traction_lift_m": actual_lift,
               "contact_steps": contacts, "gripped_steps": grips, "traction_gripped_steps": traction_grips,
               "slip_steps": slips, "safety_stops": 0}
    for name, value in metrics.items():
        same(value, case.get("metrics", {}).get(name), name)
    return {"id": case["id"], "frames": frames, "trajectory_sha256": sha256(path), "metrics": metrics,
            "actual_roll_error_max_deg": max_roll_error, "requested_motion_speed_max_m_s": requested_speed_peak,
            "actual_motion_speed_max_m_s": actual_speed_peak, "direct_withdrawal_max_line_deviation_m": max_deviation}


def validate_collision_report(path: Path, executable_hash: str, source_hashes: dict) -> tuple[dict, list[tuple[Path, str]]]:
    matrix = read_json(path)
    require(matrix.get("schema") == "endoforge.collision.matrix.v1" and matrix.get("kind") == "collision_matrix_v1"
            and matrix.get("phase") == 4 and matrix.get("passed") is True and not matrix.get("filter"),
            "A complete successful unfiltered collision matrix is required")
    require(matrix.get("experimental") is not True and not matrix.get("failure") and not matrix.get("failures"),
            "Experimental or unresolved collision evidence cannot be delivered as passing acceptance")
    require(matrix.get("executable_sha256") == executable_hash and matrix.get("source_files_sha256") == source_hashes
            and matrix.get("native_exit_code") == 0, "Collision matrix binary/source provenance or process exit differs")
    for name, expected in (("node_depth_m", .00015), ("surface_depth_m", .00015),
                           ("endpoint_error_m", .0015), ("minimum_tool_travel_m", .025)):
        same(number(matrix.get("thresholds", {}).get(name), name), expected, name, 1e-12)
    cases = matrix.get("cases", [])
    require(len(cases) == len(CASE_SPECS) and {c.get("id") for c in cases} == set(CASE_SPECS),
            "Collision matrix must cover exactly the prescribed 19 cases")
    evidence = [(path, "collision/phase4-collision-matrix.json")]
    trajectories, audits = {}, []
    for case in cases:
        shape, route, roll, speed, azimuth, grip = CASE_SPECS[case["id"]]
        require((case.get("specimen"), case.get("path"), case.get("expected_grip")) == (shape, route, grip),
                "Collision case metadata differs from the prescribed exercise")
        for key, expected in (("roll_deg", roll), ("command_speed_m_s", speed), ("approach_azimuth_deg", azimuth)):
            same(number(case.get(key), key), expected, key, 1e-12)
        checks = case.get("checks", {})
        require(case.get("passed") is True and len(checks) >= 12 and all(v is True for v in checks.values()),
                "Collision case has absent or failing assertions")
        relative = Path(case.get("trajectory_file", ""))
        require(relative.name == case["id"] + ".jsonl" and len(relative.parts) == 1,
                "Collision trajectory must be its case-named local file")
        trajectory = path.parent / relative
        audit = audit_trajectory(trajectory, case)
        audits.append(audit)
        trajectories[case["id"]] = audit["trajectory_sha256"]
        evidence.append((trajectory, "collision/" + relative.name))
    geometry_path = path.with_name("collision-geometry-audit.json")
    geometry = read_json(geometry_path)
    # This contract is kept explicit with the independent audit implementation;
    # provenance is necessary because a stale successful audit cannot bless new frames.
    require(geometry.get("schema") == "endoforge.collision.geometry-audit.v1" and geometry.get("passed") is True,
            "Independent surface/swept geometry audit failed")
    require(geometry.get("matrix_sha256") == sha256(path), "Geometry audit belongs to a different matrix")
    geometry_cases = geometry.get("cases", [])
    require(len(geometry_cases) == len(CASE_SPECS) and {item.get("id") for item in geometry_cases} == set(CASE_SPECS),
            "Independent geometry audit is incomplete")
    require({item["id"]: item.get("trajectory_sha256") for item in geometry_cases} == trajectories,
            "Geometry audit belongs to different trajectories")
    for key in ("node_tolerance_m", "surface_tolerance_m"):
        same(number(geometry.get(key), key), .00015, key, 1e-12)
    samples = geometry.get("swept_samples_between_outputs")
    require(type(samples) is int and samples >= 3, "At least three inter-frame geometry samples are required")
    raw_by_id = {item["id"]: item for item in audits}
    for item in geometry_cases:
        require(item.get("passed") is True and len(item.get("checks", {})) >= 7 and
                all(value is True for value in item["checks"].values()), "Independent geometry case has failures")
        raw = raw_by_id[item["id"]]
        require(item.get("frame_count") == raw["frames"], "Geometry audit frame count differs from raw history")
        metrics = item.get("metrics", {})
        for key in ("max_node_depth_m", "max_surface_depth_m", "max_sampled_swept_node_depth_m", "max_sampled_swept_surface_depth_m"):
            require(0 <= number(metrics.get(key), key) <= .00015, "Independent node/surface depth exceeds 0.15 mm")
        require(0 <= number(metrics.get("max_native_surface_metric_error_m"), "native surface error") <= 5e-8,
                "Native and independent triangle geometry measurements differ")
        require(metrics.get("swept_sample_count") == samples * (raw["frames"] - 1), "Missing sampled sweep frames")
        same(raw["metrics"]["tool_travel_m"], metrics.get("actual_tool_travel_m"), "independent actual tool travel")
    audit_script = Path(__file__).with_name("audit_phase4_collision_geometry.py")
    require(geometry.get("audit_script_sha256") == sha256(audit_script), "Geometry audit implementation changed")
    require(geometry.get("test_header_sha256") == source_hashes.get("Phase4CollisionTests.h"),
            "Geometry audit case implementation differs from the compiled tests")
    evidence.append((geometry_path, "collision/" + geometry_path.name))
    return {"passed": True, "case_count": len(audits), "raw_history_audits": audits,
            "independent_geometry_audit": geometry, "matrix_sha256": sha256(path)}, evidence


def collect_legacy_collision_diagnostic(directory: Path) -> tuple[dict, list[tuple[Path, str]]]:
    """Keep the old observed failure auditable, explicitly outside pass evidence."""
    reproduction_path = directory / "baseline-reproduction.json"
    geometry_path = directory / "baseline-independent-geometry.json"
    reproduction, geometry = read_json(reproduction_path), read_json(geometry_path)
    old_executable = ROOT / "output/Phase4/EndoForge/Physics/LapPhysics.exe"
    old_build = read_json(old_executable.with_name("build-info.json"))
    old_hash = sha256(old_executable)
    require(old_build.get("executable_sha256") == old_hash == reproduction.get("executable_sha256") == geometry.get("executable_sha256"),
            "Failure diagnostic must identify the preserved old Phase 4 executable")
    require(reproduction.get("returncode") == 0 and reproduction.get("regression_reproduced") is True and
            geometry.get("expected_failure") is True and geometry.get("regression_reproduced") is True,
            "Old comparison must be an explicitly labeled observed failure")
    raw = directory / "baseline-received-states.jsonl"
    actions = directory / "baseline-sessions/baseline-actions.json"
    original_driver = directory / "reproduce_phase4_collision_baseline-original.py"
    current_driver = Path(__file__).with_name("reproduce_phase4_collision_baseline.py")
    geometry_script = Path(__file__).with_name("audit_phase4_collision_geometry.py")
    require(sha256(raw) == geometry.get("raw_sha256") and sha256(actions) == geometry.get("actions_sha256"),
            "Old failure diagnostic raw inputs or states differ")
    require(sha256(original_driver) == reproduction.get("script_sha256") and
            sha256(current_driver) == geometry.get("driver_script_sha256") and
            sha256(geometry_script) == geometry.get("audit_script_sha256"),
            "Old failure diagnostic must retain the actual reproduction and audit implementations")
    indices = []
    with raw.open(encoding="utf-8-sig") as stream:
        for line in stream:
            frame = json.loads(line)
            finite_tree(frame)
            index = frame.get("session", {}).get("step_index")
            require(type(index) is int and 1 <= index <= 330 and (not indices or index > indices[-1]),
                    "Old diagnostic states are malformed or out of order")
            require(frame.get("healthy") is True and frame.get("safety_stops") == 0,
                    "Old comparison unexpectedly contains numerical protection events")
            indices.append(index)
    missing = [index for index in range(1, 331) if index not in indices]
    require(indices == reproduction.get("received_steps") and len(indices) == geometry.get("received_frames")
            and missing == reproduction.get("missing_steps") == geometry.get("missing_steps"),
            "Old diagnostic must disclose every missing received state")
    require(len(indices) >= 300 and number(geometry.get("max_node_depth_m"), "old node depth") > .00015 and
            number(geometry.get("max_surface_depth_m"), "old surface depth") > .00015,
            "Old diagnostic did not demonstrate the observed contact defect")
    prefix = "diagnostics/legacy-collision/"
    files = [(reproduction_path, prefix + reproduction_path.name), (geometry_path, prefix + geometry_path.name),
             (raw, prefix + raw.name), (actions, prefix + "baseline-sessions/" + actions.name),
             (original_driver, prefix + original_driver.name), (current_driver, prefix + current_driver.name),
             (geometry_script, prefix + geometry_script.name), (directory / "baseline.log", prefix + "baseline.log")]
    return {"diagnostic_only": True, "expected_failure": True, "executable_sha256": old_hash,
            "received_frames": len(indices), "missing_steps": missing, "geometry": geometry,
            "scope": "Observed failure of preserved old release; incomplete received-state history is not new acceptance evidence."}, files
