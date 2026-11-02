"""Prepare/run unchanged full presented contact+liver audits, four workers each.

This helper never launches UE/native code. --plan-only reads the runner API only
and launches nothing. Real execution binds exact source/trace/interpreter bytes,
records actual subprocess returns, and writes report-specific invocation proofs.
A root PAUSE_REQUEST is mirrored into both official work directories; current
chunks finish. --resume reuses only verified unchanged partial/completed work.
"""
import argparse
import ast
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / 'Scripts/Phase7/audit_trace_resumable.py'
DEFAULT_PYTHON = Path('C:/Users/Avalon/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
SOURCES = ['Scripts/Phase7/audit_trace_resumable.py', 'Scripts/Phase5/audit_trace_parallel.py',
           'Scripts/Phase5/audit_contact.py', 'Scripts/Phase5/audit_liver_contact.py',
           'Scripts/audit_phase4_collision_geometry.py']
BLAS = {name: '1' for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS')}
REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checked(value, file=False):
    path = Path(os.path.abspath(value))
    for part in reversed((path, *path.parents)):
        if part.exists() or part.is_symlink():
            info = part.stat(follow_symlinks=False)
            require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & REPARSE,
                    'Links/reparse points are forbidden: ' + str(part))
    require(not file or path.is_file(), 'Missing selected file: ' + str(path))
    return path


def sha(path):
    with checked(path, True).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def read(path):
    return json.loads(checked(path, True).read_text(encoding='utf-8-sig'))


def write_new(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2)
        handle.write('\n')


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='Fresh geometry evidence directory under tmp/phase9')
    parser.add_argument('--python', type=Path, default=DEFAULT_PYTHON)
    parser.add_argument('--resume', action='store_true', help='Resume official verified work; never rerun a failed completed report')
    parser.add_argument('--plan-only', action='store_true', help='Static CLI/API plan; no bulk input reads, writes or processes')
    args = parser.parse_args()
    require(sys.flags.optimize == 0, 'Python -O would disable inherited gates')
    trace, output, python = checked(args.trace), checked(args.output), checked(args.python)
    flags = {arg.value for node in ast.walk(ast.parse(RUNNER.read_text(encoding='utf-8-sig')))
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and node.func.attr == 'add_argument' for arg in node.args
             if isinstance(arg, ast.Constant) and isinstance(arg.value, str)}
    require({'--trajectory', '--kind', '--workers', '--chunk-states', '--work-dir', '--output'} <= flags,
            'Unchanged runner CLI differs')
    commands = {kind: [str(python), '-B', str(RUNNER), '--trajectory', str(trace), '--kind', kind,
                       '--workers', '4', '--chunk-states', '500', '--work-dir', str(output / (kind + '-work')),
                       '--output', str(output / ('presented-' + kind + '.json'))] for kind in ('contact', 'liver')}
    description = {'schema': 'endoforge.phase9.presented-geometry-plan.v1', 'commands': commands,
                   'workers_per_kind': 4, 'total_geometry_workers': 8, 'blas_environment': BLAS,
                   'root_pause_request': str(output / 'PAUSE_REQUEST'),
                   'work_pause_requests': [str(output / (kind + '-work/PAUSE_REQUEST')) for kind in commands]}
    if args.plan_only:
        print(json.dumps({**description, 'plan_only': True, 'processes_launched': 0,
                          'bulk_evidence_read': False, 'output_created': False}, indent=2))
        return 0
    checked(trace, True)
    checked(python, True)
    require(output.is_relative_to(ROOT / 'tmp/phase9') and output != ROOT / 'tmp/phase9'
            and not trace.is_relative_to(output), 'Use a separate Phase9 tmp evidence root')
    if args.resume:
        require(output.is_dir(), '--resume needs the existing owned work directory')
    else:
        require(not output.exists(), 'Use fresh output or explicit --resume')
        output.mkdir(parents=True, exist_ok=False)
    sources = {str(ROOT / relative): sha(ROOT / relative) for relative in SOURCES}
    trace_sha = sha(trace)
    frozen = {'trace': {'path': str(trace), 'sha256': trace_sha, 'bytes': trace.stat().st_size},
              'auditor_identities': sources, 'python': {'path': str(python), 'sha256': sha(python)},
              'commands': commands, 'blas_environment': BLAS, 'workers_per_kind': 4, 'chunk_states': 500}
    plan_path = output / 'invocation-plan.json'
    if args.resume:
        previous_plan = read(plan_path)
        require(previous_plan['frozen'] == frozen and previous_plan['orchestrator']['sha256'] == sha(__file__),
                'Trace, interpreter, source, command or orchestrator changed; use fresh work')
    else:
        write_new(plan_path, {**description, 'created_utc': now(), 'frozen': frozen,
                              'orchestrator': {'path': str(Path(__file__).resolve()), 'sha256': sha(__file__)}})
    require(not (output / 'execution.json').exists(), 'Completed execution is immutable')
    attempts = [int(path.stem.rsplit('-', 1)[1]) for path in output.glob('execution-attempt-*.json')]
    attempt = max(attempts, default=0) + 1
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONOPTIMIZE='0', **BLAS)

    def mirror_pause():
        if (output / 'PAUSE_REQUEST').exists():
            for kind in commands:
                work = output / (kind + '-work')
                marker = work / 'PAUSE_REQUEST'
                if (work / 'manifest.json').exists() and not marker.exists():
                    try:
                        with marker.open('x', encoding='utf-8') as handle:
                            handle.write('Mirrored owned root PAUSE_REQUEST at ' + now() + '\n')
                    except FileExistsError:
                        pass

    def execute(kind):
        started = time.monotonic()
        report_path = output / ('presented-' + kind + '.json')
        proof_path = report_path.with_suffix('.invocation.json')
        if report_path.exists():
            value, proof = read(report_path), read(proof_path)
            require(value.get('passed') is True and proof.get('passed') is True and proof.get('exit_code') == 0
                    and proof['report']['sha256'] == sha(report_path) and proof['trace_sha256'] == trace_sha
                    and proof['auditor_identities'] == sources, 'Completed failed/mismatched report cannot be reused')
            return proof
        require(not proof_path.exists(), 'Invocation proof exists without its completed report')
        record = {'schema': 'endoforge.phase9.geometry-invocation.v1', 'kind': kind,
                  'command': commands[kind], 'started_utc': now(), 'trace_sha256': trace_sha,
                  'auditor_identities': sources, 'python': frozen['python'], 'blas_environment': BLAS,
                  'workers': 4, 'chunk_states': 500, 'attempt': attempt, 'exit_code': None, 'passed': False,
                  'invocation_plan': {'path': str(plan_path), 'sha256': sha(plan_path)}}
        stdout = output / f'presented-{kind}.attempt-{attempt:02d}.stdout.log'
        stderr = output / f'presented-{kind}.attempt-{attempt:02d}.stderr.log'
        try:
            with stdout.open('x', encoding='utf-8') as out, stderr.open('x', encoding='utf-8') as error:
                result = subprocess.run(commands[kind], cwd=ROOT, env=environment, stdout=out, stderr=error,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            record['exit_code'] = result.returncode
            record['trace_unchanged'] = sha(trace) == trace_sha
            record['auditors_unchanged'] = all(sha(path) == digest for path, digest in sources.items())
            if report_path.exists():
                value = read(report_path)
                record['report'] = {'path': str(report_path), 'sha256': sha(report_path)}
                record['passed'] = bool(result.returncode == 0 and value.get('passed') is True
                                        and value.get('checks') and all(v is True for v in value['checks'].values())
                                        and value['original_trace']['sha256'] == trace_sha
                                        and record['trace_unchanged'] and record['auditors_unchanged'])
        except Exception as error:
            record['error'] = type(error).__name__ + ': ' + str(error)
        record.update(completed_utc=now(), elapsed_seconds=time.monotonic() - started,
                      stdout_path=str(stdout), stderr_path=str(stderr))
        write_new(output / f'presented-{kind}.attempt-{attempt:02d}.invocation.json', record)
        if record['passed']:
            write_new(proof_path, record)
        return record

    records = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        running = {pool.submit(execute, kind): kind for kind in commands}
        while running:
            mirror_pause()
            done, _ = wait(running, timeout=0.5, return_when=FIRST_COMPLETED)
            for future in done:
                kind = running.pop(future)
                record = future.result()
                records[kind] = record
                print(json.dumps({'kind': kind, 'exit_code': record['exit_code'], 'passed': record['passed']}), flush=True)
    result = {'schema': 'endoforge.phase9.presented-geometry-execution.v1', 'created_utc': now(),
              'passed': all(record['passed'] is True for record in records.values()),
              'native_processes_launched': 0, 'total_geometry_workers': 8,
              'trace': frozen['trace'], 'records': records, 'attempt': attempt}
    write_new(output / f'execution-attempt-{attempt:02d}.json', result)
    if result['passed']:
        write_new(output / 'execution.json', result)
        return 0
    return 3 if any(record['exit_code'] == 3 for record in records.values()) else 2


if __name__ == '__main__':
    raise SystemExit(main())
