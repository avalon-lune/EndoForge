"""Freeze inputs before the final editor build, then bind real validation evidence.

prepare writes hashes only and makes no test-success claim. protocol runs the
existing atomic snapshot test in one owned headless editor process. seal requires
that protocol result plus a successful full editor input/data exercise, all with
unchanged inputs and the same editor module. Packaged performance remains separate.
"""
import argparse
import datetime
import json
from pathlib import Path
import re
import subprocess
import time

from build_receipt import sha, source_hashes
from common import passed, read, require, write_new


TEST = 'EndoForge.Phase4.AtomicSnapshotProtocol'


def record(root, path):
    path=path.resolve()
    require(path.is_relative_to(root), 'Evidence must stay within the workspace')
    return {'path':path.relative_to(root).as_posix(),'sha256':sha(path)}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def inputs(root):
    result=source_hashes(root)
    result['docs/PHASE6.md']=sha(root/'docs/PHASE6.md')
    return result


def bound_native_suite(root,data,required):
    reference=data['native_suite']
    path=root/reference['path']
    if reference.get('status')=='pending':
        if not required:
            return None
        require(path.is_file(),'The prepared native suite is still pending; seal is forbidden')
    else:
        require(sha(path)==reference['sha256'],'Native suite evidence changed after preparation')
    suite=read(path)
    passed('native suite',suite)
    require(all(value is True for value in suite['checks'].values()),'Native suite has incomplete/failed checks')
    require(suite['checks'].get('thirty_five_native_cases') is True and
            suite['checks'].get('fifteen_long_hold_cases_and_all_raw_states') is True,
            'Final source freeze requires all twenty regression and fifteen sustained-grip cases')
    require(suite['native_binary']['sha256']==data['physics_executable']['sha256'], 'Native suite binary mismatch')
    require(suite['anatomy_asset']['sha256']==sha(root/'Assets/Phase6/physics-mesh.json'),'Native suite asset mismatch')
    return record(root,path)


def prepared(root, path):
    data=read(path)
    require(data['schema']=='endoforge.phase6.ue-freeze-prepared.v1', 'Not a prepared Phase 6 freeze')
    require(inputs(root)==data['input_sha256'], 'Source/build inputs changed after preparation')
    require(sha(root/'Physics/runtime/LapPhysics.exe')==data['physics_executable']['sha256'], 'Native binary changed')
    bound_native_suite(root,data,False)
    return data


