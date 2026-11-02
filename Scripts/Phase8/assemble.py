"""Assemble a fresh Phase8 candidate without modifying prior deliveries/runtime."""
import argparse
import json
from pathlib import Path
import shutil

from common import read, require, sha, write_new
from build_receipt import bound_record, distribution_inputs, source_hashes, verify_inheritance
from runtime_identity import child, native_files, ue_files, verify as verify_runtime


IGNORE = shutil.ignore_patterns('*.blend1', '*.log', '*.pyc', '__pycache__')


def copy_tree(source, destination, ignore=IGNORE):
    require(source.is_dir(), 'Missing source directory: ' + str(source))
    shutil.copytree(source, destination, ignore=ignore)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'ue-package', 'output', 'build-receipt'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    root, ue, out = args.root.resolve(), args.ue_package.resolve(), args.output.resolve()
    allowed = root / 'output/Phase8'
    require(out.is_relative_to(allowed) and out != allowed, 'Assembly destination must be a fresh child of output/Phase8')
    require(not out.exists(), 'Use a fresh Phase8 candidate directory')
    receipt = read(args.build_receipt)
    require(receipt.get('schema') == 'endoforge.phase8.build.v1' and receipt.get('phase') == 8,
            'Expected a Phase8 build receipt')
    require(source_hashes(root) == receipt['source_asset_sha256'], 'Current source/assets differ from frozen build')
    native = root / 'Physics/runtime'
    assets = root / 'Assets/Phase8'
    require(sha(native / 'LapPhysics.exe') == receipt['physics_exe_sha256']
            and sha(ue / 'LapTrainer/Binaries/Win64/LapTrainer.exe') == receipt['game_exe_sha256'],
            'Candidate binaries differ from the successful build receipt')
    inheritance_path = bound_record(root, receipt['native_inheritance']['source_receipt'])
    inherited = verify_inheritance(root, inheritance_path)
    require(sha(inheritance_path) == receipt['native_inheritance_receipt_sha256'], 'Native inheritance receipt changed')
    validation_path = bound_record(root, receipt['ue_validation_receipt'])
    inputs = distribution_inputs(root, inherited)
    require(inputs == receipt['distribution_inputs'], 'Native metadata or source-distribution input changed')
    runtime = dict(ue_files(ue), **native_files(native))
    runtime['Physics/build-info.json'] = inputs['native_metadata']['sha256']
    runtime['Physics/assets/phase6.json'] = inherited['physical_asset_sha256']
    require(runtime == receipt['runtime_artifacts_sha256'], 'Cooked content/native runtime changed after build receipt')
    copy_tree(ue, out, shutil.ignore_patterns('*.pdb', 'Saved', 'Logs'))
    physics = out / 'Physics'
    physics.mkdir()
    for path in native.iterdir():
        if path.is_file() and (path.suffix.lower() in ('.exe', '.dll') or path.name in ('build-info.json', 'runtime-manifest.txt')
                              or path.name.upper().startswith(('LICENSE', 'NOTICE', 'COPYING', 'THIRD-PARTY'))):
            shutil.copy2(path, physics / path.name)
    for name in ('licenses', 'etc', 'share', 'configs', 'assets'):
        if (native / name).is_dir():
            copy_tree(native / name, physics / name, ignore=None)
    # Copy the accepted post-suite receipt verbatim; never relabel native tests as Phase8.
    shutil.copy2(bound_record(root, inputs['native_metadata']), physics / 'build-info.json')
    (physics / 'assets').mkdir(exist_ok=True)
    shutil.copy2(assets / 'physics-mesh.json', physics / 'assets/phase6.json')
    copy_tree(assets, out / 'Assets/Phase8')
    for source, destination in (('Scripts/StartPhase8.ps1', 'StartTrainer.ps1'),
                                ('Scripts/Phase7ProcessPolicy.ps1', 'Phase7ProcessPolicy.ps1'),
                                ('Scripts/StartTrainer.cmd', 'StartTrainer.cmd'),
                                ('Scripts/README-Phase8-Delivery.md', 'README.md'),
                                ('Scripts/TESTING-Phase8.zh-CN.md', 'TESTING.zh-CN.md')):
        shutil.copy2(root / source, out / destination)
    source = out / 'Source'
    source.mkdir()
    native_source = source / 'Physics'
    native_source.mkdir()
    for path in (root / 'Physics').iterdir():
        if path.is_file() and path.suffix.lower() in ('.cpp', '.h', '.ps1', '.py', '.json', '.txt', '.md'):
            shutil.copy2(path, native_source / path.name)
    copy_tree(root / 'Physics/configs', native_source / 'configs')
    project = source / 'Prototype/LapTrainer'
    project.mkdir(parents=True)
    shutil.copy2(root / 'Prototype/LapTrainer/LapTrainer.uproject', project / 'LapTrainer.uproject')
    for name in ('Source', 'Config', 'Content', 'Scripts'):
        copy_tree(root / 'Prototype/LapTrainer' / name, project / name)
    copy_tree(root / 'Scripts', source / 'Scripts')
    for phase in ('Phase5', 'Phase6', 'Phase7', 'Phase8'):
        copy_tree(root / 'Assets' / phase, source / 'Assets' / phase)
    copy_tree(root / 'docs', source / 'docs')
    for name in ('README.md', 'LICENSE', '.gitattributes', '.gitignore'):
        if (root / name).is_file():
            shutil.copy2(root / name, source / name)
    for name in ('tmp/phase8/import_phase8.py', 'tmp/phase8/run_import.ps1'):
        if (root / name).is_file():
            destination = source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / name, destination)
    dependencies = source / 'Dependencies'
    dependencies.mkdir()
    shutil.copy2(bound_record(root, inputs['sofa_source']), dependencies / 'sofa-v26.06.00-source.zip')
    shutil.copy2(inheritance_path, out / receipt['packaged_evidence']['native_inheritance']['path'])
    shutil.copy2(validation_path, out / receipt['packaged_evidence']['ue_validation']['path'])
    shutil.copy2(args.build_receipt, out / 'phase8-build-receipt.json')
    verify_runtime(out, receipt)
    require(source_hashes(root) == receipt['source_asset_sha256'], 'Root inputs changed during assembly')
    for name, digest in receipt['source_asset_sha256'].items():
        require(sha(child(source, name)) == digest, 'Shipped editable source differs from frozen input: ' + name)
    rows = [{'path': path.relative_to(out).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
            for path in sorted(out.rglob('*')) if path.is_file()]
    # Candidate evidence is added after execution. Seal the final archive only
    # after that addition; retain this initial assembly identity separately.
    write_new(out / 'assembly-manifest.json', rows)
    print(json.dumps({'output': str(out), 'files': len(rows), 'bytes': sum(row['bytes'] for row in rows),
                      'native_execution_phase': 7, 'native_suite_reexecuted': False, 'new_native_35_execution': False}))


if __name__ == '__main__':
    main()
