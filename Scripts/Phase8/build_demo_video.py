"""Encode actual Phase8 UE viewport PNGs with Blender's bundled video encoder.

Adapted from Scripts/Phase7/build_demo_video.py. Run from the repository root:
blender -b --python Scripts/Phase8/build_demo_video.py -- --input <video-dir>
    --output output/Phase8/<new-name>.mp4

The source schema remains endoforge.phase7.viewport_video.v1 because UE retains
that historical schema; numeric phase must be 8. Blender only assembles existing
verified UE PNGs. Real timestamp gaps become held source frames, with no motion
interpolation, generated image or synthetic-fixture mode. This diagnostic is not
a performance measurement or acceptance claim.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys

import bpy


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def size(value):
    return isinstance(value, list) and len(value) == 2 and all(type(x) is int and x > 0 for x in value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    directory, out = args.input.resolve(), args.output.resolve()
    declared = Path(__file__).resolve().parents[2] / 'output/Phase8'
    allowed = declared.resolve()
    require(allowed == declared, 'output/Phase8 must not redirect to another directory')
    report_path = out.with_suffix('.json')
    require(out.is_relative_to(allowed) and out != allowed and out.suffix.lower() == '.mp4',
            'Use a new MP4 child of output/Phase8')
    require(not out.exists() and not report_path.exists(), 'Use fresh video and JSON report outputs')
    require(not out.is_relative_to(directory) and not report_path.is_relative_to(directory),
            'Video outputs must stay outside the source capture directory')
    metadata_path, frames_path = directory / 'video.json', directory / 'frames.jsonl'
    metadata_sha, records_sha = sha(metadata_path), sha(frames_path)
    metadata = json.loads(metadata_path.read_text(encoding='utf-8-sig'))
    require(metadata.get('schema') == 'endoforge.phase7.viewport_video.v1'
            and type(metadata.get('phase')) is int and metadata['phase'] == 8
            and metadata.get('synthetic_api_fixture') is not True,
            'Only an actual Phase8 UE viewport capture is supported')
    require(metadata.get('diagnostic_only') is True and metadata.get('error') == ''
            and metadata.get('frame_records') == 'frames.jsonl', 'Incomplete/failed viewport capture')
    frames = [json.loads(line) for line in frames_path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    require(type(metadata.get('frames')) is int and len(frames) == metadata['frames'] and len(frames) > 1,
            'Viewport frame count does not match metadata')
    capture_hz = metadata.get('maximum_capture_hz')
    require(finite(capture_hz) and capture_hz > 0, 'Invalid capture cadence')
    require(isinstance(metadata.get('visual_manifest_sha1'), str)
            and re.fullmatch('[0-9a-f]{40}', metadata['visual_manifest_sha1']), 'Missing visual identity')
    paths = []
    for index, frame in enumerate(frames):
        require(type(frame.get('frame')) is int and frame['frame'] == index
                and frame.get('file') == f'frame-{index:06d}.png', 'Unexpected UE source frame numbering')
        image = (directory / frame['file']).resolve()
        require(image.is_relative_to(directory) and image.is_file(), 'Source image escapes capture directory')
        require(finite(frame.get('wall_elapsed_s')) and frame['wall_elapsed_s'] >= 0,
                'Invalid recorded elapsed time')
        require(size(frame.get('video_size')) and size(frame.get('source_viewport_size')),
                'Invalid recorded viewport/video size')
        require(frame['video_size'] == frames[0]['video_size'], 'Source dimensions changed within capture')
        require(frame.get('visual_manifest_sha1') == metadata['visual_manifest_sha1'], 'Frame visual identity mismatch')
        require(isinstance(frame.get('png_sha1'), str) and re.fullmatch('[0-9a-f]{40}', frame['png_sha1']),
                'Missing source PNG hash')
        with image.open('rb') as stream:
            header = stream.read(24)
            stream.seek(0)
            require(hashlib.file_digest(stream, 'sha1').hexdigest() == frame['png_sha1'], 'UE PNG SHA1 mismatch')
        require(len(header) == 24 and header[:8] == b'\x89PNG\r\n\x1a\n' and header[12:16] == b'IHDR'
                and list(struct.unpack('>II', header[16:24])) == frame['video_size'], 'PNG dimensions differ from record')
        paths.append(image)
    require(abs(frames[0]['wall_elapsed_s']) <= 1e-6, 'First UE readback must define elapsed-time zero')
    require(all(b['wall_elapsed_s'] > a['wall_elapsed_s'] for a, b in zip(frames, frames[1:])),
            'Recorded wall times must strictly increase')
    require(finite(metadata.get('last_frame_elapsed_s'))
            and abs(metadata['last_frame_elapsed_s'] - frames[-1]['wall_elapsed_s']) <= 1e-6,
            'Last source frame time differs from metadata')
    width, height = frames[0]['video_size']
    require(width % 2 == 0 and height % 2 == 0, 'H264 requires even recorded dimensions; do not resample source here')
    fps = 30
    starts = [1 + round(frame['wall_elapsed_s'] * fps) for frame in frames]
    require(all(b > a for a, b in zip(starts, starts[1:])), 'Source frames collide at presentation frame rate')
    scene = bpy.context.scene
    scene.sequence_editor_clear()
    editor = scene.sequence_editor_create()
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.fps, scene.render.fps_base = fps, 1
    scene.render.use_sequencer = True
    scene.render.use_overwrite = False
    # Display-referred UE PNGs use Standard, without a second AgX/Filmic pass.
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    scene.view_settings.exposure, scene.view_settings.gamma = 0, 1
    timeline = []
    for index, (frame, image) in enumerate(zip(frames, paths)):
        strip = editor.strips.new_image('UE_' + str(index), str(image), channel=1, frame_start=starts[index])
        duration = starts[index + 1] - starts[index] if index + 1 < len(starts) else max(1, round(fps / capture_hz))
        strip.duration = duration
        timeline.append({'source_frame': frame['frame'], 'wall_elapsed_s': frame['wall_elapsed_s'],
                         'presentation_start': starts[index], 'held_presentation_frames': duration})
    scene.frame_start, scene.frame_end = 1, starts[-1] + duration - 1
    out.parent.mkdir(parents=True, exist_ok=True)
    require(not out.exists() and not report_path.exists(), 'Output appeared during source validation')
    scene.render.filepath = str(out)
    # Blender 5.2 separates still-image and video formats through media_type.
    scene.render.image_settings.media_type = 'VIDEO'
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format, scene.render.ffmpeg.codec = 'MPEG4', 'H264'
    scene.render.ffmpeg.constant_rate_factor = 'HIGH'
    scene.render.ffmpeg.ffmpeg_preset = 'GOOD'
    scene.render.ffmpeg.audio_codec = 'NONE'
    bpy.ops.render.render(animation=True)
    require(out.is_file() and out.stat().st_size > 0, 'Encoder produced no video')
    require(sha(metadata_path) == metadata_sha and sha(frames_path) == records_sha,
            'Source metadata/records changed during encoding')
    for frame, image in zip(frames, paths):
        with image.open('rb') as stream:
            require(hashlib.file_digest(stream, 'sha1').hexdigest() == frame['png_sha1'],
                    'Source PNG changed during encoding')
    report = {'schema': 'endoforge.phase8.demo-video.v1', 'phase': 8, 'diagnostic_only': True,
              'synthetic_api_fixture': False, 'source_schema': metadata['schema'],
              'video_sha256': sha(out), 'source_metadata_sha256': metadata_sha,
              'source_frame_records_sha256': records_sha, 'source_frames': len(frames),
              'visual_manifest_sha1': metadata['visual_manifest_sha1'],
              'presentation_fps': fps, 'resolution': [width, height],
              'presentation_frames': scene.frame_end, 'timeline': timeline,
              'timestamp_quantization_max_s': .5 / fps,
              'scope': 'Actual Phase8 UE viewport diagnostic, encoded from verified original PNGs. Variable real time gaps are held source frames; no interpolation or generated motion. Final frame holds for one maximum-capture interval. Not acceptance performance.'}
    with report_path.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
