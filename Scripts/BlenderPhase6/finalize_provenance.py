"""Seal authored assets and supporting source identities after validation."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'Assets'/'Phase6'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
provenance=json.loads((OUT/'provenance.json').read_text(encoding='utf8'))
provenance['script_sha256']=sha(Path(__file__).parent/'build_assets.py')
provenance['source_files']={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
provenance['source_files']['Scripts/BlenderPhase5/build_assets.py']=sha(ROOT/'Scripts'/'BlenderPhase5'/'build_assets.py')
provenance['reference_inspection_evidence']=[
    'tmp/source-review/references/Cholecyst_CholecSeg8K_VID52_seg8k-contact.jpg',
    'tmp/phase5-reference-review/male-reference-inferior.png']
provenance['files']={p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='provenance.json'}
(OUT/'provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf8')
print(json.dumps({'files':len(provenance['files']),'provenance_sha256':sha(OUT/'provenance.json')}))
