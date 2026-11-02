"""Own one unchanged endurance auditor; propagate root pause without killing."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[2]

def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()

def main():
    kind = sys.argv[1]
    if kind not in ('contact','liver'):
        raise ValueError('Expected contact or liver')
    workers = 2 if kind == 'contact' else 4
    pause = ROOT/'PAUSE_REQUEST'
    work = ROOT/(kind+'-chunks')
    child_pause = work/'PAUSE_REQUEST'
    if pause.exists():
        print(json.dumps({'kind':kind,'status':'paused_before_launch','exit_code':3}),flush=True)
        return 3
    report = ROOT/(kind+'.json')
    command = [sys.executable,'-B',str(WORKSPACE/'Scripts/Phase7/audit_trace_resumable.py'),
               '--trajectory',str(WORKSPACE/'tmp/phase9/native-qualification-final02/endurance-states.jsonl'),
               '--kind',kind,'--workers',str(workers),'--chunk-states','500',
               '--work-dir',str(work),'--output',str(report)]
    environment = dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONOPTIMIZE='0',
                       OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    started = datetime.now(timezone.utc).isoformat(); clock = time.monotonic()
    with (ROOT/(kind+'.stdout.log')).open('x',encoding='utf-8') as stdout,(ROOT/(kind+'.stderr.log')).open('x',encoding='utf-8') as stderr:
        process = subprocess.Popen(command,cwd=WORKSPACE,env=environment,stdout=stdout,stderr=stderr,
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        launch = {'kind':kind,'pid':process.pid,'command':command,'workers':workers,
                  'started_utc':started,'wrapper_sha256':sha(Path(__file__)),
                  'pause_request':str(pause),'child_pause_request':str(child_pause)}
        with (ROOT/(kind+'-launch.json')).open('x',encoding='utf-8') as stream:
            json.dump(launch,stream,indent=2);stream.write('\n')
        print(json.dumps({'kind':kind,'pid':process.pid,'status':'running','workers':workers}),flush=True)
        while process.poll() is None:
            if pause.exists() and (work/'manifest.json').exists() and not child_pause.exists():
                try:
                    with child_pause.open('x',encoding='utf-8') as stream:
                        stream.write('Propagated root PAUSE_REQUEST at '+datetime.now(timezone.utc).isoformat()+'\n')
                    print(json.dumps({'kind':kind,'status':'pause_propagated'}),flush=True)
                except FileExistsError:
                    pass
            time.sleep(.25)
    exit_code = process.wait()
    document = json.loads(report.read_text(encoding='utf-8-sig')) if report.exists() else None
    execution = {**launch,'completed_utc':datetime.now(timezone.utc).isoformat(),'exit_code':exit_code,
                 'elapsed_seconds':round(time.monotonic()-clock,3),'paused':exit_code==3,
                 'report':str(report),'report_sha256':sha(report) if report.exists() else None,
                 'passed':exit_code==0 and document is not None and document.get('passed') is True}
    with (ROOT/(kind+'-execution.json')).open('x',encoding='utf-8') as stream:
        json.dump(execution,stream,indent=2);stream.write('\n')
    print(json.dumps({key:execution[key] for key in ('kind','exit_code','paused','passed','elapsed_seconds')}),flush=True)
    return exit_code

if __name__ == '__main__':
    raise SystemExit(main())
