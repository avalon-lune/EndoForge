"""Bind a human/agent visual inspection to actual rendered images and assets.

The inspection input must describe findings, not just Boolean labels. This script
records the review and checks evidence integrity; it does not judge aesthetics.
"""
import argparse
import json
from pathlib import Path

from common import read, require, resolve_child, sha, write_new


REQUIRED = ('workspace_and_scale', 'organ_silhouette_and_detail', 'instrument_geometry',
            'tissue_and_metal_materials', 'near_contact_and_attachment',
            'no_obvious_visual_physics_detachment')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--scene', type=Path, required=True)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    review = read(args.review)
    require(review.get('reviewer') and review.get('reviewed_at_utc'), 'Reviewer identity and time are required')
    require(review.get('scope') == 'engineering_visual_inspection', 'Do not imply tutor or clinical approval')
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
    checks = {key: review['findings'][key]['passed'] for key in REQUIRED}
    report = {'schema': 'endoforge.phase6.visual-review.v1', 'phase': 6,
              'passed': all(checks.values()), 'checks': checks,
              'scene_sha256': sha(args.scene), 'reviewer': review['reviewer'],
              'reviewed_at_utc': review['reviewed_at_utc'], 'scope': review['scope'],
              'findings': review['findings'], 'images': images,
              'limitations': review.get('limitations', []), 'review_input_sha256': sha(args.review),
              'audit_script_sha256': sha(__file__)}
    write_new(args.output, report)
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if report['passed'] else 1)
