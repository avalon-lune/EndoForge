"""Copy the explicitly requested actual UE PNGs into a flat local review gallery.

No image pixels are edited, generated, re-encoded or judged. All image references
are same-directory basenames, also usable as assembler evidence names + suffixes.
The output must be a fresh child of tmp/phase9. Existing evidence is read only.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import sys


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
CURRENT = 'Prototype/LapTrainer/Saved/Phase9Candidate12Recorded'
GREY = 'Prototype/LapTrainer/Saved/Phase9GreyReview13/shape-review'
VIEW_LABELS = {'front': '正面', 'left-oblique': '左斜侧', 'right-oblique': '右斜侧',
               'superior': '上方', 'attachment': '附着区近景'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checked(path, existing=True):
    path = Path(os.path.abspath(path))
    for member in reversed((path, *path.parents)):
        if member.exists() or member.is_symlink():
            info = member.stat(follow_symlinks=False)
            require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & REPARSE,
                    'Links/reparse points are forbidden: '+str(member))
    if existing:
        require(path.is_file(), 'Missing requested original PNG: '+str(path))
    return path


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def metadata(path):
    info = path.stat(follow_symlinks=False)
    return (info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_dev, info.st_ino)


def selection():
    rows = [
        ('gallery-phase8-jaw-contact.png', 'output/Phase8/EndoForge-20261028-r1/Verification/Capture/phase6-jaw-contact.png', 'comparison', 'Phase8｜钳口接触近景', 8),
        ('gallery-phase9-jaw-contact.png', CURRENT+'/phase6-jaw-contact.png', 'comparison', 'Phase9｜钳口接触近景', 9),
        ('gallery-phase9-workspace.png', CURRENT+'/phase6-workspace.png', 'current', 'Phase9｜操作区域', 9),
        ('gallery-phase9-organ-closeup.png', CURRENT+'/phase6-organ-closeup.png', 'current', 'Phase9｜器官近景', 9),
        ('gallery-phase9-dual-traction.png', CURRENT+'/phase6-dual-traction.png', 'current', 'Phase9｜双手牵拉', 9),
    ]
    for stage, stage_label in (('rest', '未牵拉（rest）'), ('dual-traction', '双手牵拉（dual-traction）')):
        for view, view_label in VIEW_LABELS.items():
            rows.append((f'gallery-phase9-grey-{stage}-{view}.png', f'{GREY}/{stage}/{view}.png',
                         'grey-'+stage, f'Phase9 灰色诊断｜{stage_label}｜{view_label}', 9))
    require(len(rows) == 15 and len({row[0] for row in rows}) == 15, 'Expected fifteen distinct flat PNG names')
    actual = {path.relative_to(ROOT/GREY).as_posix() for path in (ROOT/GREY).rglob('*.png')}
    expected = {f'{stage}/{view}.png' for stage in ('rest', 'dual-traction') for view in VIEW_LABELS}
    require(actual == expected, 'The requested grayscale rest/dual capture must contain exactly all ten named PNGs')
    return rows


def image_card(row):
    filename = escape(row['file'], quote=True)
    label = escape(row['label'])
    source = escape(row['source_project_path'])
    return f'''<figure class="card">
  <a class="image-link" href="{filename}" target="_blank" rel="noopener" aria-label="打开原始 PNG：{label}">
    <img src="{filename}" alt="{label}，实际 UE 截图" width="{row['width']}" height="{row['height']}" loading="lazy" decoding="async">
  </a>
  <figcaption><h3>{label}</h3><a class="open" href="{filename}" target="_blank" rel="noopener">打开原始 PNG ↗</a>
    <details><summary>文件来源与 SHA-256</summary><p><code>{source}</code></p><p><code>{row['sha256']}</code></p></details>
  </figcaption>
</figure>'''


def page(images):
    def cards(group):
        return '\n'.join(image_card(row) for row in images if row['group'] == group)
    return '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Phase9 实际 UE 截图复核图库</title>
<style>
:root{color-scheme:dark;--bg:#10151d;--panel:#19212d;--line:#303c4d;--text:#edf2f8;--muted:#acb9cb;--accent:#b7d9ff;--pending:#ffe0a0}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.65 "Microsoft YaHei","PingFang SC",system-ui,sans-serif}
main{max-width:1640px;margin:auto;padding:36px 28px 72px}h1{font-size:clamp(25px,3vw,39px);line-height:1.3;margin:8px 0 14px}h2{font-size:24px;line-height:1.4;margin:0 0 6px}h3{font-size:16px;line-height:1.5;margin:0}
p{margin:8px 0}a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}a:focus-visible,summary:focus-visible{outline:3px solid var(--accent);outline-offset:5px}
.eyebrow{letter-spacing:.08em;color:var(--muted);font-size:13px}.badge{display:inline-block;border:1px solid #826b41;background:#3c3020;color:var(--pending);padding:5px 12px;border-radius:999px;font-weight:700}
.intro{max-width:1050px;color:var(--muted)}nav{display:flex;gap:10px;flex-wrap:wrap;margin:22px 0}nav a{border:1px solid var(--line);padding:6px 12px;border-radius:6px}
.notice{border-left:4px solid var(--pending);padding:15px 18px;background:#27251f;border-radius:0 8px 8px 0;margin:25px 0}.notice strong{color:var(--pending)}
section{padding-top:30px;margin-top:20px;border-top:1px solid var(--line)}.section-note{color:var(--muted);margin:5px 0 18px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.current{grid-template-columns:repeat(3,minmax(0,1fr))}
.card{margin:0;background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden}.image-link{display:block;background:#080c12}.card img{display:block;width:100%;height:auto}.card figcaption{padding:14px 16px 16px}.open{font-size:13px;display:inline-block;margin:7px 0}
details{font-size:12px;color:var(--muted);border-top:1px solid var(--line);padding-top:9px;margin-top:6px}summary{cursor:pointer}code{font:12px/1.6 ui-monospace,Consolas,monospace;overflow-wrap:anywhere;word-break:break-all}footer{color:var(--muted);font-size:13px;margin-top:36px}
@media(max-width:1000px){.current{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:680px){main{padding:24px 14px 48px}.grid,.current{grid-template-columns:1fr}h2{font-size:21px}}
</style></head><body><main>
<header><div class="eyebrow">EndoForge · 实际 UE 捕获 · 工程视觉复核</div><h1>Phase9 实际 UE 截图复核图库</h1><span class="badge">人眼验收待确认</span>
<p class="intro">以下 15 张图片均按原始 PNG 字节复制。Phase8 与 Phase9 明确分列；灰色多视角为独立的形态诊断捕获。点击图片可打开原始分辨率文件。</p>
<nav aria-label="图库导航"><a href="#comparison">Phase8 / Phase9 接触近景</a><a href="#current">Phase9 当前彩色视图</a><a href="#grey-rest">灰色：未牵拉</a><a href="#grey-dual">灰色：双手牵拉</a><a href="image_sha256.json">图像 SHA-256 清单</a></nav></header>
<aside class="notice"><strong>灰色近景请检查远端曲率分区，不能把显示面数等同于已无瑕疵</strong><p>局部明暗分带仍可能存在，请结合近景与灰色多视角逐项复核。灰色诊断用于观察形态、边界与着色，不能作为性能证据。</p></aside>
<section id="comparison"><h2>Phase8 与 Phase9｜钳口接触近景</h2><p class="section-note">左：Phase8 保存交付的实际截图；右：Phase9Candidate12Recorded 的实际截图。</p><div class="grid">'''+cards('comparison')+'''</div></section>
<section id="current"><h2>Phase9｜当前彩色视图</h2><p class="section-note">操作区域、器官近景与双手牵拉，均来自 Phase9Candidate12Recorded。</p><div class="grid current">'''+cards('current')+'''</div></section>
<section id="grey-rest"><h2>Phase9 灰色诊断｜未牵拉（rest）</h2><p class="section-note">Phase9GreyReview13 的五个真实视角。仅用于形态复核，不是性能测量。</p><div class="grid">'''+cards('grey-rest')+'''</div></section>
<section id="grey-dual"><h2>Phase9 灰色诊断｜双手牵拉（dual-traction）</h2><p class="section-note">Phase9GreyReview13 的五个真实视角。请检查牵拉状态下的曲率分区、边界与明暗连续性。</p><div class="grid">'''+cards('grey-dual-traction')+'''</div></section>
<footer><p>人眼验收待确认。本页只整理实际 UE 图像及文件来源，不提供自动外观判定或临床验收结论。</p><p>图像未编辑、未生成、未重新编码。<a href="image_sha256.json">image_sha256.json</a> 记录每张副本的原始来源、尺寸、字节数和 SHA-256。</p></footer>
</main></body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'tmp/phase9/visual-gallery01')
    args = parser.parse_args()
    output = checked(args.output, existing=False)
    allowed = ROOT/'tmp/phase9'
    require(output.is_relative_to(allowed) and output != allowed and not output.exists(),
            'Use a fresh child of tmp/phase9; earlier galleries are immutable')
    selected = selection()
    originals = [(row, checked(ROOT/row[1])) for row in selected]
    before = {str(source): metadata(source) for _,source in originals}
    output.mkdir(parents=True, exist_ok=False)
    images = []
    for (filename, relative, group, label, phase),source in originals:
        with source.open('rb') as handle:
            header = handle.read(24)
        require(header[:8] == b'\x89PNG\r\n\x1a\n' and header[12:16] == b'IHDR', 'Expected an actual original PNG: '+str(source))
        width,height = struct.unpack('>II', header[16:24])
        require(width > 0 and height > 0, 'Invalid PNG dimensions')
        digest = sha(source)
        copied = output/filename
        with source.open('rb') as original,copied.open('xb') as destination:
            shutil.copyfileobj(original,destination,2**20)
        require(sha(copied) == digest and metadata(source) == before[str(source)], 'Original changed or copy differs: '+str(source))
        images.append({'file':filename,'source_project_path':relative,'phase':phase,'group':group,'label':label,
                       'bytes':copied.stat().st_size,'width':width,'height':height,'sha256':digest})
    require(all(metadata(source) == before[str(source)] and sha(source) == row['sha256']
                for row,(_,source) in zip(images,originals)), 'An original image changed during gallery creation')
    manifest = {'schema':'endoforge.phase9.visual-gallery-images.v1','phase':9,
                'created_utc':datetime.now(timezone.utc).isoformat(),'image_count':len(images),
                'human_visual_approval':'pending','clinical_approval':'not_claimed',
                'actual_ue_captures':True,'image_editing_or_generation':False,
                'source_bytes_preserved':True,'grayscale_is_performance_evidence':False,
                'review_note':'灰色近景请检查远端曲率分区，不能把显示面数等同于已无瑕疵',
                'gallery_script_sha256':sha(Path(__file__)),'images':images}
    with (output/'image_sha256.json').open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(manifest,stream,indent=2,ensure_ascii=False);stream.write('\n')
    with (output/'visual_gallery.html').open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(page(images))
    mapping = {path.stem:{'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path),'bytes':path.stat().st_size}
               for path in sorted(output.iterdir()) if path.is_file()}
    require(len(mapping) == 17 and all(not path.is_dir() for path in output.iterdir()), 'Expected seventeen flat gallery files')
    print(json.dumps({'gallery':str(output/'visual_gallery.html'),'image_count':len(images),
                      'human_visual_approval':'pending','source_bytes_preserved':True,
                      'evidence_file_mapping':mapping},indent=2,ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
