"""Bind an engineering visual inspection to actual rendered images and assets.

The inspection input must describe findings, not just Boolean labels. This script
records the review and checks evidence integrity; it does not judge aesthetics.
"""
import argparse
import json
from pathlib import Path

from common import read, require, resolve_child, sha, write_new
from audit_appearance import audit_manifest


REQUIRED = ('workspace_and_scale', 'organ_silhouette_and_detail', 'instrument_geometry',
            'tissue_and_metal_materials', 'near_contact_and_attachment',
            'no_obvious_visual_physics_detachment', 'reference_informed_improvement',
            'phase7_comparison')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--scene', type=Path, required=True)
    parser.add_argument('--baseline-capture', type=Path, required=True)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    review = read(args.review)
    require(review.get('reviewer') and review.get('reviewed_at_utc'), 'Reviewer identity and time are required')
    require(review.get('scope') == 'engineering_visual_inspection', 'Do not imply tutor or clinical approval')
    require(review.get('clinical_review') == 'pending', 'Engineering review cannot supply clinician approval')
    require(set(review['findings']) >= set(REQUIRED), 'Missing visual review area')
    for key in REQUIRED:
        finding = review['findings'][key]
        require(type(finding.get('passed')) is bool and len(finding.get('description', '').strip()) >= 10, 'Missing actual visual finding: ' + key)
    images = []
    for image in review['images']:
        path = resolve_child(args.capture, image['file'])
        require(image.get('view') in ('workspace', 'organ_closeup', 'jaw_contact', 'dual_traction'), 'Unknown review view')
        require(path.is_file(), 'Missing reviewed image')
        images.append({'file': image['file'], 'view': image['view'], 'sha256': sha(path)})
    require({item['view'] for item in images} == {'workspace', 'organ_closeup', 'jaw_contact', 'dual_traction'}, 'Four review views are required')
    require(len(images) == 4 and len({item['sha256'] for item in images}) == 4, 'Four distinct actual views are required')
    baseline_images = []
    for image in review.get('baseline_images', []):
        path = resolve_child(args.baseline_capture, image['file'])
        require(path.is_file(), 'Missing reviewed Phase 7 comparison image')
        baseline_images.append({'file': image['file'], 'view': image['view'], 'sha256': sha(path)})
    require(len(baseline_images) == 4 and {i['view'] for i in baseline_images} == {i['view'] for i in images},
            'Four corresponding Phase 7 review views are required')
    require(isinstance(review.get('comparison_scope'), str) and len(review['comparison_scope'].strip()) >= 30,
            'Describe camera/exposure differences and limits of the before/after comparison')
    _, appearance = audit_manifest(args.capture/'dataset'/'visual-manifest.json', args.scene.parent)
    checks = {key: review['findings'][key]['passed'] for key in REQUIRED}
    report = {'schema': 'endoforge.phase8.visual-review.v1', 'phase': 8,
              'passed': all(checks.values()), 'checks': checks,
              'scene_sha256': sha(args.scene), 'reviewer': review['reviewer'],
              'reviewed_at_utc': review['reviewed_at_utc'], 'scope': review['scope'],
              'findings': review['findings'], 'images': images,
              'baseline_images': baseline_images, 'comparison_scope': review['comparison_scope'],
              'clinical_review': 'pending', 'appearance': appearance,
              'appearance_audit_script_sha256': sha(Path(__file__).with_name('audit_appearance.py')),
              'uv_audit_script_sha256': sha(Path(__file__).with_name('audit_uv.py')),
              'limitations': review.get('limitations', []), 'review_input_sha256': sha(args.review),
              'audit_script_sha256': sha(__file__)}
    write_new(args.output, report)
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if report['passed'] else 1)
