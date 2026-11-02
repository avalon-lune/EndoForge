"""Run only the assigned fresh Phase9 traces through unchanged geometry auditors.

This task-local coordinator writes no project source and launches no native or
UE executable. The sole remaining runner job uses eight CPU audit workers. PAUSE_REQUEST in
this directory stops dispatch and is forwarded to initialized work directories.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SUITE = ROOT/'tmp/phase9/native-qualification-final02'
PYTHON = Path('C:/Users/Avalon/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
RUNNER = ROOT/'Scripts/Phase7/audit_trace_resumable.py'
EXPECTED_EXE = '2ab82f5b9d74419ae4507f698d4dcb5b071e43d3cbae5ef188d41be8a3a2f3a0'
EXPECTED_MESH = 'bb78f5c1950d14c6656d476d199f6f5f03743ebe886c47d1030ca570ee8085ec'
BASE = ['dual-reference']+[f'matrix-a{angle}-s{speed}-{path}' for angle in (75,90,105)
    for speed,path in ((6,'straight'),(12,'lateral'),(18,'forward'))]
HOLDS = ['long-hold-tool0-nominal','long-hold-tool1-nominal','long-hold-dual-2mm']
CASES = BASE+HOLDS
JOBS = [(case,kind) for case in CASES for kind in ('contact','liver')]
PAUSE = OUT/'PAUSE_REQUEST'
STATUS = OUT/'coverage-index.json'
SEAL_POLL_SECONDS = 30
EARLY_SEALS = SUITE/'early-case-seals/index.json'
EXPECTED_EARLY_SEALS = {
    'tool0-nominal':'7e4301b49bcaf6962d975c7b4c2a4e713a9087a73a16fed7b53a028a560449ba',
    'tool1-nominal':'56ef85503bb485d1196703d092c75964dce0212af7dd8f0beb136da53d934757',
    'dual-2mm':'876196a7bca0306f88587191c0b07ae6afe50e4e2cec376d7ccd537f56c434dc',
}
RAW_HOLD_GATE = SUITE/'long-hold-raw-state-audit.json'
EXPECTED_RAW_HOLD_GATE = '45b11e4c772dfd0534e8b292c90795b734f1718e1f79204449c21946037bebb8'


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def require(ok,message):
    if not ok:
        raise ValueError(message)


def write_new(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8') as stream:
        json.dump(value,stream,indent=2)


def write_status(value):
    temporary=STATUS.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,indent=2),encoding='utf8')
    temporary.replace(STATUS)


def emit(event,**data):
    print(json.dumps({'utc':now(),'event':event,**data}),flush=True)


def case_paths(case,kind):
    folder=OUT/case
    return folder/(kind+'.json'), folder/(kind+'-chunks')


def checked_plan():
    path=SUITE/'adaptation-plan.json'
    raw=path.read_bytes(); plan=json.loads(raw.decode('utf-8-sig'))
    require(plan.get('schema')=='endoforge.phase9.native-qualification-plan.v1' and
        plan.get('qualification_phase')==9 and plan.get('inherited_results') is False,'Wrong native qualification plan')
    require(plan['native_binary']['sha256']==EXPECTED_EXE and plan['mesh']['sha256']==EXPECTED_MESH,
        'Plan native/mesh identity differs from the assigned fresh final02')
    require(sha(plan['native_binary']['path'])==EXPECTED_EXE and sha(plan['mesh']['path'])==EXPECTED_MESH,
        'Actual current native/mesh bytes differ from the frozen plan')
    copied=OUT/'inputs/adaptation-plan.json'
    copied.parent.mkdir(parents=True,exist_ok=True)
    if copied.exists(): require(copied.read_bytes()==raw,'Native qualification plan changed since this batch began')
    else:
        with copied.open('xb') as stream:stream.write(raw)
    return plan, {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'copied_path':str(copied)}


def read_checkpoint():
    raw=(SUITE/'checkpoint.json').read_bytes()
    checkpoint=json.loads(raw.decode('utf-8-sig'))
    require(checkpoint.get('qualification_phase')==9 and checkpoint.get('inherited_results') is False and
        checkpoint.get('native_sha256')==EXPECTED_EXE,'Wrong fresh native checkpoint identity')
    return checkpoint,raw


def checked_raw_hold_gate(plan):
    if not RAW_HOLD_GATE.exists():return None
    raw=RAW_HOLD_GATE.read_bytes(); document=json.loads(raw.decode('utf-8-sig'))
    require(hashlib.sha256(raw).hexdigest()==EXPECTED_RAW_HOLD_GATE,
        'Separate all15 raw-state receipt does not match the authorized sealed identity')
    require(document.get('schema')=='endoforge.phase9.long-hold-raw-state-audit.v1' and
        document.get('passed') is True and document.get('native_processes_launched')==0 and
        'inspect_states=True' in document.get('validator_call',''),
        'Separate every-state long-hold validation was not actually established')
    expected={case.removeprefix('long-hold-') for case in plan['expected_cases'] if case.startswith('long-hold-')}
    validation=document['validation']; audits=validation['raw_state_audits']
    require(len(expected)==validation.get('case_count')==15 and set(audits)==expected and
        all(case.get('passed') is True and type(case.get('states')) is int and case['states']>0 for case in audits.values()),
        'Separate raw-state validation does not cover every expected long-hold case')
    require(document.get('total_recorded_states_tested')==sum(case['states'] for case in audits.values())==62958,
        'Separate raw-state coverage count differs from the actual sealed run')
    required=('all_15_expected_cases_audited','every_raw_state_case_passed','validator_sources_and_documents_unchanged',
        'qualified_binary_unchanged','qualified_mesh_unchanged')
    require(all(document.get('checks',{}).get(check) is True for check in required),
        'A separate raw-state qualification gate failed')
    for path,digest in document['sources_and_input_documents_sha256'].items():
        require(sha(path)==digest,'Raw-state validator source/input changed: '+path)
    qualification=document['qualification']
    require(sha(qualification['path'])==qualification['sha256'] and read(qualification['path']).get('passed') is True,
        'Actual native35 qualification identity is missing or changed')
    copied=OUT/'inputs/long-hold-raw-state-audit.json'
    if copied.exists():require(copied.read_bytes()==raw,'Copied every-state receipt changed')
    else:
        with copied.open('xb') as stream:stream.write(raw)
    return {'path':str(RAW_HOLD_GATE),'copied_path':str(copied),'sha256':EXPECTED_RAW_HOLD_GATE,
        'passed':True,'case_count':15,'recorded_states_tested':62958,'inspect_states':True,
        'native35_qualification':qualification}


def early_entries():
    if not EARLY_SEALS.exists():return {}
    index=read(EARLY_SEALS)
    require(index.get('schema')=='endoforge.phase9.native-early-long-hold-case-seal-index.v1','Wrong early child-seal index')
    entries={}
    for name,expected in EXPECTED_EARLY_SEALS.items():
        descriptor=index.get('cases',{}).get(name)
        if descriptor is None:continue
        path=Path(descriptor['path']).resolve()
        require(path.is_relative_to(SUITE/'early-case-seals') and descriptor['sha256']==expected and sha(path)==expected,
            'Early child seal does not match the authoritative native-agent identity')
        seal=read(path)
        entries['long-hold-'+name]={'name':'long-hold-'+name,'report':seal['artifacts']['report']['path'],
            'sha256':seal['artifacts']['report']['sha256'],'early_case_seal':{'path':str(path),'sha256':expected}}
    return entries


def verify_early_seal(case,entry,plan):
    descriptor=entry['early_case_seal']; seal=read(descriptor['path']); name=case.removeprefix('long-hold-')
    require(sha(descriptor['path'])==descriptor['sha256'] and
        seal.get('schema')=='endoforge.phase9.native-early-long-hold-case-seal.v1' and seal.get('case')==name,
        'Wrong authoritative nominal child seal')
    require(seal.get('qualification_claim') is False and seal.get('stable_full_hash_passes',0)>=2,
        'An early dispatch seal cannot claim full long-hold qualification')
    require(seal['native_binary']['sha256']==EXPECTED_EXE and seal['mesh']['sha256']==EXPECTED_MESH and
        seal['mesh']['asset_fingerprint']=='fnv1a64:a401268b7d86193d','Early child input identities differ')
    child=seal['native_child_completion']
    require(child.get('exit_code')==0 and child.get('report_passed') is True and
        child.get('evidence_kind')=='executed-driver-post-subprocess-wait-passed-event','Actual successful native child completion is not established')
    driver=child['executed_driver']; driver_path=Path(driver['path']).resolve()
    require(sha(driver_path)==driver['sha256'] and any(
        Path(item['generated']).resolve()==driver_path and item['generated_sha256']==driver['sha256']
        for item in plan['adaptations']),'Executed child driver does not match the frozen suite plan')
    lines=driver_path.read_text(encoding='utf-8-sig').splitlines()
    require(all(lines[row['line']-1].strip()==row['text'].strip() for row in driver['control_flow_lines']),
        'Executed child completion control flow differs from sealed evidence')
    controls='\n'.join(row['text'] for row in driver['control_flow_lines'])
    require('subprocess.run' in controls and 'result.returncode == 0' in controls and 'future.result()' in controls,
        'Seal does not bind the actual child-return control flow')
    plan_ref=child['adaptation_plan']
    require(sha(plan_ref['path'])==plan_ref['sha256']==sha(SUITE/'adaptation-plan.json'),'Early seal plan identity differs')
    prefix_info=child['completion_log_prefix']; prefix_path=Path(prefix_info['path']).resolve()
    require(prefix_path.is_relative_to(SUITE),'Child completion log is outside final02')
    with prefix_path.open('rb') as stream:prefix=stream.read(prefix_info['bytes'])
    require(len(prefix)==prefix_info['bytes'] and hashlib.sha256(prefix).hexdigest()==prefix_info['sha256'],
        'Actual child-completion log prefix differs')
    event=child['completion_event']; event_raw=event['event_line'].encode('utf8'); offset=event['byte_offset']
    line_end=prefix.find(b'\n',offset)
    require(0 <= offset <= line_end, 'Actual child passed-event line is incomplete')
    raw_line=prefix[offset:line_end+1]
    # The authoritative seal hashes splitlines(keepends=True): retain the
    # exact recorded CRLF terminator, not only its human-readable event text.
    require(hashlib.sha256(raw_line).hexdigest()==event['event_line_sha256'] and
        raw_line.rstrip(b'\r\n')==event_raw and json.loads(event['event_line'])==event['event'] and
        event['event'].get('case')==name and event['event'].get('passed') is True,
        'Actual post-wait passed event is missing from the sealed log')
    for artifact in seal['artifacts'].values():
        path=Path(artifact['path']).resolve()
        require(path.is_relative_to(SUITE) and path.stat().st_size==artifact['bytes'] and sha(path)==artifact['sha256'],
            'Completed native child artifact changed: '+str(path))
    report=read(seal['artifacts']['report']['path'])
    require(report.get('passed') is True and report['config']==seal['config'] and
        report['checks']==seal['native_report_checks'],'Native report no longer matches the actual child seal')
    require(read(seal['artifacts']['options']['path'])==seal['options'],'Actual nominal options differ from sealed input')
    copied=OUT/'inputs'/(case+'-early-case-seal.json')
    raw=Path(descriptor['path']).read_bytes()
    if copied.exists():require(copied.read_bytes()==raw,'Copied child seal changed')
    else:
        with copied.open('xb') as stream:stream.write(raw)
    return {'kind':'authoritative_early_child_completion','path':str(copied),'sha256':descriptor['sha256'],
        'qualification_claim':False,'full15_raw_long_hold_qualification_still_required':True}


def bind_case(case,entry,checkpoint_raw,plan):
    seal_path=OUT/'inputs'/(case+'.json')
    if seal_path.exists():
        seal=read(seal_path)
        require(seal['native_case_report']['sha256']==entry['sha256'],'Sealed native report identity changed')
        require(sha(seal['native_case_report']['path'])==entry['sha256'],'Sealed native report bytes changed')
        return seal
    dispatch_seal=verify_early_seal(case,entry,plan) if 'early_case_seal' in entry else {'kind':'native_outer_checkpoint'}
    report_path=Path(entry['report']).resolve()
    require(report_path.is_relative_to(SUITE) and sha(report_path)==entry['sha256'],'Native report does not match checkpoint seal')
    report=read(report_path)
    require(report.get('passed') is True and report.get('phase')==6 and report.get('milestone')==9,
        'Native case has not passed the actual Phase9-compatible execution')
    require(report.get('checks') and all(value is True for value in report['checks'].values()),'Native report contains failed checks')
    if 'executable_sha256' in report:
        require(report['executable_sha256']==EXPECTED_EXE,'Native report executable differs from the current run')
    if 'native_exit_code' in report:
        require(report['native_exit_code']==0,'Native case did not exit cleanly')
    trace=Path(report['trace']).resolve()
    require(trace.is_relative_to(SUITE) and trace.is_file(),'Actual native trace is missing or outside final02')
    with trace.open(encoding='utf-8-sig') as stream:
        header=json.loads(next(stream)); state=json.loads(next(stream))
    require(header.get('type')=='mesh' and state.get('protocol')==5,'Invalid native trace header/state')
    require(state.get('asset_fingerprint')==report['config']['asset_fingerprint'],'Report and trace asset identity differ')
    require(state['config']==report['config'],'Report and actual trace configuration differ')
    require(state['model_id']=='endoforge-gallbladder-phase9' and str(state['model_version'])=='1','Wrong native model')
    require(state['asset_fingerprint']=='fnv1a64:a401268b7d86193d','Trace does not use the assigned Phase9 mesh')
    checkpoint_copy=OUT/'inputs'/(case+'-checkpoint.json')
    with checkpoint_copy.open('xb') as stream:stream.write(checkpoint_raw)
    seal={'schema':'endoforge.phase9.geometry-case-input.v1','phase':9,'inherited_results':False,'case':case,
        'sealed_at_utc':now(),'native_case_report':{'path':str(report_path),'sha256':entry['sha256']},
        'trace':{'path':str(trace),'sha256':sha(trace),'bytes':trace.stat().st_size},
        'checkpoint':{'path':str(checkpoint_copy),'sha256':hashlib.sha256(checkpoint_raw).hexdigest()},
        'native_binary':plan['native_binary'],'mesh':plan['mesh'],'asset_fingerprint':state['asset_fingerprint'],
        'actual_config':state['config'],'native_case_passed':True,'dispatch_seal':dispatch_seal,
        'checkpoint_scope':'The copied actual checkpoint binds native-run identity. Early nominal dispatch is established only by the separate completed-child seal, never by a fabricated checkpoint entry.'}
    write_new(seal_path,seal)
    return seal


def audit_result(case,kind,seal):
    report_path,work=case_paths(case,kind)
    if not report_path.exists():return None
    report=read(report_path)
    require(report.get('kind')==kind and report['original_trace']['sha256']==seal['trace']['sha256'],
        'Independent geometry report uses a different native trace')
    require(report.get('workers') in (1,2,4,8) and report.get('chunk_states_target')==500,'Unexpected audit worker/chunk policy')
    require(report.get('passed') is True and all(v is True for v in report['checks'].values()),'Independent geometry audit FAILED: '+case+'/'+kind)
    return {'status':'passed','case':case,'kind':kind,'report':str(report_path),'sha256':sha(report_path),
        'legacy_algorithm_schema':report['schema'],'original_state_count':report['original_trace']['original_state_count'],
        'trace_sha256':report['original_trace']['sha256'],'work_manifest_sha256':report['work_manifest_sha256'],
        'script_sha256':report['script_sha256'],'auditor_identities':report['auditor_identities'],'checks':report['checks'],
        'workers_this_final_invocation':report['workers'],'chunk_states_target':report['chunk_states_target'],
        'metrics':report['metrics']}


def forward_pause(active):
    for job in active.values():
        work=job['work']
        # A pause file before manifest initialization would look like unrelated
        # existing work to the shared runner. Wait for its verified manifest.
        if (work/'manifest.json').exists() and not (work/'PAUSE_REQUEST').exists():
            (work/'PAUSE_REQUEST').write_text('Cooperative pause requested by Phase9 batch.\n',encoding='utf8')


def main():
    lock=OUT/'RUNNING_LOCK'
    with lock.open('x',encoding='ascii') as stream:stream.write(str(os.getpid()))
    active={}; completed={}; seals={}; available={}; failure=None
    plan,plan_record=checked_plan()
    raw_hold_gate=checked_raw_hold_gate(plan)
    record={'schema':'endoforge.phase9.independent-native-geometry.v1','phase':9,'inherited_results':False,
        'started_or_resumed_utc':now(),'status':'running','passed':False,'expected_case_count':13,'expected_audit_count':26,
        'expected_cases':CASES,'kinds':['contact','liver'],'worker_limit':8,'workers_per_job':8,'parallel_job_limit':1,
        'worker_policy_transition':{'path':str(OUT/'worker-policy-transition03.json'),
            'sha256':sha(OUT/'worker-policy-transition03.json'),
            'historical_completed_reports_keep_recorded_worker_counts':True},
        'chunk_states_target':500,'source_plan':plan_record,'native_binary':plan['native_binary'],'mesh':plan['mesh'],
        'geometry_runner':{'path':str(RUNNER),'sha256':sha(RUNNER)},'results':[],
        'scope':'Fresh actual final02 Phase9 native case traces only. Historical Phase7/Phase5 geometry algorithm schemas are retained unchanged; no earlier result is inherited. No endurance, pose-offset or presented-capture swept-geometry coverage is claimed.'}
    next_poll=0.0; last_wait=None; full_holds_sealed=False; last_full_hold_wait=False
    try:
        while True:
            if time.monotonic()>=next_poll and not PAUSE.exists() and not failure:
                try:
                    checkpoint,raw=read_checkpoint()
                    available={entry['name']:(entry,raw) for entry in checkpoint.get('completed',[]) if entry['name'] in CASES}
                    expected_holds={case for case in plan['expected_cases'] if case.startswith('long-hold-')}
                    full_holds_sealed=(expected_holds.issubset({entry['name'] for entry in checkpoint.get('completed',[])}) and
                        len(expected_holds)==15 and raw_hold_gate is not None)
                    for case,entry in early_entries().items():
                        if case not in available:available[case]=(entry,raw)
                except (json.JSONDecodeError,OSError) as error:
                    emit('CHECKPOINT_READ_RETRY',error=str(error))
                next_poll=time.monotonic()+SEAL_POLL_SECONDS
            for key,job in list(active.items()):
                text=job['log_path'].read_text(encoding='utf8',errors='replace')
                lines=text.splitlines()
                for line in lines[job['observed_lines']:]:
                    try:progress=json.loads(line)
                    except json.JSONDecodeError:continue
                    if progress.get('geometric_passed') is False:
                        failure='Independent chunk geometry FAILED: '+key
                        emit('GEOMETRY_FAILURE',job=key,progress=progress)
                job['observed_lines']=len(lines)
                code=job['process'].poll()
                if code is None:continue
                job['log'].close();del active[key]
                if code==3:
                    emit('JOB_PAUSED',job=key)
                elif code!=0:
                    failure='Geometry runner failed: '+key+' exit='+str(code)
                    emit('GEOMETRY_FAILURE',job=key,exit_code=code,log=str(job['log_path']))
                else:
                    try:
                        result=audit_result(job['case'],job['kind'],seals[job['case']])
                        require(result is not None,'Geometry report missing after successful process exit')
                        completed[key]=result
                        emit('AUDIT_PASSED',job=key,completed_audits=len(completed),expected_audits=26,metrics=result['metrics'])
                    except Exception as error:
                        failure=str(error);emit('GEOMETRY_FAILURE',job=key,error=failure)
            if failure and not PAUSE.exists():PAUSE.write_text(failure+'\n',encoding='utf8')
            if PAUSE.exists():forward_pause(active)
            if not PAUSE.exists() and not failure:
                for case,kind in JOBS:
                    key=case+'/'+kind
                    if key in completed or key in active or case not in available:continue
                    if len(active)>=1:break
                    try:
                        if case not in seals:
                            entry,raw=available[case];seals[case]=bind_case(case,entry,raw,plan)
                        existing=audit_result(case,kind,seals[case])
                        if existing is not None:
                            completed[key]=existing;continue
                        report_path,work=case_paths(case,kind)
                        pause_file=work/'PAUSE_REQUEST'
                        if pause_file.exists():
                            require(pause_file.resolve().is_relative_to(OUT) and not pause_file.is_symlink() and
                                pause_file.read_text(encoding='utf8')=='Cooperative pause requested by Phase9 batch.\n',
                                'Refusing to remove an unowned or redirected chunk pause marker')
                            pause_file.unlink()
                        report_path.parent.mkdir(parents=True,exist_ok=True)
                        count=len(list(report_path.parent.glob(kind+'-invocation-*.log')))+1
                        log_path=report_path.parent/(kind+f'-invocation-{count:03d}.log')
                        log=log_path.open('x',encoding='utf8')
                        command=[str(PYTHON),str(RUNNER),'--trajectory',seals[case]['trace']['path'],'--kind',kind,
                            '--workers','8','--chunk-states','500','--work-dir',str(work),'--output',str(report_path)]
                        env=os.environ.copy()
                        for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[name]='1'
                        env['PYTHONUTF8']='1'
                        process=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env=env,
                            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                        active[key]={'case':case,'kind':kind,'process':process,'work':work,'log':log,
                            'log_path':log_path,'observed_lines':0,'command':command}
                        emit('AUDIT_STARTED',job=key,pid=process.pid,command=command)
                    except Exception as error:
                        failure=str(error);emit('GEOMETRY_FAILURE',job=key,error=failure)
                        if not PAUSE.exists():PAUSE.write_text(failure+'\n',encoding='utf8')
                        break
            record.update(updated_utc=now(),completed_audits=len(completed),results=[completed[k] for k in sorted(completed)],
                active_jobs=[{'job':key,'pid':job['process'].pid,'log':str(job['log_path']),'work_dir':str(job['work'])} for key,job in active.items()],
                sealed_cases=list(seals),waiting_for_sealed_cases=[case for case in CASES if case not in available],error=failure,
                full15_raw_long_hold_qualification_sealed=full_holds_sealed,
                separate_raw_state_gate=raw_hold_gate,
                geometry_checks_passed=len(completed)==26,
                coordinator={'path':str(Path(__file__).resolve()),'sha256':sha(Path(__file__))})
            if len(completed)==26 and not active and not failure and full_holds_sealed:
                require(checked_raw_hold_gate(plan)==raw_hold_gate,'Separate raw-state gate changed before final completion')
                record.update(status='complete',passed=True,completed_utc=now());write_status(record)
                final=OUT/'final-coverage-index.json'
                if not final.exists():write_new(final,record)
                emit('BATCH_COMPLETE',index=str(final),completed_audits=26)
                return 0
            if (PAUSE.exists() or failure) and not active:
                record['status']='failed' if failure else 'paused';write_status(record)
                emit('BATCH_STOPPED',status=record['status'],completed_audits=len(completed),error=failure)
                return 1 if failure else 3
            record['status']='pausing' if PAUSE.exists() else ('running' if active else
                ('geometry_complete_waiting_for_full15_seal' if len(completed)==26 else 'waiting_for_sealed_cases'))
            write_status(record)
            if not active and not PAUSE.exists():
                missing=tuple(record['waiting_for_sealed_cases'])
                if missing!=last_wait:emit('WAITING_FOR_SEALED_CASES',cases=list(missing));last_wait=missing
                if len(completed)==26 and not full_holds_sealed and not last_full_hold_wait:
                    emit('GEOMETRY_COMPLETE_WAITING_FOR_FULL15_RAW_SEAL');last_full_hold_wait=True
            time.sleep(1)
    finally:
        # Never terminate a worker. Normal/failure exits above wait until all
        # active runner processes finish their submitted chunks cooperatively.
        if not active and lock.exists():lock.unlink()


if __name__=='__main__':
    raise SystemExit(main())
