"""Fresh SHA-256 inventory and strict verification of pre-Phase8 deliveries.

Based on Scripts/Phase7/preservation.py. All protected files are read only.
Directory walks reject links and Windows reparse points before descending.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
import time


SCHEMA = "endoforge.phase8.preservation.v1"
FOLDERS = [
    "output/Phase1", "output/Phase2", "output/Phase3", "output/Phase4",
    "output/Phase4-CollisionFix", "output/Phase5", "output/Phase6", "output/Phase7",
    "Assets/Phase5", "Assets/Phase6", "Assets/Phase7", "source",
    "Prototype/LapTrainer/Content/Phase5", "Prototype/LapTrainer/Content/Phase6",
    "Prototype/LapTrainer/Content/Phase7",
]
REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def checked_stat(path):
    info = path.stat(follow_symlinks=False)
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & REPARSE:
        raise ValueError(f"Link or reparse point is forbidden: {path}")
    return info


def checked_ancestors(path):
    for item in reversed((path, *path.parents)):
        if item.exists() or item.is_symlink():
            checked_stat(item)


def relative_name(root, path):
    return path.relative_to(root).as_posix()


def member_path(root, name):
    pure = PurePosixPath(name)
    if (not isinstance(name, str) or not name or pure.is_absolute()
            or pure.as_posix() != name or any(x in (".", "..") for x in pure.parts)
            or "\\" in name or ":" in name):
        raise ValueError(f"Invalid project-relative path: {name!r}")
    return root.joinpath(*pure.parts)


def metadata(info):
    return (info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_dev, info.st_ino)


def file_identity(info):
    # Windows Python versions can report different ctime semantics for stat/fstat.
    # Compare identity across APIs, and compare ctime only within the same API.
    return (info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino)


def scan(root):
    """Return file metadata without following any link, junction, or reparse point."""
    files = {}
    directories = {}

    def descend(directory):
        info = checked_stat(directory)
        if not stat.S_ISDIR(info.st_mode):
            raise NotADirectoryError(directory)
        directories[relative_name(root, directory)] = metadata(info)
        with os.scandir(directory) as entries:
            children = sorted(entries, key=lambda item: item.name)
        for entry in children:
            path = Path(entry.path)
            info = checked_stat(path)
            if stat.S_ISDIR(info.st_mode):
                descend(path)
            elif stat.S_ISREG(info.st_mode):
                name = relative_name(root, path)
                if name in files:
                    raise ValueError(f"Duplicate inventory member: {name}")
                files[name] = metadata(info)
            else:
                raise ValueError(f"Unexpected filesystem member: {path}")

    for folder in FOLDERS:
        path = member_path(root, folder)
        checked_ancestors(path)
        descend(path)
    return files, directories


def sha(path, expected_metadata=None):
    before = checked_stat(path)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"Expected regular file: {path}")
    if expected_metadata is not None and metadata(before) != expected_metadata:
        raise RuntimeError(f"File metadata changed before hashing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        before_handle = os.fstat(handle.fileno())
        if file_identity(before_handle) != file_identity(before):
            raise RuntimeError(f"File identity changed while opening: {path}")
        while block := handle.read(4 * 1024 * 1024):
            digest.update(block)
        after_handle = os.fstat(handle.fileno())
    after_path = checked_stat(path)
    if metadata(before_handle) != metadata(after_handle) or metadata(before) != metadata(after_path):
        raise RuntimeError(f"File changed while hashing: {path}")
    return digest.hexdigest()


def inventory(root):
    before_files, before_directories = scan(root)
    rows = []
    summaries = []
    for folder in FOLDERS:
        members = sorted(name for name in before_files if name.startswith(folder + "/"))
        total = 0
        for name in members:
            info = before_files[name]
            rows.append({"path": name, "bytes": info[0],
                         "sha256": sha(member_path(root, name), info)})
            total += info[0]
        summary = {"folder": folder, "file_count": len(members), "bytes": total}
        summaries.append(summary)
        print(json.dumps({"event": "folder_hashed", "utc": utc_now(), **summary}),
              file=sys.stderr, flush=True)
    after_files, after_directories = scan(root)
    if before_files != after_files or before_directories != after_directories:
        raise RuntimeError("Protected membership or metadata changed during inventory; baseline rejected")
    return rows, summaries


def output_path(root, value):
    path = value if value.is_absolute() else root / value
    path = Path(os.path.abspath(path))
    name = relative_name(root, path)
    if any(name == folder or name.startswith(folder + "/") for folder in FOLDERS):
        raise ValueError("Preservation outputs must be outside all protected folders")
    checked_ancestors(path)
    return path


def atomic_json(path, data, replace):
    """Publish a complete JSON file; creation never replaces an existing baseline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    checked_ancestors(path.parent)
    if path.exists() and not replace:
        raise FileExistsError(f"Preservation baseline is immutable: {path}")
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        checked_ancestors(path)
        if replace:
            os.replace(temporary_path, path)
        elif os.name == "nt":
            # Windows rename is atomic and fails if the destination already exists.
            os.rename(temporary_path, path)
        else:
            os.link(temporary_path, path)
            temporary_path.unlink()
    except BaseException:
        # Preserve an unpublished temporary file as a diagnostic; never delete evidence.
        raise


