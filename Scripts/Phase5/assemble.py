"""Assemble a fresh Phase 5 candidate; old deliveries are never destinations."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def copy_tree(src,dst,ignore=None):
    if not src.is_dir(): raise FileNotFoundError(src)
    shutil.copytree(src,dst,ignore=ignore)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--ue-package',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--build-receipt',type=Path,required=True)
    a=p.parse_args(); root=a.root.resolve(); out=a.output.resolve(); ue=a.ue_package.resolve()
    allowed=root/'output'
    if not out.is_relative_to(allowed) or out.parts[len(allowed.parts)] not in ('Phase5','verification'):
        raise ValueError('Phase 5 output must stay inside output/Phase5 or output/verification')
    if out.exists(): raise FileExistsError('Use a fresh candidate directory')
    runtime=root/'Physics/runtime'; assets=root/'Assets/Phase5'
    for f in (ue/'LapTrainer.exe',ue/'LapTrainer/Binaries/Win64/LapTrainer.exe',
              runtime/'LapPhysics.exe',assets/'physics-mesh.json',assets/'scene.json',a.build_receipt):
        if not f.is_file(): raise FileNotFoundError(f)
    receipt=json.loads(a.build_receipt.read_text(encoding='utf-8-sig'))
    if receipt['phase']!=5 or receipt['physics_exe_sha256']!=sha(runtime/'LapPhysics.exe') or receipt['game_exe_sha256']!=sha(ue/'LapTrainer/Binaries/Win64/LapTrainer.exe'):
        raise ValueError('The candidate binaries differ from the successful build receipt')
    for name,digest in receipt['source_asset_sha256'].items():
        if sha(root/name)!=digest: raise ValueError('Source or asset changed after build receipt: '+name)
    copy_tree(ue,out,ignore=shutil.ignore_patterns('*.pdb','Saved','Logs'))
    pd=out/'Physics'; pd.mkdir()
    for f in runtime.iterdir():
        if f.is_file() and (f.suffix.lower() in ('.exe','.dll') or
                           f.name in ('build-info.json','runtime-manifest.txt') or
                           f.name.upper().startswith(('LICENSE','NOTICE','COPYING','THIRD-PARTY'))):
            shutil.copy2(f,pd/f.name)
    for name in ('licenses','etc','share','configs','assets'):
        if (runtime/name).is_dir(): copy_tree(runtime/name,pd/name)
    copy_tree(assets,out/'Assets/Phase5',ignore=shutil.ignore_patterns('*.blend1','*.log','__pycache__'))
    shutil.copy2(root/'Scripts/StartPhase5.ps1',out/'StartTrainer.ps1')
    shutil.copy2(root/'Scripts/StartTrainer.cmd',out/'StartTrainer.cmd')
    shutil.copy2(root/'Scripts/README-Phase5.md',out/'README.md')
    src=out/'Source'; src.mkdir()
    physics=src/'Physics'; physics.mkdir()
    for f in (root/'Physics').iterdir():
        if f.is_file() and f.suffix.lower() in ('.cpp','.h','.ps1','.py','.json','.txt','.md'):
            shutil.copy2(f,physics/f.name)
    copy_tree(root/'Physics/configs',physics/'configs')
    up=src/'Prototype/LapTrainer'; up.mkdir(parents=True)
    shutil.copy2(root/'Prototype/LapTrainer/LapTrainer.uproject',up/'LapTrainer.uproject')
    for folder in ('Source','Config','Content','Scripts'):
        copy_tree(root/'Prototype/LapTrainer'/folder,up/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    copy_tree(root/'Scripts',src/'Scripts',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    copy_tree(assets,src/'Assets/Phase5',ignore=shutil.ignore_patterns('*.blend1','*.log','__pycache__'))
    copy_tree(root/'docs',src/'docs')
    for name in ('README.md','LICENSE','.gitattributes','.gitignore'):
        if (root/name).is_file(): shutil.copy2(root/name,src/name)
    deps=src/'Dependencies'; deps.mkdir()
    shutil.copy2(root/'ThirdParty/SOFA/sofa-v26.06.00-source.zip',deps/'sofa-v26.06.00-source.zip')
    shutil.copy2(a.build_receipt,out/'phase5-build-receipt.json')
    for name,digest in receipt['source_asset_sha256'].items():
        if sha(root/name)!=digest: raise ValueError('Source or asset changed during assembly: '+name)
    manifest=[{'path':f.relative_to(out).as_posix(),'bytes':f.stat().st_size,'sha256':sha(f)}
              for f in sorted(out.rglob('*')) if f.is_file()]
    (out/'package-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'files':len(manifest),'bytes':sum(f['bytes'] for f in manifest),
                      'physics_sha256':sha(pd/'LapPhysics.exe'),
                      'game_sha256':sha(out/'LapTrainer/Binaries/Win64/LapTrainer.exe')}))


if __name__=='__main__': main()
