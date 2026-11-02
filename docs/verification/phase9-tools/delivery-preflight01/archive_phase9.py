"""Create, verify or freshly extract a Phase9 review-candidate ZIP.

Only this evidence helper is new; frozen project sources are never edited.
The Phase8 canonical-name/manifest/ZIP CRC+SHA validators are reused explicitly
with Phase9 receipt and assembly-manifest names. No process or test is launched.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import time
import zipfile


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
ACTUAL_ROOT = ROOT
CORE_PATH = ROOT/'Scripts/Phase8/archive.py'
spec = importlib.util.spec_from_file_location('_phase9_archive_historical_integrity_core', CORE_PATH)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
core.MANIFEST = 'assembly-manifest.json'
core.RECEIPT = 'review-candidate.json'
REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
MUTABLE_PARTS = {'saved', 'logs', 'sessions', '__pycache__'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked(path, existing=True, directory=False):
    path = Path(os.path.abspath(path))
    for member in reversed((path, *path.parents)):
        if member.exists() or member.is_symlink():
            info = member.stat(follow_symlinks=False)
            require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & REPARSE,
                    'Links/reparse points are forbidden: '+str(member))
    if existing:
        require(path.is_dir() if directory else path.is_file(), 'Required input is missing: '+str(path))
    return path


def phase9_path(path, *, existing=True, directory=False):
    path = checked(path, existing=existing, directory=directory)
    allowed = checked(ROOT/'output/Phase9', existing=False)
    require(path.is_relative_to(allowed) and path != allowed, 'Artifacts must be children of output/Phase9')
    return path


def review_receipt(value):
    require(isinstance(value, dict) and value.get('schema') == 'endoforge.phase9.review-candidate.v1'
            and type(value.get('phase')) is int and value['phase'] == 9
            and value.get('candidate_status') == 'review_candidate'
            and value.get('delivery_accepted') is False
            and value.get('human_visual_approval') in ('pending', 'approved'),
            'Expected the explicit Phase9 review-candidate receipt; no final acceptance is inferred')


core.receipt_phase8 = review_receipt


def all_files(folder):
    """Walk without ever descending into a link, junction or reparse point."""
    result = {}
    def descend(directory):
        checked(directory, directory=True)
        for member in sorted(directory.iterdir()):
            info = member.stat(follow_symlinks=False)
            require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & REPARSE,
                    'Links/reparse points are forbidden: '+str(member))
            if stat.S_ISDIR(info.st_mode):
                descend(member)
            elif stat.S_ISREG(info.st_mode):
                name = core.member_name(member.relative_to(folder).as_posix())
                require(name.casefold() not in {key.casefold() for key in result}, 'Case-colliding package member')
                result[name] = member
            else:
                raise ValueError('Unexpected filesystem member: '+str(member))
    descend(folder)
    return result


def verify_tree(folder, allow_runtime_outputs=False):
    receipt_path = checked(folder/core.RECEIPT)
    receipt = json.loads(receipt_path.read_text(encoding='utf-8-sig'))
    review_receipt(receipt)
    manifest_path = checked(folder/core.MANIFEST)
    manifest_before = sha(manifest_path)
    rows = core.manifest_rows(json.loads(manifest_path.read_text(encoding='utf-8-sig')))
    expected = {row['path'] for row in rows} | {core.MANIFEST}
    actual = all_files(folder)
    missing, extra = sorted(expected-actual.keys()), sorted(actual.keys()-expected)
    excluded = [name for name in extra if allow_runtime_outputs
                and set(part.casefold() for part in Path(name).parts) & MUTABLE_PARTS]
    require(not missing and set(extra) == set(excluded),
            'Exact package membership differs: '+json.dumps({'missing':missing,'extra':sorted(set(extra)-set(excluded))}))
    for row in rows:
        path = checked(core.safe_child(folder, row['path']))
        before = path.stat()
        require(before.st_size == row['bytes'] and sha(path) == row['sha256'], 'Manifest SHA/size mismatch: '+row['path'])
        after = path.stat()
        require((before.st_size,before.st_mtime_ns,before.st_ino) == (after.st_size,after.st_mtime_ns,after.st_ino),
                'Package member changed while hashing: '+row['path'])
    require(sha(manifest_path) == manifest_before, 'Candidate manifest changed during verification')
    return rows, manifest_before, sha(receipt_path), sorted(excluded)


def verify_zip(path):
    checked(path)
    with zipfile.ZipFile(path) as zipped:
        require(all(not item.external_attr & REPARSE for item in zipped.infolist()),
                'Windows reparse attributes are forbidden in ZIP members')
    # Historical core rejects traversal/noncanonical/reserved names, duplicates,
    # links, directory entries, encryption, wrong root, CRC or size/SHA errors.
    return core.verify_zip(path)


def report_path(value, candidate, archive, extracted):
    path = checked(value, existing=False)
    require(any(path.is_relative_to(ROOT/name) and path != ROOT/name
                for name in ('tmp/phase9', 'output/Phase9')), 'Reports must remain in Phase9 evidence/output')
    require(not path.exists() and path != archive
            and not path.is_relative_to(candidate)
            and (extracted is None or not path.is_relative_to(extracted)),
            'Use a fresh report outside candidate/extraction trees and distinct from ZIP')
    return path


def run(mode, candidate, archive, report, extracted=None, allow_runtime_outputs=False):
    candidate = phase9_path(candidate, directory=True)
    archive = phase9_path(archive, existing=mode != 'create')
    require(archive.suffix.lower() == '.zip' and not archive.is_relative_to(candidate),
            'Use a ZIP path outside the explicit candidate')
    extracted = phase9_path(extracted, existing=mode != 'extract', directory=mode != 'extract') if extracted is not None else None
    if extracted is not None:
        require(extracted != candidate and not extracted.is_relative_to(candidate)
                and not candidate.is_relative_to(extracted) and not archive.is_relative_to(extracted),
                'Extraction must be separate from the candidate and ZIP')
    require(mode != 'extract' or extracted is not None, 'extract requires --extracted')
    report = report_path(report, candidate, archive, extracted)
    started = datetime.now(timezone.utc).isoformat(); clock = time.monotonic()
    document = {'schema':'endoforge.phase9.archive-integrity.v1','phase':9,'mode':mode,
                'started_utc':started,'candidate':str(candidate),'archive':str(archive),
                'extracted':str(extracted) if extracted else None,
                'helper':{'path':str(Path(__file__).resolve()),'sha256':sha(Path(__file__))},
                'historical_integrity_core':{'path':str(CORE_PATH),'sha256':sha(CORE_PATH)},
                'allow_runtime_outputs':allow_runtime_outputs,'delivery_accepted':False,
                'scope':'Archive integrity only: exact sealed member sizes/SHA256, ZIP CRC and fresh extraction identity. No build, runtime test, aesthetic decision, clinical or final delivery acceptance is implied.',
                'fixture_only':ROOT != ACTUAL_ROOT}
    try:
        rows, manifest_sha, receipt_sha, excluded = verify_tree(candidate, allow_runtime_outputs)
        document.update(candidate_manifest_sha256=manifest_sha,candidate_receipt_sha256=receipt_sha,
                        manifest_file_count=len(rows),manifest_bytes=sum(row['bytes'] for row in rows),
                        excluded_candidate_runtime_outputs=excluded)
        if mode == 'create':
            require(not archive.exists(), 'Archive is immutable; use a fresh ZIP path')
            archive.parent.mkdir(parents=True,exist_ok=True)
            checked(archive.parent,directory=True)
            with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as zipped:
                for name in [row['path'] for row in rows]+[core.MANIFEST]:
                    zipped.write(checked(core.safe_child(candidate,name)),core.ZIP_ROOT+name)
        before_archive = sha(archive)
        document.update(archive_sha256=before_archive,archive_bytes=archive.stat().st_size)
        zip_rows, zip_manifest_sha = verify_zip(archive)
        require(zip_rows == rows and zip_manifest_sha == manifest_sha, 'ZIP and candidate manifest differ')
        if mode == 'extract':
            require(not extracted.exists(), 'Extraction destination is immutable; use a fresh directory')
            extracted.mkdir(parents=True,exist_ok=False)
            with zipfile.ZipFile(archive) as zipped:
                for name in [row['path'] for row in rows]+[core.MANIFEST]:
                    destination = core.safe_child(extracted,name)
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    checked(destination.parent,directory=True)
                    with zipped.open(core.ZIP_ROOT+name) as original,destination.open('xb') as copied:
                        while block := original.read(2**20):
                            copied.write(block)
        if extracted is not None:
            extracted_rows, extracted_manifest, _, excluded_extracted = verify_tree(extracted,
                allow_runtime_outputs if mode == 'verify' else False)
            require(extracted_rows == rows and extracted_manifest == manifest_sha, 'Extracted manifest/membership/SHA differs')
            document.update(extracted_manifest_sha256=extracted_manifest,
                            excluded_extracted_runtime_outputs=excluded_extracted)
        require(sha(archive) == before_archive, 'Archive changed during verification/extraction')
        final_rows, final_manifest, final_receipt, _ = verify_tree(candidate, allow_runtime_outputs)
        require((final_rows,final_manifest,final_receipt)==(rows,manifest_sha,receipt_sha), 'Candidate changed during archive operation')
        document.update(passed=True,archive_sha256=before_archive,archive_bytes=archive.stat().st_size,
                        zip_manifest_sha256=zip_manifest_sha,crc_all_files=True,
                        sha256_all_manifest_files=True,exact_manifest_membership=True,
                        extraction_verified=extracted is not None)
    except Exception as error:
        document.update(passed=False,error_type=type(error).__name__,error=str(error))
    document.update(completed_utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=round(time.monotonic()-clock,3))
    report.parent.mkdir(parents=True,exist_ok=True)
    checked(report.parent,directory=True)
    with report.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(document,stream,indent=2);stream.write('\n')
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('create','verify','extract'))
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--extracted',type=Path)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--allow-runtime-outputs',action='store_true',
                        help='Explicitly exclude only generated Saved/Logs/Sessions/__pycache__ files absent from sealed manifest')
    args = parser.parse_args()
    result = run(args.mode,args.candidate,args.archive,args.report,args.extracted,args.allow_runtime_outputs)
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
