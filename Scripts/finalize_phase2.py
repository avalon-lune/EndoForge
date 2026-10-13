"""Validate final Phase 2 evidence, collect it, then hash and ZIP this deliverable.

The run directory must come from the packaged executable, not the editor. Its
phase2-packaged-run.json is written by the test wrapper immediately after that
run, with phase=2, passed=true, run_kind="packaged", game_exit_code=0 and the
physics_exe_sha256/game_exe_sha256 of the executables used for the run.
No build, simulation, or evidence fabrication is performed by this script.
"""
from __future__ import annotations

import argparse
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
PHASE_ROOT = ROOT / "output/Phase2"
REQUIRED_SCREENSHOTS = (
    "phase2_01_surface_contact.png", "phase2_02_edge_approach.png",
    "phase2_03_contact_grasp.png", "phase2_04_traction.png",
    "phase2_05_frictional_slip.png", "phase2_06_release.png",
    "phase2_07_rcm_limit.png", "phase2_08_jaw_detail.png",
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
    require(isinstance(value, dict), f"Expected a JSON object: {path}")
    return value


def ensure_no_reparse(path: Path) -> None:
    """Never traverse a junction/symlink while changing a generated package."""
    for candidate in (path, *path.parents):
        if candidate.exists() or candidate.is_symlink():
            attributes = candidate.lstat()
            require(not candidate.is_symlink() and not
                    (getattr(attributes, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT),
                    f"Junctions and symbolic links are not permitted: {candidate}")


def safe_package(path: Path) -> Path:
    ensure_no_reparse(path)
    resolved = path.resolve()
    root = PHASE_ROOT.resolve()
    require(resolved != root and resolved.is_relative_to(root),
            f"Package must be a child of {root}; Phase 1 is never a destination")
    require(resolved.is_dir(), f"Assemble the package before finalizing: {resolved}")
    for entry in resolved.rglob("*"):
        ensure_no_reparse(entry)
    return resolved


def validate_phase2_report(path: Path, *, expected_hash: str | None = None) -> dict:
    require(path.name.startswith("phase2-") and "probe" not in path.name.lower(),
            f"Only final phase2-* test reports are accepted: {path}")
    report = read_json(path)
    require(report.get("phase") == 2, f"Not a Phase 2 report: {path}")
    require(report.get("passed") is True, f"Test did not pass: {path}")
    require(report.get("experimental") is not True, f"Experimental evidence is not final: {path}")
    checks = report.get("checks")
    if isinstance(checks, dict):
        require(bool(checks) and all(value is True for value in checks.values()),
                f"A check is missing or failed in {path}")
    if expected_hash is not None:
        require(str(report.get("executable_sha256", "")).lower() == expected_hash,
                f"Tested Physics executable does not match the package: {path}")
    return report


def png_size(path: Path) -> tuple[int, int]:
    require(path.is_file() and path.stat().st_size > 10000, f"Missing or empty screenshot: {path}")
    with path.open("rb") as stream:
        header = stream.read(24)
    require(header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR",
            f"Invalid PNG header: {path}")
    width, height = struct.unpack(">II", header[16:24])
    require(width >= 640 and height >= 360, f"Screenshot is too small: {path}")
    return width, height


def disposable(relative: Path) -> bool:
    if relative.parts[0] == "Verification":
        return False
    return relative.suffix.lower() == ".pdb" or any(part.lower() in ("saved", "logs") for part in relative.parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=PHASE_ROOT / "LapTrainer")
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--physics-report", type=Path,
                        default=ROOT / "Physics/runtime/phase2-physics-test-results.json")
    parser.add_argument("--network-report", type=Path,
                        default=ROOT / "Physics/runtime/phase2-network-test-results.json")
    parser.add_argument("--package-log", type=Path, required=True)
    parser.add_argument("--game-log", type=Path, help="Defaults to <run-directory>/unreal.log")
    parser.add_argument("--validate-only", action="store_true", help="Check every input without changing any file")
    args = parser.parse_args()

    package = safe_package(args.package)
    run = args.run_directory.resolve()
    require(run.is_dir(), f"Final packaged-run directory does not exist: {run}")
    require(not run.is_relative_to(package), "Keep final test evidence outside the deliverable before collecting it")
    physics_exe = package / "Physics/LapPhysics.exe"
    game_exe = package / "LapTrainer/Binaries/Win64/LapTrainer.exe"
    for required in (physics_exe, game_exe, package / "StartTrainer.cmd",
                     package / "Source/Physics/Phase2Model.h",
                     package / "Physics/etc/sofa.ini",
                     package / "Physics/licenses/TIGHT-INCLUSION-MIT.txt",
                     package / "Source/Dependencies/sofa-v26.06.00-source.zip"):
        require(required.is_file(), f"Missing packaged component: {required}")
    physics_hash, game_hash = sha256(physics_exe), sha256(game_exe)
    build_info = read_json(package / "Physics/build-info.json")
    require(build_info.get("phase") == 2 and build_info.get("tested_protocol") == 2,
            "Packaged Physics build metadata still describes another phase/protocol")
    require(str(build_info.get("executable_sha256", "")).lower() == physics_hash,
            "Packaged Physics build metadata does not match its executable")
    source_hashes = build_info.get("source_files_sha256", {})
    require("Phase2Model.h" in source_hashes, "Physics build metadata omits Phase2Model.h")
    for name, digest in source_hashes.items():
        require(Path(name).name == name and "/" not in name and "\\" not in name,
                f"Unexpected source name in build metadata: {name}")
        source = package / "Source/Physics" / name
        require(source.is_file() and sha256(source) == str(digest).lower(),
                f"Packaged Physics source differs from tested build metadata: {source}")
    physics = validate_phase2_report(args.physics_report, expected_hash=physics_hash)
    network = validate_phase2_report(args.network_report, expected_hash=physics_hash)
    input_path = run / "phase2-input-test.json"
    inputs = validate_phase2_report(input_path)
    require(inputs.get("report_version", 0) >= 2, "Use the current Phase 2 input test, report_version >= 2")
    require(not inputs.get("failure"), "Phase 2 input report contains failure details")
    require(math.isclose(float(physics.get("dt_s", 0)), 1 / 30, rel_tol=0, abs_tol=1e-10),
            "Final physics report must use the 30 Hz fixed step")

    receipt_path = run / "phase2-packaged-run.json"
    receipt = validate_phase2_report(receipt_path)
    require(receipt.get("run_kind") == "packaged" and receipt.get("game_exit_code") == 0,
            "Final run must be a successful packaged-executable run")
    require(str(receipt.get("physics_exe_sha256", "")).lower() == physics_hash,
            "Final packaged run used a different Physics executable")
    require(str(receipt.get("game_exe_sha256", "")).lower() == game_hash,
            "Final packaged run used a different UE executable")

    game_log = args.game_log.resolve() if args.game_log else run / "unreal.log"
    require(game_log.is_file(), f"Missing final UE run log: {game_log}")
    log_text = game_log.read_text(encoding="utf-8-sig", errors="replace")
    require("LAP_PHASE2_TEST complete passed=1 saved=1" in log_text,
            "The UE log does not confirm a saved, successful Phase 2 test")
    require(args.package_log.is_file(), f"Missing final UAT package log: {args.package_log}")
    require("BUILD SUCCESSFUL" in args.package_log.read_text(encoding="utf-8-sig", errors="replace"),
            "The final UAT log does not confirm BUILD SUCCESSFUL")

    for name in REQUIRED_SCREENSHOTS:
        png_size(run / name)
    screenshots = sorted(run.glob("phase2_*.png"))
    screenshot_dimensions = {path.name: png_size(path) for path in screenshots}
    readme = (package / "README.md").read_text(encoding="utf-8-sig")
    require("交付前必须更新" not in readme, "The Phase 2 README still contains a draft placeholder")
    for path in (package / "Physics").rglob("*"):
        if path.is_file():
            require(path.suffix.lower() != ".json" or path.name == "build-info.json",
                    f"Runtime contains an uncurated report/probe: {path}; reassemble Phase 2")
            require(path.suffix.lower() != ".log", f"Runtime contains a development log: {path}")

    evidence = [(args.physics_report, "phase2-physics-test-results.json"),
                (args.network_report, "phase2-network-test-results.json"),
                (input_path, "phase2-input-test.json"),
                (receipt_path, "phase2-packaged-run.json"),
                (game_log, "phase2-packaged-unreal.log"),
                (args.package_log, "phase2-package.log")]
    evidence.extend((path, path.name) for path in screenshots)
    for name in ("physics.stdout.log", "physics.stderr.log", "launcher.stdout.log", "launcher.stderr.log"):
        path = run / name
        if path.is_file():
            evidence.append((path, "phase2-" + name))
    # Only controlled telemetry copied by the packaged-run wrapper is retained.
    telemetry = sorted(run.glob("phase2-session-*.csv"))
    require(bool(telemetry), "Final packaged run has no curated phase2-session-*.csv telemetry")
    for path in telemetry:
        evidence.append((path, path.name))
    require(len({name for _, name in evidence}) == len(evidence), "Duplicate evidence destination")
    # Fail before making any change if any explicitly selected evidence is absent.
    for path, _ in evidence:
        require(path.is_file(), f"Missing evidence: {path}")

    validation = {"validated": True, "phase": 2, "package": str(package),
                  "physics_exe_sha256": physics_hash, "game_exe_sha256": game_hash,
                  "evidence_files": len(evidence), "screenshots": len(screenshots)}
    if args.validate_only:
        print(json.dumps(validation, ensure_ascii=False, indent=2))
        return

    verify = package / "Verification"
    staging = PHASE_ROOT / (".verification-staging-" + uuid.uuid4().hex)
    staging.mkdir(parents=False)
    try:
        for path, name in evidence:
            shutil.copy2(path, staging / name)
        summary = {
            "phase": 2, "assembled_at_utc": datetime.now(timezone.utc).isoformat(),
            "engine": "Unreal Engine 5.7.4", "physics": "SOFA 26.06.00",
            "platform": "Windows x64, DirectX 11, Development build",
            "physics_step_hz": 30, "render_fps_target": 60,
            "physics_regression_passed": True, "network_regression_passed": True,
            "packaged_phase2_input_test_passed": True,
            "packaged_run_telemetry_samples": receipt.get("telemetry_samples"),
            "packaged_run_physics_step_p95_ms": receipt.get("telemetry_physics_step_p95_ms"),
            "physics_exe_sha256": physics_hash, "game_exe_sha256": game_hash,
            "screenshot_dimensions": screenshot_dimensions,
            "numerical_metrics": physics.get("metrics", {}),
            "quasistatic_balance": physics.get("quasistatic_balance", {}),
            "evidence": [{"path": name, "sha256": sha256(staging / name)} for _, name in evidence],
            "limitations": [
                "Uncalibrated material, friction, and contact-load values; no clinical validation.",
                "Constraint impulses divided by the step size produce average force; displayed load is a sum of contact magnitudes, not a net resultant.",
                "Automated PlayerController input is not a physical keyboard/mouse hardware or physician usability test.",
                "Fixed 30 Hz physics and 60 FPS rendering target are separate; measured runtime performance applies only to this test machine.",
                "Contact uses simplified jaw envelopes; visual detail does not replace collision geometry; no cutting, suturing, or haptic output.",
            ],
        }
        (staging / "verification-summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        metrics = physics.get("metrics", {})
        def metric(name: str, scale: float = 1.0) -> str:
            value = metrics.get(name)
            return f"{float(value) * scale:.3f}" if isinstance(value, (int, float)) else "见原始报告"
        report = f"""# 第二阶段交付验证记录

本目录来自最终 Windows 独立打包程序。程序哈希与物理、网络及打包运行记录逐项核对；原始报告及截图保留在本目录。

| 检查 | 证据 |
|---|---|
| UE Windows 打包成功 | phase2-package.log |
| SOFA 数值与力单位回归通过 | phase2-physics-test-results.json |
| 本机 TCP 协议回归通过 | phase2-network-test-results.json |
| 最终打包版输入、接触及场景检查通过 | phase2-input-test.json、phase2-packaged-run.json、phase2-packaged-unreal.log |
| 本次画面记录 | {len(screenshots)} 张 phase2_*.png；分别展示接触、边缘接近、夹持、牵拉、滑移、释放、行程限制与器械细节 |

本次模型为 {physics.get('node_count', '见原始报告')} 个节点、{physics.get('tet_count', '见原始报告')} 个四面体。物理步长固定为 1/30 秒，与 UE 的 60 FPS 渲染目标独立。本次数值回归求解耗时 P95 为 {metric('step_p95_ms')} ms，最大值 {metric('step_max_ms')} ms；这是当前电脑和本次脚本的实测，不是持续帧率或其他硬件性能承诺。

数值回归最小单元体积比 {metric('min_tet_volume_ratio')}，最大采样穿透 {metric('max_sampled_penetration_m', 1000)} mm，最大支撑面穿透 {metric('max_floor_penetration_m', 1000)} mm。完整判定、采样范围与平衡检验见原始 JSON。采样穿透指标不等于所有接触在整个时间域的全局上界。

输入测试将事件交给 UE PlayerController，由正常交互代码读取，再检查 SOFA 状态。它不等于实体鼠标键盘操作验收或医生可用性评审。旧一期 AutoDemo/KeyTest 结果不参与二期通过判定。

显示与 CSV 中的力指标均为总接触载荷：每个接触约束的步均力大小相加，不是器械净反力或单侧夹紧法向力。材料、摩擦和载荷未做实物标定，不能当作医疗安全限值。本次不包括剪切、缝合、力反馈和临床有效性验证。

返回根目录 README.md 查看手动操作；双击 StartTrainer.cmd 启动。反馈问题时请附上新会话 CSV、运行日志和复现步骤。
"""
        (staging / "验证记录.md").write_text(report, encoding="utf-8")
        if verify.exists():
            ensure_no_reparse(verify)
            shutil.rmtree(verify)
        staging.replace(verify)
    finally:
        if staging.exists():
            ensure_no_reparse(staging)
            shutil.rmtree(staging)

    # The packaged acceptance run may have created these after assembly. Curated
    # evidence has already been copied above; remove only generated package data.
    for path in sorted(package.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.exists() and disposable(path.relative_to(package)):
            ensure_no_reparse(path)
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    (package / "Logs").mkdir(exist_ok=True)
    files = sorted(path for path in package.rglob("*") if path.is_file()
                   and path != package / "package-manifest.json")
    manifest = [{"path": path.relative_to(package).as_posix(), "bytes": path.stat().st_size,
                 "sha256": sha256(path)} for path in files]
    manifest_path = package / "package-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    files.append(manifest_path)
    zip_path = package.parent / "LapTrainer_Phase2_Win64.zip"
    ensure_no_reparse(zip_path)
    zip_temporary = zip_path.with_suffix(".zip.partial")
    ensure_no_reparse(zip_temporary)
    try:
        with zipfile.ZipFile(zip_temporary, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=5, allowZip64=True) as archive:
            for path in files:
                archive.write(path, "LapTrainer/" + path.relative_to(package).as_posix())
        with zipfile.ZipFile(zip_temporary) as archive:
            invalid = archive.testzip()
            require(invalid is None, f"ZIP CRC failure: {invalid}")
        zip_temporary.replace(zip_path)
    finally:
        if zip_temporary.exists():
            zip_temporary.unlink()
    digest = sha256(zip_path)
    sidecar = zip_path.with_suffix(zip_path.suffix + ".sha256")
    ensure_no_reparse(sidecar)
    sidecar.write_text(f"{digest}  {zip_path.name}\n", encoding="ascii")
    print(json.dumps({**validation, "zip": str(zip_path), "files": len(files),
                      "uncompressed_bytes": sum(path.stat().st_size for path in files),
                      "zip_bytes": zip_path.stat().st_size, "sha256": digest,
                      "zip_crc_passed": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(f"Phase 2 finalization failed: {error}", file=sys.stderr)
        sys.exit(1)
