"""Record a fresh Phase8 UAT build against frozen UE inputs and native inheritance.

No native build or simulation is launched. The existing native inheritance report
is rechecked against its recorded inputs, never represented as a new native suite.
"""
import argparse
import datetime
import json
from pathlib import Path

from common import read, require, sha, write_new
from runtime_identity import child, native_files, ue_files


IGNORED = {'.log', '.blend1', '.pyc'}


def source_hashes(root):
    """Exact finalized build inputs; no run outputs, self receipts or unrelated docs."""
    root = Path(root).resolve()
    files = []
    for name in ('Prototype/LapTrainer/Source', 'Prototype/LapTrainer/Config',
                 'Prototype/LapTrainer/Content', 'Prototype/LapTrainer/Scripts',
                 'Assets/Phase5', 'Assets/Phase6', 'Assets/Phase7', 'Assets/Phase8',
                 'Scripts', 'Physics/configs'):
        folder = root / name
        require(folder.is_dir(), 'Missing frozen input directory: ' + name)
        files.extend(p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() not in IGNORED
                     and '__pycache__' not in p.relative_to(folder).parts)
    files.extend(p for p in (root / 'Physics').iterdir() if p.is_file()
                 and p.suffix.lower() in ('.h', '.cpp', '.json', '.txt', '.ps1', '.py'))
    files.extend(root / name for name in ('Prototype/LapTrainer/LapTrainer.uproject', 'docs/PHASE8.md'))
    for name in ('tmp/phase8/import_phase8.py', 'tmp/phase8/run_import.ps1'):
        if (root / name).is_file():
            files.append(root / name)
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(set(files))}


def bound_record(root, record, cache=None):
    path = child(root, record['path'])
    require(path.is_file(), 'Missing bound evidence/input: ' + record['path'])
    key = record['path']
    if cache is not None and key in cache:
        digest = cache[key]
    else:
        digest = sha(path)
        if cache is not None:
            cache[key] = digest
    require(digest == record['sha256'], 'Changed bound evidence/input: ' + key)
    if 'bytes' in record:
        require(path.stat().st_size == record['bytes'], 'Changed bound input size: ' + key)
    return path


