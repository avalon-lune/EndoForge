"""Bind cooked UE content and native runtime dependencies, excluding run outputs."""
from pathlib import Path
from common import require, sha


def ue_files(root):
    root=Path(root)
    files=[p for p in root.iterdir() if p.is_file() and p.suffix.lower() in ('.exe','.dll')]
    for name in ('Engine','LapTrainer'):
        folder=root/name
        if folder.exists():
            files.extend(p for p in folder.rglob('*') if p.is_file() and p.suffix.lower()!='.pdb'
                         and not {'saved','logs'}.intersection(x.casefold() for x in p.relative_to(folder).parts))
    return {p.relative_to(root).as_posix():sha(p) for p in sorted(files)}


def native_files(runtime):
    runtime=Path(runtime)
    files=[p for p in runtime.iterdir() if p.is_file() and
           (p.suffix.lower() in ('.exe','.dll') or p.name in ('build-info.json','runtime-manifest.txt')
            or p.name.upper().startswith(('LICENSE','NOTICE','COPYING','THIRD-PARTY')))]
    for name in ('licenses','etc','share','configs','assets'):
        if (runtime/name).exists():files.extend(p for p in (runtime/name).rglob('*') if p.is_file())
    return {'Physics/'+p.relative_to(runtime).as_posix():sha(p) for p in sorted(files)}


def package_files(package):
    return dict(ue_files(package),**native_files(Path(package)/'Physics'))


def verify(package,receipt,run=None):
    expected=receipt['runtime_artifacts_sha256']
    require(expected and any(p.endswith(('.pak','.utoc','.ucas')) for p in expected), 'Missing cooked runtime identity')
    require(package_files(package)==expected, 'Cooked UE content or runtime dependency differs from successful build')
    for destination, source in (('StartTrainer.ps1','Scripts/StartPhase7.ps1'),
                                ('Phase7ProcessPolicy.ps1','Scripts/Phase7ProcessPolicy.ps1'),
                                ('StartTrainer.cmd','Scripts/StartTrainer.cmd')):
        require(sha(Path(package)/destination)==receipt['source_asset_sha256'][source],
                'Packaged launch/timing code differs from the frozen source: '+destination)
    if run is not None:
        require(run['runtime_artifacts_sha256']==expected and run['runtime_unchanged'] is True, 'Executed runtime artifacts differ from successful build')
    return expected
