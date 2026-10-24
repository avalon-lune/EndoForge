"""Hash prior deliveries and supplied references without modifying any of them."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def inventory(root, folders):
    rows = []
    for folder in folders:
        directory = root / folder
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        for path in sorted(directory.rglob('*')):
            if path.is_symlink():
                raise ValueError(f'Unexpected link: {path}')
            if path.is_file():
                rows.append({'path': path.relative_to(root).as_posix(),
                             'bytes': path.stat().st_size, 'sha256': sha(path)})
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['create', 'verify'])
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--report', type=Path)
    a = p.parse_args()
    root = a.root.resolve()
    if a.mode == 'create':
        if a.baseline.exists():
            raise FileExistsError('Preservation baseline is immutable')
        folders = ['output/Phase1', 'output/Phase2', 'output/Phase3', 'output/Phase4',
                   'output/Phase4-CollisionFix', 'source']
        files = inventory(root, folders)
        data = {'schema': 'endoforge.phase5.preservation.v1', 'folders': folders,
                'files': files, 'file_count': len(files), 'bytes': sum(x['bytes'] for x in files)}
        a.baseline.parent.mkdir(parents=True, exist_ok=True)
        a.baseline.write_text(json.dumps(data, indent=2), encoding='utf-8')
        print(json.dumps({'file_count': len(files), 'bytes': data['bytes'],
                          'baseline': str(a.baseline), 'sha256': sha(a.baseline)}))
    else:
        if a.report is None:
            raise ValueError('--report required')
        expected = json.loads(a.baseline.read_text(encoding='utf-8'))
        current = inventory(root, expected['folders'])
        old = {f['path']: f for f in expected['files']}
        new = {f['path']: f for f in current}
        missing = sorted(old.keys() - new.keys())
        added = sorted(new.keys() - old.keys())
        changed = sorted(k for k in old.keys() & new.keys() if old[k] != new[k])
        result = {'schema': 'endoforge.phase5.preservation-check.v1',
                  'passed': not (missing or added or changed), 'file_count': len(old),
                  'baseline_sha256': sha(a.baseline), 'missing': missing,
                  'added': added, 'changed': changed}
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result))
        if not result['passed']:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
