"""Bind Phase8's unchanged native inputs to the accepted fresh Phase7 suite.

This helper only reads and hashes inputs. It never launches native code, rebuilds,
or runs a simulation. A successful identity check leaves fresh integration and
packaged UE, interaction, replay, geometry, and data tests mandatory.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import runpy
import stat
import sys
import time
import zipfile


UTIL = runpy.run_path(str(Path(__file__).with_name("preservation.py")))
checked_stat = UTIL["checked_stat"]
checked_ancestors = UTIL["checked_ancestors"]
metadata = UTIL["metadata"]
member_path = UTIL["member_path"]
sha = UTIL["sha"]
atomic_json = UTIL["atomic_json"]
PACKAGE = "output/Phase7/EndoForge-20261026-r1"
FINAL = "output/Phase7/phase7-final-verification.json"
SOURCE_SUFFIXES = {".cpp", ".c", ".h", ".hpp", ".inl", ".cmake", ".py", ".ps1", ".json", ".txt", ".md"}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def file_names(directory, excluded=(), suffixes=None):
    """List regular files without following links or Windows reparse points."""
    checked_ancestors(directory)
    result = set()

    def descend(path):
        if not stat.S_ISDIR(checked_stat(path).st_mode):
            raise NotADirectoryError(path)
        with os.scandir(path) as entries:
            children = sorted(entries, key=lambda entry: entry.name)
        for entry in children:
            child = Path(entry.path)
            info = checked_stat(child)
            if stat.S_ISDIR(info.st_mode):
                if child.name not in excluded:
                    descend(child)
            elif stat.S_ISREG(info.st_mode):
                if suffixes is None or child.suffix.lower() in suffixes:
                    result.add(child.relative_to(directory).as_posix())
            else:
                raise ValueError(f"Unexpected filesystem member: {child}")

    descend(directory)
    return result


class Audit:
    def __init__(self, root):
        self.root = root
        self.checks = {}
        self.failures = []
        self.records = {}
        self.snapshots = {}
        self.memberships = []

    def check(self, name, passed, **details):
        if name in self.checks:
            raise ValueError("Duplicate check name: " + name)
        self.checks[name] = bool(passed)
        if not passed:
            self.failures.append({"check": name, **details})

    def record(self, name):
        path = member_path(self.root, name)
        checked_ancestors(path)
        if name not in self.records:
            info = checked_stat(path)
            self.records[name] = {"path": name, "bytes": info.st_size,
                                  "sha256": sha(path, metadata(info))}
            self.snapshots[name] = metadata(info)
        return self.records[name]

    def match(self, name, digest, label, expected_bytes=None):
        try:
            row = self.record(name)
            passed = row["sha256"] == digest and (expected_bytes is None or row["bytes"] == expected_bytes)
            self.check(label, passed, path=name, expected_sha256=digest, actual=row,
                       expected_bytes=expected_bytes)
            return {**row, "expected_sha256": digest, "matches": passed}
        except (FileNotFoundError, NotADirectoryError) as exc:
            self.check(label, False, path=name, expected_sha256=digest, error=str(exc))
            return {"path": name, "expected_sha256": digest, "matches": False, "missing": True}

    def read(self, name):
        self.record(name)
        return json.loads(member_path(self.root, name).read_text(encoding="utf-8"))

    def membership(self, relative, names, **kwargs):
        current = file_names(member_path(self.root, relative), **kwargs)
        self.memberships.append((relative, current, kwargs))
        self.check("membership:" + relative, current == set(names),
                   missing=sorted(set(names) - current), added=sorted(current - set(names)))
        return current

    def finish_stability(self):
        changed = []
        for name, expected in self.snapshots.items():
            try:
                if metadata(checked_stat(member_path(self.root, name))) != expected:
                    changed.append(name)
            except FileNotFoundError:
                changed.append(name)
        self.check("all_bound_file_metadata_stable_during_audit", not changed, changed=changed)
        for index, (relative, expected, kwargs) in enumerate(self.memberships):
            current = file_names(member_path(self.root, relative), **kwargs)
            self.check("stable_membership:" + str(index), current == expected,
                       directory=relative, missing=sorted(expected - current), added=sorted(current - expected))


def audit(root, mesh, baseline_name):
    a = Audit(root)
    preservation = a.read(baseline_name)
    UTIL["validate_baseline"](preservation)
    preserved = {row["path"]: row for row in preservation["files"]}

    def accepted(name):
        expected = preserved[name]
        a.match(name, expected["sha256"], "preserved:" + name, expected["bytes"])
        return a.read(name)

    final = accepted(FINAL)
    manifest_name = PACKAGE + "/package-manifest.json"
    manifest_rows = accepted(manifest_name)
    manifest = {}
    for row in manifest_rows:
        member_path(root, row["path"])
        if row["path"].casefold() in {name.casefold() for name in manifest}:
            raise ValueError("Duplicate accepted manifest member: " + row["path"])
        manifest[row["path"]] = row
    a.check("accepted_final_passed_phase7", final.get("schema") == "endoforge.phase7.final-delivery.v1"
            and final.get("phase") == 7 and final.get("passed") is True)
    a.check("accepted_manifest_file_count", len(manifest) == final["manifest_files"])

    def packaged(name):
        row = manifest[name]
        full = PACKAGE + "/" + name
        a.match(full, row["sha256"], "manifest:" + name, row["bytes"])
        expected = preserved[full]
        a.check("preservation_manifest_agree:" + name,
                row["sha256"] == expected["sha256"] and row["bytes"] == expected["bytes"])
        return full

    qualification = final["native_requalification"]
    a.check("accepted_native_was_fresh_phase7_execution",
            qualification.get("schema") == "endoforge.phase7.native-requalification.v1"
            and qualification.get("phase") == 7 and qualification.get("passed") is True
            and qualification.get("native_suite_reexecuted") is True
            and qualification.get("inherited_physics_acceptance") is False
            and qualification.get("solver_mode") == 6)
    suite_name = packaged("Verification/Reports/native.json")
    stage_name = packaged("Verification/Native/phase7-native-workspace.json")
    build_name = packaged("phase7-build-receipt.json")
    build_generator_name = packaged("Source/Scripts/Phase7/build_receipt.py")
    metadata_name = packaged("Verification/Native/build-info.json")
    suite, stage, build, post_metadata = [a.read(name) for name in (suite_name, stage_name, build_name, metadata_name)]
    suite_hash = a.record(suite_name)["sha256"]
    a.check("native_suite_bound_to_accepted_final", suite_hash == qualification["native_suite"]["sha256"])
    a.check("native_staging_bound_to_accepted_final",
            a.record(stage_name)["sha256"] == qualification["staging_receipt_sha256"])
    a.check("native_stage_is_explicit_phase7_workspace",
            stage.get("schema") == "endoforge.phase7.native-workspace.v1" and stage.get("phase") == 7
            and stage.get("solver_mode") == 6)
    a.check("native_suite_complete_35_cases", suite.get("passed") is True
            and all(value is True for value in suite["checks"].values())
            and suite["checks"].get("thirty_five_native_cases") is True
            and suite["checks"].get("fifteen_long_hold_cases_and_all_raw_states") is True
            and suite["metrics"].get("native_case_count") == 35)
    a.check("accepted_build_native_qualification_matches_final", build.get("native_requalification") == qualification)

    binary_digest = final["physics_exe_sha256"]
    asset_digest = final["physics_asset_sha256"]
    a.check("all_accepted_native_binary_identities_agree", binary_digest == qualification["native_binary_sha256"]
            == suite["native_binary"]["sha256"] == stage["native_executable_sha256"] == build["physics_exe_sha256"])
    a.check("all_accepted_physical_asset_identities_agree", asset_digest == qualification["physical_asset_sha256"]
            == suite["anatomy_asset"]["sha256"] == stage["source_phase7_asset_sha256"])
    physical_name = packaged("Assets/Phase7/physics-mesh.json")
    a.match(physical_name, asset_digest, "accepted_physical_mesh_identity")
    physical = a.match(mesh, asset_digest, "phase8_explicit_mesh_identical_to_accepted_phase7", suite["anatomy_asset"]["bytes"])
    a.check("accepted_package_phase6_alias_is_explicit_phase7_mesh",
            build.get("native_asset_alias", {}).get("path") == "Physics/assets/phase6.json"
            and build["native_asset_alias"].get("source") == "Assets/Phase7/physics-mesh.json"
            and manifest["Physics/assets/phase6.json"]["sha256"] == asset_digest)

    source_rows = []
    source_members = {name[len("Source/Physics/"):] for name in manifest if name.startswith("Source/Physics/")}
    a.membership("Physics", source_members, excluded={"runtime", "build", "diagnostics", "__pycache__"},
                 suffixes=SOURCE_SUFFIXES)
    for name in sorted(source_members):
        packaged("Source/Physics/" + name)
        expected = manifest["Source/Physics/" + name]["sha256"]
        current = "Physics/" + name
        source_rows.append(a.match(current, expected, "native_source:" + name))
        if Path(name).suffix.lower() == ".md":
            # The accepted generator's source_hashes includes native h/cpp/json/
            # txt/ps1/py, plus Physics/configs, and deliberately excludes .md.
            # Documentation remains strictly bound to package and fresh stage.
            a.check("documentation_outside_declared_build_source_map:" + name,
                    current not in build["source_asset_sha256"])
        else:
            a.check("native_source_bound_to_build_receipt:" + name,
                    build["source_asset_sha256"].get(current) == expected)
        a.check("native_source_bound_to_fresh_stage:" + name,
                stage["unmodified_test_and_native_sources"].get(current) == expected
                and stage["stage_files_sha256"].get(current) == expected)

    harness_rows = []
    for current, expected in sorted(stage["unmodified_test_and_native_sources"].items()):
        if current.startswith("Physics/"):
            continue
        packaged("Source/" + current)
        a.check("harness_manifest_matches_fresh_stage:" + current,
                manifest["Source/" + current]["sha256"] == expected)
        harness_rows.append(a.match(current, expected, "native_harness:" + current))
    for name, expected in suite["sources_sha256"].items():
        # The unchanged legacy runner used this explicitly disclosed Phase7 alias.
        current = mesh if name == "../Assets/Phase6/physics-mesh.json" else (
            name[3:] if name.startswith("../") else "Physics/" + name)
        a.match(current, expected, "native_suite_source:" + name)

    runtime_rows = []
    runtime_manifest = {name[len("Physics/"):] for name in manifest if name.startswith("Physics/")}
    actual_runtime = file_names(root / "Physics/runtime")
    active = lambda name: Path(name).suffix.lower() in {".dll", ".exe", ".ini", ".cfg", ".conf", ".cmake"} or name.startswith(("configs/", "etc/", "share/", "assets/", "licenses/")) or name in {"runtime-manifest.txt", "build-info.json"}
    actual_active = {name for name in actual_runtime if active(name)}
    a.check("complete_runtime_input_membership", actual_active == runtime_manifest,
            missing=sorted(runtime_manifest - actual_active), added=sorted(actual_active - runtime_manifest))
    a.memberships.append(("Physics/runtime", actual_runtime, {}))
    generated_key = "Physics/runtime/build-info.json"
    a.check("only_disclosed_generated_metadata_exception",
            set(stage["generated_metadata_before_sha256"]) == {generated_key}
            and generated_key not in stage["stage_files_sha256"])
    generated_metadata = {}
    unused_alias = {}
    for name in sorted(runtime_manifest):
        packaged("Physics/" + name)
        expected = manifest["Physics/" + name]["sha256"]
        current = "Physics/runtime/" + name
        if name == "build-info.json":
            initial = stage["generated_metadata_before_sha256"][generated_key]
            generated_metadata = {"current": a.match(current, initial, "root_metadata_matches_pre_suite_output"),
                                  "accepted_post_suite": a.record(metadata_name),
                                  "accepted_packaged": a.record(PACKAGE + "/Physics/build-info.json"),
                                  "policy": stage["generated_metadata_policy"],
                                  "scope": "Generated summarizer output is not read as native execution configuration. Root output remains the exact pre-suite bytes disclosed by accepted Phase7 staging; it is not used as proof of current binary qualification."}
            a.check("accepted_post_suite_metadata_bound_to_final",
                    a.record(metadata_name)["sha256"] == qualification["generated_runtime_metadata"]["sha256"] == expected
                    and post_metadata.get("executable_sha256") == binary_digest
                    and post_metadata.get("native_suite_sha256") == suite_hash
                    and post_metadata.get("source_files_sha256") == suite["sources_sha256"])
        elif name == "assets/phase6.json":
            old_asset = preserved["Assets/Phase6/physics-mesh.json"]
            unused_alias = {"current": a.match(current, old_asset["sha256"], "unused_root_alias_matches_preserved_old_source", old_asset["bytes"]),
                            "accepted_package_alias": a.record(PACKAGE + "/Physics/assets/phase6.json"),
                            "selected_mesh": mesh, "selected_mesh_sha256": asset_digest,
                            "scope": "The root legacy default alias is unused by the required explicit --mesh invocation. The accepted Phase7 package and fresh Phase7 suite deliberately mapped their legacy alias to the Phase7 physical mesh."}
            a.check("fresh_suite_runtime_alias_was_phase7_mesh",
                    stage["stage_files_sha256"].get(current) == asset_digest)
        else:
            runtime_rows.append(a.match(current, expected, "runtime_input:" + name))
            a.check("runtime_bound_to_fresh_phase7_stage:" + name,
                    stage["stage_files_sha256"].get(current) == expected)
    runtime_list = (root / "Physics/runtime/runtime-manifest.txt").read_text(encoding="utf-8-sig").splitlines()
    listed = {name.strip() for name in runtime_list if name.strip()}
    native_modules = {name for name in runtime_manifest if Path(name).suffix.lower() in {".exe", ".dll"}}
    a.check("runtime_manifest_exact_executable_dll_set", listed == native_modules,
            missing=sorted(native_modules - listed), added=sorted(listed - native_modules))

    dependencies = a.read(PACKAGE + "/Source/Physics/dependencies.json")["dependencies"]
    dependency_pins = a.read(PACKAGE + "/Source/Physics/dependency-hashes.json")
    pins = {entry["archive"]: entry["sha256"].lower() for entry in dependencies}
    for entry in dependency_pins:
        name, expected = entry["Path"], entry["Hash"].lower()
        if name in pins:
            a.check("dependency_pin_declarations_agree:" + name, pins[name] == expected)
        pins[name] = expected
    dependency_rows = [a.match(name, expected, "dependency_artifact:" + name) for name, expected in sorted(pins.items())]

    # Compare all possibly selected header/import-library/CMake/runtime SDK inputs
    # against the exact accepted pinned archives, without extracting or executing.
    selected_trees = {
        "SOFA Windows SDK": ("include", "lib", "plugins", "bin", "etc"),
        "CMake portable": ("bin", "share"),
        "Eigen": ("Eigen", "unsupported"),
        "Boost": ("boost",),
    }
    expanded = []
    for dependency in dependencies:
        if dependency["name"] not in selected_trees:
            continue
        archive_name = dependency["archive"]
        marker_relative = dependency["marker"][len(dependency["extract"]) + 1:]
        archive_root = marker_relative.split("/")[0]
        selected = selected_trees[dependency["name"]]
        with zipfile.ZipFile(member_path(root, archive_name)) as archive:
            members = {}
            for entry in archive.infolist():
                if not entry.is_dir() and any(entry.filename.startswith(archive_root + "/" + prefix + "/") for prefix in selected):
                    member_path(root, entry.filename)
                    if entry.filename in members:
                        raise ValueError("Duplicate archive member: " + entry.filename)
                    members[entry.filename] = entry
            actual_names = set()
            for prefix in selected:
                relative = dependency["extract"] + "/" + archive_root + "/" + prefix
                expected = {name[len(archive_root + "/" + prefix + "/"):] for name in members
                            if name.startswith(archive_root + "/" + prefix + "/")}
                actual = a.membership(relative, expected)
                actual_names.update(archive_root + "/" + prefix + "/" + name for name in actual)
            digests = {}
            mismatch_names = []
            for member in sorted(members):
                digest = hashlib.sha256()
                with archive.open(members[member]) as handle:
                    while block := handle.read(1024 * 1024):
                        digest.update(block)
                current = dependency["extract"] + "/" + member
                row = a.match(current, digest.hexdigest(), "expanded_build_input:" + current, members[member].file_size)
                if row.get("sha256"):
                    digests[current] = row["sha256"]
                if not row["matches"]:
                    mismatch_names.append(current)
            expanded.append({"dependency": dependency["name"], "archive": archive_name,
                             "archive_sha256": pins[archive_name], "selected_subtrees": list(selected),
                             "file_count": len(members), "bytes": sum(entry.file_size for entry in members.values()),
                             "actual_files_sha256": digests, "mismatches": mismatch_names,
                             "archive_membership_matches": actual_names == set(members)})
        print(json.dumps({"event": "expanded_dependencies_checked", "utc": utc_now(),
                          "dependency": dependency["name"], "files": len(members), "mismatches": len(mismatch_names)}),
              file=sys.stderr, flush=True)

    a.finish_stability()
    return {"passed": all(a.checks.values()), "checks": a.checks, "failures": a.failures,
            "execution_phase": 7, "native_suite_reexecuted": False, "new_native_35_execution": False,
            "phase6_acceptance_inherited": False, "integration_tests_still_required": True,
            "accepted_phase7_native_execution": {"suite": a.record(suite_name), "staging": a.record(stage_name),
                "suite_legacy_schema": suite["schema"], "suite_legacy_phase_field": suite.get("phase"),
                "scope": "The historical suite schema and solver filenames say Phase6; this exact report is the freshly reexecuted Phase7 qualification, bound by the accepted Phase7 final receipt. No older Phase6 acceptance is used.",
                "metrics": suite["metrics"]},
            "accepted_final": a.record(FINAL), "accepted_manifest": a.record(manifest_name),
            "accepted_build_receipt_generator": a.record(build_generator_name),
            "build_receipt_source_scope": "The accepted source_hashes generator includes native .h/.cpp/.json/.txt/.ps1/.py files and Physics/configs. Its three .md documentation files are separately bound by the package manifest and fresh Phase7 staging receipt.",
            "preservation_baseline": a.record(baseline_name),
            "native_binary_sha256": binary_digest, "physical_asset_sha256": asset_digest,
            "physical_mesh": physical, "native_source_inputs": source_rows,
            "native_test_harness_inputs": harness_rows, "runtime_inputs": runtime_rows,
            "runtime_dll_count": sum(Path(row["path"]).suffix.lower() == ".dll" for row in runtime_rows),
            "generated_runtime_metadata": generated_metadata, "unused_root_legacy_alias": unused_alias,
            "dependency_artifacts": dependency_rows, "expanded_build_inputs": expanded,
            "bound_distinct_files": len(a.records), "bound_distinct_bytes": sum(row["bytes"] for row in a.records.values()),
            "required_native_launch_contract": {"executable": "Physics/runtime/LapPhysics.exe", "arguments": ["--phase6", "--mesh", mesh],
                "scope": "Identity inheritance applies to this explicit mesh selection. Integration evidence must verify the actual running process, mesh identity, effective configuration, and UE/native pairing."},
            "compiler_provenance": {key: post_metadata.get(key) for key in ("compiler", "windows_sdk", "cmake", "build_configuration")},
            "scope": "Exact current native/source/runtime/dependency/physical-input identity against the accepted freshly executed Phase7 35-case suite. No new Phase8 native execution or rebuild. Integration, packaged interaction, replay, geometry, rendering and data acceptance remain separate mandatory gates. Pinned archives and expanded build inputs establish current dependency identity; historical compiler binaries are represented only by the accepted recorded toolchain versions."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--mesh", default="Assets/Phase8/physics-mesh.json")
    parser.add_argument("--preservation-baseline", default="tmp/phase8/preserved-baseline.json")
    args = parser.parse_args()
    root = Path(os.path.abspath(args.root))
    checked_ancestors(root)
    report = args.report if args.report.is_absolute() else root / args.report
    report = Path(os.path.abspath(report))
    relative = report.relative_to(root)
    if (relative.parent.as_posix() != "tmp/phase8" or not report.name.startswith("native-inheritance")
            or report.suffix != ".json"):
        parser.error("--report must be tmp/phase8/native-inheritance*.json")
    member_path(root, args.mesh)
    member_path(root, args.preservation_baseline)
    started, clock_start = utc_now(), time.monotonic()
    result = {"schema": "endoforge.phase8.native-inheritance.v1", "phase": 8, "started_utc": started}
    try:
        result.update(audit(root, args.mesh, args.preservation_baseline))
    except Exception as exc:
        result.update(passed=False, native_suite_reexecuted=False, new_native_35_execution=False,
                      integration_tests_still_required=True, error_type=type(exc).__name__, error=str(exc))
    result.update(completed_utc=utc_now(), elapsed_seconds=round(time.monotonic() - clock_start, 3),
                  helper_sha256=sha(Path(__file__)), preservation_helper_sha256=sha(Path(__file__).with_name("preservation.py")))
    atomic_json(report, result, replace=True)
    print(json.dumps({"report": relative.as_posix(), "sha256": sha(report),
                      **{key: result.get(key) for key in ("passed", "started_utc", "completed_utc", "elapsed_seconds", "bound_distinct_files", "bound_distinct_bytes", "native_binary_sha256", "physical_asset_sha256", "error_type", "error")},
                      "failed_checks": len(result.get("failures", []))}), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
