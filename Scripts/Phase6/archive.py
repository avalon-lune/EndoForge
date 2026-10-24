"""Build and verify a portable Phase 6 archive without including runtime sessions.

Only files listed in the sealed manifest enter the ZIP. Verification outputs are
written alongside the archive, preventing a self-referential checksum chain.
"""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def sha(path):
    with path.open('rb') as handle: return hashlib.file_digest(handle,'sha256').hexdigest()


def safe_child(root,name):
    p=(root/name).resolve()
    if not p.is_relative_to(root.resolve()): raise ValueError('Path escapes destination: '+name)
    return p


def verify(root):
    rows=json.loads((root/'package-manifest.json').read_text(encoding='utf-8-sig'))
    if not rows or len({x['path'] for x in rows})!=len(rows): raise ValueError('Empty/duplicate manifest')
    for row in rows:
        p=safe_child(root,row['path'])
        if not p.is_file() or p.stat().st_size!=row['bytes'] or sha(p)!=row['sha256']:
            raise ValueError('Manifest mismatch: '+row['path'])
    return rows


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['seal','create','extract','verify'])
    p.add_argument('--package',type=Path,required=True)
    p.add_argument('--archive',type=Path)
    p.add_argument('--report',type=Path)
    a=p.parse_args(); package=a.package.resolve()
    if a.mode=='seal':
        excluded={'Logs','Sessions','Saved','__pycache__'}
        files=[f for f in sorted(package.rglob('*')) if f.is_file() and not set(f.relative_to(package).parts)&excluded and f.name!='package-manifest.json' and f.suffix.lower() not in ('.blend1','.pyc','.pdb')]
        rows=[{'path':f.relative_to(package).as_posix(),'bytes':f.stat().st_size,'sha256':sha(f)} for f in files]
        (package/'package-manifest.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
        result={'sealed':True,'files':len(rows),'bytes':sum(x['bytes'] for x in rows)}
    elif a.mode=='create':
        if a.archive is None: raise ValueError('--archive required')
        if a.archive.exists(): raise FileExistsError('Use a fresh archive name')
        rows=verify(package); a.archive.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(a.archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
            for name in [r['path'] for r in rows]+['package-manifest.json']:
                z.write(safe_child(package,name),'EndoForge/'+name)
        with zipfile.ZipFile(a.archive) as z:
            bad=z.testzip()
            if bad: raise ValueError('Archive CRC failed: '+bad)
        result={'passed':True,'archive':str(a.archive),'sha256':sha(a.archive),'bytes':a.archive.stat().st_size,'files':len(rows)+1,'crc_all_files':True}
    elif a.mode=='extract':
        if a.archive is None: raise ValueError('--archive required')
        if package.exists(): raise FileExistsError('Fresh extraction destination required')
        package.mkdir(parents=True)
        with zipfile.ZipFile(a.archive) as z:
            for info in z.infolist():
                if not info.filename.startswith('EndoForge/'): raise ValueError('Unexpected ZIP root')
                name=info.filename[len('EndoForge/'):]
                if not name: continue
                out=safe_child(package,name)
                if info.is_dir(): out.mkdir(parents=True,exist_ok=True)
                else:
                    out.parent.mkdir(parents=True,exist_ok=True)
                    with z.open(info) as src, out.open('xb') as dst:
                        while data:=src.read(2**20): dst.write(data)
        rows=verify(package)
        result={'passed':True,'archive_sha256':sha(a.archive),'extracted_to':str(package),'verified_files':len(rows)}
    else:
        rows=verify(package); result={'passed':True,'verified_files':len(rows),'package':str(package)}
    if a.report:
        a.report.parent.mkdir(parents=True,exist_ok=True)
        a.report.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
