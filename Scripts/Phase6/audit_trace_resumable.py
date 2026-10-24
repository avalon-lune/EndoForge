"""Run unchanged geometry auditors with verified, resumable per-chunk evidence.

A PAUSE_REQUEST file in the work directory stops dispatch at chunk boundaries.
The currently executing chunks finish and are saved before the runner exits.
Final pass still requires every original state and interpolation edge.
"""
import argparse
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import json
import multiprocessing
import os
from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'Phase5'))
from audit_trace_parallel import audit_worker, sha, split_trace, summarize


def write(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trajectory', type=Path, required=True)
    parser.add_argument('--kind', choices=('contact', 'liver'), required=True)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--chunk-states', type=int, default=1000)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.workers <= 64 or args.chunk_states < 30:
        raise ValueError('Invalid worker count or chunk size')
    if args.output.exists():
        raise FileExistsError('Use a new final report path')
    started = time.monotonic()
    args.work_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.work_dir / 'manifest.json'
    auditor = HERE.parent / 'Phase5' / ('audit_contact.py' if args.kind == 'contact' else 'audit_liver_contact.py')
    dependencies = [Path(__file__), auditor, HERE.parent / 'Phase5/audit_trace_parallel.py']
    if args.kind == 'contact':
        dependencies.append(HERE.parent / 'audit_phase4_collision_geometry.py')
    identities = {str(path.resolve()): sha(path) for path in dependencies}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        assert manifest['kind'] == args.kind and manifest['chunk_states'] == args.chunk_states
        assert manifest['auditor_identities'] == identities, 'Auditor changed; use fresh work directory'
        assert manifest['original']['sha256'] == sha(args.trajectory), 'Original trace changed'
        assert manifest['trajectory'] == str(args.trajectory.resolve())
        chunks, original = manifest['chunks'], manifest['original']
        for chunk in chunks:
            assert sha(Path(chunk['path'])) == chunk['sha256'], 'Chunk changed'
    else:
        if any(args.work_dir.iterdir()):
            raise FileExistsError('Work directory has files but no verified manifest')
        chunks, original = split_trace(args.trajectory, args.work_dir, args.chunk_states)
        manifest = {'kind': args.kind, 'trajectory': str(args.trajectory.resolve()),
                    'chunk_states': args.chunk_states, 'original': original, 'chunks': chunks,
                    'auditor_identities': identities}
        write(manifest_path, manifest)
    results = {}
    pending = []
    for chunk in chunks:
        result_path = args.work_dir / f"result-{chunk['part']:04d}.json"
        if result_path.exists():
            record = json.loads(result_path.read_text(encoding='utf-8'))
            assert record['chunk_membership'] == chunk, 'Result belongs to a different chunk'
            results[chunk['part']] = record
        else:
            pending.append(chunk)
    for variable in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ.setdefault(variable, '1')
    pause = args.work_dir / 'PAUSE_REQUEST'
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context('spawn')) as pool:
        running = {}
        while pending or running:
            while pending and len(running) < args.workers and not pause.exists():
                chunk = pending.pop(0)
                running[pool.submit(audit_worker, (args.kind, chunk))] = chunk
            if not running:
                break
            finished, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in finished:
                chunk = running.pop(future)
                result = future.result()
                write(args.work_dir / f"result-{chunk['part']:04d}.json", result)
                results[chunk['part']] = result
                print(json.dumps({'kind': args.kind, 'completed_chunks': len(results),
                                  'total_chunks': len(chunks), 'part': chunk['part'],
                                  'geometric_passed': result['chunk_geometric_passed']}), flush=True)
    if pending:
        print(json.dumps({'paused': True, 'completed_chunks': len(results), 'remaining_chunks': len(pending)}))
        return 3
    cases = [results[chunk['part']] for chunk in chunks]
    checks, metrics = summarize(args.kind, cases, original)
    checks['original_trace_unchanged'] = sha(args.trajectory) == original['sha256']
    checks['auditors_unchanged'] = all(sha(Path(path)) == value for path, value in identities.items())
    report = {'schema': f'endoforge.phase6.parallel-{args.kind}.v1', 'kind': args.kind,
              'passed': all(checks.values()), 'checks': checks, 'metrics': metrics, 'cases': cases,
              'original_trace': {'path': str(args.trajectory.resolve()), **original},
              'chunk_states_target': args.chunk_states, 'workers': args.workers,
              'elapsed_this_invocation_seconds': time.monotonic() - started,
              'script_sha256': sha(Path(__file__)), 'auditor_sha256': sha(auditor),
              'auditor_identities': identities, 'work_manifest_sha256': sha(manifest_path),
              'coverage_policy': 'Every original state is audited. Adjacent chunks share one identical state; each interpolation edge appears exactly once. Geometric/health checks are unchanged. Per-chunk motion/minimum-state checks are replaced only by their complete-trace coverage gates.',
              'distance_sampling_policy': 'Liver triangle intersection and winding containment check every state. Exact minimum distance is sampled at each chunk start, each stage change and local stride 30. No continuous-collision proof.'}
    if args.kind == 'contact':
        report['geometry_kernel_sha256'] = sha(HERE.parent / 'audit_phase4_collision_geometry.py')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write(args.output, report)
    print(json.dumps({key: report[key] for key in ('passed', 'checks', 'metrics')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    multiprocessing.freeze_support()
    raise SystemExit(main())
