"""Capture exact source/asset and final binary identities after a successful UAT build."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path


def sha(path):
    with path.open('rb') as handle: return hashlib.file_digest(handle,'sha256').hexdigest()


def source_hashes(root):
    files=[]
    for folder in ('Prototype/LapTrainer/Source','Prototype/LapTrainer/Config',
                   'Prototype/LapTrainer/Content','Prototype/LapTrainer/Scripts',
                   'Assets/Phase6','Scripts/BlenderPhase6','Scripts/BlenderPhase5','Scripts/Phase6'):
        files.extend(p for p in (root/folder).rglob('*') if p.is_file() and p.suffix not in ('.log','.blend1','.pyc'))
    files.append(root/'Prototype/LapTrainer/LapTrainer.uproject')
    files.extend(root/'Assets/Phase5'/name for name in ('physics-mesh.json','scene.json'))
    for name in ('StartPhase6.ps1', 'TestPhase6Package.ps1', 'README-Phase6.md'):
        files.append(root/'Scripts'/name)
    for p in (root/'Physics').iterdir():
        if p.is_file() and p.suffix in ('.h','.cpp','.json','.txt','.ps1','.py'):
            files.append(p)
    return {p.relative_to(root).as_posix():sha(p) for p in sorted(set(files))}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--ue-package',type=Path,required=True)
    p.add_argument('--package-log',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); root=a.root.resolve()
    log=a.package_log.read_text(encoding='utf-8-sig',errors='replace')
    if 'BUILD SUCCESSFUL' not in log or 'AutomationTool exiting with ExitCode=0' not in log:
        raise RuntimeError('Successful final UAT build/cook/package evidence is required')
    game=a.ue_package/'LapTrainer/Binaries/Win64/LapTrainer.exe'
    native=root/'Physics/runtime/LapPhysics.exe'
    # Bind the packaged build to the editor validation freeze, not just to the
    # source files present at receipt creation time.
    frozen_path=root/'tmp/phase6/ue-final-validation.json'
    frozen=json.loads(frozen_path.read_text(encoding='utf-8-sig'))
    assert frozen['source_frozen'] is True and frozen['protocol']['passed'] is True
    for item in frozen['source_files']+frozen['additional_build_inputs']+frozen['assets']:
        assert sha(root/item['path'])==item['sha256'], 'Changed frozen build input: '+item['path']
    freeze=datetime.datetime.fromisoformat(frozen['created_utc'].replace('Z','+00:00')).timestamp()
    assert a.package_log.stat().st_mtime>=freeze and game.stat().st_mtime>=freeze, 'UAT/game predates validated source freeze'
    data={'phase':6,'schema':'endoforge.phase6.build.v1',
          'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'physics_exe_sha256':sha(native),'game_exe_sha256':sha(game),
          'package_log_sha256':sha(a.package_log),'source_asset_sha256':source_hashes(root),
          'ue_validation_receipt_sha256':sha(frozen_path),'ue_frozen_inputs_match':True}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(data,indent=2),encoding='utf-8')
    print(json.dumps({'receipt':str(a.output),'source_asset_files':len(data['source_asset_sha256']),
                      'physics_exe_sha256':data['physics_exe_sha256'],'game_exe_sha256':data['game_exe_sha256']}))
