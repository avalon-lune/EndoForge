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
        'presented-contact','presented-liver','dataset','snapshot','preservation')}
    report_paths.update(native=a.native/'native-suite-report.json',
                        packaged=a.capture/'phase5-packaged-run.json',
                        input=a.capture/'phase5-input-test.json',
                        assets=root/'Assets/Phase5/asset-contract-check.json',
                        blender=root/'Assets/Phase5/blend-verification.json')
    reports={name:read(path) for name,path in report_paths.items()}
    for name,report in reports.items():
        validate_pass(name,report)
    asset=package/'Assets/Phase5/physics-mesh.json'; asset_hash=sha(asset)
    receipt=read(package/'phase5-build-receipt.json')
    assert sha(package/'Physics/LapPhysics.exe')==receipt['physics_exe_sha256']==reports['native']['native_binary']['sha256']==reports['packaged']['physics_exe_sha256']
    assert sha(package/'LapTrainer/Binaries/Win64/LapTrainer.exe')==receipt['game_exe_sha256']==reports['packaged']['game_exe_sha256']
    assert asset_hash==reports['native']['anatomy_asset']['sha256']==reports['geometry']['asset_sha256']==reports['assets']['physics_sha256']==reports['dataset']['physics_mesh_sha256']
    assert reports['blender']['blend_sha256']==sha(package/'Assets/Phase5/EndoForge_Anatomy.blend')
    assert reports['assets']['scene_sha256']==sha(package/'Assets/Phase5/scene.json')
    assert reports['input']['checks']['dual_traction_retained'] is True
    assert reports['input']['stereo_frames']>=24 and reports['dataset']['frame_count']>=24
    # An audit must cover these accepted trajectories, rather than a prior run
    # with the same model and a convenient passing result.
    matrix_hashes={item['trajectory']['sha256'] for name,item in reports['native']['evidence'].items() if name.startswith('matrix-')}
    assert matrix_hashes and matrix_hashes=={item['sha256'] for item in reports['contact-matrix']['cases']}
    assert matrix_hashes=={item['trajectory_sha256'] for item in reports['liver-matrix']['cases']}
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
        presented_traces.add(path)
    assert len(presented_traces)==1
    assert sha(a.capture/'dataset/visual-manifest.json')==reports['dataset']['visual_manifest_sha256']
    for frame in reports['dataset']['frames']:
        frame_path=a.capture/'dataset'/frame['sequence']/f"{frame['frame']:04d}"/'frame.json'
        assert sha(frame_path)==frame['frame_json_sha256']
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
    copy(root/'tmp/phase5/preserved-baseline.json',out/'preserved-baseline.json')
    copy(root/'tmp/phase5/machine.json',out/'machine.json')
    copy(root/'Scripts/Phase5/acceptance-spec.json',out/'acceptance-spec.json')
    ue_receipt=root/'tmp/phase5/ue-final-validation.json'; ue=read(ue_receipt)
    assert ue['protocol']['passed'] is True
    for item in ue['source_files']+ue['additional_build_inputs']:
        assert sha(root/item['path'])==item['sha256'], 'UE input differs from validated editor: '+item['path']
    copy(ue_receipt,out/'Build/ue-final-validation.json')
    for item in (ue['editor_build_log'],ue['protocol']['log']):
        path=root/item['path']; assert sha(path)==item['sha256']
        copy(path,out/'Build'/path.name)
    uat_log=root/'tmp/phase5/uat-final.log'
    assert sha(uat_log)==receipt['package_log_sha256']
    copy(uat_log,out/'Build/uat-final.log')
    for path in presented_traces: copy(path,out/'AuditedTraces'/(path.name+'.gz'),True)
    # Historical failure retained as a diagnostic, never counted as a passed gate.
    strict_failure=root/'tmp/phase5-physics-v2/network/report.json'
    assert read(strict_failure)['passed'] is False
    copy(strict_failure,out/'Diagnostics/original-strict-replay-failure.json')
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
    native_folders={a.native/folder for folder in ('network','asset-validation')}
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
    summary={'schema':'endoforge.phase5.candidate-verification.v1','phase':5,'passed':True,
             'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'checks':{name:True for name in reports},'physics_exe_sha256':receipt['physics_exe_sha256'],
             'game_exe_sha256':receipt['game_exe_sha256'],'physics_asset_sha256':asset_hash,
             'native_metrics':reports['native']['metrics'],'interactive_performance':reports['input']['performance'],
             'preserved_files':reports['preservation']['file_count'],'stereo_frames':reports['dataset']['frame_count'],
             'scope':'Candidate passed engineering gates. Fresh extraction acceptance and archive SHA-256 are separately recorded beside the final ZIP. Anatomy review and clinical material calibration remain pending.',
             'evidence':index}
    (out/'verification-index.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'bundled_files':len(index),'directory':str(out)}))
