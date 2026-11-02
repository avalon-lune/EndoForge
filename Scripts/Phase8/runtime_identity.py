"""Bind Phase8 cooked content, authored assets and unchanged native dependencies."""
from pathlib import Path, PurePosixPath

from common import require, sha


LAUNCH_SOURCES = (
    ('StartTrainer.ps1', 'Scripts/StartPhase8.ps1'),
    ('Phase7ProcessPolicy.ps1', 'Scripts/Phase7ProcessPolicy.ps1'),
    ('StartTrainer.cmd', 'Scripts/StartTrainer.cmd'),
    ('TESTING.zh-CN.md', 'Scripts/TESTING-Phase8.zh-CN.md'),
)
IGNORED_SUFFIXES = {'.log', '.blend1', '.pyc'}


def child(root, name):
    pure = PurePosixPath(name)
    require(isinstance(name, str) and name and not pure.is_absolute()
            and pure.as_posix() == name and not {'..', '.'}.intersection(pure.parts)
            and '\\' not in name and ':' not in name, 'Invalid relative identity path: ' + str(name))
    root = Path(root).resolve()
    path = root.joinpath(*pure.parts).resolve()
    require(path.is_relative_to(root), 'Identity path escapes its root: ' + name)
    return path


def ue_files(root):
    root = Path(root)
    files = [p for p in root.iterdir() if p.is_file() and p.suffix.lower() in ('.exe', '.dll')]
    for name in ('Engine', 'LapTrainer'):
        folder = root / name
        if folder.exists():
            files.extend(p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() != '.pdb'
                         and not {'saved', 'logs'}.intersection(x.casefold() for x in p.relative_to(folder).parts))
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(set(files))}


def native_files(runtime):
    runtime = Path(runtime)
    files = [p for p in runtime.iterdir() if p.is_file() and
             (p.suffix.lower() in ('.exe', '.dll') or p.name in ('build-info.json', 'runtime-manifest.txt')
              or p.name.upper().startswith(('LICENSE', 'NOTICE', 'COPYING', 'THIRD-PARTY')))]
    for name in ('licenses', 'etc', 'share', 'configs', 'assets'):
        if (runtime / name).exists():
            files.extend(p for p in (runtime / name).rglob('*') if p.is_file())
    return {'Physics/' + p.relative_to(runtime).as_posix(): sha(p) for p in sorted(set(files))}


def package_files(package):
    return dict(ue_files(package), **native_files(Path(package) / 'Physics'))


def verify(package, receipt, run=None):
    package = Path(package).resolve()
    require(receipt.get('phase') == 8 and receipt.get('schema') == 'endoforge.phase8.build.v1',
            'Expected a Phase8 build receipt')
    expected = receipt['runtime_artifacts_sha256']
    require(expected and any(p.endswith(('.pak', '.utoc', '.ucas')) for p in expected),
            'Missing cooked runtime identity')
    require(package_files(package) == expected, 'Cooked UE content or native runtime differs from the successful build')
    for destination, source in LAUNCH_SOURCES:
        require(sha(package / destination) == receipt['source_asset_sha256'][source],
                'Packaged launch/timing code differs from frozen source: ' + destination)
    expected_assets = {name: digest for name, digest in receipt['source_asset_sha256'].items()
                       if name.startswith('Assets/Phase8/')}
    asset_root = package / 'Assets/Phase8'
    actual_assets = {p.relative_to(package).as_posix(): sha(p) for p in sorted(asset_root.rglob('*'))
                     if p.is_file() and p.suffix.lower() not in IGNORED_SUFFIXES
                     and '__pycache__' not in p.relative_to(asset_root).parts}
    require(expected_assets and actual_assets == expected_assets, 'Packaged Phase8 authored assets differ from frozen source')
    inherited = receipt['native_inheritance']
    require(inherited.get('passed') is True and inherited.get('phase') == 8
            and inherited.get('execution_phase') == 7 and inherited.get('native_suite_reexecuted') is False
            and inherited.get('new_native_35_execution') is False, 'Invalid native inheritance scope')
    require(sha(package / 'Physics/LapPhysics.exe') == inherited['native_binary_sha256']
            and sha(asset_root / 'physics-mesh.json') == inherited['physical_asset_sha256'],
            'Packaged native executable or explicitly selected physical mesh differs from inherited qualification')
    for name, record in receipt['packaged_evidence'].items():
        require(sha(child(package, record['path'])) == record['sha256'], 'Packaged bound evidence differs: ' + name)
    if run is not None:
        require(run.get('phase') == 8 and run.get('runtime_unchanged') is True
                and run['runtime_artifacts_sha256'] == expected, 'Executed runtime differs from successful build')
    return expected
