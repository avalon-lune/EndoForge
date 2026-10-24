"""Audit every recorded state in parallel using the unchanged Phase 5 auditors.

Adjacent chunks share exactly one original state, preserving every interpolation
edge. Per-chunk motion is diagnostic: the >5 mm motion coverage gate applies to
the complete trace. Geometric and health gates are never relaxed. Liver exact
distance sampling restarts at each chunk; its all-state intersection/containment
checks do not downsample.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import time


HERE=Path(__file__).resolve().parent
COVERAGE_CHECKS={'enough_recorded_states','actual_jaw_travel_over_5mm','all_recorded_states_tested'}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def split_trace(source,work,limit):
    """Stream to disk, retaining only one state line between chunks."""
    before=source.stat(); original_hash=hashlib.sha256(); state_hash=hashlib.sha256()
    chunks=[]; handle=None; last=None; count=0
    try:
        with source.open('rb') as stream:
            header_raw=stream.readline(); original_hash.update(header_raw)
            header=json.loads(header_raw.decode('utf-8-sig'))
            if header.get('type')!='mesh': raise ValueError('First line must be a native mesh header')
            for raw in stream:
                if not raw.strip(): raise ValueError('Blank state lines are not permitted')
                original_hash.update(raw); state_hash.update(raw)
                if handle is None or chunks[-1]['states']==limit:
                    if handle is not None: handle.close()
                    index=len(chunks); part=work/f'part-{index:04d}.jsonl'
                    part_header=dict(header);part_header['case_id']=str(header['case_id'])+f'.part{index:04d}'
                    handle=part.open('xb')
                    handle.write(json.dumps(part_header,separators=(',',':')).encode('utf-8')+b'\n')
                    chunk={'part':index,'path':str(part.resolve()),'first_original_state':count if last is None else count-1,
                           'last_original_state':count-1,'states':0,'overlap_with_previous':last is not None}
                    if last is not None:
                        handle.write(last);chunk['states']=1
                    chunks.append(chunk)
                handle.write(raw);chunks[-1]['states']+=1;chunks[-1]['last_original_state']=count
                last=raw;count+=1
    finally:
        if handle is not None: handle.close()
    after=source.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise RuntimeError('Input trace changed during splitting')
    if count<30: raise ValueError('At least 30 original states are required')
    if len(chunks)>1 and chunks[-1]['states']<30:
        tail=chunks.pop(); previous=chunks[-1]; tail_path=Path(tail['path'])
        with tail_path.open('rb') as src,Path(previous['path']).open('ab') as dst:
            src.readline();src.readline()  # Header and the one duplicated state.
            while data:=src.read(2**20): dst.write(data)
        previous['last_original_state']=tail['last_original_state']
        previous['states']+=tail['states']-1
        if tail_path.resolve().parent!=work.resolve(): raise ValueError('Unexpected chunk path')
        tail_path.unlink()  # Only our new, merged, single-file temporary chunk.
    reconstructed=hashlib.sha256();seen=0
    for i,chunk in enumerate(chunks):
        path=Path(chunk['path']);chunk['sha256']=sha(path);chunk['bytes']=path.stat().st_size
        assert chunk['states']==chunk['last_original_state']-chunk['first_original_state']+1
        if i: assert chunk['first_original_state']==chunks[i-1]['last_original_state']
        with path.open('rb') as stream:
            stream.readline()
            if i:
                overlap=json.loads(stream.readline().decode('utf-8'))
                chunk['overlap_grasping']=[bool(t.get('grasping',False)) for t in overlap['tools']]
                chunk['overlap_stage']=overlap.get('stage','unknown')
            for raw in stream: reconstructed.update(raw);seen+=1
    assert seen==count and reconstructed.digest()==state_hash.digest(), 'Chunk membership changed original state bytes'
    assert chunks[0]['first_original_state']==0 and chunks[-1]['last_original_state']==count-1
    return chunks,{'case_id':header['case_id'],'sha256':original_hash.hexdigest(),'bytes':before.st_size,
                   'original_state_count':count,'duplicated_overlap_count':len(chunks)-1,
                   'original_state_lines_sha256':state_hash.hexdigest(),
                   'source_header_sha256':hashlib.sha256(header_raw).hexdigest(),
                   'exact_state_bytes_and_membership_verified':True}


def audit_worker(task):
    kind,chunk=task;path=Path(chunk['path'])
    try:
        if kind=='contact':
            from audit_contact import audit
            result=audit(path,3)
        else:
            from audit_liver_contact import audit
            result=audit(path,30)
        if sha(path)!=chunk['sha256']: raise RuntimeError('Chunk changed during audit')
        geometric={k:v for k,v in result['checks'].items() if k not in COVERAGE_CHECKS}
        result['chunk_geometric_checks']=geometric
        result['chunk_geometric_passed']=bool(geometric) and all(v is True for v in geometric.values())
        result['audit_completed']=True
    except Exception as error:
        result={'passed':False,'audit_completed':False,'chunk_geometric_passed':False,
                'error':type(error).__name__+': '+str(error)}
    result['chunk_membership']=chunk
    return result


def summarize(kind,cases,original):
    completed=all(c.get('audit_completed') is True for c in cases)
    checks={'all_chunks_completed':completed,'all_chunk_geometry_and_health_checks_passed':
            bool(cases) and all(c.get('chunk_geometric_passed') is True for c in cases),
            'at_least_30_original_states':original['original_state_count']>=30,
            'exact_state_bytes_and_membership_verified':original['exact_state_bytes_and_membership_verified']}
    metrics={}
    if completed:
        field='states' if kind=='contact' else 'recorded_states_tested'
        count=sum(c[field] for c in cases)
        checks['all_original_states_audited']=count==original['original_state_count']+original['duplicated_overlap_count']
        metrics['states_audited_including_overlap']=count
        if kind=='contact':
            for key in ('maximum_node_depth_mm','maximum_whole_triangle_depth_mm','maximum_interpolated_depth_mm',
                        'maximum_inter_tool_jaw_overlap_mm','maximum_liver_surface_in_jaw_mm'):
                metrics[key]=max(c[key] for c in cases)
            for key in ('minimum_tet_volume_ratio','minimum_triangle_area_ratio'):
                metrics[key]=min(c[key] for c in cases)
            for key in ('interpolated_samples','reset_boundaries_not_interpolated'):
                metrics[key]=sum(c[key] for c in cases)
            metrics['jaw_travel_mm']=[sum(c['jaw_travel_mm'][i] for c in cases) for i in range(2)]
            metrics['grasping_states_per_tool']=[sum(c['grasping_states_per_tool'][i]-int(c['chunk_membership'].get('overlap_grasping',[False,False])[i]) for c in cases) for i in range(2)]
            metrics['simultaneous_grasping_states']=sum(c['simultaneous_grasping_states']-int(all(c['chunk_membership'].get('overlap_grasping',[False,False]))) for c in cases)
            metrics['liver_enclosed_jaw_centers_including_overlap']=sum(c['liver_enclosed_jaw_centers'] for c in cases)
            checks['global_actual_jaw_travel_over_5mm']=max(metrics['jaw_travel_mm'])>=5
            checks['all_non_reset_interpolation_edges_audited']=metrics['interpolated_samples']==3*(original['original_state_count']-1-metrics['reset_boundaries_not_interpolated'])
        else:
            for key in ('intersecting_or_touching_states','wall_inside_liver_states','broad_phase_candidate_pairs_tested'):
                metrics[key+'_including_overlap']=sum(c[key] for c in cases)
            metrics['maximum_winding_integer_error']=max(c['maximum_winding_integer_error'] for c in cases)
            metrics['minimum_clearance_mm_among_distance_samples']=min(c['minimum_clearance_mm_among_distance_samples'] for c in cases)
            samples={c['chunk_membership']['first_original_state']+sample['sample'] for c in cases for sample in c['distance_samples']}
            metrics['unique_clearance_states_sampled']=len(samples)
            metrics['clearance_original_state_indices']=sorted(samples)
            stages=Counter()
            for c in cases:
                stages.update(c['stages'])
                if c['chunk_membership']['overlap_with_previous']:stages[c['chunk_membership']['overlap_stage']]-=1
            metrics['stages_unique_original_states']=dict(stages)
            checks['one_immutable_asset_fingerprint']=len({c['asset_fingerprint'] for c in cases})==1
    else: checks['all_original_states_audited']=False
    return checks,metrics


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trajectory',type=Path,required=True)
    parser.add_argument('--kind',choices=('contact','liver'),required=True)
    parser.add_argument('--workers',type=int,default=3)
    parser.add_argument('--chunk-states',type=int,default=2000)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args()
    if not 1<=a.workers<=64 or a.chunk_states<30: raise ValueError('Workers must be 1..64 and chunk size at least 30')
    if not a.trajectory.is_file(): raise FileNotFoundError(a.trajectory)
    if a.work_dir.exists() or a.output.exists(): raise FileExistsError('Use fresh work and output paths')
    started=time.monotonic();a.work_dir.mkdir(parents=True)
    chunks,original=split_trace(a.trajectory,a.work_dir,a.chunk_states)
    for variable in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
        os.environ.setdefault(variable,'1')
    tasks=[(a.kind,chunk) for chunk in chunks]
    if a.workers==1: cases=[audit_worker(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=a.workers,mp_context=multiprocessing.get_context('spawn')) as pool:
            cases=list(pool.map(audit_worker,tasks))
    checks,metrics=summarize(a.kind,cases,original)
    checks['original_trace_unchanged']=sha(a.trajectory)==original['sha256']
    auditor=HERE/('audit_contact.py' if a.kind=='contact' else 'audit_liver_contact.py')
    report={'schema':f'endoforge.phase5.parallel-{a.kind}.v1','kind':a.kind,
            'passed':all(checks.values()),'checks':checks,'metrics':metrics,'cases':cases,
            'original_trace':{'path':str(a.trajectory.resolve()),**original},
            'chunk_states_target':a.chunk_states,'workers':a.workers,'elapsed_seconds':time.monotonic()-started,
            'script_sha256':sha(Path(__file__)),'auditor_sha256':sha(auditor),
            'coverage_policy':'Every original state is audited. Adjacent chunks share one identical state; each interpolation edge appears exactly once. Original per-chunk checks remain visible. Motion and minimum-state requirements are global coverage gates; geometric/health checks are unchanged.',
            'distance_sampling_policy':'Liver triangle intersection and winding containment check every state. Exact minimum distance is sampled at each chunk start, each stage change and local stride 30; sample positions may differ from a serial run. No CCD proof.'}
    if a.kind=='contact':report['geometry_kernel_sha256']=sha(HERE.parent/'audit_phase4_collision_geometry.py')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('schema','passed','checks','metrics','elapsed_seconds')}))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    multiprocessing.freeze_support()
    raise SystemExit(main())
