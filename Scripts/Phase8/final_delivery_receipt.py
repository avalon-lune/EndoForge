"""Bind the exact Phase8 ZIP to a fresh extracted run and its independent audits."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from common import read, require, sha, write_new
from archive import verify, verify_zip
from runtime_identity import child
from collect_evidence import validate_capture, validate_pass, validate_preservation, validate_visual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'archive', 'archive-report', 'extraction-report', 'package', 'extracted',
                 'capture', 'audits', 'visual-review', 'preservation', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    root, package, extracted, capture, audits, output = [value.resolve() for value in
        (args.root, args.package, args.extracted, args.capture, args.audits, args.output)]
    require(not output.exists() and output.is_relative_to(root / 'output/Phase8')
            and not output.is_relative_to(package) and not output.is_relative_to(extracted), 'Use a fresh final receipt outside package trees under output/Phase8')
    require(package != extracted and package.is_relative_to(root / 'output/Phase8')
            and extracted.is_relative_to(root / 'output/Phase8'), 'Candidate and fresh extraction must be distinct Phase8 directories')
    archive_report, extraction_report = read(args.archive_report), read(args.extraction_report)
    digest = sha(args.archive)
    for name, report, mode in (('archive', archive_report, 'create'), ('extraction', extraction_report, 'extract')):
        validate_pass(name, report)
        require(report.get('schema') == 'endoforge.phase8.archive.v1' and report.get('phase') == 8 and report.get('mode') == mode
                and all(report.get(key) is True for key in ('crc_all_files', 'sha256_all_manifest_files', 'exact_manifest_membership')),
                'Incomplete exact ZIP verification: ' + name)
    require(digest == archive_report['sha256'] == extraction_report['archive_sha256']
            and Path(extraction_report['extracted_to']).resolve() == extracted, 'Archive/extraction identity mismatch')
    archive_rows, manifest_sha = verify_zip(args.archive)
    require(verify(package) == verify(extracted) == archive_rows, 'ZIP/candidate/extracted file identities differ')
    require(manifest_sha == sha(package / 'package-manifest.json') == sha(extracted / 'package-manifest.json')
            == archive_report['manifest_sha256'] == extraction_report['manifest_sha256'], 'Sealed manifest mismatch')
    candidate = read(extracted / 'Verification/verification-index.json')
    validate_pass('sealed candidate', candidate)
    require(candidate.get('schema') == 'endoforge.phase8.candidate-verification.v1' and candidate.get('phase') == 8
            and candidate.get('clinical_review') == 'pending' and candidate.get('new_native_35_execution') is False,
            'Wrong candidate/native/clinical scope')
    for row in candidate['evidence']:
        path = child(extracted / 'Verification', row['path'])
        require(path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], 'Sealed candidate evidence changed')
    require(candidate['assembly_manifest_sha256'] == sha(extracted / 'assembly-manifest.json')
            and candidate['build_receipt_sha256'] == sha(extracted / 'phase8-build-receipt.json'), 'Candidate build/assembly binding differs')
    result = validate_capture(extracted, capture, audits, shipped_auditors=True)
    review = validate_visual(args.visual_review, extracted, capture)
    require(capture != Path(candidate['capture_directory']).resolve() and audits != Path(candidate['audit_directory']).resolve(),
            'Fresh extraction must have its own capture and audit directories')
    started = datetime.fromisoformat(result['run']['tested_at_utc'].replace('Z', '+00:00')).timestamp()
    require(started >= args.extraction_report.stat().st_mtime, 'Extracted run predates the fresh extraction receipt')
    native, build, reports = (result[key] for key in ('native', 'build', 'reports'))
    require(native['native_binary_sha256'] == candidate['physics_exe_sha256'] == build['physics_exe_sha256']
            and build['game_exe_sha256'] == candidate['game_exe_sha256']
            and native['physical_asset_sha256'] == candidate['physics_asset_sha256'], 'Fresh/candidate binary or mesh identity differs')
    inherited = read(extracted / 'Verification/Native/accepted-phase7-native.json')
    require(sha(extracted / 'Verification/Native/accepted-phase7-native.json') ==
            native['accepted_phase7_native_execution']['suite']['sha256'], 'Accepted inherited native report changed')
    preservation = validate_preservation(args.preservation, candidate['preservation_baseline_sha256'], result['audit']['completed_utc'])
    require(sha(root / 'tmp/phase8/preserved-baseline.json') == candidate['preservation_baseline_sha256'], 'Current preservation baseline changed')
    for snapshot in reports['snapshot']['snapshots']:
        require(snapshot['screenshot']['dimensions'] == [1920, 1080], 'Fresh snapshot does not match the actual display target')
    evidence_paths = [args.archive_report, args.extraction_report, args.preservation, args.visual_review,
                      capture / 'phase8-packaged-run.json', audits / 'audit-run.json']
    evidence_paths.extend(audits / (name + '.json') for name in reports)
    data = {'schema': 'endoforge.phase8.final-delivery.v1', 'phase': 8, 'passed': True,
        'created_at_utc': datetime.now(timezone.utc).isoformat(), 'clinical_review': 'pending',
        'checks': {'candidate_gates_passed': True, 'archive_crc_sha256_exact_membership': True,
                   'fresh_extracted_packaged_run': True, 'fresh_shipped_source_audits': True,
                   'fresh_four_frame_alignment_and_snapshot': True, 'fresh_contact_and_liver_geometry': True,
                   'fresh_engineering_visual_review': True, 'prior_deliveries_and_references_unchanged': True},
        'archive': {'path': str(args.archive.resolve()), 'bytes': args.archive.stat().st_size, 'sha256': digest},
        'manifest_files': len(archive_rows), 'manifest_sha256': manifest_sha,
        'candidate_verification_sha256': sha(extracted / 'Verification/verification-index.json'),
        'physics_exe_sha256': build['physics_exe_sha256'], 'game_exe_sha256': build['game_exe_sha256'],
        'physics_asset_sha256': native['physical_asset_sha256'], 'source_model': 'Assets/Phase8/EndoForge_Anatomy.blend',
        'native_inheritance': build['native_inheritance'], 'native_execution_phase': 7, 'new_native_35_execution': False,
        'inherited_native_metrics': inherited['metrics'], 'predecessor_archive': candidate['predecessor_archive'],
        'fresh_interactive_performance': reports['runtime']['performance'],
        'fresh_interaction_metrics': reports['runtime']['interaction_metrics'], 'fresh_render_ablations': reports['runtime']['ablations'],
        'fresh_contact_metrics': reports['presented-contact']['metrics'], 'fresh_liver_metrics': reports['presented-liver']['metrics'],
        'fresh_internal_alignment_frames': 4, 'preserved_files': preservation['file_count'],
        'evidence': [{'path': str(path.resolve()), 'bytes': path.stat().st_size, 'sha256': sha(path)} for path in evidence_paths],
        'scope': 'Shared Phase8 engineering foundation and tested finite paths, bound to this exact ZIP and fresh extracted run. Accepted Phase7 native qualification is inherited, never described as current35 execution. Clinical calibration/review remains pending. Four alignment frames are internal regressions; no specialized research sequences, downstream-reader acceptance, suturing or universal collision guarantee.'}
    write_new(output, data)
    print(json.dumps({'passed': True, 'receipt': str(output), 'archive_sha256': digest, 'new_native_35_execution': False}))


if __name__ == '__main__':
    main()
