"""Run a fresh native candidate and its independent geometry audits in two stages.

The native stage retains the existing 20 cases and adds 15 mandatory long holds.
Only legacy socket-test ports/output locations are isolated. The audits stage
uses the unchanged geometric kernels. Run neither stage alongside performance
acceptance. plan is read-only and launches no workload.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

from common import read, require, sha, write_new
from complete_native_suite import expected_cases
from native_long_hold import REPRESENTATIVE_CASES


ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent


def footprint():
    runtime=ROOT/'Physics/runtime'
    paths=list(runtime.glob('*.dll'))+[runtime/'LapPhysics.exe',runtime/'assets/phase6.json',ROOT/'Assets/Phase6/physics-mesh.json']
    paths += [path for path in (ROOT/'Physics').iterdir() if path.is_file() and path.suffix in ('.h','.cpp','.py','.ps1','.txt','.json')]
    paths += [Path(__file__),HERE/'complete_native_suite.py',HERE/'native_long_hold.py',HERE/'acceptance-spec.json']
    return {str(path.relative_to(ROOT).as_posix()):sha(path) for path in sorted(set(paths))}


def isolate_legacy(phase,out,port):
    """Keep the original test logic and native runtime, redirect only evidence/port."""
    folder=out/f'legacy-phase{phase}-network-isolated'
    folder.mkdir(exist_ok=False)
    original=ROOT/f'Physics/test_phase{phase}_network.py'
    source=original.read_text(encoding='utf-8-sig')
    if phase==3:
        replacements={
            'PORT = 47324':f'PORT = {port}',
            "(RUNTIME / 'phase3-network-test.log').open":f'pathlib.Path({str(folder/"service.log")!r}).open',
            "(RUNTIME / 'phase3-network-test-results.json').write_text":f'pathlib.Path({str(folder/"report.json")!r}).write_text'}
    elif phase==4:
        replacements={
            'PORT=47326':f'PORT={port}',
            "SESSION=RUNTIME/'phase4-network-session'":f'SESSION=pathlib.Path({str(folder/"sessions")!r})',
            "REPORT=RUNTIME/'phase4-network-test-results.json'":f'REPORT=pathlib.Path({str(folder/"report.json")!r})',
            "log=(RUNTIME/'phase4-network-test.log').open":f'log=pathlib.Path({str(folder/"service.log")!r}).open',
            "(RUNTIME/'phase4-network-states.json').write_text":f'pathlib.Path({str(folder/"states.json")!r}).write_text'}
    else:
        raise ValueError('Only legacy phases 3 and 4 are supported')
    for old,new in replacements.items():
        require(source.count(old)==1,'Legacy test isolation anchor changed: '+old)
        source=source.replace(old,new)
    adapted=folder/'isolated-test.py'
    adapted.write_text('__file__ = '+repr(str(original))+'\n'+source,encoding='utf-8')
    write_new(folder/'isolation.json',{'original_path':str(original),'original_sha256':sha(original),
              'adapted_sha256':sha(adapted),'overrides':replacements,
              'scope':'Only port and output files differ. Test logic, native executable and thresholds are unchanged.'})
    return adapted,folder/'report.json'


def run(command,log,expected):
    print(json.dumps({'starting':log.stem,'log':str(log)}),flush=True)
    with log.open('x',encoding='utf-8') as stream:
        result=subprocess.run([str(item) for item in command],cwd=ROOT,stdout=stream,
                              stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    require(result.returncode==0,'Validation command failed: '+str(log))
    if expected is not None:
        report=read(expected)
        require(report.get('passed') is True,'Missing/failed report: '+str(expected))
    print(json.dumps({'completed':log.stem,'exit_code':result.returncode}),flush=True)


def native_stage(native):
    launch=native.with_name(native.name+'-runner')
    require(not native.exists() and not launch.exists(),'Use fresh native and runner directories')
    launch.mkdir(parents=True)
    frozen=footprint()
    original=ROOT/'Physics/run_phase6_regression.py'
    source=original.read_text(encoding='utf-8-sig')
    old="""        runtime_report = BASE / f'runtime/phase{phase}-network-test-results.json'
        run(f'legacy-phase{phase}-network', [sys.executable, BASE / f'test_phase{phase}_network.py'], runtime_report)"""
    new="""        isolated_script, runtime_report = isolate_legacy(phase, out, 47333 + phase)
        run(f'legacy-phase{phase}-network', [sys.executable, isolated_script], runtime_report)"""
    require(source.count(old)==1,'Original native runner isolation anchor changed')
    adapted=launch/'isolated-regression.py'
    prefix='import sys\nsys.path.insert(0, '+repr(str(HERE))+')\nfrom validate_native_candidate import isolate_legacy\n__file__ = '+repr(str(original))+'\n'
    adapted.write_text(prefix+source.replace(old,new),encoding='utf-8')
    metadata={'schema':'endoforge.phase6.native-candidate-launch.v1',
              'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'frozen_files_sha256':frozen,'original_runner_sha256':sha(original),
              'adapted_runner_path':str(adapted),'adapted_runner_sha256':sha(adapted),
              'runner_override':{'original':old,'replacement':new},
              'expected_cases':expected_cases(),
              'scope':'Unchanged twenty regression cases plus fifteen sustained-grip cases; only legacy socket evidence/ports are isolated. Long holds use at most two correctness workers and their timings are not interactive performance.'}
    write_new(launch/'launch.json',metadata)
    run([sys.executable,adapted,'--output',native],launch/'regression.log',None)
    require(footprint()==frozen,'Native files changed during regression')
    checkpoint=read(native/'checkpoint.json')
    require(checkpoint['status']=='complete' and [case['name'] for case in checkpoint['completed']]==expected_cases(),
            'All twenty regression and fifteen sustained-grip cases are required')
    for case in checkpoint['completed']:
        path=Path(case['report']);report=read(path)
        require(sha(path)==case['sha256'] and report.get('passed') is True,'Native case mismatch')
    guard=native/'tool-guard'
    run([sys.executable,ROOT/'Physics/test_phase6_tool_guard_suite.py','--output',guard],
        launch/'tool-guard.log',guard/'report.json')
    require(footprint()==frozen,'Native files changed during collision guard tests')
    latency=native/'latency'
    run([sys.executable,ROOT/'Physics/test_phase6_latency.py','--output',latency,'--port','47331'],
        launch/'latency.log',latency/'report.json')
    require(footprint()==frozen,'Native files changed during latency test')
    suite=native/'native-suite-report.json'
    run([sys.executable,ROOT/'Physics/summarize_phase6_tests.py','--output',native,'--latency',latency/'report.json'],
        launch/'summary.log',suite)
    metadata.update(passed=True,native_suite_sha256=sha(suite),
                    native_binary_sha256=frozen['Physics/runtime/LapPhysics.exe'],
                    launch_receipt_sha256=sha(launch/'launch.json'),
                    finished_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    write_new(native/'validation-orchestration.json',metadata)
    print(json.dumps({'native_stage_passed':True,'suite':str(suite),'next':'Run audits only after coordinating CPU workloads.'}),flush=True)


def audits_stage(native,audits,workers):
    import numpy  # Fail before starting if this interpreter lacks the audit runtime.
    require(not audits.exists(),'Use a fresh audit directory; interrupted per-chunk work can be resumed directly')
    suite=read(native/'native-suite-report.json')
    require(suite['passed'] is True,'Native suite must pass first')
    require(sha(ROOT/'Physics/runtime/LapPhysics.exe')==suite['native_binary']['sha256'],'Candidate binary changed')
    if (native/'validation-orchestration.json').exists():
        orchestration=read(native/'validation-orchestration.json')
        require(orchestration['native_suite_sha256']==sha(native/'native-suite-report.json'),'Suite changed')
        require(footprint()==orchestration['frozen_files_sha256'],'Candidate files changed since tests')
    audits.mkdir(parents=True)
    for variable in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
        os.environ.setdefault(variable,'1')
    matrix=[Path(item['trajectory']['path']) for name,item in suite['evidence'].items() if name.startswith('matrix-')]
    require(len(matrix)==9,'Expected all nine matrix traces')
    run([sys.executable,ROOT/'Scripts/Phase5/audit_geometry.py','--mesh',ROOT/'Assets/Phase6/physics-mesh.json',
         '--output',audits/'geometry.json'],audits/'geometry.log',audits/'geometry.json')
    arguments=[value for path in matrix for value in ('--trajectory',path)]
    run([sys.executable,ROOT/'Scripts/Phase5/audit_contact.py',*arguments,'--workers',workers,
         '--output',audits/'contact-matrix.json'],audits/'contact-matrix.log',audits/'contact-matrix.json')
    parts=audits/'liver-matrix-parts';parts.mkdir()
    def liver_case(path):
        output=parts/(path.stem+'.json')
        run([sys.executable,ROOT/'Scripts/Phase5/audit_liver_contact.py','--trajectory',path,'--output',output],
            parts/(path.stem+'.log'),output)
        return read(output)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results=list(pool.map(liver_case,matrix))
    liver={key:value for key,value in results[0].items() if key not in ('cases','passed')}
    liver['cases']=[report['cases'][0] for report in results]
    liver['passed']=all(report['passed'] is True and len(report['cases'])==1 for report in results)
    liver['orchestration']='Independent unchanged CLI audits run in parallel, one original trace per process.'
    write_new(audits/'liver-matrix.json',liver)
    trace=Path(suite['evidence']['endurance']['trajectory']['path'])
    for kind in ('contact','liver'):
        output=audits/(kind+'-endurance.json')
        run([sys.executable,HERE/'audit_trace_resumable.py','--trajectory',trace,'--kind',kind,
             '--workers',workers,'--chunk-states','1000','--work-dir',audits/('endurance-'+kind+'-chunks'),
             '--output',output],audits/(kind+'-endurance.log'),output)
    # Prolonged geometry coverage is bounded to both nominal single grasps and
    # the dual case. All fifteen cases still have independent raw-state checks
    # in the native summary; no offset geometry audit is implied.
    representative=[Path(suite['evidence']['long-hold-'+name]['trajectory']['path'])
                    for name in REPRESENTATIVE_CASES]
    arguments=[value for path in representative for value in ('--trajectory',path)]
    run([sys.executable,ROOT/'Scripts/Phase5/audit_contact.py',*arguments,'--workers',workers,
         '--output',audits/'contact-long-hold.json'],audits/'contact-long-hold.log',audits/'contact-long-hold.json')
    parts=audits/'liver-long-hold-parts';parts.mkdir()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results=list(pool.map(liver_case,representative))
    liver={key:value for key,value in results[0].items() if key not in ('cases','passed')}
    liver['cases']=[report['cases'][0] for report in results]
    liver['passed']=all(report['passed'] is True and len(report['cases'])==1 for report in results)
    liver['orchestration']='Three nominal long-hold traces only; unchanged CLI kernels. Offset cases are not independently whole-face audited.'
    write_new(audits/'liver-long-hold.json',liver)
    names=('geometry','contact-matrix','liver-matrix','contact-endurance','liver-endurance',
           'contact-long-hold','liver-long-hold')
    reports={name:read(audits/(name+'.json')) for name in names}
    expected={item['trajectory']['sha256'] for name,item in suite['evidence'].items() if name.startswith('matrix-')}
    require({item['sha256'] for item in reports['contact-matrix']['cases']}==expected,'Contact matrix trace mismatch')
    require({item['trajectory_sha256'] for item in reports['liver-matrix']['cases']}==expected,'Liver matrix trace mismatch')
    for kind in ('contact','liver'):
        require(reports[kind+'-endurance']['original_trace']['sha256']==suite['evidence']['endurance']['trajectory']['sha256'],
                'Endurance trace mismatch')
    expected_holds={suite['evidence']['long-hold-'+name]['trajectory']['sha256'] for name in REPRESENTATIVE_CASES}
    require({item['sha256'] for item in reports['contact-long-hold']['cases']}==expected_holds,
            'Representative long-hold contact trace mismatch')
    require({item['trajectory_sha256'] for item in reports['liver-long-hold']['cases']}==expected_holds,
            'Representative long-hold liver trace mismatch')
    require(all(report['passed'] is True for report in reports.values()),'Independent audit failed')
    write_new(audits/'native-audit-index.json',{'schema':'endoforge.phase6.native-audit-index.v1','passed':True,
              'native_suite_sha256':sha(native/'native-suite-report.json'),'native_binary_sha256':suite['native_binary']['sha256'],
              'reports':{name:sha(audits/(name+'.json')) for name in names}})
    print(json.dumps({'independent_native_audits_passed':True,'audits':str(audits)}),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('plan','native','audits'))
    parser.add_argument('--native-dir',type=Path,required=True)
    parser.add_argument('--audit-dir',type=Path)
    parser.add_argument('--workers',type=int,default=3)
    args=parser.parse_args();native=args.native_dir.resolve()
    require(native.is_relative_to(ROOT/'tmp/phase6'),'Native evidence must remain under tmp/phase6')
    require(1<=args.workers<=8,'Use one to eight audit workers')
    audits=args.audit_dir.resolve() if args.audit_dir is not None else None
    if audits is not None:require(audits.is_relative_to(ROOT/'tmp/phase6'),'Audits must remain under tmp/phase6')
    if args.mode=='plan':
        print(json.dumps({'launches_workloads':False,'native_directory':str(native),
                          'audit_directory':str(audits) if audits else None,'native_cases':expected_cases(),
                          'ports':{'phase6_network_and_replay':47332,'legacy3':47336,'legacy4':47337,'latency':47331},
                          'stages':['native20','long_hold15','latency','native_summary','independent_geometry','matrix_contact',
                                    'matrix_liver','endurance_contact','endurance_liver','representative_long_hold_contact','representative_long_hold_liver'],
                          'coordination':'Run native and audits as separate explicit invocations, with no concurrent performance acceptance.'},indent=2))
    elif args.mode=='native':native_stage(native)
    else:
        require(audits is not None,'--audit-dir required')
        audits_stage(native,audits,args.workers)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
