"""Seal, create and verify a fresh Phase8 ZIP without overwriting any output.

Adapted from Scripts/Phase7/archive.py. Only sealed manifest files enter the ZIP;
runtime session/cache files stay outside it. ZIP membership, CRC and SHA-256 are
checked before extraction. Every mutation is confined to output/Phase8. Reports
stay outside the package tree to avoid self-referential checksums. No deletion or
replacement is performed, including after a failed operation.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile


MANIFEST = 'package-manifest.json'
RECEIPT = 'phase8-build-receipt.json'
ZIP_ROOT = 'EndoForge/'
EXCLUDED_PARTS = {'Logs', 'Sessions', 'Saved', '__pycache__'}
EXCLUDED_SUFFIXES = {'.blend1', '.pyc', '.pdb'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def member_name(name):
    require(isinstance(name, str) and bool(name), 'Missing member name')
    parts = PurePosixPath(name).parts
    require(name == '/'.join(parts) and parts and not name.startswith('/')
            and all(part not in ('.', '..') and not part.endswith((' ', '.'))
                    and not any(ord(c) < 32 or c in '\\:<>"|?*' for c in part)
                    for part in parts), 'Unsafe/noncanonical member name: ' + name)
    devices = {'CON', 'PRN', 'AUX', 'NUL'} | {prefix + str(i) for prefix in ('COM', 'LPT') for i in range(1, 10)}
    require(all(part.split('.')[0].upper() not in devices for part in parts),
            'Reserved Windows member name: ' + name)
    return name


def safe_child(root, name):
    member_name(name)
    root = root.resolve()
    path = (root / name).resolve()
    require(path.is_relative_to(root) and path != root, 'Path escapes package: ' + name)
    return path


def receipt_phase8(value):
    require(isinstance(value, dict) and value.get('schema') == 'endoforge.phase8.build.v1'
            and type(value.get('phase')) is int and value['phase'] == 8,
            'A Phase8 identity-bound build receipt is required')


def manifest_rows(value):
    require(isinstance(value, list) and bool(value), 'Empty/invalid manifest')
    names = set()
    for row in value:
        require(isinstance(row, dict), 'Invalid manifest row')
        name = member_name(row.get('path'))
        require(name != MANIFEST and name.casefold() not in names, 'Self/duplicate manifest member: ' + name)
        names.add(name.casefold())
        require(type(row.get('bytes')) is int and row['bytes'] >= 0
                and isinstance(row.get('sha256'), str)
                and re.fullmatch('[0-9a-f]{64}', row['sha256']), 'Invalid manifest size/hash: ' + name)
    require(RECEIPT.casefold() in names, 'Manifest omits the Phase8 build receipt')
    return value


def package_files(root, *, exact=False):
    files = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'Package symlinks are unsupported: ' + str(path))
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        if name == MANIFEST:
            continue
        if not exact and (set(Path(name).parts) & EXCLUDED_PARTS or path.suffix.lower() in EXCLUDED_SUFFIXES):
            continue
        member_name(name)
        require(path.resolve().is_relative_to(root.resolve()), 'Package member escapes its root: ' + name)
        files[name] = path
    require(len({name.casefold() for name in files}) == len(files), 'Case-colliding package members')
    return files


def verify(root, *, exact=False):
    receipt_phase8(json.loads((root / RECEIPT).read_text(encoding='utf-8-sig')))
    rows = manifest_rows(json.loads((root / MANIFEST).read_text(encoding='utf-8-sig')))
    files = package_files(root, exact=exact)
    expected = {row['path'] for row in rows}
    require(set(files) == expected, 'Package/manifest membership mismatch: '
            + json.dumps({'missing': sorted(expected - set(files)), 'extra': sorted(set(files) - expected)}))
    for row in rows:
        path = safe_child(root, row['path'])
        require(path.is_file() and path.stat().st_size == row['bytes'] and sha(path) == row['sha256'],
                'Manifest mismatch: ' + row['path'])
    return rows


def verify_zip(archive):
    with zipfile.ZipFile(archive) as zipped:
        infos = zipped.infolist()
        names = []
        for info in infos:
            require(info.filename.startswith(ZIP_ROOT) and not info.is_dir()
                    and not stat.S_ISLNK(info.external_attr >> 16) and not info.flag_bits & 1,
                    'Unexpected ZIP root/directory/link/encryption: ' + info.filename)
            names.append(member_name(info.filename[len(ZIP_ROOT):]))
        require(len(set(name.casefold() for name in names)) == len(names), 'Duplicate/case-colliding ZIP members')
        require(MANIFEST in names, 'ZIP has no package manifest')
        manifest_bytes = zipped.read(ZIP_ROOT + MANIFEST)
        rows = manifest_rows(json.loads(manifest_bytes.decode('utf-8-sig')))
        expected = {row['path'] for row in rows} | {MANIFEST}
        require(set(names) == expected, 'ZIP membership differs from manifest: '
                + json.dumps({'missing': sorted(expected - set(names)), 'extra': sorted(set(names) - expected)}))
        bad = zipped.testzip()
        require(bad is None, 'Archive CRC failed: ' + str(bad))
        for row in rows:
            info = zipped.getinfo(ZIP_ROOT + row['path'])
            require(info.file_size == row['bytes'], 'ZIP manifest size mismatch: ' + row['path'])
            with zipped.open(info) as stream:
                require(hashlib.file_digest(stream, 'sha256').hexdigest() == row['sha256'],
                        'ZIP manifest SHA-256 mismatch: ' + row['path'])
        receipt_phase8(json.loads(zipped.read(ZIP_ROOT + RECEIPT).decode('utf-8-sig')))
    return rows, hashlib.sha256(manifest_bytes).hexdigest()


def phase8_path(path, workspace, label):
    path = path.resolve()
    declared = workspace / 'output/Phase8'
    allowed = declared.resolve()
    require(allowed == declared, 'output/Phase8 must not redirect to another directory')
    require(path.is_relative_to(allowed) and path != allowed,
            label + ' must be a child of output/Phase8')
    return path


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('seal', 'create', 'extract', 'verify'))
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    workspace = Path(__file__).resolve().parents[2]
    package = phase8_path(args.package, workspace, 'Package/extraction destination')
    archive = phase8_path(args.archive, workspace, 'Archive') if args.archive else None
    report = phase8_path(args.report, workspace, 'Report') if args.report else None
    if archive:
        require(archive.suffix.lower() == '.zip' and not archive.is_relative_to(package),
                'Use a ZIP path outside the package tree')
    if report:
        require(not report.exists() and not report.is_relative_to(package) and report != archive,
                'Use a fresh report outside the package tree and distinct from the archive')
    if args.mode in ('create', 'extract'):
        require(archive is not None, '--archive required')
    if args.mode == 'seal':
        require(archive is None, 'seal does not use --archive')
        require(not (package / MANIFEST).exists(), 'Manifest exists; verify it or assemble a fresh package')
        receipt_phase8(json.loads((package / RECEIPT).read_text(encoding='utf-8-sig')))
        rows = [{'path': name, 'bytes': path.stat().st_size, 'sha256': sha(path)}
                for name, path in package_files(package).items()]
        manifest_rows(rows)
        write_new(package / MANIFEST, rows)
        verify(package)
        result = {'sealed': True, 'files': len(rows), 'bytes': sum(row['bytes'] for row in rows)}
    elif args.mode == 'create':
        require(not archive.exists(), 'Use a fresh archive name')
        rows = verify(package)
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as zipped:
            for name in [row['path'] for row in rows] + [MANIFEST]:
                zipped.write(safe_child(package, name), ZIP_ROOT + name)
        archived_rows, manifest_sha = verify_zip(archive)
        require(archived_rows == rows and sha(package / MANIFEST) == manifest_sha,
                'Source manifest changed during archive creation')
        result = {'passed': True, 'archive': str(archive), 'sha256': sha(archive),
                  'bytes': archive.stat().st_size, 'files': len(rows) + 1,
                  'crc_all_files': True, 'sha256_all_manifest_files': True,
                  'exact_manifest_membership': True, 'manifest_sha256': manifest_sha}
    elif args.mode == 'extract':
        require(not package.exists(), 'Fresh extraction destination required')
        archive_sha = sha(archive)
        rows, manifest_sha = verify_zip(archive)
        package.mkdir(parents=True, exist_ok=False)
        with zipfile.ZipFile(archive) as zipped:
            for name in [row['path'] for row in rows] + [MANIFEST]:
                out = safe_child(package, name)
                out.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(ZIP_ROOT + name) as source, out.open('xb') as destination:
                    while data := source.read(2**20):
                        destination.write(data)
        require(verify(package, exact=True) == rows and sha(package / MANIFEST) == manifest_sha,
                'Extracted manifest differs from verified ZIP')
        require(sha(archive) == archive_sha, 'Archive changed during extraction')
        result = {'passed': True, 'archive_sha256': archive_sha, 'extracted_to': str(package),
                  'verified_files': len(rows), 'crc_all_files': True,
                  'sha256_all_manifest_files': True, 'exact_manifest_membership': True,
                  'manifest_sha256': manifest_sha}
    else:
        rows = verify(package)
        result = {'passed': True, 'verified_files': len(rows), 'package': str(package),
                  'sha256_all_manifest_files': True, 'exact_manifest_membership': True,
                  'runtime_exclusions': sorted(EXCLUDED_PARTS),
                  'runtime_excluded_suffixes': sorted(EXCLUDED_SUFFIXES),
                  'manifest_sha256': sha(package / MANIFEST)}
        if archive:
            archived_rows, manifest_sha = verify_zip(archive)
            require(archived_rows == rows and manifest_sha == result['manifest_sha256'],
                    'Archive and package manifests differ')
            result.update(archive_sha256=sha(archive), crc_all_files=True)
    result.update(schema='endoforge.phase8.archive.v1', phase=8, mode=args.mode)
    if report:
        write_new(report, result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
