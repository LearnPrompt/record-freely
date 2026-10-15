import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image
import pytest

from background_masks import SurfaceFiller
from render_reviewed import load_plan, paint_frame
from redact_video import probe


def save_plan(tmp_path, **changes):
    plan = dict(version=1, source_sha256='a'*64, start_frame=0, end_frame=6, review_status='approved', regions=[], overlays=[])
    plan.update(changes)
    path = tmp_path/'plan.json'
    path.write_text(json.dumps(plan))
    return path


def test_bound_assets_transparent_overlay_and_bitmap_holes(tmp_path):
    mask = np.full((10, 20), 255, np.uint8)
    mask[3:7, 8:12] = 0
    Image.fromarray(mask).save(tmp_path/'mask.png')
    overlay = np.zeros((10, 20, 4), np.uint8)
    overlay[:, :5] = [255, 0, 0, 128]
    Image.fromarray(overlay).save(tmp_path/'label.png')
    path = save_plan(tmp_path, regions=[dict(id='r', start_frame=0, end_frame=6,
        geometry={'box': [20, 20, 20, 10], 'mask_path': 'mask.png', 'mask_sha256': hashlib.sha256((tmp_path/'mask.png').read_bytes()).hexdigest()},
        fill={'mode': 'fixed', 'color_bgr': [20, 20, 20]})],
        overlays=[dict(path='label.png', sha256=hashlib.sha256((tmp_path/'label.png').read_bytes()).hexdigest(), x=0, y=0, start_frame=0, end_frame=6)])
    _, regions, overlays, _ = load_plan(path, 'a'*64, 80, 60)
    original = np.full((60, 80, 3), 100, np.uint8)
    output, meta = paint_frame(original, 0, regions, overlays, SurfaceFiller())
    assert output[23, 28].tolist() == [100, 100, 100]
    assert output[20, 20].tolist() == [20, 20, 20]
    assert output[0, 0].tolist() == [50, 50, 178]
    assert output[0, 10].tolist() == [100, 100, 100]
    assert meta['outside_changed_pixels'] == 0
    (tmp_path/'mask.png').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='SHA256'):
        load_plan(path, 'a'*64, 80, 60)


def test_pending_or_incomplete_track_or_unrelated_source_cannot_render(tmp_path):
    path = save_plan(tmp_path, review_status='pending')
    with pytest.raises(ValueError, match='approval'):
        load_plan(path, 'a'*64, 80, 60)
    path = save_plan(tmp_path, pending_gaps=[1])
    with pytest.raises(ValueError, match='approval'):
        load_plan(path, 'a'*64, 80, 60)
    path = save_plan(tmp_path, regions=[dict(id='r', start_frame=0, end_frame=6, geometry_by_frame={'0': {'box': [1, 1, 5, 5]}})])
    with pytest.raises(ValueError, match='every active'):
        load_plan(path, 'a'*64, 80, 60)
    path = save_plan(tmp_path)
    with pytest.raises(ValueError, match='SHA256'):
        load_plan(path, 'b'*64, 80, 60)


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_cli_render_from_original_once_preserves_frames_audio_and_tags(tmp_path):
    source = tmp_path/'source.mkv'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=80x60:rate=30:duration=0.4',
                    '-f', 'lavfi', '-i', 'sine=frequency=700:sample_rate=48000:duration=0.4', '-c:v', 'ffv1', '-c:a', 'pcm_s16le',
                    str(source)], check=True)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    path = save_plan(tmp_path, source_sha256=source_hash, start_frame=3, end_frame=9,
                     regions=[dict(id='r', start_frame=3, end_frame=9, geometry={'box': [20, 20, 20, 10]}, fill={'mode': 'fixed', 'color_bgr': [30, 30, 30]})])
    output = tmp_path/'rendered'
    script = Path(__file__).resolve().parents[1]/'scripts/render_reviewed.py'
    subprocess.run([sys.executable, str(script), str(source), '--patch', str(path), '--output-dir', str(output),
                    '--crf', '16', '--preset', 'medium', '--color-space', 'bt709'], check=True)
    report = json.loads((output/'report.json').read_text())
    assert report['status'] == 'complete' and report['processed_frames'] == 6
    assert report['encoding']['video_encoding_generations'] == 1
    assert report['refinement_verification']['outside_pixels_equal_before_encode']
    assert [r['source_frame'] for r in report['frames']] == list(range(3, 9))
    assert report['encoding_verification']['explicit_color_tags_verified']
    streams = probe(output/'redacted.mp4')['streams']
    assert streams[0]['nb_frames'] == '6' and any(s['codec_type'] == 'audio' for s in streams)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    retry = subprocess.run([sys.executable, str(script), str(source), '--patch', str(path), '--output-dir', str(output)], capture_output=True)
    assert retry.returncode != 0 and b'Output directory exists' in retry.stderr


