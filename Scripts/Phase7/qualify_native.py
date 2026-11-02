"""Bind newly executed native evidence to the revised Phase7 physical asset."""
from pathlib import Path
from common import read, require, sha

GENERATED_METADATA = 'Physics/runtime/build-info.json'


def verify(root,native_suite):
    native_suite=Path(native_suite).resolve()
    require(native_suite.is_relative_to(root/'tmp/phase7'), 'Phase7 physical revision requires a fresh Phase7 suite')
    suite=read(native_suite)
    require(suite.get('passed') is True and all(v is True for v in suite['checks'].values()), 'Native suite incomplete/failed')
    require(suite['checks']['thirty_five_native_cases'] is True and suite['checks']['fifteen_long_hold_cases_and_all_raw_states'] is True, 'Full35 native cases required')
    stage_root=next((p for p in native_suite.parents if (p/'phase7-native-workspace.json').is_file()),None)
    require(stage_root is not None, 'Missing explicit Phase7 native staging identity')
    stage=read(stage_root/'phase7-native-workspace.json')
    require(stage.get('schema')=='endoforge.phase7.native-workspace.v1' and stage.get('phase')==7 and stage.get('solver_mode')==6,
            'Invalid Phase7 staged workspace identity')
    require(Path(stage['workspace']).resolve()==stage_root, 'Staging receipt belongs to another workspace')
    require(set(stage.get('generated_metadata_before_sha256',{}))=={GENERATED_METADATA} and
            GENERATED_METADATA not in stage['stage_files_sha256'], 'Incorrect generated metadata exception')
    asset=sha(root/'Assets/Phase7/physics-mesh.json');binary=sha(root/'Physics/runtime/LapPhysics.exe')
    require(asset==stage['source_phase7_asset_sha256']==suite['anatomy_asset']['sha256'], 'Requalified physical asset changed')
    require(binary==stage['native_executable_sha256']==suite['native_binary']['sha256'], 'Requalified native executable changed')
    for name,digest in stage['stage_files_sha256'].items():
        require(sha(stage_root/name)==digest, 'Staged validation input changed: '+name)
        if name.startswith('Physics/runtime/') and name!='Physics/runtime/assets/phase6.json':
            require(sha(root/name)==digest, 'Runtime dependency differs from tested workspace: '+name)
    for name,digest in stage['unmodified_test_and_native_sources'].items():
        require(sha(root/name)==digest, 'Native/test source differs from tested version: '+name)
    # A metadata exception must not permit a stale/fabricated successful build
    # label. These are fields actually written by the unchanged summarizer.
    metadata_path=stage_root/GENERATED_METADATA
    metadata=read(metadata_path)
    suite_hash=sha(native_suite)
    require(metadata.get('phase')==6 and metadata.get('tested_protocol')==5,
            'Generated metadata does not identify the tested compatible solver')
    require(metadata.get('executable_sha256')==binary and metadata.get('native_suite_sha256')==suite_hash,
            'Generated metadata is not bound to the current native suite/executable')
    require(metadata.get('source_files_sha256')==suite['sources_sha256'] and
            metadata.get('source_sha256')==suite['sources_sha256']['main.cpp'],
            'Generated metadata source identities differ from the native suite')
    require(set(metadata.get('tested_protocols',[]))=={3,4,5} and
            set(metadata.get('tested_execution_modes',[]))=={'phase3','phase4','phase6'},
            'Generated metadata omits required tested protocols/modes')
    for name,item in suite['evidence'].items():
        if isinstance(item,dict) and 'path' in item and 'sha256' in item:
            require(sha(Path(item['path']))==item['sha256'], 'Native evidence changed: '+name)
            if 'trajectory' in item:
                require(sha(Path(item['trajectory']['path']))==item['trajectory']['sha256'], 'Native trajectory changed: '+name)
    return {'schema':'endoforge.phase7.native-requalification.v1','phase':7,'passed':True,
            'native_suite_reexecuted':True,'inherited_physics_acceptance':False,'solver_mode':6,
            'native_binary_sha256':binary,'physical_asset_sha256':asset,
            'native_suite':{'path':str(native_suite),'sha256':suite_hash},
            'staging_receipt_sha256':sha(stage_root/'phase7-native-workspace.json'),
            'staging_receipt_path':str(stage_root/'phase7-native-workspace.json'),
            'generated_runtime_metadata':{'path':str(metadata_path),'sha256':sha(metadata_path),
                                          'initial_sha256':stage['generated_metadata_before_sha256'][GENERATED_METADATA],
                                          'scope':'Summarizer-produced metadata; post-suite contents validated, not an immutable runtime dependency.'},
            'scope':'New35-case regression for revised Phase7 physical liver, with original test logic in an explicitly staged workspace. Fresh UE/package geometry/data tests remain mandatory.'}