def editor_build(root, data, log):
    module=root/'Prototype/LapTrainer/Binaries/Win64/UnrealEditor-LapTrainer.dll'
    text=log.read_text(encoding='utf-8-sig',errors='replace')
    require('Result: Succeeded' in text, 'Successful final editor build log required')
    timestamp=datetime.datetime.fromisoformat(data['created_utc']).timestamp()
    require(log.stat().st_mtime>=timestamp, 'Editor build log predates input preparation')
    compiled=[root/name for name in data['input_sha256'] if name.startswith('Prototype/LapTrainer/Source/')]
    require(all(path.stat().st_mtime<=module.stat().st_mtime for path in compiled), 'Editor module predates source')
    return module


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','protocol','seal'))
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepared',type=Path)
    parser.add_argument('--editor-build-log',type=Path)
    parser.add_argument('--engine-root',type=Path,default=Path('E:/UE_5.7'))
    parser.add_argument('--protocol-log',type=Path)
    parser.add_argument('--protocol-receipt',type=Path)
    parser.add_argument('--capture',type=Path)
    parser.add_argument('--native-suite',type=Path,
                        help='Passed exact-binary native suite to bind during prepare; defaults to the original regression directory')
    parser.add_argument('--allow-pending-native-suite',action='store_true',
                        help='prepare only: freeze an explicit future suite path without a pass claim; seal still requires the completed passed suite')
    args=parser.parse_args();root=args.root.resolve()
    require(not args.output.exists(), 'Use a fresh receipt output')
    if args.mode=='prepare':
        native=args.native_suite.resolve() if args.native_suite is not None else root/'tmp/phase6/physics/regression/native-suite-report.json'
        exe=record(root,root/'Physics/runtime/LapPhysics.exe')
        require(native.is_relative_to(root),'Native suite must remain in the workspace')
        if native.exists():
            reference=record(root,native)
        else:
            require(args.allow_pending_native_suite and args.native_suite is not None,
                    'Absent suite requires explicit --native-suite and --allow-pending-native-suite')
            reference={'path':native.relative_to(root).as_posix(),'status':'pending',
                       'expected_native_binary_sha256':exe['sha256']}
        result={'schema':'endoforge.phase6.ue-freeze-prepared.v1','phase':6,
                'created_utc':now(),'source_frozen':False,'status':'inputs_prepared_no_validation_claim',
                'input_sha256':inputs(root),'physics_executable':exe,'native_suite':reference,
                'native_validation_status':'pending_not_accepted' if reference.get('status')=='pending' else 'passed_exact_binary'}
        bound_native_suite(root,result,False)
        write_new(args.output,result)
        print(json.dumps({'prepared':str(args.output),'inputs':len(result['input_sha256']),
                          'next':'Build final editor; run protocol and complete full editor input/data exercise; then seal.'}))
        return 0
    require(args.prepared is not None and args.editor_build_log is not None,
            '--prepared and --editor-build-log are required')
    data=prepared(root,args.prepared)
    module=editor_build(root,data,args.editor_build_log)
    module_before=record(root,module)
    if args.mode=='protocol':
        require(args.protocol_log is not None, '--protocol-log required')
        require(not args.protocol_log.exists(), 'Use a fresh protocol log')
        args.protocol_log.parent.mkdir(parents=True,exist_ok=True)
        executable=args.engine_root/'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
        command=[str(executable),str(root/'Prototype/LapTrainer/LapTrainer.uproject'),
                 '-ExecCmds=Automation RunTests '+TEST+';Quit',
                 '-TestExit=Automation Test Queue Empty','-unattended','-nullrhi',
                 '-nosplash','-nosound','-NoP4','-abslog='+str(args.protocol_log.resolve())]
        started=now();wall=time.monotonic()
        with args.protocol_log.with_suffix('.stdout.log').open('x',encoding='utf-8') as stream:
            process=subprocess.run(command,cwd=root,stdout=stream,stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW,timeout=240)
        text=args.protocol_log.read_text(encoding='utf-8-sig',errors='replace')
        matches=[line for line in text.splitlines() if 'Test Completed.' in line and 'Path={'+TEST+'}' in line]
        success=len(matches)==1 and re.search(r'Result=\{(?:Success|Succeeded|成功)\}',matches[0]) is not None
        prepared(root,args.prepared)
        require(record(root,module)==module_before, 'Editor module changed during protocol test')
        result={'schema':'endoforge.phase6.ue-protocol-run.v1','phase':6,
                'passed':process.returncode==0 and success,'test_name':TEST,
                'process_exit_code':process.returncode,'started_utc':started,'elapsed_seconds':time.monotonic()-wall,
                'prepared_sha256':sha(args.prepared),'editor_module':module_before,
                'editor_build_log':record(root,args.editor_build_log),'log':record(root,args.protocol_log),
                'success_assertion':matches[0] if len(matches)==1 else None,'command':command}
        write_new(args.output,result)
        print(json.dumps({'passed':result['passed'],'receipt':str(args.output),'process_exit_code':process.returncode}))
        return 0 if result['passed'] else 2
    require(args.protocol_receipt is not None and args.capture is not None,
            '--protocol-receipt and --capture required for seal')
    native_suite=bound_native_suite(root,data,True)
    protocol=read(args.protocol_receipt);passed('protocol',protocol)
    require(protocol['prepared_sha256']==sha(args.prepared), 'Protocol used a different input freeze')
    require(protocol['editor_module']==module_before and protocol['editor_build_log']==record(root,args.editor_build_log),
            'Protocol module/build differs from final editor')
    require(sha(root/protocol['log']['path'])==protocol['log']['sha256'], 'Protocol log changed')
    capture=args.capture.resolve()
    input_path=capture/'phase5-input-test.json';interaction_path=capture/'phase6-interaction-test.json'
    lifecycle_path=capture/'editor-run.json';runtime_path=capture/'phase6-runtime.json'
    input_report=read(input_path);interaction=read(interaction_path);lifecycle=read(lifecycle_path);runtime=read(runtime_path)
    for name,report in (('editor input',input_report),('interaction',interaction)):
        passed(name,report)
        require(report['phase']==6 and all(value is True for value in report['checks'].values()), 'Incomplete Phase 6 input checks')
    require(input_report['stereo_frames']>=24 and input_report['checks']['dual_traction_retained'] is True,
            'Full stereo and retained dual traction required before freeze')
    require(lifecycle['game_exit_code']==lifecycle['native_exit_code']==0 and
            lifecycle['native_graceful_exit'] is True and not lifecycle.get('error'), 'Editor/native lifecycle did not finish cleanly')
    require(runtime['phase']==6, 'Incorrect runtime milestone')
    timestamp=datetime.datetime.fromisoformat(data['created_utc']).timestamp()
    require(all(path.stat().st_mtime>=timestamp for path in (input_path,interaction_path,lifecycle_path,runtime_path)),
            'Editor evidence predates preparation')
    require(module.stat().st_mtime<=input_path.stat().st_mtime, 'Editor module was rebuilt after input test')
    source=[];assets=[];additional=[]
    for name,digest in data['input_sha256'].items():
        target=source if name.startswith('Prototype/LapTrainer/Source/') else assets if name.startswith(('Assets/','Prototype/LapTrainer/Content/')) else additional
        target.append({'path':name,'sha256':digest})
    result={'schema':'endoforge.phase6.ue-validation.v1','phase':6,'created_utc':now(),
            'source_frozen':True,'source_files':source,'additional_build_inputs':additional,'assets':assets,
            'prepared_receipt':record(root,args.prepared),'editor_module':module_before,
            'editor_build_log':record(root,args.editor_build_log),
            'protocol':{**protocol,'same_final_editor_module':True,'receipt':record(root,args.protocol_receipt)},
            'editor_input':{'passed':True,'report':record(root,input_path),'interaction':record(root,interaction_path),
                            'lifecycle':record(root,lifecycle_path),'runtime':record(root,runtime_path),
                            'stereo_frames':input_report['stereo_frames'],'runtime_run_kind':runtime['run_kind']},
            'physics_executable':data['physics_executable'],'native_suite':native_suite,
            'scope':'Frozen source/editor integration receipt. Actual packaged runtime, isolated performance, geometry, dataset and fresh-ZIP acceptance remain separate required gates.'}
    write_new(args.output,result)
    print(json.dumps({'source_frozen':True,'receipt':str(args.output),'editor_module_sha256':module_before['sha256']}))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
