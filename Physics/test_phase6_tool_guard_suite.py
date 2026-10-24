"""Verify guard mathematics, real TCP/replay, and loaded release on current assets."""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT=pathlib.Path(__file__).resolve().parent.parent
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run(out):
    out.mkdir(parents=True,exist_ok=False)
    native=ROOT/'Physics/runtime/LapPhysics.exe'
    unit=ROOT/'Physics/build/Release/Phase6ToolCollisionTests.exe'
    mesh=ROOT/'Assets/Phase6/physics-mesh.json'
    frozen=sha(native);asset_hash=sha(mesh)
    report={'schema':'endoforge.phase6.tool-guard-suite.v1','passed':False,
            'native_sha256':frozen,'asset_sha256':asset_hash,'checks':{},'evidence':{}}
    def invoke(name,cmd,document=None):
        log=out/(name+'.log')
        with log.open('w',encoding='utf-8') as f:
            process=subprocess.run([str(x) for x in cmd],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        assert sha(native)==frozen and sha(mesh)==asset_hash,'Test inputs changed'
        ok=process.returncode==0
        if document is not None:
            data=json.loads(document.read_text(encoding='utf-8-sig'))
            ok &= data.get('passed') is True and all(v is True for v in data['checks'].values())
        report['checks'][name]=ok
        report['evidence'][name]={'exit_code':process.returncode,'log_sha256':sha(log)}
        if document is not None:report['evidence'][name].update(report_path=str(document),report_sha256=sha(document))
        assert ok,'Guard verification failed: '+name
        return log
    try:
        assert unit.stat().st_mtime>=max((ROOT/'Physics/Phase6ToolCollision.h').stat().st_mtime,
                                      (ROOT/'Physics/Phase6ToolCollisionTests.cpp').stat().st_mtime),'Rebuild standalone guard tests'
        log=invoke('geometry-math',[unit])
        assert re.search(r'checks=18 failures=0\b',log.read_text()),'Incomplete standalone geometry coverage'
        report['unit']={'binary_sha256':sha(unit),'test_source_sha256':sha(ROOT/'Physics/Phase6ToolCollisionTests.cpp'),
                        'guard_source_sha256':sha(ROOT/'Physics/Phase6ToolCollision.h')}
        tcp=out/'tcp'
        invoke('tcp-replay',[sys.executable,ROOT/'Physics/test_phase6_tool_guard.py','--output',tcp],tcp/'report.json')
        asset=json.loads(mesh.read_text());recipes=asset['phase6_interaction']['recipes']
        options={'reference_targets_m':[r['rest_ready_tip_m'] for r in recipes],
                 'rolls_deg':[r['roll_deg'] for r in recipes],'right_axial_clearance_m':.025,
                 'dual_lift_m':.002,'dual_hold_steps':30,'loaded_block_release_probe':True}
        options_path=out/'loaded-options.json';options_path.write_text(json.dumps(options,indent=2))
        loaded=out/'loaded-block.json'
        invoke('loaded-grip-release',[native,'--self-test-phase6-fast-handoff','--mesh',mesh,
                                     '--probe-options',options_path,'--report',loaded],loaded)
        report['passed']=all(report['checks'].values())
    finally:
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return 0 if report['passed'] else 2
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,required=True)
    raise SystemExit(run(p.parse_args().output.resolve()))
