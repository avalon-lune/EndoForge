"""Freeze inputs before the final editor build, then bind real validation evidence.

prepare writes hashes only and makes no test-success claim. protocol runs the
existing atomic snapshot test in one owned headless editor process. seal requires
that protocol result plus a successful full editor input/data exercise, all with
unchanged inputs and the same editor module. Packaged performance remains separate.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

# These helpers may import unchanged auditors; source freezes never write caches.
sys.dont_write_bytecode = True
from build_receipt import sha, source_hashes, verify_inheritance
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
    require('docs/PHASE8.md' in result, 'Finalized Phase8 milestone documentation must be frozen')
    allowed_tmp={'tmp/phase8/import_phase8.py','tmp/phase8/run_import.ps1'}
    require(all(not name.startswith('tmp/') or name in allowed_tmp for name in result),
            'Downstream receipts/capture/audit outputs must not enter the source freeze')
    return result


def bound_native_inheritance(root,data):
    reference=data['native_inheritance']
    path=root/reference['path']
    require(sha(path)==reference['sha256'], 'Native inheritance receipt changed after preparation')
    inherited=verify_inheritance(root,path)
    require(inherited['native_binary_sha256']==data['physics_executable']['sha256'], 'Inherited native binary mismatch')
    require(inherited['physical_asset_sha256']==sha(root/'Assets/Phase8/physics-mesh.json'), 'Inherited physical mesh mismatch')
    return record(root,path)


def prepared(root, path):
    data=read(path)
    require(data['schema']=='endoforge.phase8.ue-freeze-prepared.v1' and data.get('phase')==8,
            'Not a prepared Phase 8 freeze')
    require(inputs(root)==data['input_sha256'], 'Source/build inputs changed after preparation')
    require(sha(root/'Physics/runtime/LapPhysics.exe')==data['physics_executable']['sha256'], 'Native binary changed')
    bound_native_inheritance(root,data)
    require(inputs(root)==data['input_sha256'], 'Source/build inputs changed during native identity verification')
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
    parser.add_argument('--native-inheritance',type=Path,default=Path('tmp/phase8/native-inheritance.json'),
                        help='Existing passed exact-identity Phase7 inheritance receipt; no new native suite is run')
    args=parser.parse_args();root=args.root.resolve()
    require(not args.output.exists(), 'Use a fresh receipt output')
    output=args.output.resolve()
    require(output.is_relative_to(root/'tmp/phase8') or output.is_relative_to(root/'output/Phase8'),
            'Phase8 receipts must remain under tmp/phase8 or output/Phase8')
    if args.mode=='prepare':
        native=(args.native_inheritance if args.native_inheritance.is_absolute() else root/args.native_inheritance).resolve()
        exe=record(root,root/'Physics/runtime/LapPhysics.exe')
        require(native.is_relative_to(root) and native.is_file(), 'Existing native inheritance receipt must remain in the workspace')
        reference=record(root,native)
        result={'schema':'endoforge.phase8.ue-freeze-prepared.v1','phase':8,
                'created_utc':now(),'source_frozen':False,'status':'inputs_prepared_no_validation_claim',
                'input_sha256':inputs(root),'physics_executable':exe,'native_inheritance':reference,
                'native_validation_status':'inherited_exact_phase7_identity_no_new_native_execution',
                'native_execution_phase':7,'new_native_35_execution':False,
                'input_scope':'Exact shared source_hashes policy: finalized source/config/content/assets/scripts plus docs/PHASE8.md and present canonical import helpers. Capture/audit outputs, self receipts, unrelated and still-edited general documentation are excluded.'}
        bound_native_inheritance(root,result)
        require(inputs(root)==result['input_sha256'], 'Source/build inputs changed while preparing the freeze')
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
        protocol_log=args.protocol_log.resolve()
        require(protocol_log.is_relative_to(root/'tmp/phase8') or protocol_log.is_relative_to(root/'output/Phase8'),
                'Phase8 protocol logs must remain under tmp/phase8 or output/Phase8')
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
        result={'schema':'endoforge.phase8.ue-protocol-run.v1','phase':8,
                'passed':process.returncode==0 and success,'test_name':TEST,
                'process_exit_code':process.returncode,'started_utc':started,'elapsed_seconds':time.monotonic()-wall,
                'prepared_sha256':sha(args.prepared),'editor_module':module_before,
                'editor_build_log':record(root,args.editor_build_log),'log':record(root,args.protocol_log),
                'success_assertion':matches[0] if len(matches)==1 else None,'command':command,
                'native_inheritance':data['native_inheritance'],
                'native_execution_phase':7,'new_native_35_execution':False}
        write_new(args.output,result)
        print(json.dumps({'passed':result['passed'],'receipt':str(args.output),'process_exit_code':process.returncode}))
        return 0 if result['passed'] else 2
    require(args.protocol_receipt is not None and args.capture is not None,
            '--protocol-receipt and --capture required for seal')
    # prepared() has already reverified every recorded inherited identity for
    # this invocation. There is no pending suite to validate a second time.
    native_inheritance=record(root,root/data['native_inheritance']['path'])
    require(native_inheritance==data['native_inheritance'], 'Native inheritance receipt changed during seal')
    protocol=read(args.protocol_receipt);passed('protocol',protocol)
    require(protocol.get('schema')=='endoforge.phase8.ue-protocol-run.v1' and protocol.get('phase')==8
            and protocol.get('test_name')==TEST and protocol.get('process_exit_code')==0,
            'Successful Phase8 receipt for the unchanged atomic snapshot protocol is required')
    require(protocol.get('native_inheritance')==data['native_inheritance']
            and protocol.get('native_execution_phase')==7 and protocol.get('new_native_35_execution') is False,
            'Protocol native inheritance scope differs from preparation')
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
        require(report['phase']==8 and all(value is True for value in report['checks'].values()), 'Incomplete Phase 8 input checks')
        require(report.get('mechanics_phase')==6, 'Editor evidence must retain its accepted mechanics identity')
    require(interaction.get('schema')=='endoforge.phase8.interaction.v1', 'Incorrect interaction presentation schema')
    require(input_report['stereo_frames']==4 and input_report['checks']['dual_traction_retained'] is True,
            'Exactly four internal alignment frames and retained dual traction are required before freeze')
    require(lifecycle['game_exit_code']==lifecycle['native_exit_code']==0 and
            lifecycle['native_graceful_exit'] is True and not lifecycle.get('error'), 'Editor/native lifecycle did not finish cleanly')
    require(runtime['phase']==8 and runtime.get('schema')=='endoforge.phase8.runtime.v1'
            and runtime.get('mechanics_phase')==6 and runtime.get('run_kind')=='acceptance_test',
            'Incorrect or incomplete editor runtime scope')
    frame_paths=sorted((capture/'dataset').glob('*/*/frame.json'))
    frame_counts={}
    for frame_path in frame_paths:
        frame=read(frame_path)
        require(frame.get('phase')==8 and frame.get('mechanics_phase')==6 and frame.get('capture_complete') is True,
                'Missing completed Phase8 alignment frame')
        sequence=frame.get('sequence')
        require(sequence==frame_path.parent.parent.name, 'Alignment-frame path/sequence mismatch')
        frame_counts[sequence]=frame_counts.get(sequence,0)+1
    require(frame_counts=={'left_traction':3,'bimanual_traction':1}, 'Actual internal alignment-frame membership differs')
    manifest_path=capture/'dataset/visual-manifest.json'
    manifest=read(manifest_path)
    require(manifest.get('phase')==8 and manifest.get('mechanics_phase')==6, 'Incorrect captured appearance identity')
    manifest_sha1=hashlib.sha1(manifest_path.read_bytes()).hexdigest()
    require(runtime.get('visual_manifest_sha1')==input_report.get('visual_manifest_sha1')==manifest_sha1,
            'Editor input/runtime evidence is bound to another captured appearance')
    timestamp=datetime.datetime.fromisoformat(data['created_utc']).timestamp()
    require(all(path.stat().st_mtime>=timestamp for path in (input_path,interaction_path,lifecycle_path,runtime_path,manifest_path,*frame_paths)),
            'Editor evidence predates preparation')
    require(module.stat().st_mtime<=input_path.stat().st_mtime, 'Editor module was rebuilt after input test')
    require(sha(root/'Physics/runtime/LapPhysics.exe')==data['physics_executable']['sha256'],
            'Native executable changed during seal')
    require(inputs(root)==data['input_sha256'], 'Source/build inputs changed during seal')
    source=[];assets=[];additional=[]
    for name,digest in data['input_sha256'].items():
        target=source if name.startswith('Prototype/LapTrainer/Source/') else assets if name.startswith(('Assets/','Prototype/LapTrainer/Content/')) else additional
        target.append({'path':name,'sha256':digest})
    result={'schema':'endoforge.phase8.ue-validation.v1','phase':8,'created_utc':now(),
            'source_frozen':True,'source_files':source,'additional_build_inputs':additional,'assets':assets,
            'prepared_receipt':record(root,args.prepared),'editor_module':module_before,
            'editor_build_log':record(root,args.editor_build_log),
            'protocol':{**protocol,'same_final_editor_module':True,'receipt':record(root,args.protocol_receipt)},
            'editor_input':{'passed':True,'report':record(root,input_path),'interaction':record(root,interaction_path),
                            'lifecycle':record(root,lifecycle_path),'runtime':record(root,runtime_path),
                            'stereo_frames':input_report['stereo_frames'],'runtime_run_kind':runtime['run_kind'],
                            'visual_manifest':record(root,manifest_path),
                            'alignment_frames':[record(root,path) for path in frame_paths]},
            'physics_executable':data['physics_executable'],'native_inheritance':native_inheritance,
            'native_execution_phase':7,'new_native_35_execution':False,
            'scope':'Frozen Phase8 source/editor integration receipt with separately inherited exact Phase7 native identity; no new native regression execution. Four internal alignment checks are not research-sequence delivery. Actual packaged runtime, isolated performance, independent geometry/data audits, preservation and fresh-ZIP acceptance remain separate required gates.'}
    write_new(args.output,result)
    print(json.dumps({'source_frozen':True,'receipt':str(args.output),'editor_module_sha256':module_before['sha256']}))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
