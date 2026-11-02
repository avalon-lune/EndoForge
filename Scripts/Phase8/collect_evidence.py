"""Bind and bundle one actually audited Phase8 candidate before final ZIP sealing.

Only current-run reports, selected captures and small inherited identity reports
are copied. Accepted Phase7 native evidence is kept verbatim and explicitly
inherited; its 35 raw trajectories are never rerun or copied by this helper.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
from common import read, require, sha, write_new
from archive import manifest_rows, package_files
from build_receipt import bound_record, source_hashes
from runtime_identity import child, verify as verify_runtime
from run_capture_audits import DEPENDENCIES, EXPECTED_FRAMES, bind_reports, descriptor, safe_path

REPORTS = ('appearance', 'runtime', 'geometry', 'dataset', 'snapshot', 'context', 'presented-contact', 'presented-liver')


def validate_pass(name, report):
    require(report.get('passed') is True, 'Missing/failed evidence: ' + name)
    require(all(value is True for value in report.get('checks', {}).values()), 'Incomplete checks: ' + name)
    finite_tree(report)


def finite_tree(value):
    if type(value) in (int, float):
        require(math.isfinite(value), 'Nonfinite numeric evidence')
    elif isinstance(value, dict):
        for item in value.values():
            finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            finite_tree(item)


def absolute_record(record):
    path = safe_path(record['path'])
    require(path.is_file() and sha(path) == record['sha256'], 'Changed bound file: ' + str(path))
    if 'bytes' in record:
        require(path.stat().st_size == record['bytes'], 'Changed bound size: ' + str(path))
    return path


def verify_sources(package, build, root=None):
    expected = build['source_asset_sha256']
    require(expected, 'Missing frozen editable source identity')
    if root is not None:
        require(source_hashes(root) == expected, 'Root source/assets changed after the frozen build')
    for name, digest in expected.items():
        require(sha(child(package / 'Source', name)) == digest, 'Shipped source differs from frozen input: ' + name)


def verify_assembly(package):
    require(not (package / 'package-manifest.json').exists(), 'Collect before final archive seal; use assembly-manifest.json')
    rows = manifest_rows(read(package / 'assembly-manifest.json'))
    require(set(package_files(package)) == {row['path'] for row in rows} | {'assembly-manifest.json'},
            'Assembly membership changed outside excluded runtime sessions/caches')
    for row in rows:
        path = child(package, row['path'])
        require(path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], 'Assembly member changed: ' + row['path'])
    return rows


def numerical_limits(reports, spec):
    perf, gate = reports['runtime']['performance'], spec['performance']
    require([perf['width'], perf['height']] == [gate['width'], gate['height']] == [1920, 1080], 'Wrong measured display size')
    require(perf['mean_fps'] >= gate['display_mean_fps_minimum'] == 55
            and perf['frame_p95_ms'] <= gate['display_p95_frame_ms_maximum'] == 25
            and perf['simulation_to_wall_ratio'] >= gate['simulation_to_wall_ratio_minimum'] == .95,
            'Measured display/progression limits failed')
    metrics, limits = reports['runtime']['interaction_metrics'], spec['interaction']
    for key, limit in (('response_p95_ms', 'response_p95_ms_maximum'), ('target_lead_max_mm', 'target_lead_mm_maximum'),
                       ('stop_residual_travel_max_mm', 'stop_residual_travel_mm_maximum')):
        roundoff = 0 if key == 'response_p95_ms' else 1e-9
        require(0 <= metrics[key] <= limits[limit] + roundoff, 'Interaction limit failed: ' + key)
    contact, liver = reports['presented-contact']['metrics'], reports['presented-liver']['metrics']
    for key in ('maximum_node_depth_mm', 'maximum_whole_triangle_depth_mm', 'maximum_interpolated_depth_mm',
                'maximum_inter_tool_jaw_overlap_mm', 'maximum_liver_surface_in_jaw_mm'):
        require(0 <= contact[key] <= .15, 'Unchanged 0.15mm contact bound failed: ' + key)
    require(contact['minimum_tet_volume_ratio'] > 0 and contact['minimum_triangle_area_ratio'] > 0
            and contact['liver_enclosed_jaw_centers_including_overlap'] == 0, 'Invalid contact element/containment evidence')
    require(liver['intersecting_or_touching_states_including_overlap'] == liver['wall_inside_liver_states_including_overlap'] == 0
            and 0 <= liver['maximum_winding_integer_error'] < 1e-5, 'Liver geometry limits failed')


def validate_capture(package, capture, audits, root=None, shipped_auditors=False):
    """Read-only binding reuse for collection and fresh-extraction finalization."""
    build = read(package / 'phase8-build-receipt.json')
    run_path = capture / 'phase8-packaged-run.json'
    run, audit = read(run_path), read(audits / 'audit-run.json')
    validate_pass('packaged run', run)
    require(run.get('schema') == 'endoforge.phase8.package-run.v1' and run.get('phase') == 8
            and run.get('run_kind') == 'packaged' and Path(run['package_root']).resolve() == package,
            'Capture was not executed against this exact Phase8 package')
    require(run['game_exit_code'] == run['native_exit_code'] == 0 and run.get('stereo_frames') == 4, 'Incomplete packaged lifecycle/alignment')
    verify_runtime(package, build, run)
    verify_sources(package, build, root)
    validate_pass('capture orchestration', audit)
    require(audit.get('schema') == 'endoforge.phase8.capture-audits.v1' and audit.get('phase') == 8
            and audit.get('status') == 'capture_audits_passed' and audit.get('delivery_accepted') is False,
            'Incomplete or incorrectly scoped capture audit run')
    paths = {key: safe_path(value) for key, value in audit['paths'].items()}
    require(paths['capture'] == capture and paths['output'] == audits and paths['assets'] == package / 'Assets/Phase8'
            and paths['native_executable'] == package / 'Physics/LapPhysics.exe', 'Audit paths identify another capture/package')
    require(paths['dataset'] == capture / 'dataset' and paths['scene'] == package / 'Assets/Phase8/scene.json'
            and paths['physics_mesh'] == package / 'Assets/Phase8/physics-mesh.json', 'Audit scene/data paths differ')
    require(paths['source_root'] == package / 'Source' if shipped_auditors else
            paths['source_root'] in {root, package / 'Source'}, 'Unexpected auditor source tree')
    require(audit['expected_internal_alignment_frames'] == EXPECTED_FRAMES, 'Wrong alignment audit scope')
    require(set(audit['dependencies']) == set(DEPENDENCIES), 'Changed auditor dependency membership')
    for name, record in audit['dependencies'].items():
        require(absolute_record(record) == paths['source_root'] / name
                and record['sha256'] == sha(child(package / 'Source', name)), 'Auditor is not the shipped source: ' + name)
    for record in audit['inputs'].values():
        absolute_record(record)
    jobs = {job['name']: job for job in audit['jobs']}
    require(len(jobs) == len(audit['jobs']) and set(jobs) == set(REPORTS) | {'extract'}, 'Incomplete/duplicate audit jobs')
    reports = {}
    for name, job in jobs.items():
        require(job['exit_code'] == 0 and absolute_record(job['log']) == audits / (name + '.log'), 'Failed/mismatched audit log')
        if name != 'extract':
            require(absolute_record(job['report']) == audits / (name + '.json'), 'Report belongs to another audit run')
            reports[name] = read(audits / (name + '.json'))
            validate_pass(name, reports[name])
    snapshots = sorted(capture.glob('*snapshot-*.json'))
    trace = absolute_record(audit['extracted_trace'])
    require(trace == audits / 'presented-native-trace.jsonl', 'Unexpected extracted presented trace')
    bind_reports(paths, snapshots, reports, trace, audit['inputs'], audit['dependencies'])
    for field, key in (('input_report_sha256', 'input'), ('runtime_report_sha256', 'runtime'), ('interaction_report_sha256', 'interaction')):
        require(run[field] == audit['inputs'][key]['sha256'], 'Packaged run/audit input mismatch: ' + key)
    native_path = child(package, build['packaged_evidence']['native_inheritance']['path'])
    native = read(native_path)
    validate_pass('inherited native identity', native)
    require(native.get('execution_phase') == 7 and native.get('native_suite_reexecuted') is False
            and native.get('new_native_35_execution') is False, 'Inherited native execution scope changed')
    require(sha(native_path) == audit['inputs']['native_inheritance']['sha256'] == build['native_inheritance_receipt_sha256'],
            'Native identity evidence differs across package/build/audit')
    require(native['native_binary_sha256'] == run['physics_exe_sha256'] == build['physics_exe_sha256']
            and native['physical_asset_sha256'] == reports['dataset']['physics_mesh_sha256'], 'Native/physical identity differs')
    numerical_limits(reports, read(package / 'Source/Scripts/Phase8/acceptance-spec.json'))
    return {'build': build, 'run': run, 'audit': audit, 'paths': paths, 'reports': reports, 'native': native,
            'native_path': native_path, 'trace': trace, 'snapshots': snapshots, 'run_path': run_path}


def validate_visual(path, package, capture):
    review = read(path)
    validate_pass('visual inspection', review)
    require(review.get('schema') == 'endoforge.phase8.visual-review.v1' and review.get('phase') == 8
            and review.get('scope') == 'engineering_visual_inspection' and review.get('clinical_review') == 'pending',
            'Visual review must retain its engineering/clinical-pending scope')
    require(review['scene_sha256'] == sha(package / 'Assets/Phase8/scene.json'), 'Visual review uses another scene')
    for name in ('audit_script_sha256', 'appearance_audit_script_sha256', 'uv_audit_script_sha256'):
        script = {'audit_script_sha256': 'record_visual_review.py', 'appearance_audit_script_sha256': 'audit_appearance.py',
                  'uv_audit_script_sha256': 'audit_uv.py'}[name]
        require(review[name] == sha(package / 'Source/Scripts/Phase8' / script), 'Visual review auditor differs from shipped source')
    require(len(review['images']) == 4 and {row['view'] for row in review['images']} ==
            {'workspace', 'organ_closeup', 'jaw_contact', 'dual_traction'}, 'Four distinct review views are required')
    for row in review['images']:
        require(sha(child(capture, row['file'])) == row['sha256'], 'Reviewed image changed')
    require(len({row['sha256'] for row in review['images']}) == 4, 'Visual review repeats the same image')
    return review


def validate_preservation(path, baseline_sha, after=None):
    report = read(path)
    validate_pass('preservation', report)
    require(report.get('schema') == 'endoforge.phase8.preservation-check.v1' and report.get('mode') == 'verify'
            and report['baseline_sha256'] == baseline_sha and not any(report.get(key) for key in ('missing', 'added', 'changed')),
            'Preservation evidence is incomplete or belongs to another baseline')
    if after:
        require(datetime.fromisoformat(report['completed_utc'].replace('Z', '+00:00')) >=
                datetime.fromisoformat(after.replace('Z', '+00:00')), 'Preservation predates the completed capture audits')
    return report


def import_evidence(root, path, scene_sha, mesh_sha):
    receipt = read(path)
    validate_pass('scoped UE import', receipt)
    require(receipt.get('schema') == 'endoforge.phase8.editor-import-receipt.v1' and receipt.get('phase') == 8
            and receipt.get('exit_code') == 0 and not receipt.get('error'), 'Wrong/failed import receipt')
    for key in ('protected_assets_unchanged', 'material_report_fresh', 'geometry_report_fresh',
                'material_compile_statistics_passed', 'geometry_import_passed', 'final_success_marker'):
        require(receipt.get(key) is True, 'Incomplete import gate: ' + key)
    require(not receipt.get('changed_protected_assets') and receipt['physics_sha256'] == mesh_sha, 'Import physical/protected identity differs')
    material_path, geometry_path = [absolute_record(receipt['reports'][name]) for name in ('material', 'geometry')]
    material, geometry = read(material_path), read(geometry_path)
    validate_pass('imported materials', material); validate_pass('imported geometry', geometry)
    require(geometry['scene_sha256'] == scene_sha and geometry['coordinate_tolerance_cm'] == .0002, 'Imported scene/tolerance differs')
    require(len(geometry['objects']) == 7 and len(material['materials']) == 3, 'Incomplete imported geometry/material membership')
    for obj in geometry['objects']:
        validate_pass('imported object', obj)
        require(obj['missing_correspondences'] == 0 and 0 <= obj['coordinate_max_error_cm'] <= .0002
                and 0 <= obj['uv_max_error'] < .00005 and obj['minimum_pn_shading_normal_dot'] > .998,
                'Unchanged imported-buffer numeric limits failed')
    for item in material['materials']:
        require(item.get('compiled_instructions_available') is True and item['asset'].startswith('/Game/Phase8/Materials/')
                and all(item['statistics'][name] > 0 for name in ('num_vertex_shader_instructions', 'num_pixel_shader_instructions')),
                'Missing compiled material instructions')
    before_path, after_path = [safe_path(receipt[name]) for name in ('protected_before', 'protected_after')]
    before, after = read(before_path), read(after_path)
    baseline = root / 'tmp/phase8/preserved-baseline.json'
    require(sha(baseline) == receipt['baseline_sha256'] == before['baseline_sha256'] == after['baseline_sha256'], 'Import preservation baseline differs')
    require(before['files_sha256'] == after['files_sha256'] and len(before['files_sha256']) == receipt['protected_assets_count'] == 23,
            'Protected import membership changed')
    baseline_rows = {row['path']: row for row in read(baseline)['files']}
    for name, digest in before['files_sha256'].items():
        require(baseline_rows[name]['sha256'] == digest == sha(child(root, name)), 'Protected old content changed: ' + name)
    return receipt, {'receipt': path, 'material': material_path, 'geometry': geometry_path,
                     'protected-before': before_path, 'protected-after': after_path, 'log': safe_path(receipt['log'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'package', 'capture', 'audits', 'visual-review', 'import-receipt'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--preservation', type=Path, help='Passed candidate preservation check; defaults to audits/preservation.json')
    args = parser.parse_args()
    root, package, capture, audits = [safe_path(value) for value in (args.root, args.package, args.capture, args.audits)]
    require(package.is_relative_to(root / 'output/Phase8') and package != root / 'output/Phase8', 'Candidate must be under output/Phase8')
    out = package / 'Verification'
    require(not out.exists(), 'Use a candidate without an existing Verification bundle')
    verify_assembly(package)
    result = validate_capture(package, capture, audits, root)
    build, reports, native = (result[key] for key in ('build', 'reports', 'native'))
    review = validate_visual(args.visual_review, package, capture)
    import_receipt, import_files = import_evidence(root, args.import_receipt, reports['dataset']['scene_sha256'], native['physical_asset_sha256'])
    preservation_path = args.preservation.resolve() if args.preservation else audits / 'preservation.json'
    preservation = validate_preservation(preservation_path, import_receipt['baseline_sha256'])
    provenance = read(package / 'Assets/Phase8/provenance.json')
    require(provenance.get('schema') == 'endoforge.phase8.provenance.v1' and provenance.get('physical_geometry_changed') is False
            and provenance['physics_sha256'] == native['physical_asset_sha256'], 'Authored provenance/physical identity differs')
    require({'EndoForge_Anatomy.blend', 'scene.json', 'physics-mesh.json'} <= set(provenance['files']), 'Incomplete editable asset provenance')
    for name, digest in provenance['files'].items():
        require(sha(child(package / 'Assets/Phase8', name)) == digest, 'Authored artifact changed: ' + name)
    for name, digest in provenance['authoring_dependencies'].items():
        require(sha(child(package / 'Source', name)) == digest, 'Authoring source changed: ' + name)
    accepted_suite = bound_record(root, native['accepted_phase7_native_execution']['suite'])
    accepted_final = bound_record(root, native['accepted_final'])
    accepted_manifest = bound_record(root, native['accepted_manifest'])
    old_rows = {row['path']: row for row in read(accepted_manifest)}
    require(len(review['baseline_images']) == 4, 'Four accepted Phase7 comparison images are required')
    comparison = []
    for row in review['baseline_images']:
        name = 'Verification/Capture/' + row['file']
        require(name in old_rows and old_rows[name]['sha256'] == row['sha256'], 'Comparison image is not the accepted Phase7 image')
        comparison.append((child(accepted_manifest.parent, name), row['file']))
    out.mkdir()
    evidence, copied = [], set()

    def copy(source, relative, compress=False):
        source, destination = safe_path(source), child(out, relative)
        if relative in copied:
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        original = descriptor(source)
        if compress:
            with source.open('rb') as inp, destination.open('xb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as target:
                digest=hashlib.sha256()
                while block:=inp.read(2**20):
                    digest.update(block);target.write(block)
                require(digest.hexdigest()==original['sha256'], 'Compressed evidence source changed')
        else:
            with source.open('rb') as inp, destination.open('xb') as target:
                shutil.copyfileobj(inp, target)
            require(sha(destination) == original['sha256'], 'Copied evidence changed')
        evidence.append({'path': relative, 'bytes': destination.stat().st_size, 'sha256': sha(destination),
                         'source': original['path'], 'source_sha256': original['sha256'], 'gzip': compress})
        copied.add(relative)

    for name in REPORTS:
        copy(audits / (name + '.json'), 'Reports/' + name + '.json')
    for source, relative in ((audits / 'audit-run.json', 'Reports/audit-run.json'), (args.visual_review, 'Reports/visual-review.json'),
            (preservation_path, 'Reports/preservation.json'), (result['native_path'], 'Reports/native-inheritance.json'),
            (accepted_suite, 'Native/accepted-phase7-native.json'), (accepted_final, 'Native/accepted-phase7-final.json'),
            (accepted_manifest, 'Native/accepted-phase7-manifest.json'), (root / 'tmp/phase8/preserved-baseline.json', 'preserved-baseline.json')):
        copy(source, relative)
    for name, path in import_files.items():
        copy(path, 'Import/' + name + ('.log' if name == 'log' else '.json'))
    for job in result['audit']['jobs']:
        copy(absolute_record(job['log']), 'AuditLogs/' + job['name'] + '.log')
    selected = {result['run_path'], *(capture / name for name in ('phase5-input-test.json', 'phase6-runtime.json', 'phase6-interaction-test.json')),
                absolute_record(result['audit']['inputs']['log']), capture / 'dataset/visual-manifest.json'}
    for image in [*review['images'], *reports['runtime']['images']]:
        selected.add(child(capture, image['file']))
    for snapshot in reports['snapshot']['snapshots']:
        selected.update((child(capture, snapshot['file']), child(capture, snapshot['screenshot']['file'])))
    for frame in reports['dataset']['frames']:
        frame_path = capture / 'dataset' / frame['sequence'] / f"{frame['frame']:04d}" / 'frame.json'
        selected.add(frame_path)
        selected.update(child(frame_path.parent, name) for name in frame['audited_payload_sha256'])
    for name in ('launcher.stdout.log', 'launcher.stderr.log', 'physics.stdout.log', 'physics.stderr.log', 'native-timer-policy.json', 'ue-timer-policy.json'):
        if (capture / name).is_file():
            selected.add(capture / name)
    for source in sorted(selected):
        copy(source, 'Capture/' + source.relative_to(capture).as_posix())
    copy(capture / 'phase5-presented-states.jsonl', 'Capture/phase5-presented-states.jsonl.gz', True)
    copy(result['trace'], 'AuditedTraces/presented-native-trace.jsonl.gz', True)
    for source, name in comparison:
        copy(source, 'Comparison/Phase7/' + name)
    for source in sorted((capture / 'native-sessions').rglob('*')):
        if source.is_file() and source.suffix.lower() in ('.json', '.jsonl') and not {'cache', 'saved', 'logs'}.intersection(part.lower() for part in source.parts):
            relative = source.relative_to(capture).as_posix()
            copy(source, 'Capture/' + relative + ('.gz' if source.suffix == '.jsonl' else ''), source.suffix == '.jsonl')
    verify_sources(package, build, root)
    for row in evidence:
        require(sha(child(out, row['path'])) == row['sha256'], 'Bundled evidence changed before index seal')
    index = {'schema': 'endoforge.phase8.candidate-verification.v1', 'phase': 8, 'passed': True,
        'created_at_utc': datetime.now(timezone.utc).isoformat(), 'clinical_review': 'pending',
        'checks': {'frozen_source_and_runtime': True, 'actual_packaged_input': True, 'all_capture_audits': True,
                   'engineering_visual_review': True, 'scoped_actual_import': True, 'prior_deliveries_preserved': True},
        'capture_directory': str(capture), 'audit_directory': str(audits),
        'assembly_manifest_sha256': sha(package / 'assembly-manifest.json'), 'build_receipt_sha256': sha(package / 'phase8-build-receipt.json'),
        'physics_exe_sha256': build['physics_exe_sha256'], 'game_exe_sha256': build['game_exe_sha256'],
        'physics_asset_sha256': native['physical_asset_sha256'], 'source_model': 'Assets/Phase8/EndoForge_Anatomy.blend',
        'native_inheritance': build['native_inheritance'], 'native_execution_phase': 7, 'new_native_35_execution': False,
        'inherited_native_metrics': read(accepted_suite)['metrics'], 'predecessor_archive': read(accepted_final)['archive'],
        'interactive_performance': reports['runtime']['performance'], 'interaction_metrics': reports['runtime']['interaction_metrics'],
        'render_ablations': reports['runtime']['ablations'], 'internal_alignment_frames': 4,
        'preserved_files': preservation['file_count'], 'preservation_baseline_sha256': import_receipt['baseline_sha256'],
        'evidence': evidence,
        'scope': 'Candidate engineering gates for this actual Phase8 package; final archive CRC/SHA, fresh extraction/run/audits and final preservation remain required. Native qualification is inherited from accepted Phase7, not reexecuted. Clinical review remains pending; no specialized research sequences or teammate-reader acceptance.'}
    write_new(out / 'verification-index.json', index)
    print(json.dumps({'passed': True, 'bundle': str(out), 'files': len(evidence), 'new_native_35_execution': False,
                      'next': 'Seal final package-manifest, archive, extract freshly, run/audit/review extracted package, then final receipt.'}))


if __name__ == '__main__':
    main()
