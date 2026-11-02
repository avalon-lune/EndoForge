"""Bind completed engineering evidence for human review; never grant approval.

This tmp-only helper launches no apps/tests/audits and copies no large reports.
It writes a new compact summary only after actual passed evidence and identities
agree. --plan-only checks current source/schema APIs without bulk reads or writes.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Scripts/Phase7'))
sys.path.insert(0, str(ROOT / 'Scripts/Phase9'))
from audit_identity import verify_geometry_report
from run_native_qualification import expected_cases

REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
CAPTURE_KINDS = {'appearance', 'runtime', 'geometry', 'snapshot', 'dataset', 'context', 'presented_contact', 'presented_liver'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def path(value, directory=False, existing=True):
    selected = Path(value)
    if not selected.is_absolute():
        selected = ROOT / selected
    selected = Path(os.path.abspath(selected))
    for part in reversed((selected, *selected.parents)):
        if part.exists() or part.is_symlink():
            info = part.stat(follow_symlinks=False)
            require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & REPARSE, 'Links/reparse points forbidden')
    require(not existing or (selected.is_dir() if directory else selected.is_file()), 'Missing selected evidence: ' + str(selected))
    return selected


def sha(value):
    with path(value).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def read(value):
    return json.loads(path(value).read_text(encoding='utf-8-sig'))


def ref(value):
    selected = path(value)
    return {'path': str(selected), 'sha256': sha(selected), 'bytes': selected.stat().st_size}


def bind(value):
    selected = path(value['path'])
    require(sha(selected) == value['sha256'], 'Referenced evidence SHA256 changed: ' + str(selected))
    if 'bytes' in value:
        require(selected.stat().st_size == value['bytes'], 'Referenced evidence size changed')
    return selected


def passed(value, schema=None):
    document = read(value)
    require(document.get('passed') is True, 'Actual evidence has not passed: ' + str(value))
    if schema:
        require(document.get('schema') == schema, 'Wrong evidence schema: ' + str(value))
    if 'checks' in document:
        require(document['checks'] and all(type(v) is bool and v for v in document['checks'].values()), 'Failed/incomplete actual checks')
    return document


def api_contract():
    archive = ROOT / 'tmp/phase9/delivery-preflight01/archive_phase9.py'
    tree = ast.parse(archive.read_text(encoding='utf-8-sig'))
    strings = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    require({'endoforge.phase9.archive-integrity.v1', '--candidate', '--archive', '--extracted', '--report', 'create', 'verify', 'extract'} <= strings,
            'Actual archive helper API/schema differs')
    require(len(expected_cases()) == 35, 'Actual native qualification contract differs')
    return {'archive_helper': str(archive), 'archive_schema': 'endoforge.phase9.archive-integrity.v1',
            'candidate_schema': 'endoforge.phase9.review-candidate.v1', 'native_case_count': len(expected_cases())}


def capture_index(value, inputs):
    index = passed(value, 'endoforge.phase9.complete-audit-index.v1')
    require(index['inputs'] == inputs and set(index['reports']) == CAPTURE_KINDS, 'Eight actual capture audits or input identities differ')
    documents = {}
    for name, item in index['reports'].items():
        documents[name] = passed(bind(item))
    actual = passed(index['reports']['runtime']['path'], 'endoforge.phase9.runtime-audit.v1')
    receipt_path = bind(index['actual_package_run_receipt'])
    receipt = read(receipt_path)
    require(receipt['integration_capture_completed'] is True and receipt['game_exit_code'] == receipt['native_exit_code'] == 0
            and receipt['native_graceful_exit'] is True and receipt['error'] is None, 'Actual package process receipt did not succeed')
    require(receipt['inputs_sha256'] == receipt['inputs_after_sha256']
            and receipt['inputs_sha256']['native_executable'] == inputs['physics_exe_sha256']
            and receipt['inputs_sha256']['physics_mesh'] == inputs['physics_mesh_sha256']
            and receipt['inputs_sha256']['game_executable'] == inputs['game_exe_sha256'], 'Capture process receipt input identity differs')
    measured = {key: actual['performance'][key] for key in ('mean_fps', 'frame_p95_ms', 'simulation_to_wall_ratio', 'measured_wall_seconds', 'measured_native_seconds')}
    measured['input_response_p95_ms'] = actual['raw_latency_p95_ms']
    measured['capture'] = index['capture']
    measured['package'] = index['package']
    measured['runtime_audit'] = ref(index['reports']['runtime']['path'])
    measured['package_run_receipt'] = ref(receipt_path)
    return index, documents, measured


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate', 'zip', 'archive-create', 'archive-extract', 'archive-verify', 'complete-index',
                 'native-qualification', 'raw-holds', 'native-geometry', 'endurance-index', 'build-receipt', 'preservation', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--original-complete-index', type=Path, help='Original packaged capture; otherwise use candidate provided packaged_audits evidence')
    parser.add_argument('--plan-only', action='store_true', help='Source/API plan only; no bulk evidence reads, output or process launch')
    args = parser.parse_args()
    require(sys.flags.optimize == 0, 'Run without Python -O')
    api = api_contract()
    if args.plan_only:
        print(json.dumps({'schema': 'endoforge.phase9.delivery-review-summary-plan.v1', 'api': api,
                          'arguments': {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                          'processes_launched': 0, 'bulk_evidence_read': False, 'output_created': False,
                          'engineering_ready_for_human_review_claim': False}, indent=2))
        return 0
    candidate, archive = path(args.candidate, True), path(args.zip)
    output = path(args.output, existing=False)
    require(not output.exists() and not output.is_relative_to(candidate)
            and any(output.is_relative_to(ROOT / folder) for folder in ('tmp/phase9', 'output/Phase9')), 'Use a fresh separate summary path')
    evidence_args = ('archive_create', 'archive_extract', 'archive_verify', 'complete_index', 'native_qualification',
                     'raw_holds', 'native_geometry', 'endurance_index', 'build_receipt', 'preservation')
    evidence = {name: ref(getattr(args, name)) for name in evidence_args}
    receipt_path = candidate / 'review-candidate.json'
    candidate_receipt = read(receipt_path)
    require(candidate_receipt.get('schema') == api['candidate_schema'] and candidate_receipt.get('phase') == 9
            and candidate_receipt.get('candidate_status') == 'review_candidate' and candidate_receipt.get('delivery_accepted') is False
            and candidate_receipt.get('human_visual_approval') == 'pending', 'Actual candidate must remain pending human review')
    inputs = candidate_receipt['validated_inputs']
    require(inputs == {'physics_exe_sha256': sha(candidate / 'Physics/LapPhysics.exe'),
                       'physics_mesh_sha256': sha(candidate / 'Assets/Phase9/physics-mesh.json'),
                       'game_exe_sha256': sha(candidate / 'LapTrainer/Binaries/Win64/LapTrainer.exe')}, 'Current candidate bytes differ from validated inputs')
    validation_record = candidate_receipt['validation_receipt']
    validation_path = candidate / validation_record['package_path']
    require(sha(validation_path) == validation_record['sha256'], 'Candidate validation receipt changed')
    validation = passed(validation_path, 'endoforge.phase9.validation.v1')
    require(validation['inputs'] == inputs and validation['human_visual_approval'] == 'pending', 'Candidate validation IDs/review state differ')
    archive_sha = sha(archive)
    manifest_sha = sha(candidate / 'assembly-manifest.json')
    candidate_sha = sha(receipt_path)
    archives = {mode: passed(getattr(args, 'archive_' + mode), api['archive_schema']) for mode in ('create', 'extract', 'verify')}
    extracted = path(archives['extract']['extracted'], True)
    require(not output.is_relative_to(extracted), 'Summary must be outside the tested extraction tree')
    for mode, report in archives.items():
        require(report['mode'] == mode and path(report['candidate'], True) == candidate and path(report['archive']) == archive
                and report['archive_sha256'] == archive_sha and report['archive_bytes'] == archive.stat().st_size
                and report['candidate_manifest_sha256'] == report['zip_manifest_sha256'] == manifest_sha
                and report['candidate_receipt_sha256'] == candidate_sha
                and report['crc_all_files'] is True and report['sha256_all_manifest_files'] is True
                and report['exact_manifest_membership'] is True and report['fixture_only'] is False, 'Actual archive integrity/identity differs: ' + mode)
        if mode != 'create':
            require(path(report['extracted'], True) == extracted and report['extraction_verified'] is True
                    and report['extracted_manifest_sha256'] == manifest_sha, 'Fresh extraction/verify identity differs')
        bind(report['helper'])
        bind(report['historical_integrity_core'])
    require(sha(extracted / 'assembly-manifest.json') == manifest_sha and sha(extracted / 'review-candidate.json') == candidate_sha,
            'Current extracted manifest/receipt differs')
    native = passed(args.native_qualification, 'endoforge.phase9.native-qualification.v1')
    require(native['case_count'] == native['expected_case_count'] == 35 and native['native_execution_started'] is True
            and native['inherited_results'] is False and native['native_exit_code'] == 0
            and native['native_binary']['sha256'] == inputs['physics_exe_sha256'] and native['mesh']['sha256'] == inputs['physics_mesh_sha256']
            and [item['name'] for item in native['completed']] == expected_cases(), 'Fresh native35 identity/completion differs')
    native_rows = {item['name']: item for item in native['completed']}
    native_cases = {item['name']: passed(bind({'path': item['report'], 'sha256': item['sha256']})) for item in native['completed']}
    raw = passed(args.raw_holds, 'endoforge.phase9.long-hold-raw-state-audit.v1')
    require(raw['qualification']['sha256'] == evidence['native_qualification']['sha256'] and 'inspect_states=True' in raw['validator_call']
            and raw['native_processes_launched'] == 0 and raw['validation']['case_count'] == 15
            and len(raw['validation']['raw_state_audits']) == 15, 'All15 actual raw-state validation is mandatory')
    for name, item in raw['validation']['evidence'].items():
        require(name in native_rows and item['sha256'] == native_rows[name]['sha256'], 'Raw hold report differs from native35 seal')
        bind(item)
        bind(item['trajectory'])
        require(raw['validation']['raw_state_audits'][name.removeprefix('long-hold-')]['passed'] is True, 'A raw hold audit failed')
    geometry = passed(args.native_geometry, 'endoforge.phase9.independent-native-geometry.v1')
    expected_geometry = {'dual-reference', *[name for name in expected_cases() if name.startswith('matrix-')],
                         'long-hold-tool0-nominal', 'long-hold-tool1-nominal', 'long-hold-dual-2mm'}
    require(geometry['expected_audit_count'] == len(geometry['results']) == 26
            and {(item['case'], item['kind']) for item in geometry['results']} == {(case, kind) for case in expected_geometry for kind in ('contact', 'liver')}
            and geometry['native_binary']['sha256'] == inputs['physics_exe_sha256'] and geometry['mesh']['sha256'] == inputs['physics_mesh_sha256']
            and geometry['separate_raw_state_gate']['sha256'] == evidence['raw_holds']['sha256'], 'Native26 case coverage or identity differs')
    for item in geometry['results']:
        report = passed(bind({'path': item['report'], 'sha256': item['sha256']}))
        require(item['status'] == 'passed' and report['original_trace']['sha256'] == sha(native_cases[item['case']]['trace']), 'Native geometry trace identity differs')
        verify_geometry_report(report, candidate / 'Source', item['kind'], 7)
    endurance = passed(args.endurance_index, 'endoforge.phase9.endurance-geometry-index.v1')
    require(set(endurance['reports']) == {'contact', 'liver'} and endurance['inputs']['physics_exe_sha256'] == inputs['physics_exe_sha256']
            and endurance['inputs']['physics_mesh_sha256'] == inputs['physics_mesh_sha256'], 'Both full endurance audits/identities are mandatory')
    endurance_sha = sha(native_cases['endurance']['trace'])
    for kind, item in endurance['reports'].items():
        report = passed(bind(item))
        require(report['original_trace']['sha256'] == endurance_sha
                and report['original_trace']['original_state_count'] == native_cases['endurance']['metrics']['samples'], 'Endurance trace/state membership differs')
        verify_geometry_report(report, candidate / 'Source', kind, 7)
    build = read(args.build_receipt)
    require(build.get('schema') == 'endoforge.phase9.build-receipt.v1' and build['build_succeeded'] is True
            and build['source_snapshot_unchanged'] is True
            and build['native_runtime_files_sha256']['LapPhysics.exe'] == inputs['physics_exe_sha256']
            and build['asset_files_sha256']['physics-mesh.json'] == inputs['physics_mesh_sha256']
            and build['ue_package_files_sha256']['LapTrainer/Binaries/Win64/LapTrainer.exe'] == inputs['game_exe_sha256'], 'Successful frozen build identities differ')
    for key, prefix in (('native_runtime_files_sha256', 'Physics'), ('ue_package_files_sha256', ''), ('asset_files_sha256', 'Assets/Phase9')):
        for relative, digest in build[key].items():
            require(sha(candidate / prefix / relative) == sha(extracted / prefix / relative) == digest,
                    'Candidate/extracted redistribution bytes differ from build receipt: ' + relative)
    preservation = passed(args.preservation, 'endoforge.phase9.preservation-check.v1')
    fresh, fresh_documents, fresh_metrics = capture_index(args.complete_index, inputs)
    require(path(fresh['package'], True) == extracted, 'Fresh complete8 audit index must describe this actual ZIP extraction')
    provided = candidate_receipt['provided_evidence']
    original_path = path(args.original_complete_index) if args.original_complete_index else candidate / provided['packaged_audits']['package_path']
    if not args.original_complete_index:
        require(sha(original_path) == provided['packaged_audits']['sha256'], 'Shipped original package audit index changed')
    original, original_documents, original_metrics = capture_index(original_path, inputs)
    require(path(original['capture'], True) != path(fresh['capture'], True), 'Original and fresh-extraction captures must be distinct actual runs')
    require('asset_contract' in provided, 'Shipped actual negative asset contract evidence is mandatory')
    asset_path = candidate / provided['asset_contract']['package_path']
    require(sha(asset_path) == provided['asset_contract']['sha256'], 'Shipped asset contract evidence changed')
    asset = passed(asset_path, 'endoforge.phase9.asset-contract-rejection.v1')
    require(asset['case_count'] == asset['expected_case_count'] == 19 and asset['identity']['native_binary']['sha256'] == inputs['physics_exe_sha256']
            and asset['identity']['source_mesh']['sha256'] == inputs['physics_mesh_sha256'], 'Negative asset contract identities/count differ')
    evidence['asset_contract'] = ref(asset_path)
    for name, item in provided.items():
        if 'gallery' in name.lower() or 'visual' in name.lower() or name == 'image_sha256':
            selected = candidate / item['package_path']
            require(sha(selected) == item['sha256'], 'Bound gallery/visual-review evidence changed')
            evidence['review_' + name] = ref(selected)
    evidence.update(candidate_receipt=ref(receipt_path), candidate_validation=ref(validation_path),
                    original_complete_index=ref(original_path), extracted_manifest=ref(extracted / 'assembly-manifest.json'))
    require(all(sha(item['path']) == item['sha256'] for item in evidence.values()) and sha(archive) == archive_sha,
            'A bound evidence document or archive changed while sealing')
    checks = {key: True for key in ('actual_candidate_and_zip_identity', 'archive_create_extract_verify_passed',
        'fresh_zip_extraction_runtime_and_all_eight_audits_passed', 'original_package_measurements_bound_separately',
        'fresh_native35_passed', 'all15_raw_hold_states_passed', 'native26_geometry_and_full_endurance2_passed',
        'successful_frozen_build_and_complete_redistribution_identity', 'earlier_phase_preservation_passed',
        'all19_negative_asset_contract_cases_passed', 'all_bound_reports_and_input_hashes_match')}
    document = {'schema': 'endoforge.phase9.delivery-review-summary.v1', 'phase': 9,
                'created_utc': datetime.now(timezone.utc).isoformat(), 'passed': True,
                'engineering_ready_for_human_review': True, 'checks': checks, 'inputs': inputs,
                'candidate': str(candidate), 'archive': ref(archive), 'fresh_extraction': str(extracted),
                'manifest_sha256': manifest_sha, 'evidence': evidence,
                'measurements': {'actual_packaged_capture': original_metrics, 'fresh_zip_extraction_capture': fresh_metrics},
                'coverage': {'native_cases': 35, 'raw_hold_cases': 15, 'raw_hold_states': raw['total_recorded_states_tested'],
                             'native_geometry_audits': 26, 'endurance_audits': 2, 'negative_asset_cases': 19,
                             'endurance_states': native_cases['endurance']['metrics']['samples'],
                             'fresh_presented_states': fresh['coverage']['original_states'],
                             'fresh_nonreset_edges': fresh['coverage']['non_reset_edges'],
                             'fresh_interpolated_samples': fresh['coverage']['interpolated_samples']},
                'human_visual_approval': 'pending', 'delivery_accepted': False, 'clinical_approval': 'not_claimed',
                'known_visual_review_note': 'Residual grey curvature bands remain for human review; aesthetic acceptance belongs to the human reviewer.',
                'helper': ref(__file__),
                'scope': 'Compact hash-bound engineering evidence and scoped measurements for this review candidate/ZIP and its actual fresh extraction. No automatic visual, clinical or final delivery acceptance.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(document, handle, indent=2)
        handle.write('\n')
    print(json.dumps({**ref(output), 'engineering_ready_for_human_review': True}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
