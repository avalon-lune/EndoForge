"""Extract actual Phase9 presented native states without coordinate changes.

The explicit physical mesh, current native reference and captured manifest bind
the source identity. This is trace preparation, not native qualification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from audit_uv import physics_contract


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--presented', type=Path, required=True)
    parser.add_argument('--native-reference', type=Path, required=True)
    parser.add_argument('--physics-mesh', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    partial = args.output.with_name(args.output.name+'.partial')
    require(not args.output.exists() and not partial.exists(), 'Use a fresh output path; partial evidence is preserved')
    manifest_path = args.presented.resolve().parent/'dataset/visual-manifest.json'
    paths = {'presented': args.presented.resolve(), 'native_reference': args.native_reference.resolve(),
             'physics_mesh': args.physics_mesh.resolve(), 'visual_manifest': manifest_path}
    hashes = {name: sha(path) for name,path in paths.items()}
    with args.native_reference.open(encoding='utf-8-sig') as stream:
        header, reference = json.loads(next(stream)), json.loads(next(stream))
    require(header.get('type') == 'mesh' and reference.get('protocol') == 5 and reference.get('type') == 'state',
            'Current native reference must contain a compatible mesh and state')
    _, physical = physics_contract(args.physics_mesh, reference)
    require(reference['triangles'] == header['triangles'] and
            len(reference['vertices']) == len(header['rest_vertices']), 'Native reference geometry/header differs')
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode('utf-8-sig'))
    manifest_sha1 = hashlib.sha1(manifest_bytes).hexdigest()
    require(manifest.get('phase') == 9 and manifest.get('mechanics_phase') == 6,
            'Presented trace manifest must identify Phase9 and compatible mechanics')
    require(manifest.get('physics_fingerprint') == physical['asset_fingerprint'] and
            manifest['asset_file_hashes']['physics-mesh.json'].lower() == physical['sha1'],
            'Captured manifest does not bind the explicit physical source')
    header['case_id'] = args.presented.parent.name+'-presented'
    header['provenance'] = {'phase': 9, 'presented_sha256': hashes['presented'],
        'native_reference_sha256': hashes['native_reference'], 'physics_mesh_sha256': hashes['physics_mesh'],
        'visual_manifest_sha256': hashes['visual_manifest'], 'extractor_sha256': sha(Path(__file__)),
        'physical_source': physical}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    count, episodes = 0, set()
    with args.presented.open(encoding='utf-8-sig') as stream, partial.open('x', encoding='utf8') as out:
        out.write(json.dumps(header, separators=(',', ':'))+'\n')
        for line in stream:
            record = json.loads(line)
            state = record['native_state']
            require(record.get('phase') == 9 and record.get('mechanics_phase') == 6 and state.get('protocol') == 5,
                    'Presented record must identify Phase9 and compatible protocol5')
            require(record.get('visual_manifest_sha1') == manifest_sha1, 'Presented record manifest identity differs')
            require(state.get('asset_fingerprint') == physical['asset_fingerprint'] and
                    state.get('model_id') == physical['model_id'] and
                    str(state.get('model_version')) == str(physical['model_version']),
                    'Presented state does not use the explicit physical source')
            require(state['config'] == reference['config'], 'Presented native configuration differs from current reference')
            require(state['triangles'] == header['triangles'] and
                    len(state['vertices']) == len(header['rest_vertices']), 'Presented topology differs from current native reference')
            state['stage'] = record['record_kind']
            out.write(json.dumps(state, separators=(',', ':'))+'\n')
            count += 1
            episodes.add(state['simulation_id'])
    require(count >= 30, 'At least 30 actual presented states are required')
    require(all(sha(path) == hashes[name] for name,path in paths.items()), 'Trace extraction input changed during the invocation')
    # A hard-link publication cannot overwrite a concurrently created report.
    # The partial trace remains available on failure; no partial final is used.
    os.link(partial, args.output)
    partial.unlink()
    print(json.dumps({'path': str(args.output), 'states': count, 'simulation_ids': sorted(episodes),
        'sha256': sha(args.output), 'asset_fingerprint': physical['asset_fingerprint'],
        'physics_mesh_sha256': physical['sha256'], 'phase': 9,
        'scope': 'Unresampled actual presented native states only; qualification remains separate.'}))


if __name__ == '__main__':
    main()
