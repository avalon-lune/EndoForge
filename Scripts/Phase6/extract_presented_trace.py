"""Extract accepted UE states with the independently recorded native mesh header.

No coordinates are inferred or resampled. Reset/episode boundaries are retained
for audit_contact.py to avoid interpolating across a deliberate reset.
"""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--presented',type=Path,required=True)
    p.add_argument('--native-reference',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists(): raise FileExistsError('Use a fresh extracted trace')
    with a.native_reference.open(encoding='utf-8-sig') as f:
        header=json.loads(next(f)); reference=json.loads(next(f))
    assert header['type']=='mesh' and reference['protocol']==5
    header['case_id']=a.presented.parent.name+'-presented'
    header['provenance']={'presented_sha256':sha(a.presented),'native_reference_sha256':sha(a.native_reference),
                          'extractor_sha256':sha(Path(__file__))}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    count=0; episodes=set()
    with a.presented.open(encoding='utf-8-sig') as f, a.output.open('w',encoding='utf-8') as out:
        out.write(json.dumps(header,separators=(',',':'))+'\n')
        for line in f:
            record=json.loads(line); state=record['native_state']
            assert record['phase']==6 and state['protocol']==5
            assert state['asset_fingerprint']==reference['asset_fingerprint']
            assert state['config']==reference['config'], 'Actual UE material/configuration differs from the reference'
            assert state['triangles']==header['triangles']
            assert len(state['vertices'])==len(header['rest_vertices'])
            state['stage']=record['record_kind']
            out.write(json.dumps(state,separators=(',',':'))+'\n')
            count+=1; episodes.add(state['simulation_id'])
    assert count>=30
    print(json.dumps({'path':str(a.output),'states':count,'simulation_ids':sorted(episodes),
                      'sha256':sha(a.output),'asset_fingerprint':reference['asset_fingerprint']}))
