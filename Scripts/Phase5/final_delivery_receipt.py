"""Bind a freshly extracted, actually executed ZIP to its final independent audits."""
import argparse
import datetime
import json
from pathlib import Path

from archive import sha, verify
from collect_evidence import read, validate_pass


def main():
    p=argparse.ArgumentParser()
    for name in ('archive','archive-report','extraction-report','package','extracted','capture','audits','preservation','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if a.output.exists(): raise FileExistsError('Use a fresh final receipt')
    archive_report=read(a.archive_report); extraction=read(a.extraction_report)
    archive_hash=sha(a.archive)
    assert archive_report['passed'] is True and archive_report['crc_all_files'] is True
    assert extraction['passed'] is True
    assert archive_hash==archive_report['sha256']==extraction['archive_sha256']
    assert Path(extraction['extracted_to']).resolve()==a.extracted.resolve()
    files=verify(a.extracted)
    assert sha(a.package/'package-manifest.json')==sha(a.extracted/'package-manifest.json')
    candidate=read(a.extracted/'Verification/verification-index.json')
    validate_pass('candidate',candidate)
    build=read(a.extracted/'phase5-build-receipt.json')
    reports={name:read(a.audits/(name+'.json')) for name in ('presented-contact','presented-liver','dataset','snapshot')}
    reports.update(packaged=read(a.capture/'phase5-packaged-run.json'),input=read(a.capture/'phase5-input-test.json'),preservation=read(a.preservation))
    for name,report in reports.items(): validate_pass(name,report)
    game=sha(a.extracted/'LapTrainer/Binaries/Win64/LapTrainer.exe')
    native=sha(a.extracted/'Physics/LapPhysics.exe')
    asset=sha(a.extracted/'Assets/Phase5/physics-mesh.json')
    assert native==build['physics_exe_sha256']==candidate['physics_exe_sha256']==reports['packaged']['physics_exe_sha256']
    assert game==build['game_exe_sha256']==candidate['game_exe_sha256']==reports['packaged']['game_exe_sha256']
    assert asset==candidate['physics_asset_sha256']==reports['dataset']['physics_mesh_sha256']
    assert Path(reports['packaged']['package_root']).resolve()==a.extracted.resolve()
    assert reports['packaged']['native_exit_code']==reports['packaged']['game_exit_code']==0
    assert sha(a.capture/'phase5-input-test.json')==reports['packaged']['input_report_sha256']
    assert reports['input']['checks']['dual_traction_retained'] is True
    assert reports['input']['stereo_frames']>=24 and reports['dataset']['frame_count']>=24
    assert reports['input']['performance']['mean_fps']>=30
    assert sha(a.capture/'dataset/visual-manifest.json')==reports['dataset']['visual_manifest_sha256']
    for frame in reports['dataset']['frames']:
        path=a.capture/'dataset'/frame['sequence']/f"{frame['frame']:04d}"/'frame.json'
        assert sha(path)==frame['frame_json_sha256']
    for snapshot in reports['snapshot']['snapshots']:
        assert sha(a.capture/snapshot['file'])==snapshot['snapshot_sha256']
        assert sha(a.capture/snapshot['screenshot']['file'])==snapshot['screenshot']['sha256']
        assert snapshot['screenshot']['dimensions']==[1920,1080]
    for name in ('presented-contact','presented-liver'):
        trace=reports[name]['original_trace']; path=Path(trace['path'])
        assert sha(path)==trace['sha256']
        with path.open(encoding='utf-8-sig') as stream: header=json.loads(next(stream))
        assert header['provenance']['presented_sha256']==sha(a.capture/'phase5-presented-states.jsonl')
    evidence=[a.archive_report,a.extraction_report,a.preservation,a.capture/'phase5-packaged-run.json',a.capture/'phase5-input-test.json']
    evidence += [a.audits/(name+'.json') for name in ('presented-contact','presented-liver','dataset','snapshot')]
    result={
        'schema':'endoforge.phase5.final-delivery.v1','phase':5,'passed':True,
        'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'checks':{'candidate_acceptance_passed':True,'archive_crc_and_sha256_verified':True,
                  'fresh_extraction_manifest_verified':True,'fresh_packaged_input_passed':True,
                  'fresh_contact_and_organ_geometry_audited':True,'fresh_stereo_and_snapshot_audited':True,
                  'display_1920x1080_mean_fps_at_least_30':True,'prior_deliveries_and_references_unchanged':True},
        'archive':{'path':str(a.archive.resolve()),'sha256':archive_hash,'bytes':a.archive.stat().st_size},
        'manifest_files':len(files),'physics_exe_sha256':native,'game_exe_sha256':game,'physics_asset_sha256':asset,
        'source_model':'Assets/Phase5/EndoForge_Anatomy.blend',
        'native_metrics':candidate['native_metrics'],'fresh_interactive_performance':reports['input']['performance'],
        'fresh_contact_metrics':reports['presented-contact']['metrics'],
        'fresh_liver_metrics':reports['presented-liver']['metrics'],
        'fresh_stereo_frames':reports['dataset']['frame_count'],'preserved_files':reports['preservation']['file_count'],
        'evidence':[{'path':str(path.resolve()),'sha256':sha(path)} for path in evidence],
        'scope':'Phase 5 engineering scene and tested finite paths. No suturing, clinical tissue calibration or completed research dataset. Replay is tolerance-based, not bit-identical. Display FPS and actual simulation progression are separate measurements.'}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'receipt':str(a.output),'archive_sha256':archive_hash,'performance':result['fresh_interactive_performance']}))


if __name__=='__main__': main()
