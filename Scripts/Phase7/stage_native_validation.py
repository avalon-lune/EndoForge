"""Stage an isolated Phase6-solver test workspace with the revised Phase7 liver.

The established native test scripts and kernels are copied byte-for-byte. Their
legacy Assets/Phase6 and runtime/assets/phase6.json paths carry the explicitly
identified Phase7 candidate inside this isolated workspace only. Neither the
original runtime nor old assets/deliveries are changed.
"""
import argparse
import json
import shutil
from pathlib import Path
from common import read, require, sha, write_new

GENERATED_METADATA = 'Physics/runtime/build-info.json'


def stage(root, output):
    output=output.resolve()
    require(output.is_relative_to(root/'tmp/phase7') and output != root/'tmp/phase7', 'Isolated workspace must be a fresh child of tmp/phase7')
    require(not output.exists(), 'Use a new native workspace for each physical candidate')
    output.mkdir(parents=True)
    physics=output/'Physics';physics.mkdir()
    for path in (root/'Physics').iterdir():
        if path.is_file() and path.suffix in ('.cpp','.h','.py','.ps1','.json','.txt','.md'):
            shutil.copy2(path,physics/path.name)
    shutil.copytree(root/'Physics/configs',physics/'configs')
    runtime=physics/'runtime';runtime.mkdir()
    for path in (root/'Physics/runtime').iterdir():
        if path.is_file() and (path.suffix.lower() in ('.exe','.dll') or path.name in ('build-info.json','runtime-manifest.txt')
                              or path.name.upper().startswith(('LICENSE','NOTICE','COPYING','THIRD-PARTY'))):
            shutil.copy2(path,runtime/path.name)
    for name in ('licenses','etc','share','configs','assets'):
        if (root/'Physics/runtime'/name).is_dir():shutil.copytree(root/'Physics/runtime'/name,runtime/name)
    unit=physics/'build/Release/Phase6ToolCollisionTests.exe';unit.parent.mkdir(parents=True)
    shutil.copy2(root/'Physics/build/Release/Phase6ToolCollisionTests.exe',unit)
    shutil.copytree(root/'Scripts',output/'Scripts',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copytree(root/'Assets/Phase5',output/'Assets/Phase5',ignore=shutil.ignore_patterns('*.blend1','*.log'))
    shutil.copytree(root/'Assets/Phase7',output/'Assets/Phase6',ignore=shutil.ignore_patterns('*.blend1','*.log'))
    shutil.copy2(root/'Assets/Phase7/physics-mesh.json',physics/'runtime/assets/phase6.json')
    paths=[p for p in sorted(output.rglob('*')) if p.is_file()]
    require((output/GENERATED_METADATA).is_file(), 'Missing runtime build metadata')
    # summarize_phase6_tests legitimately rewrites this receipt after success.
    # It is evidence output, never an executable/configuration dependency.
    metadata_before={GENERATED_METADATA:sha(output/GENERATED_METADATA)}
    files={p.relative_to(output).as_posix():sha(p) for p in paths
           if p.relative_to(output).as_posix()!=GENERATED_METADATA}
    def native_source(name):
        return (name.startswith('Physics/') and '/runtime/' not in name and '/build/' not in name) or name.startswith(('Scripts/Phase6/','Scripts/Phase5/','Scripts/audit_phase4_collision_geometry.py'))
    original_sources={p.relative_to(output).as_posix():sha(root/p.relative_to(output)) for p in paths
                      if native_source(p.relative_to(output).as_posix())}
    require(all(files[k]==v for k,v in original_sources.items()), 'Test/native source copy changed')
    report={'schema':'endoforge.phase7.native-workspace.v1','phase':7,'solver_mode':6,
            'workspace':str(output),'source_phase7_asset_sha256':sha(root/'Assets/Phase7/physics-mesh.json'),
            'native_executable_sha256':sha(root/'Physics/runtime/LapPhysics.exe'),
            'stage_files_sha256':files,'unmodified_test_and_native_sources':original_sources,
            'generated_metadata_before_sha256':metadata_before,
            'generated_metadata_policy':'Only Physics/runtime/build-info.json may be rewritten by the unchanged native summarizer. Qualification validates its post-suite content and binds its final hash; binaries, libraries, configuration and assets remain immutable.',
            'scope':'Fresh execution required. Legacy path aliases contain the Phase7 candidate only in this isolated workspace. No physics acceptance is inherited from Phase6.'}
    write_new(output/'phase7-native-workspace.json',report)
    print(json.dumps({'workspace':str(output),'files':len(files),'asset_sha256':report['source_phase7_asset_sha256']}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();stage(a.root.resolve(),a.output)
