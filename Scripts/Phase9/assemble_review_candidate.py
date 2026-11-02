"""Assemble a fresh Phase9 review candidate from explicitly supplied evidence.

This is a copy/hash helper, not a build, test run, visual approval or final
delivery receipt. All mutations stay in a new child of output/Phase9. Inputs
and all earlier deliveries remain read only; links/reparse points are rejected.

Required validation receipt contract:
  schema: endoforge.phase9.validation.v1; phase: 9; passed: true
  checks: a nonempty object containing only true Boolean values
  human_visual_approval: pending or approved
  inputs: physics_exe_sha256, physics_mesh_sha256, game_exe_sha256
  evidence: named {path, sha256, optional bytes} records, including
            native_qualification from run_native_qualification.py and
            build_receipt from write_build_receipt.py
Paths in supplied evidence records are absolute or workspace-relative. Evidence
is never discovered by searching for a passed file. Diagnostic-only or inherited
native qualification cannot qualify this candidate.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys


sys.dont_write_bytecode = True
from run_native_qualification import expected_cases
from write_build_receipt import verify_build_receipt


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = 'endoforge.phase9.review-candidate.v1'
REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
EXCLUDED_DIRS = {'.git', '.svn', '.cache', '.vs', '.idea', '.vscode',
                 '__pycache__', 'node_modules', 'build', 'builds', 'binaries',
                 'intermediate', 'deriveddatacache', 'saved', 'logs', 'cache'}
EXCLUDED_SUFFIXES = {'.pdb', '.pyc', '.pyo', '.log', '.blend1', '.blend2', '.tmp'}
SOURCE_SUFFIXES = {'.cpp', '.c', '.h', '.hpp', '.cs', '.ini', '.json', '.txt',
                   '.md', '.py', '.ps1', '.cmd', '.bat', '.usf', '.ush'}
NATIVE_SUBDIRS = ('licenses', 'etc', 'share', 'configs', 'assets')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_stat(path):
    info = Path(path).stat(follow_symlinks=False)
    require(not stat.S_ISLNK(info.st_mode)
            and not getattr(info, 'st_file_attributes', 0) & REPARSE,
            'Links/reparse points are forbidden: ' + str(path))
    return info


def checked_path(value, *, directory=False, existing=True):
    path = Path(os.path.abspath(value))
    for ancestor in reversed((path, *path.parents)):
        if ancestor.exists() or ancestor.is_symlink():
            checked_stat(ancestor)
    if existing:
        info = checked_stat(path)
        require(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode),
                'Expected ' + ('directory: ' if directory else 'file: ') + str(path))
    return path


def metadata(path):
    info = checked_stat(path)
    return (info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_dev, info.st_ino)


def relative_name(name):
    require(isinstance(name, str) and name, 'Missing relative package member')
    pure = PurePosixPath(name)
    require(not pure.is_absolute() and pure.as_posix() == name
            and not {'.', '..'}.intersection(pure.parts)
            and '\\' not in name and ':' not in name,
            'Invalid package member: ' + name)
    return name


def tree_files(folder, *, source=False, ue=False):
    folder = checked_path(folder, directory=True)
    result = []

    def descend(directory):
        for entry in sorted(directory.iterdir(), key=lambda item: item.name):
            info = checked_stat(entry)
            if stat.S_ISDIR(info.st_mode):
                excluded = {'saved', 'logs'} if ue else EXCLUDED_DIRS
                if entry.name.casefold() not in excluded:
                    descend(entry)
            elif stat.S_ISREG(info.st_mode):
                if entry.suffix.lower() in EXCLUDED_SUFFIXES:
                    continue
                if not source or entry.suffix.lower() in SOURCE_SUFFIXES:
                    result.append(entry)
            else:
                raise ValueError('Unexpected filesystem member: ' + str(entry))
    descend(folder)
    return result


def true_checks(data, label):
    checks = data.get('checks')
    require(isinstance(checks, dict) and checks
            and all(type(value) is bool and value is True for value in checks.values()),
            label + ' requires explicit nonempty passed Boolean checks')
    return checks


def digest_value(value, label):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value),
            'Invalid SHA256: ' + label)
    return value


def bind_record(record, label):
    require(isinstance(record, dict) and isinstance(record.get('path'), str),
            'Missing explicit evidence path: ' + label)
    path = Path(record['path'])
    path = checked_path(path if path.is_absolute() else ROOT / path)
    digest = digest_value(record.get('sha256'), label)
    require(sha(path) == digest, 'Evidence SHA256 mismatch: ' + label)
    if 'bytes' in record:
        require(type(record['bytes']) is int and record['bytes'] == path.stat().st_size,
                'Evidence size mismatch: ' + label)
    return path


def validation(path, executable, mesh, game):
    document = json.loads(path.read_text(encoding='utf-8-sig'))
    require(document.get('schema') == 'endoforge.phase9.validation.v1'
            and type(document.get('phase')) is int and document['phase'] == 9
            and document.get('passed') is True,
            'An explicitly passed Phase9 validation receipt is required')
    true_checks(document, 'Phase9 validation')
    require(document.get('diagnostic_only') is not True
            and document.get('inherited_results') is not True,
            'Diagnostic-only or inherited validation cannot qualify Phase9')
    require(document.get('human_visual_approval') in ('pending', 'approved'),
            'Human visual approval must explicitly be pending or approved')
    inputs = document.get('inputs')
    require(isinstance(inputs, dict), 'Validation must bind current input hashes')
    for key, actual in (('physics_exe_sha256', executable),
                        ('physics_mesh_sha256', mesh), ('game_exe_sha256', game)):
        require(digest_value(inputs.get(key), key) == sha(actual),
                'Validation uses a different selected input: ' + key)
    evidence = document.get('evidence')
    require(isinstance(evidence, dict) and {'native_qualification', 'build_receipt'}.issubset(evidence),
            'Explicit hash-bound fresh native qualification and complete build provenance are mandatory')
    require(len({name.casefold() for name in evidence}) == len(evidence),
            'Case-colliding evidence names')
    bound = {}
    for name, record in evidence.items():
        require(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', name),
                'Invalid evidence name: ' + str(name))
        bound[name] = bind_record(record, name)
    native_path = bound['native_qualification']
    native = json.loads(native_path.read_text(encoding='utf-8-sig'))
    require(native.get('schema') == 'endoforge.phase9.native-qualification.v1'
            and native.get('phase') == 9 and native.get('passed') is True
            and native.get('native_execution_started') is True
            and native.get('inherited_results') is False
            and native.get('diagnostic_only') is not True,
            'Fresh executed Phase9 native qualification is required; no inherited or diagnostic-only pass')
    true_checks(native, 'Fresh native qualification')
    require(native.get('native_binary', {}).get('sha256') == inputs['physics_exe_sha256']
            and native.get('mesh', {}).get('sha256') == inputs['physics_mesh_sha256'],
            'Fresh native qualification does not bind the selected executable and mesh')
    completed = native.get('completed')
    names = expected_cases()
    require(native.get('case_count') == native.get('expected_case_count') == len(names) == 35
            and isinstance(completed, list)
            and [item.get('name') for item in completed] == names,
            'All 35 freshly executed cases, in canonical order, are required')
    case_files = {}
    for item in completed:
        report = bind_record({'path': item.get('report'), 'sha256': item.get('sha256')},
                             'native case ' + item['name'])
        require(report.is_relative_to(native_path.parent), 'Native report escapes its qualification run')
        value = json.loads(report.read_text(encoding='utf-8-sig'))
        require(value.get('passed') is True, 'Failed current native report: ' + item['name'])
        if 'checks' in value:
            true_checks(value, 'Native case ' + item['name'])
        case_files[item['name']] = report
    build = verify_build_receipt(bound['build_receipt'], game.parents[3], executable.parent, mesh.parent)
    require(build['native_runtime_files_sha256']['LapPhysics.exe'] == inputs['physics_exe_sha256']
            and build['asset_files_sha256']['physics-mesh.json'] == inputs['physics_mesh_sha256']
            and build['ue_package_files_sha256']['LapTrainer/Binaries/Win64/LapTrainer.exe'] == inputs['game_exe_sha256'],
            'Build provenance and validation input hashes disagree')
    return document, bound, native, case_files, build


def select_files(args, ue, native, assets, validation_path, evidence, cases):
    selected = {}

    def add(source, destination, group):
        source = checked_path(source)
        destination = relative_name(destination)
        require(destination.casefold() not in {name.casefold() for name in selected},
                'Colliding selected package member: ' + destination)
        selected[destination] = {'source': source, 'group': group}

    def tree(folder, destination, group, **options):
        for source in tree_files(folder, **options):
            add(source, (PurePosixPath(destination) / source.relative_to(folder).as_posix()).as_posix(), group)

    tree(ue, '', 'ue_package', ue=True)
    for source in sorted(native.iterdir()):
        info = checked_stat(source)
        if stat.S_ISREG(info.st_mode) and (source.suffix.lower() in ('.exe', '.dll')
                or source.name in ('build-info.json', 'runtime-manifest.txt')
                or source.name.upper().startswith(('LICENSE', 'LICENCE', 'NOTICE', 'COPYING', 'THIRD-PARTY'))):
            add(source, 'Physics/' + source.name, 'native_runtime')
    for name in NATIVE_SUBDIRS:
        if (native / name).exists():
            tree(native / name, 'Physics/' + name, 'native_runtime')
    tree(assets, 'Assets/Phase9', 'authored_assets')
    for source in sorted((ROOT / 'Physics').iterdir()):
        if source.is_file() and source.suffix.lower() in SOURCE_SUFFIXES:
            add(source, 'Source/Physics/' + source.name, 'editable_source')
    tree(ROOT / 'Physics/configs', 'Source/Physics/configs', 'editable_source', source=True)
    project = ROOT / 'Prototype/LapTrainer'
    add(project / 'LapTrainer.uproject', 'Source/Prototype/LapTrainer/LapTrainer.uproject', 'editable_source')
    for name in ('Source', 'Config', 'Scripts'):
        tree(project / name, 'Source/Prototype/LapTrainer/' + name, 'editable_source', source=True)
    tree(ROOT / 'Scripts', 'Source/Scripts', 'editable_source', source=True)
    for source, destination in ((ROOT / 'Scripts/StartPhase9.ps1', 'StartTrainer.ps1'),
                                (ROOT / 'Scripts/StartTrainer.cmd', 'StartTrainer.cmd'),
                                (ROOT / 'Scripts/Phase9ProcessPolicy.ps1', 'Phase9ProcessPolicy.ps1'),
                                (args.readme, 'README.md'), (args.manual, 'TESTING.zh-CN.md')):
        add(source, destination, 'launch_and_manual')
    add(validation_path, 'Evidence/validation-receipt.json', 'provided_validation')
    for name, source in evidence.items():
        add(source, 'Evidence/' + name + source.suffix.lower(), 'provided_evidence')
    for name, source in cases.items():
        add(source, 'Evidence/Native/' + name + '.json', 'fresh_native_case_report')
    require('LapTrainer/Binaries/Win64/LapTrainer.exe' in selected
            and any(name.lower().endswith(('.pak', '.utoc', '.ucas')) for name in selected),
            'The explicit UE package must contain the actual game and cooked content')
    require('Assets/Phase9/EndoForge_Anatomy.blend' in selected,
            'Editable original Phase9 Blender file is required')
    return selected


def write_new(path, data):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


def verify_staged_inputs(output, selected, frozen, build, ue, native, assets):
    require({path.relative_to(output).as_posix() for path in tree_files(output, ue=True)} == set(selected),
            'Staged package membership differs from explicit selected inputs')
    for group, key, source_root in (('ue_package', 'ue_package_files_sha256', ue),
                                    ('native_runtime', 'native_runtime_files_sha256', native),
                                    ('authored_assets', 'asset_files_sha256', assets)):
        staged = {item['source'].relative_to(source_root).as_posix(): sha(output.joinpath(*PurePosixPath(name).parts))
                  for name,item in selected.items() if item['group'] == group}
        require(staged == build[key], 'Staged complete tree differs from successful build provenance: '+group)
    require(all(sha(output.joinpath(*PurePosixPath(name).parts)) == row['sha256']
                for name,row in frozen.items()), 'A staged source/evidence file differs from its frozen input')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ('ue-package', 'native-runtime', 'assets', 'output', 'validation-receipt'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--readme', type=Path, default=ROOT / 'Scripts/README-Phase9-Delivery.md')
    parser.add_argument('--manual', type=Path, default=ROOT / 'Scripts/TESTING-Phase9.zh-CN.md')
    parser.add_argument('--plan-only', action='store_true', help='Validate supplied inputs/evidence and print selection; write nothing')
    args = parser.parse_args()
    ue = checked_path(args.ue_package, directory=True)
    native = checked_path(args.native_runtime, directory=True)
    assets = checked_path(args.assets, directory=True)
    require(assets == ROOT / 'Assets/Phase9', '--assets must be the actual workspace Assets/Phase9 directory')
    output = checked_path(args.output, existing=False)
    allowed = checked_path(ROOT / 'output/Phase9', existing=False)
    require(output.is_relative_to(allowed) and output != allowed and not output.exists(),
            'Use a completely fresh child of output/Phase9')
    validation_path = checked_path(args.validation_receipt)
    args.readme, args.manual = checked_path(args.readme), checked_path(args.manual)
    for source in (ue, native, assets, validation_path, args.readme, args.manual):
        require(not output.is_relative_to(source) and not source.is_relative_to(output),
                'Candidate output must be separate from every selected input')
    document, evidence, native_report, cases, build = validation(validation_path,
        native / 'LapPhysics.exe', assets / 'physics-mesh.json', ue / 'LapTrainer/Binaries/Win64/LapTrainer.exe')
    selected = select_files(args, ue, native, assets, validation_path, evidence, cases)
    frozen = {name: {'source': str(item['source']), 'group': item['group'],
                     'bytes': item['source'].stat().st_size, 'sha256': sha(item['source']),
                     'metadata': metadata(item['source'])} for name, item in selected.items()}
    for name, row in frozen.items():
        if row['group'] in ('editable_source', 'launch_and_manual'):
            source = Path(row['source'])
            expected = (build['source_files_sha256'].get(source.relative_to(ROOT).as_posix())
                        if source.is_relative_to(ROOT) else build['dependency_files_sha256'].get(str(source)))
            require(expected == row['sha256'], 'Selected source/manual was not frozen in the successful build: '+str(source))
    if args.plan_only:
        print(json.dumps({'schema': SCHEMA, 'plan_only': True, 'output': str(output),
                          'selected_files': len(frozen), 'selected_bytes': sum(row['bytes'] for row in frozen.values()),
                          'human_visual_approval': document['human_visual_approval'],
                          'fresh_native_cases': len(cases), 'inputs': frozen,
                          'executes_build_or_test': False, 'writes_files': False}, indent=2))
        return 0
    started = datetime.now(timezone.utc).isoformat()
    output.mkdir(parents=True, exist_ok=False)
    for name, item in selected.items():
        source = item['source']
        require(metadata(source) == frozen[name]['metadata'], 'Input changed before copy: ' + str(source))
        destination = output.joinpath(*PurePosixPath(name).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        with source.open('rb') as original, destination.open('xb') as copied:
            while block := original.read(2**20):
                digest.update(block)
                copied.write(block)
        require(digest.hexdigest() == frozen[name]['sha256']
                and metadata(source) == frozen[name]['metadata'], 'Input changed while copying: ' + str(source))
    after = select_files(args, ue, native, assets, validation_path, evidence, cases)
    require(list(after) == list(selected) and all(metadata(item['source']) == frozen[name]['metadata']
            for name, item in after.items()), 'Selected source membership or metadata changed during assembly')
    verify_staged_inputs(output, selected, frozen, build, ue, native, assets)
    input_files = [{'package_path': name, **{key: value for key, value in row.items() if key != 'metadata'}}
                   for name, row in frozen.items()]
    evidence_records = {name: {'source': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size,
                              'package_path': 'Evidence/' + name + path.suffix.lower()}
                        for name, path in evidence.items()}
    receipt = {'schema': SCHEMA, 'phase': 9, 'candidate_status': 'review_candidate',
               'started_utc': started, 'completed_utc': datetime.now(timezone.utc).isoformat(),
               'human_visual_approval': document['human_visual_approval'],
               'clinical_approval': 'not_claimed', 'delivery_accepted': False,
               'provided_validation_checks': document['checks'],
               'provided_tests': document.get('tests', {}), 'provided_evidence': evidence_records,
               'validation_receipt': {'source': str(validation_path), 'sha256': sha(validation_path),
                                      'package_path': 'Evidence/validation-receipt.json'},
               'build_receipt': evidence_records['build_receipt'],
               'validated_inputs': document['inputs'],
               'fresh_native_qualification': {'schema': native_report['schema'], 'case_count': len(cases),
                   'native_execution_started': True, 'inherited_results': False, 'diagnostic_only': False,
                   'physics_exe_sha256': native_report['native_binary']['sha256'],
                   'physics_mesh_sha256': native_report['mesh']['sha256']},
               'input_roots': {'ue_package': str(ue), 'native_runtime': str(native), 'assets': str(assets)},
               'input_files': input_files, 'manifest': 'assembly-manifest.json',
               'source_scope': 'Current Physics top-level source/configs, UE Source/Config/uproject/project Scripts, repository Scripts, and top-level Assets/Phase9 Blender originals. Reference data, dependency SDKs, old runtime/source trees, UE Content authoring binaries, build trees and caches are excluded.',
               'scope': 'Review candidate copied from explicitly selected inputs and hash-bound supplied current evidence. Complete cooked UE/native redistribution/Assets9 maps and selected source bytes match successful build provenance before copying and in staged destinations. Human visual approval may remain pending. Shipped source is review source, not a self-contained clean regeneration/cook distribution. No build, simulation, editor, performance measurement, clinical approval or final delivery acceptance is performed by assembly.'}
    write_new(output / 'review-candidate.json', receipt)
    rows = [{'path': path.relative_to(output).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
            for path in tree_files(output, ue=True)]
    require(not any(row['path'] == 'assembly-manifest.json' for row in rows), 'Manifest must be fresh')
    write_new(output / 'assembly-manifest.json', rows)
    print(json.dumps({'schema': SCHEMA, 'candidate': str(output), 'files': len(rows),
                      'bytes': sum(row['bytes'] for row in rows),
                      'manifest_sha256': sha(output / 'assembly-manifest.json'),
                      'receipt_sha256': sha(output / 'review-candidate.json'),
                      'human_visual_approval': document['human_visual_approval'], 'delivery_accepted': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
