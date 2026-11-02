"""Use the frozen gallery copy/layout helper with the actual packaged capture.
Only source selection and factual HTML labels differ; PNG bytes stay exact.
"""
from pathlib import Path
import contextlib,hashlib,importlib.util,io,json,sys
R=Path(__file__).resolve().parents[2]
helper=R/'Scripts/Phase9/create_review_gallery.py'
spec=importlib.util.spec_from_file_location('frozen_gallery_copy_helper',helper)
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
def record(p):
    p=Path(p)
    with p.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':str(p),'sha256':digest,'bytes':p.stat().st_size}
capture=R/'tmp/phase9/package-tests/Phase9Package-final01'
run=json.loads((capture/'package-run.json').read_text(encoding='utf-8-sig'))
assert run['integration_capture_completed'] and run['game_exit_code']==run['native_exit_code']==0
g.CURRENT=capture.relative_to(R).as_posix()
original_page=g.page
g.page=lambda images: original_page(images).replace('Phase9Candidate12Recorded','Phase9Package-final01（实际打包运行）')
out=R/'tmp/phase9/visual-gallery02'
sys.argv=[str(helper),'--output',str(out)]
buffer=io.StringIO()
with contextlib.redirect_stdout(buffer): result=g.main()
assert result==0
result=json.loads(buffer.getvalue())
mapping=R/'tmp/phase9/visual-gallery02-evidence-map.json'
with mapping.open('x',encoding='utf-8') as f:json.dump(result['evidence_file_mapping'],f,indent=2,ensure_ascii=False);f.write('\n')
execution=R/'tmp/phase9/visual-gallery02-execution.json'
data={'schema':'endoforge.phase9.packaged-gallery-recipe.v1','phase':9,
      'source_selection_override':g.CURRENT,'factual_html_label_override':'Phase9Package-final01（实际打包运行）',
      'image_editing_or_generation':False,'human_visual_approval':'pending',
      'copy_and_layout_helper':record(helper),'execution_wrapper':record(__file__),
      'actual_package_receipt':record(capture/'package-run.json'),
      'evidence_mapping':record(mapping),'gallery':record(out/'visual_gallery.html'),
      'image_count':result['image_count'],'source_bytes_preserved':result['source_bytes_preserved']}
with execution.open('x',encoding='utf-8') as f:json.dump(data,f,indent=2,ensure_ascii=False);f.write('\n')
print(json.dumps({'mapping':record(mapping),'execution':record(execution),'gallery':str(out/'visual_gallery.html')}))