def validate_baseline(data):
    if data.get("schema") != SCHEMA or data.get("folders") != FOLDERS:
        raise ValueError("Unexpected baseline schema or protected scope")
    files = data.get("files")
    if not isinstance(files, list):
        raise ValueError("Baseline files must be a list")
    seen = set()
    for row in files:
        name = row["path"]
        member_path(Path("."), name)
        if name.casefold() in seen or not any(name.startswith(x + "/") for x in FOLDERS):
            raise ValueError(f"Duplicate or out-of-scope baseline member: {name}")
        seen.add(name.casefold())
        digest = row["sha256"]
        if (not isinstance(row["bytes"], int) or isinstance(row["bytes"], bool) or row["bytes"] < 0
                or not isinstance(digest, str) or len(digest) != 64
                or any(x not in "0123456789abcdef" for x in digest)):
            raise ValueError(f"Invalid baseline file record: {name}")
    if data.get("file_count") != len(files) or data.get("bytes") != sum(x["bytes"] for x in files):
        raise ValueError("Baseline totals do not match its file records")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["create", "verify"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--report", type=Path, help="Required for verify; optional create receipt")
    args = parser.parse_args()
    started = utc_now()
    clock_start = time.monotonic()
    root = Path(os.path.abspath(args.root))
    checked_ancestors(root)
    if not root.is_dir():
        raise NotADirectoryError(root)
    baseline = output_path(root, args.baseline)
    report = output_path(root, args.report) if args.report is not None else None
    if args.mode == "verify" and report is None:
        parser.error("--report is required for verify")
    if report == baseline:
        parser.error("--report must differ from --baseline")
    receipt = {"schema": "endoforge.phase8.preservation-check.v1" if args.mode == "verify"
               else "endoforge.phase8.preservation-create.v1",
               "mode": args.mode, "started_utc": started,
               "baseline": relative_name(root, baseline),
               "hash_algorithm": "SHA-256", "hash_reuse": "none; every protected byte read afresh",
               "reparse_policy": "reject links and all Windows reparse points",
               "scope_stability": "file and directory membership/metadata checked before and after hashing"}
    try:
        if args.mode == "create":
            if baseline.exists():
                raise FileExistsError(f"Preservation baseline is immutable: {baseline}")
            rows, summaries = inventory(root)
            data = {"schema": SCHEMA, "folders": FOLDERS, "started_utc": started,
                    "completed_utc": utc_now(), "hash_algorithm": "SHA-256",
                    "hash_reuse": receipt["hash_reuse"], "reparse_policy": receipt["reparse_policy"],
                    "scope_stability": receipt["scope_stability"], "files": rows,
                    "file_count": len(rows), "bytes": sum(x["bytes"] for x in rows),
                    "folder_totals": summaries}
            atomic_json(baseline, data, replace=False)
            receipt.update(passed=True, file_count=data["file_count"], bytes=data["bytes"],
                           folder_totals=summaries, baseline_sha256=sha(baseline))
        else:
            baseline_before = metadata(checked_stat(baseline))
            expected = json.loads(baseline.read_text(encoding="utf-8"))
            validate_baseline(expected)
            baseline_digest = sha(baseline, baseline_before)
            rows, summaries = inventory(root)
            old = {row["path"]: row for row in expected["files"]}
            new = {row["path"]: row for row in rows}
            missing = sorted(old.keys() - new.keys())
            added = sorted(new.keys() - old.keys())
            changed = sorted(name for name in old.keys() & new.keys()
                             if old[name]["bytes"] != new[name]["bytes"]
                             or old[name]["sha256"] != new[name]["sha256"])
            if metadata(checked_stat(baseline)) != baseline_before or sha(baseline) != baseline_digest:
                raise RuntimeError("Preservation baseline changed during verification")
            receipt.update(passed=not (missing or added or changed), file_count=len(rows),
                           expected_file_count=len(old), bytes=sum(x["bytes"] for x in rows),
                           baseline_sha256=baseline_digest, folder_totals=summaries,
                           missing=missing, added=added, changed=changed)
    except Exception as exc:
        receipt.update(passed=False, error_type=type(exc).__name__, error=str(exc))
    receipt.update(completed_utc=utc_now(), elapsed_seconds=round(time.monotonic() - clock_start, 3))
    if report is not None:
        atomic_json(report, receipt, replace=True)
    print(json.dumps(receipt, ensure_ascii=False), flush=True)
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
