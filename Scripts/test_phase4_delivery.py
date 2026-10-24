"""Delivery-gate regression tests using explicitly synthetic, temporary fixtures."""
from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest

from finalize_phase4 import collect_network_recordings, report, validate_endurance, validate_repeats


class DeliveryGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="endoforge-delivery-fixtures-")
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def repeats(self):
        return {"specimens": [{"specimen": name,
            "metrics": {"all_healthy": True, "all_finite": True, "gripped_steps": 100, "max_displacement_m": .004},
            "repeats": [{"repeat": i+1, "completed": True, "same_discrete_events": True,
                         "steps": 360, "max_frame_node_rms_m": .0001} for i in range(5)]}
            for name in ("flat", "curved")]}

    def test_repeatability_requires_actual_grip(self):
        valid = self.repeats()
        validate_repeats(valid)
        bad = copy.deepcopy(valid)
        bad["specimens"][1]["metrics"]["gripped_steps"] = 0
        with self.assertRaises(ValueError):
            validate_repeats(bad)

    def test_repeatability_rejects_nan_and_event_changes(self):
        for field, value in (("max_frame_node_rms_m", float("nan")),
                             ("max_frame_node_rms_m", .000501),
                             ("same_discrete_events", False), ("completed", False)):
            bad = self.repeats()
            bad["specimens"][0]["repeats"][4][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_repeats(bad)

    def test_report_rejects_stale_binary_and_missing_checks(self):
        path = self.root / "synthetic-report.json"
        value = {"phase": 4, "passed": True, "checks": {"gate": True}, "executable_sha256": "a"*64}
        path.write_text(json.dumps(value), encoding="utf-8")
        report(path, "a"*64)
        with self.assertRaises(ValueError):
            report(path, "b"*64)
        value["checks"] = {}
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(ValueError):
            report(path, "a"*64)

    def endurance(self):
        path = self.root / "synthetic-endurance.json"
        history = self.root / "synthetic-endurance-states.csv"
        fields = ["state_id", "simulation_id", "step_index", "time_s", "healthy", "safety_stops", "min_tet_volume_ratio",
                  "min_triangle_area_ratio", "max_displacement_m", "max_sampled_penetration_m", "step_ms", "grasping"]
        with history.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(fields)
            for step in range(1, 18001):
                writer.writerow([step, 1, step, step/30, 1, 0, .8, .8, .004, .00002, 20,
                                 int(45 <= (step-1) % 300 < 180)])
        value = {"kind": "continuous_endurance", "specimen": "flat",
                 "cycles": [{"gripped": True, "safety_stops": 0} for _ in range(60)],
                 "metrics": {"all_healthy": True, "all_finite": True, "safety_stops": 0,
                     "reset_count_during_test": 0, "accepted_steps": 18000, "simulated_seconds": 600,
                     "cycles_with_grip": 60, "max_sampled_penetration_m": .00002,
                     "sampled_penetration_tolerance_m": .00015}}
        return value, path, history

    def test_endurance_audits_raw_history_instead_of_summary_only(self):
        value, path, history = self.endurance()
        _, audit = validate_endurance(value, "flat", path)
        self.assertEqual(audit["rows"], 18000)
        lines = history.read_text(encoding="utf-8").splitlines()
        lines[901] = lines[900]  # Stale state while the summary still claims success.
        history.write_text("\n".join(lines)+"\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_endurance(value, "flat", path)

    def test_endurance_rejects_short_duration_and_protection(self):
        value, path, _ = self.endurance()
        for field, changed in (("simulated_seconds", 599), ("safety_stops", 1),
                               ("reset_count_during_test", 1), ("all_finite", False)):
            bad = copy.deepcopy(value)
            bad["metrics"][field] = changed
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_endurance(bad, "flat", path)

    def test_endurance_checks_traction_and_release_in_every_cycle(self):
        value, path, history = self.endurance()
        with history.open(encoding="utf-8", newline="") as stream:
            original = list(csv.DictReader(stream))
        for scenario in ("lost_lift_grip", "late_release_grip", "no_deformation_while_holding"):
            rows = copy.deepcopy(original)
            for row in rows:
                cycle, phase = divmod(int(row["step_index"])-1, 300)
                if cycle == 37 and 90 <= phase <= 179:
                    if scenario == "lost_lift_grip":
                        row["grasping"] = "0"
                    if scenario == "no_deformation_while_holding":
                        row["max_displacement_m"] = ".001"
                if scenario == "late_release_grip" and cycle == 37 and phase == 250:
                    row["grasping"] = "1"
            with history.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            with self.subTest(scenario=scenario), self.assertRaises(ValueError):
                validate_endurance(value, "flat", path)

    def test_network_evidence_ignores_stale_takes_and_rejects_bad_identity(self):
        session = self.root / "sessions"
        session.mkdir()
        for name in ("selected-a", "selected-b"):
            actions = {"schema": "endoforge.actions.v1", "dt_s": 1/30,
                       "config": {"name": "synthetic-fixture"}, "steps": [{} for _ in range(130)]}
            metadata = {"schema": "endoforge.session.v1", "actions_file": name + "-actions.json",
                        "states_file": name + "-states.jsonl", "config": actions["config"],
                        "accepted_steps": 130, "duration_s": 130/30, "initial_state_included": True}
            (session / (name + "-actions.json")).write_text(json.dumps(actions), encoding="utf-8")
            (session / (name + "-metadata.json")).write_text(json.dumps(metadata), encoding="utf-8")
            with (session / (name + "-states.jsonl")).open("w", encoding="utf-8") as stream:
                for step in range(131):
                    stream.write(json.dumps({"schema": "endoforge.physics-state.v1", "protocol": 4,
                        "simulation_id": 3, "state_id": step, "session": {"step_index": step},
                        "time": step/30, "healthy": True, "safety_stops": 0, "config": actions["config"],
                        "vertices": [[0., 0., 0.]], "node_ids": [0]}) + "\n")
        (session / "stale-diagnostic-actions.json").write_text("not part of evidence", encoding="utf-8")
        network = {"metrics": {"safety_stops": 0, "replay_final_rms_m": 0., "recorded_steps": 130,
            "actions_file": str(session / "selected-a-actions.json"),
            "snapshot_file": str(session / "selected-a-states.jsonl")},
            "persisted_replay": {"steps": 130, "matched_received_steps": 130, "max_received_frame_node_rms_m": 0.,
            "actions_file": str(session / "selected-b-actions.json"),
            "states_file": str(session / "selected-b-states.jsonl")}}
        report_path = self.root / "tcp-report.json"
        evidence, audits = collect_network_recordings(network, report_path)
        self.assertEqual(len(evidence), 6)
        self.assertEqual(len(audits), 2)
        self.assertTrue(all("stale" not in name for _, name in evidence))
        bad = copy.deepcopy(network)
        bad["persisted_replay"]["steps"] = 131
        with self.assertRaises(ValueError):
            collect_network_recordings(bad, report_path)
        bad = copy.deepcopy(network)
        bad["metrics"]["actions_file"] = str(self.root.parent / "external-actions.json")
        with self.assertRaises(ValueError):
            collect_network_recordings(bad, report_path)
        path = session / "selected-b-states.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        lines[50] = lines[49]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            collect_network_recordings(network, report_path)


if __name__ == "__main__":
    unittest.main()
