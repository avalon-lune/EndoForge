"""Bundle completed acceptance evidence; incomplete or mismatched reports fail.

This seals candidate evidence only. The separate fresh-ZIP run receipt is written
beside the archive after extraction, so no self-referential ZIP hash is needed.
"""
import argparse
import datetime
import gzip
import hashlib
import json
import math
import shutil
from pathlib import Path

from qualify_native import verify as verify_native_inheritance
from runtime_identity import verify as verify_runtime
from audit_identity import verify_geometry_report
from native_long_hold import REPRESENTATIVE_CASES, expected_long_hold_cases, validate_long_hold


def sha(path):
    with path.open('rb') as handle: return hashlib.file_digest(handle,'sha256').hexdigest()


def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))


def validate_pass(name, report):
    assert report.get('passed') is True, 'Missing/failed acceptance: '+name
    numeric_limits = {
        'outer_wall_binding_error_m': 1e-12,
        'max_normal_squared_length_error': 1e-6,
        'max_anchor_binding_reconstruction_error_m': 1e-8,
    } if name == 'assets' else {}
    for key, value in report.get('checks', {}).items():
        if key in numeric_limits:
            assert type(value) in (int, float) and math.isfinite(value) and 0 <= value <= numeric_limits[key], (name, key)
        else:
            assert value is True, (name, key)
    if numeric_limits:
        assert numeric_limits.keys() <= report['checks'].keys()


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--package',type=Path,required=True)
    p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--audits',type=Path,required=True)
    p.add_argument('--native',type=Path,required=True)
    a=p.parse_args(); root=a.root.resolve(); package=a.package.resolve()
    out=package/'Verification'
    if out.exists(): raise FileExistsError('Use a package without an existing evidence bundle')
    report_paths={name:a.audits/(name+'.json') for name in (
        'geometry','contact-matrix','contact-endurance','liver-matrix','liver-endurance',
        'contact-long-hold','liver-long-hold',
        'presented-contact','presented-liver','dataset','snapshot','preservation','runtime','visual-review','context')}
    report_paths.update(native=a.native/'native-suite-report.json',
                        tool_guard=a.native/'tool-guard/report.json',
                        packaged=a.capture/'phase7-packaged-run.json',
                        input=a.capture/'phase5-input-test.json',
                        assets=root/'Assets/Phase7/asset-contract-check.json',
                        blender=root/'Assets/Phase7/blend-verification.json',
                        independent_assets=root/'Assets/Phase7/independent-asset-audit.json',
                        ue_static_assets=root/'tmp/phase7/ue-static-asset-verification.json')
    reports={name:read(path) for name,path in report_paths.items()}
    inheritance=verify_native_inheritance(root,a.native/'native-suite-report.json')
    for name,report in reports.items():
        validate_pass(name,report)
    geometry_auditors={'geometry':('geometry',None),
                      'contact-matrix':('contact',None),'contact-long-hold':('contact',None),
                      'liver-matrix':('liver',None),'liver-long-hold':('liver',None),
                      'contact-endurance':('contact',6),'liver-endurance':('liver',6),
                      'presented-contact':('contact',7),'presented-liver':('liver',7)}
    for name,(kind,runner_phase) in geometry_auditors.items():
        for source_root in (root,package/'Source'):
            verify_geometry_report(reports[name],source_root,kind,runner_phase)
    audit_sources={'runtime':'Scripts/Phase7/audit_runtime.py','dataset':'Scripts/Phase7/audit_dataset.py','snapshot':'Scripts/Phase7/audit_snapshot.py','visual-review':'Scripts/Phase7/record_visual_review.py'}
    for name,script in audit_sources.items():
        assert reports[name]['audit_script_sha256']==sha(root/script)==sha(package/'Source'/script), 'Auditor identity changed: '+name
    for name in ('runtime','dataset','snapshot','visual-review'):
        assert reports[name]['appearance_audit_script_sha256']==sha(root/'Scripts/Phase7/audit_appearance.py')==sha(package/'Source/Scripts/Phase7/audit_appearance.py')
    for name in ('dataset','snapshot'):
        assert reports[name]['attachment_audit_script_sha256']==sha(root/'Scripts/Phase7/audit_attachment.py')==sha(package/'Source/Scripts/Phase7/audit_attachment.py')
    for name in ('runtime','dataset','snapshot','visual-review'):
        assert reports[name]['uv_audit_script_sha256']==sha(root/'Scripts/Phase7/audit_uv.py')==sha(package/'Source/Scripts/Phase7/audit_uv.py')
    asset=package/'Assets/Phase7/physics-mesh.json'; asset_hash=sha(asset)
    receipt=read(package/'phase7-build-receipt.json')
    assert receipt['native_requalification']==inheritance
    assert Path(reports['packaged']['package_root']).resolve()==package, 'Acceptance was run against another package directory'
    verify_runtime(package,receipt,reports['packaged'])
    assert sha(package/'Physics/LapPhysics.exe')==receipt['physics_exe_sha256']==reports['native']['native_binary']['sha256']==reports['packaged']['physics_exe_sha256']
    assert reports['native']['checks'].get('thirty_five_native_cases') is True
    assert reports['tool_guard']['native_sha256']==receipt['physics_exe_sha256']
    assert reports['tool_guard']['asset_sha256']==asset_hash
    assert reports['tool_guard']['unit']['guard_source_sha256']==sha(root/'Physics/Phase6ToolCollision.h')
    assert reports['tool_guard']['unit']['test_source_sha256']==sha(root/'Physics/Phase6ToolCollisionTests.cpp')
    assert reports['native']['checks'].get('fifteen_long_hold_cases_and_all_raw_states') is True
    long_hold=validate_long_hold(root,a.native/'long-hold/long-hold-report.json',
                                 receipt['physics_exe_sha256'],reports['native']['model_config'])
    assert long_hold['summary']==reports['native']['long_hold_validation']['summary']
    raw_holds=reports['native']['long_hold_validation']['raw_state_audits']
    assert set(raw_holds)==set(expected_long_hold_cases()) and all(item['passed'] is True for item in raw_holds.values())
    for name,item in long_hold['evidence'].items():
        assert item['sha256']==reports['native']['evidence'][name]['sha256']
        assert item['trajectory']==reports['native']['evidence'][name]['trajectory']
    assert sha(package/'LapTrainer/Binaries/Win64/LapTrainer.exe')==receipt['game_exe_sha256']==reports['packaged']['game_exe_sha256']
    assert asset_hash==reports['native']['anatomy_asset']['sha256']==reports['geometry']['asset_sha256']==reports['assets']['physics_sha256']==reports['dataset']['physics_mesh_sha256']
    assert reports['blender']['blend_sha256']==sha(package/'Assets/Phase7/EndoForge_Anatomy.blend')
    assert reports['assets']['scene_sha256']==sha(package/'Assets/Phase7/scene.json')
    assert reports['independent_assets']['scene_sha256']==reports['assets']['scene_sha256']==reports['ue_static_assets']['scene_sha256']
    assert reports['independent_assets']['physical_asset_sha256']==asset_hash
    assert reports['ue_static_assets']['objects'] and all(item['passed'] is True and all(item['checks'].values()) for item in reports['ue_static_assets']['objects'])
    assert reports['context']['scene_sha256']==sha(package/'Assets/Phase7/scene.json')
    assert reports['context']['presented_sha256']==sha(a.capture/'phase5-presented-states.jsonl')
    assert reports['context']['native_reference_sha256']==reports['native']['evidence']['dual-reference']['trajectory']['sha256']
    assert reports['context']['audit_script_sha256']==sha(root/'Scripts/Phase7/audit_context.py')==sha(package/'Source/Scripts/Phase7/audit_context.py')
    for name,digest in reports['context']['dependency_sha256'].items():
        assert sha(root/name)==digest==sha(package/'Source'/name)
    assert reports['input']['checks']['dual_traction_retained'] is True
    assert reports['input']['phase']==7 and reports['packaged']['phase']==7
    assert reports['runtime']['phase']==7
    assert reports['runtime']['acceptance_spec_sha256']==sha(root/'Scripts/Phase7/acceptance-spec.json')==sha(package/'Source/Scripts/Phase7/acceptance-spec.json')
    assert reports['runtime']['runtime_sha256']==sha(a.capture/'phase6-runtime.json')==reports['packaged']['runtime_report_sha256']
    assert reports['runtime']['interaction_sha256']==sha(a.capture/'phase6-interaction-test.json')==reports['packaged']['interaction_report_sha256']
    assert reports['runtime']['unreal_log_sha256']==sha(a.capture/'unreal.log')
    for image in reports['runtime']['images']:
        assert sha(a.capture/image['file'])==image['sha256']
    assert reports['visual-review']['phase']==7
    assert reports['visual-review']['scene_sha256']==sha(package/'Assets/Phase7/scene.json')
    for image in reports['visual-review']['images']:
        assert sha(a.capture/image['file'])==image['sha256']
    assert reports['input']['stereo_frames']>=24 and reports['dataset']['frame_count']>=24
    # An audit must cover these accepted trajectories, rather than a prior run
    # with the same model and a convenient passing result.
    matrix_hashes={item['trajectory']['sha256'] for name,item in reports['native']['evidence'].items() if name.startswith('matrix-')}
    assert matrix_hashes and matrix_hashes=={item['sha256'] for item in reports['contact-matrix']['cases']}
    assert matrix_hashes=={item['trajectory_sha256'] for item in reports['liver-matrix']['cases']}
    hold_hashes={reports['native']['evidence']['long-hold-'+name]['trajectory']['sha256'] for name in REPRESENTATIVE_CASES}
    assert hold_hashes=={item['sha256'] for item in reports['contact-long-hold']['cases']}
    assert hold_hashes=={item['trajectory_sha256'] for item in reports['liver-long-hold']['cases']}
    assert reports['packaged']['input_report_sha256']==sha(report_paths['input'])
    for name in ('contact-endurance','liver-endurance'):
        assert reports[name]['original_trace']['sha256']==reports['native']['evidence']['endurance']['trajectory']['sha256']
    presented_hash=sha(a.capture/'phase5-presented-states.jsonl')
    presented_traces=set()
    for name in ('presented-contact','presented-liver'):
        trace=reports[name]['original_trace']; path=Path(trace['path'])
        assert sha(path)==trace['sha256']
        with path.open(encoding='utf-8-sig') as stream: header=json.loads(next(stream))
        assert header['provenance']['presented_sha256']==presented_hash
        assert header['provenance']['native_reference_sha256']==reports['native']['evidence']['dual-reference']['trajectory']['sha256']
        assert header['provenance']['extractor_sha256']==sha(root/'Scripts/Phase7/extract_presented_trace.py')==sha(package/'Source/Scripts/Phase7/extract_presented_trace.py')
        presented_traces.add(path)
    assert len(presented_traces)==1
    assert sha(a.capture/'dataset/visual-manifest.json')==reports['dataset']['visual_manifest_sha256']
    for frame in reports['dataset']['frames']:
        frame_path=a.capture/'dataset'/frame['sequence']/f"{frame['frame']:04d}"/'frame.json'
        assert sha(frame_path)==frame['frame_json_sha256']
        for relative,digest in frame['audited_payload_sha256'].items():
            payload=(frame_path.parent/relative).resolve()
            assert payload.is_relative_to(frame_path.parent.resolve()) and sha(payload)==digest

    for snapshot in reports['snapshot']['snapshots']:
        assert sha(a.capture/snapshot['file'])==snapshot['snapshot_sha256']
        assert sha(a.capture/snapshot['screenshot']['file'])==snapshot['screenshot']['sha256']
    out.mkdir(); index=[]

    def copy(src,dst,compress=False):
        dst.parent.mkdir(parents=True,exist_ok=True)
        if compress:
            with src.open('rb') as inp,gzip.open(dst,'wb',compresslevel=6) as target: shutil.copyfileobj(inp,target)
        else: shutil.copy2(src,dst)
        index.append({'source':str(src.resolve()),'source_sha256':sha(src),'path':dst.relative_to(out).as_posix(),
                      'bytes':dst.stat().st_size,'sha256':sha(dst),'gzip':compress})

    for name,path in report_paths.items(): copy(path,out/'Reports'/(name+'.json'))
    staging=Path(inheritance['staging_receipt_path'])
    metadata=inheritance['generated_runtime_metadata'];metadata_path=Path(metadata['path'])
    assert sha(staging)==inheritance['staging_receipt_sha256']
    assert sha(metadata_path)==metadata['sha256']==sha(package/'Physics/build-info.json')
    copy(staging,out/'Native/phase7-native-workspace.json')
    copy(metadata_path,out/'Native/build-info.json')
    copy(root/'tmp/phase7/preserved-baseline.json',out/'preserved-baseline.json')
    copy(root/'tmp/phase7/machine.json',out/'machine.json')
    copy(root/'Scripts/Phase7/acceptance-spec.json',out/'acceptance-spec.json')
    ue_receipt=root/'tmp/phase7/ue-final-validation.json'; ue=read(ue_receipt)
    assert ue['protocol']['passed'] is True
    for item in ue['source_files']+ue['additional_build_inputs']:
        assert sha(root/item['path'])==item['sha256'], 'UE input differs from validated editor: '+item['path']
    copy(ue_receipt,out/'Build/ue-final-validation.json')
    for item in (ue.get('prepared_receipt'),ue['protocol'].get('receipt')):
        if item is not None:
            path=root/item['path']; assert sha(path)==item['sha256']
            copy(path,out/'Build'/path.name)
    for item in (ue['editor_build_log'],ue['protocol']['log']):
        path=root/item['path']; assert sha(path)==item['sha256']
        copy(path,out/'Build'/path.name)
    uat_log=root/'tmp/phase7/uat-final.log'
    assert sha(uat_log)==receipt['package_log_sha256']
    copy(uat_log,out/'Build/uat-final.log')
    for path in presented_traces: copy(path,out/'AuditedTraces'/(path.name+'.gz'),True)
    # A Phase 5 diagnostic is not evidence for a changed Phase 7 binary. Current
    # failures may be retained in native diagnostic folders but never pass gates.
    # Preserve each native report and its exact accepted-state trajectory. Paths in
    # reports retain their original provenance; this index maps them to the bundle.
    copied=set()
    native_records=list(reports['native']['evidence'].values())+list(reports['native'].get('stress_exploration_4mm',{}).values())
    for item in native_records:
        for record in [item]+([item['trajectory']] if 'trajectory' in item else []):
            src=Path(record['path']); assert sha(src)==record['sha256']
            rel=src.resolve().relative_to(root)
            if str(rel) in copied: continue
            copied.add(str(rel)); compressed=src.suffix=='.jsonl'
            copy(src,out/'Native'/str(rel.with_suffix(rel.suffix+'.gz') if compressed else rel),compressed)
    native_folders={a.native/folder for folder in ('network','asset-validation','long-hold','tool-guard')}
    for phase in (3,4):
        isolated_legacy=a.native/f'legacy-phase{phase}-network-isolated'
        if isolated_legacy.is_dir(): native_folders.add(isolated_legacy)
    orchestration=a.native/'validation-orchestration.json'
    if orchestration.is_file():
        orchestration_report=read(orchestration)
        assert orchestration_report['passed'] is True
        assert orchestration_report['native_suite_sha256']==sha(report_paths['native'])
        assert orchestration_report['native_binary_sha256']==reports['native']['native_binary']['sha256']
        copy(orchestration,out/'Native/validation-orchestration.json')
        adapted=Path(orchestration_report['adapted_runner_path'])
        assert sha(adapted)==orchestration_report['adapted_runner_sha256']
        assert sha(adapted.parent/'launch.json')==orchestration_report['launch_receipt_sha256']
        for src in sorted(adapted.parent.iterdir()):
            if src.is_file(): copy(src,out/'Native/Runner'/src.name)
    for name in ('network','asset_validation'):
        if name in reports['native']['evidence']:
            native_folders.add(Path(reports['native']['evidence'][name]['path']).parent)
    for folder in sorted(native_folders):
        for src in sorted(folder.rglob('*')):
            if not src.is_file(): continue
            rel=src.resolve().relative_to(root)
            if str(rel) in copied: continue
            copied.add(str(rel)); compressed=src.suffix=='.jsonl'
            copy(src,out/'Native'/str(rel.with_suffix(rel.suffix+'.gz') if compressed else rel),compressed)
    # Keep relative snapshot/manifest/dataset links intact within Capture/.
    for src in sorted(a.capture.rglob('*')):
        if not src.is_file() or src.suffix in ('.pid','.dmp'): continue
        rel=src.relative_to(a.capture); compressed=src.suffix=='.jsonl'
        copy(src,out/'Capture'/str(rel.with_suffix(rel.suffix+'.gz') if compressed else rel),compressed)
    summary={'schema':'endoforge.phase7.candidate-verification.v1','phase':7,'passed':True,
             'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'checks':{name:True for name in reports},'physics_exe_sha256':receipt['physics_exe_sha256'],
             'game_exe_sha256':receipt['game_exe_sha256'],'physics_asset_sha256':asset_hash,
             'native_requalification':inheritance,'native_metrics':reports['native']['metrics'],'interactive_performance':reports['runtime']['performance'],
             'startup':reports['runtime']['startup'],
             'long_hold_geometry_scope':long_hold['geometry_scope'],
             'interaction_metrics':reports['runtime']['interaction_metrics'],
             'render_ablations':reports['runtime']['ablations'],
             'preserved_files':reports['preservation']['file_count'],'stereo_frames':reports['dataset']['frame_count'],
             'scope':'Phase 7 common foundation candidate passed engineering gates. Fresh extraction acceptance and archive SHA-256 are separately recorded beside the final ZIP. Anatomy review and clinical material calibration remain pending; no Project 1/2 specialized dataset completion.',
             'evidence':index}
    (out/'verification-index.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'bundled_files':len(index),'directory':str(out)}))
