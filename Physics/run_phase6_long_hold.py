"""Validate sustained mechanical grips at authored and perturbed ready poses.

Every case uses the production SOFA model and records every accepted step.
At most two independent native processes may run; timings are diagnostic only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait


ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "Physics/runtime/LapPhysics.exe"
def authored_targets():
    asset=json.loads((ROOT/"Assets/Phase6/physics-mesh.json").read_text())
    return [r["rest_ready_tip_m"] for r in asset["phase6_interaction"]["recipes"]]


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def cases():
    singles = []
    authored=authored_targets()
    for tool in (0, 1):
        nominal = authored[tool].copy()
        for label, axis, offset in [("nominal", None, 0)] + [
            (f"{axis_name}-{direction}", axis, sign * .0001)
            for axis, axis_name in enumerate("xyz") for direction, sign in (("minus", -1), ("plus", 1))
        ]:
            pose = nominal.copy()
            if axis is not None:
                pose[axis] += offset
            targets = [p.copy() for p in authored]
            targets[tool] = pose
            options = {"dual": False, "single_tool": tool, "targets": targets,
                       "lift_m": .001, "speed_m_s": .005,
                       "grasp_hold_steps": 1800, "traction_hold_steps": 1800,
                       "minimum_traction_increment_m": .0005, "assembly_compare": True}
            singles.append((f"tool{tool}-{label}", options))
    dual = ("dual-2mm", {"dual": True, "lift_m": .002, "speed_m_s": .005,
                        "grasp_hold_steps": 1800, "traction_hold_steps": 1800,
                        "minimum_traction_increment_m": .0015, "assembly_compare": True})
    return [singles[0], singles[7], dual] + singles[1:7] + singles[8:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", action="append", help="Select named cases; omission runs all 15")
    parser.add_argument("--workers", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("Use a fresh evidence directory")
    selected = [(name, options) for name, options in cases() if args.case is None or name in args.case]
    if not selected or (args.case is not None and set(args.case) != {name for name, _ in selected}):
        raise ValueError("Unknown or empty case selection")
    output.mkdir(parents=True)
    identity = sha(EXE)
    source_names = ("main.cpp", "Phase3Model.h", "Phase4Session.h", "Phase5Tests.h", "Phase6FEM.h", "Phase6ReadyRecipes.h", "Phase6ToolCollision.h", "Phase6Tests.h")
    sources = {name: sha(ROOT / "Physics" / name) for name in source_names}
    index = {"schema": "endoforge.phase6.long-hold.v1", "passed": False,
             "native_binary": {"path": str(EXE), "sha256": identity}, "sources_sha256": sources,
             "runner_sha256": sha(Path(__file__)), "cases": {},
             "scope": "60 s stationary grip, 1 mm single/2 mm dual traction and 60 s hold, loaded retraction, release; both tools and independent +/-0.1 mm x/y/z offsets",
             "pose_provenance": {"authored_rest_ready_tips_m": authored_targets(),
                                 "source": "Assets/Phase6/physics-mesh.json phase6_interaction; material-bound shared public preset recipe, sampled at each approach"},
             "validation_workers": args.workers,
             "performance_scope": "Offline physical correctness only; concurrent native processes may affect timings; not UE throughput or input latency"}
    started = time.monotonic()
    def run_case(case):
        name, options = case
        assert sha(EXE) == identity, "Native executable changed during validation"
        option_path = output / (name + "-options.json")
        option_path.write_text(json.dumps(options, indent=2) + "\n", encoding="utf-8")
        report = output / (name + ".json")
        with (output / (name + ".log")).open("wb") as log:
            result = subprocess.run([str(EXE), "--phase6", "--self-test-phase5", "--probe-options", str(option_path), "--report", str(report)], stdout=log, stderr=subprocess.STDOUT)
        value = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
        ok = result.returncode == 0 and value.get("passed") is True
        return name, {"passed": ok, "exit_code": result.returncode,
                      "report": str(report), "report_sha256": sha(report) if report.exists() else None,
                      "options_sha256": sha(option_path), "checks": value.get("checks", {})}
    pending = iter(selected)
    failed = False
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        running = set()
        for _ in range(args.workers):
            if (case := next(pending, None)) is not None:
                running.add(pool.submit(run_case, case))
        while running:
            done, running = wait(running, return_when=FIRST_COMPLETED)
            for future in done:
                name, result = future.result()
                index["cases"][name] = result
                failed |= not result["passed"]
                print(json.dumps({"case": name, "passed": result["passed"], "completed": len(index["cases"]), "total": len(selected)}), flush=True)
            if not failed:
                while len(running) < args.workers and (case := next(pending, None)) is not None:
                    running.add(pool.submit(run_case, case))
    index["checks"] = {"all_selected_cases_completed": len(index["cases"]) == len(selected),
                       "all_case_checks_passed": all(item["passed"] for item in index["cases"].values()),
                       "native_binary_unchanged": sha(EXE) == identity,
                       "native_sources_unchanged": all(sha(ROOT / "Physics" / name) == value for name, value in sources.items())}
    index["passed"] = all(index["checks"].values())
    index["elapsed_seconds"] = time.monotonic() - started
    (output / "long-hold-report.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return 0 if index["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
