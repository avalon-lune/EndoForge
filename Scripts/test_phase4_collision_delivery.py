"""Synthetic delivery guard tests; these are not physical acceptance evidence."""
from __future__ import annotations

import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import finalize_phase4 as delivery
from verify_phase4_collision import audit_trajectory


class CollisionDeliveryGuardTests(unittest.TestCase):
    def test_collision_destination_cannot_touch_original_phase4(self):
        phase_root, package, baseline, archive = delivery.delivery_paths(True, None, None)
        self.assertEqual(phase_root, delivery.ROOT / "output/Phase4-CollisionFix")
        self.assertEqual(package, phase_root / "EndoForge")
        self.assertEqual(baseline, delivery.ROOT / "tmp/phase4-collision-fix/preserved-baseline.json")
        self.assertEqual(archive, "EndoForge_Phase4_CollisionFix_Win64.zip")
        for unsafe in (delivery.ROOT / "output/Phase4/EndoForge", phase_root,
                       phase_root / "../Phase4/EndoForge", delivery.ROOT / "tmp/EndoForge"):
            with self.subTest(path=unsafe), self.assertRaises(ValueError):
                delivery.delivery_paths(True, unsafe, None)

    def test_original_default_remains_separate(self):
        phase_root, package, _, archive = delivery.delivery_paths(False, None, None)
        self.assertEqual(phase_root, delivery.ROOT / "output/Phase4")
        self.assertEqual(package, phase_root / "EndoForge")
        self.assertEqual(archive, "EndoForge_Phase4_Win64.zip")

    def test_correction_cannot_drop_original_acceptance_checks(self):
        with tempfile.TemporaryDirectory(prefix="endoforge-acceptance-fixture-") as directory:
            path = Path(directory) / "baseline-report.json"
            path.write_text(json.dumps({"checks": {"grasp": True, "cut": True}}), encoding="utf-8")
            delivery.retain_acceptance_checks({"checks": {"grasp": True, "cut": True, "new": True}}, path)
            for checks in ({"grasp": True}, {"grasp": True, "cut": False}):
                with self.assertRaises(ValueError):
                    delivery.retain_acceptance_checks({"checks": checks}, path)

    def test_preservation_includes_four_phases_and_exact_membership(self):
        with tempfile.TemporaryDirectory(prefix="endoforge-preservation-fixture-") as directory:
            root = Path(directory)
            phases = tuple(f"Phase{i}" for i in range(1, 5))
            entries = []
            for phase in phases:
                path = root / "output" / phase / "synthetic.bin"
                path.parent.mkdir(parents=True)
                path.write_bytes(phase.encode("ascii"))
                entries.append({"path": path.relative_to(root).as_posix(), "size": path.stat().st_size,
                                "sha256": delivery.sha256(path)})
            baseline = root / "baseline.json"
            baseline.write_text(json.dumps({"files": entries}), encoding="utf-8")
            with patch.object(delivery, "ROOT", root):
                self.assertEqual(delivery.check_preserved(baseline, phases)["verified_files"], 4)
                changed = root / "output/Phase4/synthetic.bin"
                changed.write_bytes(b"changed")
                with self.assertRaises(ValueError):
                    delivery.check_preserved(baseline, phases)
                changed.write_bytes(b"Phase4")
                added = root / "output/Phase4/unexpected.bin"
                added.write_bytes(b"new")
                with self.assertRaises(ValueError):
                    delivery.check_preserved(baseline, phases)
                added.unlink()
                changed.unlink()
                with self.assertRaises(ValueError):
                    delivery.check_preserved(baseline, phases)


class CollisionHistoryGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="endoforge-collision-synthetic-")
        self.path = Path(self.temporary.name) / "flat_straight_90_fast.jsonl"
        self.header = {"type": "mesh", "case_id": "flat_straight_90_fast", "dt_s": 1/30,
                       "rest_vertices": [[0,0,0], [.005,0,0], [0,.005,0], [0,0,.001]],
                       "triangles": [[0,1,2]], "jaw_half_extents_m": [.00725,.00125,.0007]}
        home, target = [-.022,-.047,.006], [-.022,-.015,.006]
        pose = {"center_m": [0,0,0], "axis": [1,0,0], "side": [0,1,0], "normal": [0,0,1]}
        self.frames = []
        for step in range(201):
            tip = target.copy()
            if step == 0:
                phase, tip = "initial", home.copy()
            elif step <= 30:
                phase = "approach"
                tip = [home[a] + (target[a]-home[a])*step/30 for a in range(3)]
            elif step <= 60:
                phase = "close"
            elif step <= 90:
                phase = "traction"
                tip[2] += .004*(step-60)/30
            elif step <= 120:
                phase = "release"
                tip[2] += .004
            else:
                phase = "straight_withdraw"
                lifted = [target[0], target[1], target[2]+.004]
                tip = [lifted[a]+(home[a]-lifted[a])*(step-120)/80 for a in range(3)]
            grasp = phase in ("close", "traction")
            tool = {"tip_m": tip, "grasping": grasp, "jaw_poses": [pose,pose], "penetration_m": .00002,
                    "contact_count": int(step > 0), "grip_state": "holding" if grasp else "open", "roll_deg": 90}
            self.frames.append({"type": "collision_frame", "frame": step-1, "step_index": step,
                "time_s": step/30, "phase": phase, "command_tip_m": tip, "actual_tip_m": tip,
                "command_roll_deg": 90, "vertices": self.header["rest_vertices"], "tools": [tool,tool],
                "healthy": True, "safety_stops": 0, "min_tet_volume_ratio": .8,
                "min_triangle_area_ratio": .8, "surface_depth_m": .00003, "max_displacement_m": .004})
        travel = sum(math.dist(a["actual_tip_m"], b["actual_tip_m"]) for a,b in zip(self.frames,self.frames[1:]))
        self.case = {"id": self.header["case_id"], "frame_count": 201, "roll_deg": 90, "expected_grip": True,
            "command_speed_m_s": .0121, # Synthetic fixture speed, not a real matrix exercise.
            "metrics": {"accepted_steps": 200, "simulated_seconds": 200/30, "max_node_depth_m": .00002,
                "max_surface_depth_m": .00003, "max_displacement_m": .004, "min_tet_volume_ratio": .8,
                "min_triangle_area_ratio": .8, "tool_travel_m": travel, "withdrawal_endpoint_error_m": 0.,
                "actual_traction_lift_m": .004, "contact_steps": 200, "gripped_steps": 60,
                "traction_gripped_steps": 30, "slip_steps": 0, "safety_stops": 0}}

    def tearDown(self):
        self.temporary.cleanup()

    def write_history(self):
        self.path.write_text("\n".join(json.dumps(item) for item in [self.header, *self.frames])+"\n", encoding="utf-8")

    def test_complete_history_recomputes_motion_and_contact_metrics(self):
        self.write_history()
        result = audit_trajectory(self.path, self.case)
        self.assertEqual(result["frames"], 201)
        self.assertEqual(result["metrics"]["traction_gripped_steps"], 30)

    def test_failed_late_frame_cannot_hide_in_passing_summary(self):
        self.frames[-2]["safety_stops"] = 1
        self.write_history()
        with self.assertRaises(ValueError):
            audit_trajectory(self.path, self.case)

    def test_summary_cannot_change_raw_trajectory_statistics(self):
        self.write_history()
        self.case["metrics"]["tool_travel_m"] += .01
        with self.assertRaises(ValueError):
            audit_trajectory(self.path, self.case)

    def test_requested_angle_does_not_substitute_for_actual_angle(self):
        self.frames[65]["tools"][0]["roll_deg"] = 75
        self.write_history()
        with self.assertRaisesRegex(ValueError, "actual instrument did not reach"):
            audit_trajectory(self.path, self.case)

    def test_declared_speed_requires_the_corresponding_command_motion(self):
        self.write_history()
        for speed in (.006, .018):
            self.case["command_speed_m_s"] = speed
            with self.subTest(speed=speed), self.assertRaises(ValueError):
                audit_trajectory(self.path, self.case)

    def test_direct_home_command_cannot_hide_an_actual_detour(self):
        self.case["id"] = self.header["case_id"] = "curved_straight_regression"
        for frame in self.frames:
            if frame["phase"] == "straight_withdraw":
                frame["command_tip_m"] = [-.022,-.047,.006]
        self.write_history()
        audit_trajectory(self.path, self.case)
        self.frames[150]["actual_tip_m"][2] += .0002
        self.write_history()
        with self.assertRaisesRegex(ValueError, "backtracked or detoured"):
            audit_trajectory(self.path, self.case)


if __name__ == "__main__":
    unittest.main()