def evidence_record(root, path):
    path = Path(path).resolve()
    require(path.is_relative_to(root), 'Evidence must remain in the workspace')
    return {'path': path.relative_to(root).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def verify_inheritance(root, path):
    """Rehash all identities explicitly recorded by the existing read-only audit."""
    root, path = Path(root).resolve(), Path(path).resolve()
    original_hash = sha(path)
    data = read(path)
    require(data.get('schema') == 'endoforge.phase8.native-inheritance.v1' and data.get('phase') == 8
            and data.get('passed') is True and data.get('execution_phase') == 7
            and data.get('native_suite_reexecuted') is False and data.get('new_native_35_execution') is False,
            'Passed exact Phase7 native inheritance evidence is required')
    require(data.get('checks') and all(value is True for value in data['checks'].values())
            and not data.get('failures'), 'Native inheritance contains failed/incomplete checks')
    cache = {}
    source_fallbacks = {}

    def inspect(value):
        if isinstance(value, dict):
            if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
                if value['path'] == 'ThirdParty/SOFA/sofa-v26.06.00-source.zip' and not (root / value['path']).exists():
                    fallback = distribution_inputs(root, data)['sofa_source']
                    require(fallback['sha256'] == value['sha256']
                            and ('bytes' not in value or fallback['bytes'] == value['bytes']),
                            'Accepted SOFA source fallback differs from the recorded archive')
                    bound_record(root, fallback, cache)
                    source_fallbacks[value['path']] = fallback
                else:
                    bound_record(root, value, cache)
            for key, item in value.items():
                if key in ('files_sha256', 'actual_files_sha256'):
                    require(isinstance(item, dict), 'Invalid expanded native input map')
                    for name, digest in item.items():
                        bound_record(root, {'path': name, 'sha256': digest}, cache)
                else:
                    inspect(item)
        elif isinstance(value, list):
            for item in value:
                inspect(item)

    inspect(data)
    require(sha(root / 'Scripts/Phase8/inherit_native.py') == data['helper_sha256']
            and sha(root / 'Scripts/Phase8/preservation.py') == data['preservation_helper_sha256'],
            'Native inheritance helper identity changed')
    require(sha(root / 'Physics/runtime/LapPhysics.exe') == data['native_binary_sha256']
            and sha(root / 'Assets/Phase8/physics-mesh.json') == data['physical_asset_sha256'],
            'Current native executable/explicit Phase8 mesh differs from inherited qualification')
    require(data['required_native_launch_contract']['arguments'] ==
            ['--phase6', '--mesh', 'Assets/Phase8/physics-mesh.json'], 'Unexpected native launch contract')
    require(sha(path) == original_hash, 'Native inheritance report changed during verification')
    return {**data, 'verification_distribution_source_fallbacks': source_fallbacks}


def distribution_inputs(root, inherited):
    """Use unchanged accepted native metadata and a manifest-verified SOFA source ZIP."""
    manifest_path = bound_record(root, inherited['accepted_manifest'])
    rows = read(manifest_path)
    manifest = {row['path']: row for row in rows}
    require(len(manifest) == len(rows), 'Duplicate accepted package manifest member')
    package = manifest_path.parent
    metadata = inherited['generated_runtime_metadata']['accepted_packaged']
    metadata_path = bound_record(root, metadata)
    require(metadata_path == package / 'Physics/build-info.json', 'Unexpected accepted native metadata origin')
    require(sha(metadata_path) == manifest['Physics/build-info.json']['sha256'],
            'Accepted native metadata differs from its package manifest')
    relative = 'Source/Dependencies/sofa-v26.06.00-source.zip'
    expected = manifest[relative]
    source = root / 'ThirdParty/SOFA/sofa-v26.06.00-source.zip'
    if not source.exists():
        source = package / relative
    require(source.is_file() and source.stat().st_size == expected['bytes'] and sha(source) == expected['sha256'],
            'SOFA corresponding source ZIP is missing or differs from the accepted manifest')
    return {'native_metadata': evidence_record(root, metadata_path),
            'sofa_source': evidence_record(root, source),
            'accepted_manifest': inherited['accepted_manifest'],
            'native_metadata_scope': 'Unmodified accepted Phase7 post-suite metadata; its original native test/compiler provenance is inherited, not rewritten as a Phase8 execution.'}


def frozen_inputs(root, path, inheritance_path, inherited, source_map):
    frozen = read(path)
    require(frozen.get('schema') == 'endoforge.phase8.ue-validation.v1' and frozen.get('phase') == 8
            and frozen.get('source_frozen') is True, 'A completed Phase8 source/editor validation freeze is required')
    rows = frozen['source_files'] + frozen['additional_build_inputs'] + frozen['assets']
    expected = {row['path']: row['sha256'] for row in rows}
    require(len(rows) == len(expected) and expected == source_map, 'Frozen/current source or asset identity/membership differs')
    for row in rows:
        bound_record(root, row)
    require(bound_record(root, frozen['native_inheritance']) == inheritance_path,
            'UE freeze binds a different native inheritance report')
    require(bound_record(root, frozen['physics_executable']) == root / 'Physics/runtime/LapPhysics.exe'
            and frozen['physics_executable']['sha256'] == inherited['native_binary_sha256'], 'UE/native freeze mismatch')
    module = bound_record(root, frozen['editor_module'])
    protocol = frozen['protocol']
    require(protocol.get('passed') is True and protocol.get('same_final_editor_module') is True
            and protocol.get('editor_module') == frozen['editor_module'], 'Successful same-module protocol evidence is required')
    bound_record(root, protocol['log'])
    editor = frozen['editor_input']
    require(editor.get('passed') is True and editor.get('stereo_frames') == 4, 'Exactly four editor alignment frames are required')
    documents = {name: read(bound_record(root, editor[name])) for name in ('report', 'interaction', 'lifecycle', 'runtime')}
    for name in ('report', 'interaction'):
        require(documents[name].get('phase') == 8 and documents[name].get('passed') is True
                and documents[name].get('checks') and all(value is True for value in documents[name]['checks'].values()),
                'Incomplete Phase8 editor evidence: ' + name)
    require(documents['report']['stereo_frames'] == 4 and documents['runtime']['phase'] == 8,
            'Incorrect Phase8 editor runtime/alignment scope')
    life = documents['lifecycle']
    require(life.get('game_exit_code') == life.get('native_exit_code') == 0
            and life.get('native_graceful_exit') is True and not life.get('error'), 'Editor/native lifecycle failed')
    require(module.stat().st_mtime <= bound_record(root, editor['report']).stat().st_mtime,
            'Editor module was rebuilt after its input exercise')
    return frozen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'ue-package', 'package-log', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--native-inheritance', type=Path, default=Path('tmp/phase8/native-inheritance.json'))
    parser.add_argument('--ue-validation', type=Path, default=Path('tmp/phase8/ue-final-validation.json'))
    args = parser.parse_args()
    root, ue, output = args.root.resolve(), args.ue_package.resolve(), args.output.resolve()
    require(not output.exists(), 'Use a fresh build receipt')
    require(output.is_relative_to(root / 'tmp/phase8') or output.is_relative_to(root / 'output/Phase8'),
            'Phase8 receipts must stay under tmp/phase8 or output/Phase8')
    inheritance_path = args.native_inheritance if args.native_inheritance.is_absolute() else root / args.native_inheritance
    validation_path = args.ue_validation if args.ue_validation.is_absolute() else root / args.ue_validation
    inheritance_path, validation_path = inheritance_path.resolve(), validation_path.resolve()
    require(inheritance_path.is_relative_to(root) and validation_path.is_relative_to(root), 'Evidence must stay in the workspace')
    inherited = verify_inheritance(root, inheritance_path)
    source_map = source_hashes(root)
    frozen = frozen_inputs(root, validation_path, inheritance_path, inherited, source_map)
    log_path = args.package_log.resolve()
    text = log_path.read_text(encoding='utf-8-sig', errors='replace')
    require('BUILD SUCCESSFUL' in text and 'AutomationTool exiting with ExitCode=0' in text,
            'Successful final UAT build/cook/package evidence is required')
    normalized = text.replace('\\', '/').replace('"', '').lower()
    require((root / 'Prototype/LapTrainer/LapTrainer.uproject').as_posix().lower() in normalized
            and ue.parent.as_posix().lower() in normalized, 'UAT log identifies a different project/archive destination')
    game, native = ue / 'LapTrainer/Binaries/Win64/LapTrainer.exe', root / 'Physics/runtime/LapPhysics.exe'
    freeze = datetime.datetime.fromisoformat(frozen['created_utc'].replace('Z', '+00:00')).timestamp()
    require(log_path.stat().st_mtime >= freeze and game.stat().st_mtime >= freeze, 'UAT/game predates validated source freeze')
    inputs = distribution_inputs(root, inherited)
    runtime = dict(ue_files(ue), **native_files(root / 'Physics/runtime'))
    cooked = [child(ue, name) for name in runtime if name.endswith(('.pak', '.utoc', '.ucas'))]
    require(cooked and all(path.stat().st_mtime >= freeze for path in cooked), 'Fresh cooked content is required')
    runtime['Physics/build-info.json'] = inputs['native_metadata']['sha256']
    runtime['Physics/assets/phase6.json'] = inherited['physical_asset_sha256']
    require(source_hashes(root) == source_map, 'Inputs changed while recording the build')
    inheritance_record, validation_record = evidence_record(root, inheritance_path), evidence_record(root, validation_path)
    summary = {key: inherited[key] for key in ('schema', 'phase', 'passed', 'execution_phase', 'native_suite_reexecuted',
               'new_native_35_execution', 'native_binary_sha256', 'physical_asset_sha256', 'accepted_final', 'accepted_manifest',
               'accepted_phase7_native_execution', 'compiler_provenance')}
    summary['source_receipt'] = inheritance_record
    summary['distribution_source_fallbacks'] = inherited['verification_distribution_source_fallbacks']
    summary['scope'] = 'Exact accepted Phase7 native qualification inherited; no new Phase8 native suite execution. Fresh integrated UE/package validation remains separate.'
    data = {'schema': 'endoforge.phase8.build.v1', 'phase': 8,
            'created_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'physics_exe_sha256': sha(native), 'game_exe_sha256': sha(game),
            'package_log': evidence_record(root, log_path), 'package_log_sha256': sha(log_path),
            'source_asset_sha256': source_map, 'runtime_artifacts_sha256': runtime,
            'native_inheritance': summary, 'native_inheritance_receipt_sha256': inheritance_record['sha256'],
            'ue_validation_receipt': validation_record, 'ue_validation_receipt_sha256': validation_record['sha256'],
            'ue_frozen_inputs_match': True, 'distribution_inputs': inputs,
            'native_asset_alias': {'path': 'Physics/assets/phase6.json', 'source': 'Assets/Phase8/physics-mesh.json',
                'scope': 'Package-only compatible solver alias; explicit Phase8 mesh is authoritative. Root runtime alias and earlier deliveries remain unchanged.'},
            'packaged_evidence': {'native_inheritance': {'path': 'native-inheritance.json', 'sha256': inheritance_record['sha256']},
                'ue_validation': {'path': 'phase8-ue-validation.json', 'sha256': validation_record['sha256']}}}
    write_new(output, data)
    print(json.dumps({'receipt': str(output), 'source_asset_files': len(source_map), 'native_execution_phase': 7,
                      'native_suite_reexecuted': False, 'new_native_35_execution': False}))


if __name__ == '__main__':
    main()
