"""Prepare input hashes, then bind successful Phase9 build outputs to them.

Neither mode builds, launches, imports, runs tests or declares delivery accepted.
prepare is an input snapshot only. seal requires unchanged input membership and
bytes, explicit zero build exit codes and supplied native/editor/UAT logs. It
records complete selected cooked UE, native redistribution and Assets9 maps.
No current workspace state is presumed final by this helper.

Future usage after the maintainer finishes changes (from the workspace root):
  python -B Scripts/Phase9/write_build_receipt.py prepare --engine-root E:/UE_5.7
    --output tmp/phase9/build-inputs-final01.json
    --additional-input "C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/MSVC/14.38.33130"
    --additional-input "C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/MSVC/14.44.35207"
    --additional-input "C:/Program Files (x86)/Windows Kits/10/Include/10.0.22621.0"
    --additional-input "C:/Program Files (x86)/Windows Kits/10/Lib/10.0.22621.0"
    --additional-input "C:/Program Files (x86)/Windows Kits/10/bin/10.0.22621.0/x64"
  Run Physics/build.ps1, the Editor Build.ps1, and Package.ps1 to separate fresh
  logs; retain their actual exit codes. No command is run by this module.
  python -B Scripts/Phase9/write_build_receipt.py seal
    --prepared tmp/phase9/build-inputs-final01.json
    --ue-package tmp/phase9/ue-archive-final01/Windows
    --native-runtime Physics/runtime --assets Assets/Phase9
    --native-build-log tmp/phase9/native-build-final01.log --native-exit-code 0
    --editor-build-log tmp/phase9/ue-editor-build-final01.log --editor-exit-code 0
    --package-log tmp/phase9/ue-package-final01.log --package-exit-code 0
    --output tmp/phase9/build-receipt-final01.json

The later validation.v1 receipt must name this output under evidence.build_receipt
and the separately executed native report under evidence.native_qualification,
each with its actual SHA256. Human approval can stay pending. The assembler
verifies complete maps before copying and again in staged destinations. Review
Source deliberately omits UE Content and predecessor assets needed for a clean
regeneration/cook; no self-contained rebuild claim is made.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SCHEMA = 'endoforge.phase9.build-receipt.v1'
SNAPSHOT_SCHEMA = 'endoforge.phase9.build-inputs.v1'
REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
EXCLUDED_DIRS = {'.git', '.svn', '.cache', '.vs', '.idea', '.vscode', '__pycache__',
                 'node_modules', 'build', 'builds', 'binaries', 'intermediate',
                 'deriveddatacache', 'saved', 'logs', 'cache'}
EXCLUDED_SUFFIXES = {'.pdb', '.pyc', '.pyo', '.log', '.blend1', '.blend2', '.tmp'}
SOURCE_SUFFIXES = {'.cpp', '.c', '.h', '.hpp', '.cs', '.ini', '.json', '.txt',
                   '.md', '.py', '.ps1', '.cmd', '.bat', '.usf', '.ush'}
NATIVE_SUBDIRS = ('licenses', 'etc', 'share', 'configs', 'assets')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checked(path, directory=False):
    path = Path(os.path.abspath(path))
    for member in reversed((path, *path.parents)):
        if member.exists() or member.is_symlink():
            info = member.stat(follow_symlinks=False)
            require(not stat.S_ISLNK(info.st_mode) and
                    not getattr(info, 'st_file_attributes', 0) & REPARSE,
                    'Link/reparse point forbidden: ' + str(member))
    require(path.is_dir() if directory else path.is_file(), 'Missing input: ' + str(path))
    return path


def sha(path):
    with checked(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_log(path):
    raw = path.read_bytes()
    return raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig', errors='replace')


def files(folder, source=False, ue=False):
    folder = checked(folder, directory=True)
    result = []
    for entry in sorted(folder.iterdir()):
        info = entry.stat(follow_symlinks=False)
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & REPARSE,
                'Link/reparse point forbidden: ' + str(entry))
        if stat.S_ISDIR(info.st_mode):
            ignored = {'saved', 'logs'} if ue else EXCLUDED_DIRS
            if entry.name.casefold() not in ignored:
                result.extend(files(entry, source=source, ue=ue))
        elif stat.S_ISREG(info.st_mode) and entry.suffix.lower() not in EXCLUDED_SUFFIXES:
            if not source or entry.suffix.lower() in SOURCE_SUFFIXES:
                result.append(entry)
        elif not stat.S_ISREG(info.st_mode):
            raise ValueError('Unexpected member: ' + str(entry))
    return result


def file_map(folder, kind):
    folder = checked(folder, directory=True)
    if kind == 'native':
        selected = [p for p in sorted(folder.iterdir()) if p.is_file() and
                    (p.suffix.lower() in ('.exe', '.dll') or p.name in ('build-info.json', 'runtime-manifest.txt')
                     or p.name.upper().startswith(('LICENSE', 'LICENCE', 'NOTICE', 'COPYING', 'THIRD-PARTY')))]
        for name in NATIVE_SUBDIRS:
            if (folder/name).exists():
                selected.extend(files(folder/name))
    else:
        selected = files(folder, ue=kind == 'ue')
    require(selected, 'Empty selected input tree: ' + str(folder))
    before = {p.relative_to(folder).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns) for p in selected}
    result = {p.relative_to(folder).as_posix(): sha(p) for p in selected}
    require(before == {p.relative_to(folder).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns) for p in selected},
            'Input metadata changed during hashing: ' + str(folder))
    return result


def source_files():
    physics = ROOT/'Physics'
    selected = [p for p in sorted(physics.iterdir()) if p.is_file() and p.suffix.lower() in SOURCE_SUFFIXES]
    require(physics/'CMakeLists.txt' in selected, 'Native CMake definition is mandatory')
    for name in ('Physics/configs', 'Prototype/LapTrainer/Source', 'Prototype/LapTrainer/Config',
                 'Prototype/LapTrainer/Scripts', 'Scripts'):
        selected.extend(files(ROOT/name, source=True))
    # Binary Content is a cook input even though review Source deliberately
    # excludes it. Authoring scripts also read predecessor assets explicitly.
    selected.extend(files(ROOT/'Prototype/LapTrainer/Content'))
    selected.append(checked(ROOT/'Prototype/LapTrainer/LapTrainer.uproject'))
    for phase in range(5, 10):
        selected.extend(files(ROOT/f'Assets/Phase{phase}'))
    return sorted(set(selected))


def dependency_files(engine_root, additional):
    selected = []
    for name in ('ThirdParty/SOFA/sdk/SOFA_v26.06.00_Win64/include',
                 'ThirdParty/SOFA/sdk/SOFA_v26.06.00_Win64/lib',
                 'ThirdParty/physics-tools/eigen-3.4.0/Eigen',
                 'ThirdParty/physics-tools/eigen-3.4.0/unsupported',
                 'ThirdParty/physics-tools/boost_1_87_0/boost',
                 'ThirdParty/physics-tools/nlohmann',
                 'ThirdParty/physics-tools/cmake-4.4.4-windows-x86_64'):
        selected.extend(files(ROOT/name))
    manifest = json.loads((ROOT/'Physics/dependencies.json').read_text(encoding='utf-8-sig'))
    for item in manifest['dependencies']:
        archive = checked(ROOT/item['archive'])
        require(sha(archive) == item['sha256'].lower(),
                'Dependency archive differs from its recorded pin: '+item['archive'])
        selected.append(archive)
    engine = checked(engine_root, directory=True)
    for name in ('Engine/Build/Build.version', 'Engine/Build/BatchFiles/Build.bat',
                 'Engine/Build/BatchFiles/RunUAT.bat',
                 'Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll',
                 'Engine/Binaries/DotNET/AutomationTool/AutomationTool.dll'):
        selected.append(checked(engine/name))
    for value in additional:
        path = Path(value)
        selected.extend(files(path) if path.is_dir() else [checked(path)])
    return sorted(set(selected))


def absolute_map(paths):
    return {str(path): sha(path) for path in paths}


def current_snapshot(engine_root, additional):
    source = source_files()
    dependency = dependency_files(engine_root, additional)
    return {'source_files_sha256': {p.relative_to(ROOT).as_posix(): sha(p) for p in source},
            'dependency_files_sha256': absolute_map(dependency)}


def compare_snapshot(snapshot):
    current = current_snapshot(snapshot['engine_root'], snapshot['additional_inputs'])
    for key in ('source_files_sha256', 'dependency_files_sha256'):
        require(current[key] == snapshot[key], 'Build input bytes or membership changed: ' + key)
    return current


def verify_build_receipt(path, ue, native, assets):
    """Rehash all receipt-bound inputs; safe to reuse before candidate copying."""
    document = json.loads(checked(path).read_text(encoding='utf-8-sig'))
    require(document.get('schema') == SCHEMA and document.get('phase') == 9
            and document.get('build_succeeded') is True
            and document.get('source_snapshot_unchanged') is True,
            'A current Phase9 build provenance receipt is mandatory')
    compare_snapshot(document)
    for key, folder, kind in (('ue_package_files_sha256', ue, 'ue'),
                              ('native_runtime_files_sha256', native, 'native'),
                              ('asset_files_sha256', assets, 'assets')):
        expected = document.get(key)
        require(isinstance(expected, dict) and expected and file_map(folder, kind) == expected,
                'Build receipt differs from actual complete selected tree: ' + key)
    for item in document['build_logs'].values():
        require(sha(item['path']) == item['sha256'], 'Build log changed: ' + item['path'])
    toolchain = document.get('native_cmake_and_compiler_sha256')
    require(isinstance(toolchain, dict) and toolchain, 'Missing actual native CMake/compiler identities')
    require(all(sha(name) == digest for name, digest in toolchain.items()),
            'Actual native CMake configuration or compiler changed')
    module = document.get('editor_module')
    require(isinstance(module, dict) and sha(module['path']) == module['sha256'],
            'Selected editor module changed')
    require(sha(document['prepared_snapshot']['path']) == document['prepared_snapshot']['sha256'],
            'Prepared source/dependency snapshot changed')
    return document


def write_new(path, data):
    path = Path(os.path.abspath(path))
    require(any(path.is_relative_to(ROOT/name) and path != ROOT/name for name in ('tmp/phase9', 'output/Phase9')),
            'New receipts must remain under tmp/phase9 or output/Phase9')
    require(not path.exists(), 'Receipt is immutable; use a fresh output')
    path.parent.mkdir(parents=True, exist_ok=True)
    checked(path.parent, directory=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'seal'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--engine-root', type=Path, default=Path('E:/UE_5.7'))
    parser.add_argument('--additional-input', type=Path, action='append', default=[],
                        help='Additional exact compiler/SDK/toolchain file or directory to freeze')
    parser.add_argument('--prepared', type=Path)
    for name in ('ue-package', 'native-runtime', 'assets', 'native-build-log', 'editor-build-log', 'package-log'):
        parser.add_argument('--'+name, type=Path)
    for name in ('native', 'editor', 'package'):
        parser.add_argument('--'+name+'-exit-code', type=int, choices=(0,))
    args = parser.parse_args()
    now = datetime.now(timezone.utc).isoformat()
    if args.mode == 'prepare':
        data = {'schema': SNAPSHOT_SCHEMA, 'phase': 9, 'status': 'inputs_snapshot_only',
                'created_utc': now, 'engine_root': str(checked(args.engine_root, directory=True)),
                'additional_inputs': [str(checked(p, directory=p.is_dir())) for p in args.additional_input],
                **current_snapshot(args.engine_root, args.additional_input),
                'scope': 'Current input snapshot only; no build, test success, final-input status, human approval or delivery acceptance is claimed.'}
        require(current_snapshot(args.engine_root, args.additional_input) ==
                {k: data[k] for k in ('source_files_sha256', 'dependency_files_sha256')},
                'Inputs changed while preparing snapshot')
    else:
        for name in ('prepared', 'ue_package', 'native_runtime', 'assets', 'native_build_log',
                     'editor_build_log', 'package_log', 'native_exit_code', 'editor_exit_code', 'package_exit_code'):
            require(getattr(args, name) is not None, 'seal requires --'+name.replace('_', '-'))
        prepared = checked(args.prepared)
        snapshot = json.loads(prepared.read_text(encoding='utf-8-sig'))
        require(snapshot.get('schema') == SNAPSHOT_SCHEMA and snapshot.get('phase') == 9,
                'Expected a prepared Phase9 source/dependency snapshot')
        current = compare_snapshot(snapshot)
        ue, native, assets = (checked(p, directory=True) for p in (args.ue_package, args.native_runtime, args.assets))
        require(assets == ROOT/'Assets/Phase9', 'Select the actual Assets/Phase9 directory')
        logs = {}
        start = datetime.fromisoformat(snapshot['created_utc']).timestamp()
        for label, value in (('native', args.native_build_log), ('editor', args.editor_build_log), ('package', args.package_log)):
            path = checked(value)
            text = read_log(path)
            require(path.stat().st_mtime >= start, 'Build log predates input snapshot: '+label)
            if label == 'native':
                require('LapPhysics' in text and '.exe' in text and str(native/'LapPhysics.exe').replace('\\','/').casefold() in text.replace('\\','/').casefold(), 'Native log does not identify the selected output')
            elif label == 'editor':
                require('LapTrainerEditor' in text and ('Result: Succeeded' in text or 'BUILD SUCCESSFUL' in text), 'Successful project editor build log required')
            else:
                require('BUILD SUCCESSFUL' in text and 'AutomationTool exiting with ExitCode=0' in text, 'Successful UAT package log required')
                normalized = text.replace('\\','/').replace('"','').casefold()
                require((ROOT/'Prototype/LapTrainer/LapTrainer.uproject').as_posix().casefold() in normalized
                        and ue.parent.as_posix().casefold() in normalized,
                        'UAT log does not bind this project/package destination')
            logs[label] = {'path': str(path), 'sha256': sha(path), 'exit_code': getattr(args, label+'_exit_code')}
        runtime_map = file_map(native, 'native')
        ue_map = file_map(ue, 'ue')
        require('LapPhysics.exe' in runtime_map and 'LapTrainer/Binaries/Win64/LapTrainer.exe' in ue_map
                and any(name.endswith(('.pak','.utoc','.ucas')) for name in ue_map), 'Missing native/game/cooked outputs')
        compiled_native = {name: digest for name,digest in current['source_files_sha256'].items()
                           if Path(name).parent.as_posix() == 'Physics' and Path(name).suffix.lower() in ('.h','.cpp')}
        require('Physics/AnatomyAsset.h' in compiled_native and 'Physics/CMakeLists.txt' in current['source_files_sha256'],
                'Complete current native headers/CMake identity is mandatory')
        for name in compiled_native:
            require((ROOT/name).stat().st_mtime <= (native/'LapPhysics.exe').stat().st_mtime,
                    'Native source is newer than selected executable: '+name)
        cache_text = (ROOT/'Physics/build/CMakeCache.txt').read_text(encoding='utf-8-sig')
        version = []
        for part in ('MAJOR', 'MINOR', 'PATCH'):
            value = re.search(r'^CMAKE_CACHE_'+part+r'_VERSION:INTERNAL=(\d+)\s*$', cache_text, re.M)
            require(value is not None, 'Actual CMake cache version is missing: '+part)
            version.append(value.group(1))
        compiler_metadata = [checked(ROOT/'Physics/build/CMakeFiles'/'.'.join(version)/'CMakeCXXCompiler.cmake')]
        compiler_text = compiler_metadata[0].read_text(encoding='utf-8-sig')
        match = re.search(r'set\(CMAKE_CXX_COMPILER "([^"]+)"\)', compiler_text)
        require(match is not None, 'Actual native compiler path missing from CMake metadata')
        compiler = checked(Path(match.group(1)))
        metadata_files = [ROOT/'Physics/build/CMakeCache.txt', ROOT/'Physics/build/LapPhysics.vcxproj', *compiler_metadata]
        toolchain = absolute_map(metadata_files+[compiler])
        module = checked(ROOT/'Prototype/LapTrainer/Binaries/Win64/UnrealEditor-LapTrainer.dll')
        compare_snapshot(snapshot)
        data = {'schema': SCHEMA, 'phase': 9, 'created_utc': now, 'build_succeeded': True,
                'source_snapshot_unchanged': True, 'prepared_snapshot': {'path': str(prepared), 'sha256': sha(prepared)},
                'engine_root': snapshot['engine_root'], 'additional_inputs': snapshot['additional_inputs'],
                **current, 'compiled_native_source_files_sha256': compiled_native,
                'native_cmake_and_compiler_sha256': toolchain, 'build_logs': logs,
                'editor_module': {'path': str(module), 'sha256': sha(module)},
                'ue_package_files_sha256': ue_map, 'native_runtime_files_sha256': runtime_map,
                'asset_files_sha256': file_map(assets, 'assets'),
                'human_visual_approval': 'pending', 'delivery_accepted': False,
                'scope': 'Build provenance only, against unchanged prepared source/dependency bytes and explicit supplied zero exit codes/logs. All Physics headers/cpp/CMake, UE cook inputs, scripts including Blender authoring ancestors, Assets5-9, expanded SOFA/Eigen/Boost/JSON/CMake inputs and declared additional toolchain files are bound. Installed UE is represented by Build.version/build tools rather than every engine file. No native qualification, performance, visual or final delivery acceptance is implied.'}
    write_new(args.output, data)
    print(json.dumps({'output': str(args.output), 'schema': data['schema'], 'sha256': sha(args.output),
                      'delivery_accepted': False, 'build_or_runtime_launched': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
