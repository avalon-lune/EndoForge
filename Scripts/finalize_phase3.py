"""Validate exact Phase 3 binaries and real test evidence, then create the ZIP.

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
import stat
import struct
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PHASE_ROOT = ROOT / "output/Phase3"
SCREENSHOTS = (
    "phase3_01_ready.png", "phase3_02_grasp.png", "phase3_03_traction.png",
    "phase3_04_cut.png", "phase3_05_separation.png", "phase3_06_release.png",
    "phase3_07_reset.png",
)


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


def report(path: Path, executable_hash: str | None = None, checks: bool = True) -> dict:
    value = read_json(path)
    require(value.get("phase") == 3 and value.get("passed") is True,
            f"Expected successful Phase 3 evidence: {path}")
    require(value.get("experimental") is not True and not value.get("failure")
            and not value.get("failures"), f"Report has unresolved failures: {path}")
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=PHASE_ROOT / "EndoForge")
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--physics-report", type=Path, default=ROOT / "Physics/runtime/phase3-physics-test-results.json")
    parser.add_argument("--network-report", type=Path, default=ROOT / "Physics/runtime/phase3-network-test-results.json")
    parser.add_argument("--package-log", type=Path, required=True)
    parser.add_argument("--protocol-directory", type=Path, help="Optional UE editor atomic-protocol automation evidence")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    no_reparse(args.package)
    package = args.package.resolve()
    require(package != PHASE_ROOT.resolve() and package.is_relative_to(PHASE_ROOT.resolve()),
            "Destination must be a child of output/Phase3; previous phases are preserved")
    require(package.is_dir(), "Assemble the Phase 3 package first")
    for item in package.rglob("*"):
        no_reparse(item)
    run = args.run_directory.resolve()
    require(run.is_dir() and not run.is_relative_to(package), "Keep packaged-run evidence outside the deliverable")
    physics_exe = package / "Physics/LapPhysics.exe"
    game_exe = package / "LapTrainer/Binaries/Win64/LapTrainer.exe"
    for path in (physics_exe, game_exe, package / "StartTrainer.cmd", package / "StartTrainer.ps1",
                 package / "Source/Physics/Phase3Model.h", package / "Source/docs/PHASE3.md",
                 package / "Physics/etc/sofa.ini", package / "Physics/licenses/TIGHT-INCLUSION-MIT.txt",
                 package / "Source/Dependencies/sofa-v26.06.00-source.zip"):
        require(path.is_file(), f"Missing packaged file: {path}")
    for path in (package / "README.md", package / "Source/docs/PHASE3.md"):
        require(path.is_file() and "PHASE3_DOCUMENTATION_PENDING_MODEL_SYNC" not in path.read_text(encoding="utf-8-sig"),
                f"Model documentation must be synchronized before finalization: {path}")
    physics_hash, game_hash = sha256(physics_exe), sha256(game_exe)
    build = read_json(package / "Physics/build-info.json")
    require(build.get("phase") == 3 and build.get("protocol") == 3 and build.get("tested_protocol") == 3,
            "Physics build metadata must describe tested Phase 3 protocol 3")
    require(build.get("executable_sha256", "").lower() == physics_hash, "Physics build metadata hash differs")
    sources = build.get("source_files_sha256", {})
    require("Phase3Model.h" in sources and "main.cpp" in sources, "Missing physics source provenance")
    for name, digest in sources.items():
        require(Path(name).name == name and "/" not in name and "\\" not in name, f"Invalid source filename: {name}")
        source = package / "Source/Physics" / name
        require(source.is_file() and sha256(source) == digest.lower(), f"Packaged source differs: {source}")
    physics = report(args.physics_report, physics_hash)
    network = report(args.network_report, physics_hash)
    inputs = report(run / "phase3-input-test.json")
    require(inputs["checks"].get("regular_exercise_without_safety_stops") is True and
            inputs.get("metrics", {}).get("safety_stop_count") == 0,
            "UE input acceptance must prove the regular exercise had no protection events")
    receipt = report(run / "phase3-packaged-run.json", checks=False)
    require(receipt.get("run_kind") == "packaged" and receipt.get("game_exit_code") == 0, "Missing packaged acceptance")
    require(receipt.get("physics_exe_sha256") == physics_hash and receipt.get("game_exe_sha256") == game_hash,
            "Packaged acceptance binary hashes differ")
    require(receipt.get("engine_protocol_or_fatal_errors") == 0 and receipt.get("physics_errors") == 0,
            "Packaged run logged runtime errors")
    require(receipt.get("telemetry_safety_stops") == 0, "Packaged run must verify zero numerical protection events")
    game_log = run / "unreal.log"
    require(game_log.is_file() and "LAP_PHASE3_TEST complete passed=1 saved=1" in
            game_log.read_text(encoding="utf-8-sig", errors="replace"), "UE did not save a successful test")
    require(args.package_log.is_file() and "BUILD SUCCESSFUL" in
            args.package_log.read_text(encoding="utf-8-sig", errors="replace"), "Missing successful UAT build log")
    screenshot_dimensions = {name: png_size(run / name) for name in SCREENSHOTS}
    evidence = [(args.physics_report, "phase3-physics-test-results.json"),
                (args.network_report, "phase3-network-test-results.json"),
                (run / "phase3-input-test.json", "phase3-input-test.json"),
                (run / "phase3-packaged-run.json", "phase3-packaged-run.json"),
                (game_log, "phase3-packaged-unreal.log"), (args.package_log, "phase3-package.log")]
    evidence += [(run / name, name) for name in SCREENSHOTS]
    for name in ("physics.stdout.log", "physics.stderr.log", "launcher.stdout.log", "launcher.stderr.log"):
        evidence.append((run / name, "phase3-" + name))
    protocol = None
    if args.protocol_directory:
        protocol = report(args.protocol_directory / "protocol-result.json", checks=False)
        module_hash = protocol.get("module_sha256", "")
        require(len(module_hash) == 64 and all(c in "0123456789abcdef" for c in module_hash.lower()),
                "Editor protocol evidence must identify its tested module SHA-256")
        index = read_json(args.protocol_directory / "index.json")
        require(index.get("failed") == 0 and index.get("succeeded", 0) + index.get("succeededWithWarnings", 0) == 1,
                "Editor protocol automation did not report exactly one successful test")
        matching = [test for test in index.get("tests", [])
                    if test.get("fullTestPath") == "EndoForge.Phase3.AtomicTopologyProtocol"]
        require(len(matching) == 1 and matching[0].get("state") == "Success" and matching[0].get("errors") == 0,
                "Missing successful atomic topology protocol test")
        evidence += [(args.protocol_directory / "protocol-result.json", "phase3-editor-protocol-result.json"),
                     (args.protocol_directory / "index.json", "phase3-editor-protocol-index.json")]
    telemetry = list(run.glob("phase3-session-*.csv"))
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
            require(path.suffix.lower() != ".json" or path.name == "build-info.json", f"Uncurated runtime report: {path}")
            require(path.suffix.lower() != ".log", f"Uncurated runtime log: {path}")
    validation = {"validated": True, "phase": 3, "package": str(package), "physics_exe_sha256": physics_hash,
                  "game_exe_sha256": game_hash, "evidence_files": len(evidence), "screenshots": len(SCREENSHOTS)}
    if args.validate_only:
        print(json.dumps(validation, ensure_ascii=False, indent=2))
        return
    staging = PHASE_ROOT / (".verification-staging-" + uuid.uuid4().hex)
    staging.mkdir()
    try:
        for path, name in evidence:
            shutil.copy2(path, staging / name)
        summary = {**validation, "assembled_at_utc": datetime.now(timezone.utc).isoformat(),
                   "native_checks": physics["checks"], "network_checks": network["checks"], "input_checks": inputs["checks"],
                   "physics_model": physics.get("model", {}),
                   "physics_metrics": physics.get("metrics", {}), "input_metrics": inputs.get("metrics", {}),
                   "editor_protocol_evidence": protocol,
                   "telemetry_samples": receipt.get("telemetry_samples"),
                   "telemetry_physics_step_p95_ms": receipt.get("telemetry_physics_step_p95_ms"),
                   "screenshot_dimensions": screenshot_dimensions,
                   "evidence": [{"path": name, "sha256": sha256(staging / name)} for _, name in evidence],
                   "limitations": ["Training membrane, not calibrated biological tissue or validated clinical training.",
                       "Automated UE PlayerController input is not physical mouse/keyboard or clinician usability testing.",
                       "Local Windows machine performance only; no hard real-time or haptic guarantee.",
                       "See Source/docs/PHASE3.md for the exact cutting discretization, contact model and exclusions."]}
        (staging / "verification-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (staging / "验证记录.md").write_text(
            "# 第三阶段交付验证记录\n\n"
            "本目录保留最终独立打包程序的实际验收记录。原生物理、TCP 协议和 UE 正常输入路径的测试均核对了最终程序 SHA-256。\n\n"
            "- `phase3-physics-test-results.json`：剪切后力学连接、组织分离、抓持及复位等原生测试。\n"
            "- `phase3-network-test-results.json`：真实本机 TCP 协议、双器械状态和拓扑同步测试。\n"
            "- `phase3-input-test.json`、`phase3-packaged-run.json`：UE 双器械操作和剪切输入测试。\n"
            "- `phase3-package.log`：Windows 打包日志。\n"
            "- `phase3_*.png`：准备、抓持、牵拉、剪开、分离、释放和复位画面。\n"
            "- `phase3-session-acceptance.csv`：本次运行的受控会话数据。\n\n"
            f"本次会话记录 {receipt.get('telemetry_samples')} 条；物理求解步耗时 P95 为 "
            f"{receipt.get('telemetry_physics_step_p95_ms')} ms。具体通过条件、原始测量值与模型边界见 JSON 及 `Source/docs/PHASE3.md`。\n\n"
            "输入测试经过 UE PlayerController 和正常交互代码，不代表实体键鼠手感验收或医生评审。"
            "材料、接触和剪切参数未经真实组织标定；当前结果不能证明临床训练有效性。\n\n"
            "ZIP 解压到新目录的独立运行测试在压缩包完成后进行，其报告位于 `output/Phase3/archive-relocation-verification.json`，不写回 ZIP。\n",
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
                     any(part.lower() in ("saved", "logs") for part in relative.parts))
        if path.exists() and disposable:
            no_reparse(path)
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    (package / "Logs").mkdir(exist_ok=True)
    files = sorted(path for path in package.rglob("*") if path.is_file() and path.name != "package-manifest.json")
    manifest_path = package / "package-manifest.json"
    manifest_path.write_text(json.dumps([{"path": path.relative_to(package).as_posix(), "bytes": path.stat().st_size,
                           "sha256": sha256(path)} for path in files], ensure_ascii=False, indent=2), encoding="utf-8")
    files.append(manifest_path)
    zip_path = PHASE_ROOT / "EndoForge_Phase3_Win64.zip"
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
    sidecar = zip_path.with_suffix(".zip.sha256")
    no_reparse(sidecar)
    sidecar.write_text(f"{digest}  {zip_path.name}\n", encoding="ascii")
    print(json.dumps({**validation, "zip": str(zip_path), "sha256": digest, "zip_crc_passed": True,
                      "files": len(files), "zip_bytes": zip_path.stat().st_size}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(f"Phase 3 finalization failed: {error}", file=sys.stderr)
        sys.exit(1)
