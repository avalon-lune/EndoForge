"""Compare every physical value emitted by the offline Phase6 replay diagnostic."""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def rows(path, recorded=False):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            value = json.loads(line)
            if recorded:
                step = value["session"]["step_index"]
                if step == 0:
                    continue
                value = {
                    "step": step, "time_s": value["time"],
                    "vertices": value["vertices"], "tools": value["tools"],
                    "healthy": value["healthy"], "safety_stops": value["safety_stops"],
                    "minimum_area_ratio": value["min_triangle_area_ratio"],
                    "minimum_volume_ratio": value["min_tet_volume_ratio"],
                }
            yield value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--reference-recorded", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = {
        "schema": "endoforge.phase6-replay-exact-differential.v1",
        "reference": {"path": str(args.reference), "sha256": sha256(args.reference)},
        "candidate": {"path": str(args.candidate), "sha256": sha256(args.candidate)},
        "comparison": "node distance <= 1e-12 m; every non-position field exactly equal; exact equality reported separately",
        "node_equivalence_tolerance_m": 1e-12,
        "steps_compared": 0, "node_positions_compared": 0,
        "maximum_node_error_m": 0.0, "differing_steps": 0, "first_differences": [],
        "non_position_differing_steps": 0, "invalid_or_mismatched_geometry_steps": 0,
    }
    for index, (reference, candidate) in enumerate(itertools.zip_longest(
        rows(args.reference, args.reference_recorded), rows(args.candidate)
    ), 1):
        report["steps_compared"] += 1
        if reference is None or candidate is None:
            report["differing_steps"] += 1
            report["non_position_differing_steps"] += 1
            if len(report["first_differences"]) < 20:
                report["first_differences"].append({"row": index, "fields": ["row_count"]})
            continue
        vertices_a, vertices_b = reference["vertices"], candidate["vertices"]
        geometry_valid = len(vertices_a) == len(vertices_b) and all(
            len(v) == 3 and all(math.isfinite(x) for x in v) for v in vertices_a + vertices_b
        )
        if not geometry_valid:
            report["invalid_or_mismatched_geometry_steps"] += 1
        report["node_positions_compared"] += min(len(vertices_a), len(vertices_b))
        for a, b in zip(vertices_a, vertices_b):
            if a != b:
                report["maximum_node_error_m"] = max(report["maximum_node_error_m"], math.dist(a, b))
        if reference != candidate:
            report["differing_steps"] += 1
            fields = [key for key in reference.keys() | candidate.keys() if reference.get(key) != candidate.get(key)]
            if any(key != "vertices" for key in fields):
                report["non_position_differing_steps"] += 1
            if len(report["first_differences"]) < 20:
                report["first_differences"].append({"row": index, "fields": sorted(fields)})
    report["exact_equal"] = report["steps_compared"] > 0 and report["differing_steps"] == 0
    report["passed"] = (report["steps_compared"] > 0 and report["non_position_differing_steps"] == 0
                        and report["invalid_or_mismatched_geometry_steps"] == 0
                        and report["maximum_node_error_m"] <= report["node_equivalence_tolerance_m"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
