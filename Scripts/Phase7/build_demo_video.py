"""Encode diagnostic UE viewport frames with Blender's bundled video encoder.

Run: blender -b --python Scripts/Phase7/build_demo_video.py -- --input <video-dir>
     --output <new.mp4>
The visible pixels come from UE. Blender only assembles/encodes existing frames;
this is not a Blender simulation or a performance measurement.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import bpy


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--synthetic-api-test',action='store_true',help='Encode only a marked synthetic API fixture; never evidence of project rendering.')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);directory=a.input.resolve();out=a.output.resolve()
    if out.exists():raise FileExistsError('Use a fresh video output')
    metadata=json.loads((directory/'video.json').read_text(encoding='utf-8-sig'))
    if a.synthetic_api_test:
        assert metadata.get('synthetic_api_fixture') is True, 'Synthetic test requires an explicitly marked fixture'
    else:
        assert metadata.get('schema')=='endoforge.phase7.viewport_video.v1' and metadata.get('synthetic_api_fixture') is not True
    frames=[json.loads(line) for line in (directory/'frames.jsonl').read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    assert metadata['diagnostic_only'] is True and not metadata['error'] and len(frames)==metadata['frames'] and len(frames)>1
    assert all(b['wall_elapsed_s']>a['wall_elapsed_s'] for a,b in zip(frames,frames[1:]))
    for frame in frames:
        image=(directory/frame['file']).resolve()
        assert image.is_relative_to(directory) and hashlib.sha1(image.read_bytes()).hexdigest()==frame['png_sha1']
    scene=bpy.context.scene;scene.sequence_editor_clear();editor=scene.sequence_editor_create()
    width,height=frames[0]['video_size'];fps=30
    scene.render.resolution_x=width;scene.render.resolution_y=height;scene.render.resolution_percentage=100
    scene.render.fps=fps;scene.render.fps_base=1;scene.render.use_sequencer=True
    # Display-referred PNGs are copied through the standard colour transform,
    # never through AgX/Filmic a second time.
    scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
    scene.view_settings.exposure=0;scene.view_settings.gamma=1
    starts=[1+round(frame['wall_elapsed_s']*fps) for frame in frames]
    assert all(b>a for a,b in zip(starts,starts[1:])), 'Source frames collide at presentation frame rate'
    for i,frame in enumerate(frames):
        strip=editor.strips.new_image('UE_'+str(i),str(directory/frame['file']),channel=1,frame_start=starts[i])
        duration=starts[i+1]-starts[i] if i+1<len(starts) else max(1,round(fps/metadata['maximum_capture_hz']))
        strip.duration=duration
    scene.frame_start=1;scene.frame_end=starts[-1]+duration-1
    out.parent.mkdir(parents=True,exist_ok=True);scene.render.filepath=str(out)
    # Blender 5.2 separates still-image and video formats through media_type.
    scene.render.image_settings.media_type='VIDEO'
    scene.render.image_settings.file_format='FFMPEG';scene.render.ffmpeg.format='MPEG4';scene.render.ffmpeg.codec='H264'
    scene.render.ffmpeg.constant_rate_factor='HIGH';scene.render.ffmpeg.ffmpeg_preset='GOOD'
    scene.render.ffmpeg.audio_codec='NONE'
    bpy.ops.render.render(animation=True)
    assert out.is_file() and out.stat().st_size>0
    report={'schema':'endoforge.phase7.video-api-test.v1' if a.synthetic_api_test else 'endoforge.phase7.demo-video.v1','phase':7,'diagnostic_only':True,
            'synthetic_api_fixture':a.synthetic_api_test,
            'video_sha256':sha(out),'source_metadata_sha256':sha(directory/'video.json'),
            'source_frame_records_sha256':sha(directory/'frames.jsonl'),'source_frames':len(frames),
            'presentation_fps':fps,'resolution':[width,height],'presentation_frames':scene.frame_end,
            'timestamp_quantization_max_s':.5/fps,'scope':('SYNTHETIC API TEST ONLY; no project simulation, rendering or acceptance evidence.' if a.synthetic_api_test else 'Actual UE viewport diagnostic, encoded from original PNGs. Variable real frame gaps retained as held frames; no interpolation or generated motion. Not acceptance performance.')}
    out.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