def test_invalid_fill_is_rejected_before_render(tmp_path):
    for fill in ({'mode': 'fixed', 'color_bgr': [30, 30, 30], 'smooth_alpha': 0},
                 {'mode': 'plane', 'max_gradient': -.5},
                 {'mode': 'local', 'max_local_edge': float('inf')},
                 {'mode': 'local', 'sample_box': [-1, 0, 5, 5]},
                 {'mode': 'local', 'unexpected_fallback': True}):
        path = save_plan(tmp_path, regions=[dict(id='r', start_frame=0, end_frame=6, geometry={'box': [20, 20, 20, 10]}, fill=fill)])
        with pytest.raises(ValueError):
            load_plan(path, 'a'*64, 80, 60)


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='FFmpeg required')
def test_reviewed_decoder_explicitly_stops_at_selected_count(tmp_path, monkeypatch):
    import render_reviewed as renderer
    source = tmp_path/'source.mkv'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=80x60:rate=30:duration=3',
                    '-c:v', 'ffv1', str(source)], check=True)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    path = save_plan(tmp_path, source_sha256=source_hash, start_frame=3, end_frame=9)
    original_popen = subprocess.Popen
    commands = []
    def observed_popen(command, *args, **kwargs):
        commands.append(command)
        return original_popen(command, *args, **kwargs)
    monkeypatch.setattr(renderer.subprocess, 'Popen', observed_popen)
    monkeypatch.setattr(sys, 'argv', ['render_reviewed.py', str(source), '--patch', str(path), '--output-dir', str(tmp_path/'out')])
    renderer.main()
    decoder = next(c for c in commands if 'trim=start_frame=3:end_frame=9' in c)
    assert decoder[decoder.index('-frames:v')+1] == '6'
    report = json.loads((tmp_path/'out/report.json').read_text())
    assert len(report['frames']) == 6 and report['status'] == 'complete'


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='FFmpeg required')
def test_report_additive_rectangles_require_exact_hash_binding(tmp_path):
    source = tmp_path/'source.mkv'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=80x60:rate=30:duration=0.2',
                    '-c:v', 'ffv1', str(source)], check=True)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    baseline = dict(status='complete', width=80, height=60, fps=30, start=0, source_sha256=source_hash, processed_frames=6,
                    frames=[dict(frame=i, boxes=[[20, 20, 20, 10]], regions=[{}], origins=['automatic']) for i in range(6)])
    baseline_path = tmp_path/'automatic.json'
    baseline_path.write_text(json.dumps(baseline))
    baseline_hash = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    script = Path(__file__).resolve().parents[1]/'scripts/render_reviewed.py'
    plan = save_plan(tmp_path, source_sha256=source_hash)
    result = subprocess.run([sys.executable, str(script), str(source), '--patch', str(plan), '--report', str(baseline_path),
                             '--output-dir', str(tmp_path/'rejected')], capture_output=True)
    assert result.returncode != 0 and b'source_report_sha256' in result.stderr
    assert not (tmp_path/'rejected').exists()
    plan = save_plan(tmp_path, source_sha256=source_hash, source_report_sha256=baseline_hash)
    subprocess.run([sys.executable, str(script), str(source), '--patch', str(plan), '--report', str(baseline_path),
                    '--output-dir', str(tmp_path/'accepted')], check=True)
    final = json.loads((tmp_path/'accepted/report.json').read_text())
    assert final['refinement_baseline_sha256'] == baseline_hash
    assert all(r['boxes'] == [[20, 20, 20, 10]] for r in final['frames'])


@pytest.mark.parametrize('mode', ['local', 'plane'])
def test_sampling_never_borrows_original_private_pixels_under_overlay_canvas(mode):
    regions = [dict(id='adjacent-ui', start_frame=0, end_frame=1, geometry={'box': [60, 40, 20, 12]},
                    fill={'mode': mode, 'radius': 60, 'sample_box': [70, 20, 60, 70], 'min_samples': 32})]
    pixels = np.full((50, 50, 4), [5, 5, 5, 255], np.uint8)
    overlays = [dict(x=80, y=30, pixels=pixels, start_frame=0, end_frame=1, sha256='opaque-cover')]
    results = []
    for private_color in (180, 220):
        original = np.full((120, 160, 3), 40, np.uint8)
        original[40:52, 60:80] = 255
        # The sources differ ONLY beneath the supplied privacy-cover canvas.
        original[30:80, 80:130] = private_color
        output, audit = paint_frame(original, 0, regions, overlays, SurfaceFiller())
        results.append((output, audit))
        assert audit['surface_audit'][0]['color_bgr'] == [40, 40, 40]
        assert np.all(output[40:52, 60:80] == 40)
        assert audit['outside_changed_pixels'] == 0
    assert np.array_equal(results[0][0], results[1][0])
    assert results[0][1]['surface_audit'] == results[1][1]['surface_audit']


def test_overlay_canvas_exclusion_keeps_fixed_fill_and_rgba_compositing_exact():
    original = np.full((60, 80, 3), 100, np.uint8)
    region = dict(id='fixed', start_frame=0, end_frame=1, geometry={'box': [20, 20, 20, 10]},
                  fill={'mode': 'fixed', 'color_bgr': [20, 30, 40]})
    pixels = np.zeros((10, 20, 4), np.uint8)
    pixels[:, :5] = [255, 0, 0, 128]
    overlay = dict(x=20, y=20, pixels=pixels, start_frame=0, end_frame=1, sha256='trusted')
    output, _ = paint_frame(original, 0, [region], [overlay], SurfaceFiller())
    expected = original.copy()
    expected[20:30, 20:40] = [20, 30, 40]
    alpha = 128/255
    expected[20:30, 20:25] = np.rint(np.array([0, 0, 255])*alpha+np.array([20, 30, 40])*(1-alpha)).astype(np.uint8)
    assert np.array_equal(output, expected)
