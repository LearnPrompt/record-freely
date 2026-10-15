"""Actual muxed media color tags and pixel conversion, not just argv assertions."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from encoding import add_encoding_arguments, video_encoding_options, encoding_config, verify_encoding
import redact_video as r


def args(*values):
    parser = argparse.ArgumentParser()
    add_encoding_arguments(parser)
    return parser.parse_args(values)


@pytest.mark.parametrize('value', ['nan', 'inf', '-1', '52'])
def test_invalid_quality_rejected(value):
    with pytest.raises(SystemExit):
        args('--crf', value)


def test_legacy_default_and_explicit_quality_are_distinct():
    default = args()
    assert default.crf == 18 and default.preset == 'fast' and default.color_space is None
    assert '-colorspace' not in video_encoding_options(default)
    assert 'scale=' not in video_encoding_options(default)[-1]
    requested = args('--crf', '16', '--preset', 'medium', '--color-space', 'bt709')
    options = video_encoding_options(requested)
    assert options[options.index('-crf') + 1] == '16.0'
    assert options[options.index('-preset') + 1] == 'medium'
    assert 'out_color_matrix=bt709' in options[-1]
    assert encoding_config(requested)['video_encoding_generations'] == 1
    with pytest.raises(RuntimeError, match='color tags'):
        verify_encoding({}, requested)


HAS_FFMPEG = shutil.which('ffmpeg') and shutil.which('ffprobe')


@pytest.mark.skipif(not HAS_FFMPEG, reason='FFmpeg required')
def test_bt709_conversion_and_tags_survive_copy_mux(tmp_path):
    pixels = np.empty((48, 64, 3), np.uint8)
    pixels[:, :32] = (0, 0, 255)  # RGB red, Y limited BT.709 ~63 (BT.601 ~81).
    pixels[:, 32:] = (0, 255, 0)  # RGB green, Y limited BT.709 ~173.
    requested = args('--crf', '0', '--preset', 'medium', '--color-space', 'bt709')
    silent = tmp_path / 'silent.mp4'
    final = tmp_path / 'muxed.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', '64x48',
                    '-r', '30', '-i', 'pipe:0', '-an', *video_encoding_options(requested), str(silent)],
                   input=pixels.tobytes(), check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-i', str(silent), '-map', '0:v:0', '-c:v', 'copy',
                    '-map_metadata', '-1', '-movflags', '+faststart', str(final)], check=True)
    video = r.probe(final)['streams'][0]
    assert verify_encoding(video, requested)['explicit_color_tags_verified']
    assert video['width'] == 64 and video['height'] == 48
    decoded = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(final), '-frames:v', '1',
                              '-f', 'rawvideo', '-pix_fmt', 'yuv420p', 'pipe:1'], capture_output=True, check=True).stdout
    y = np.frombuffer(decoded[:48*64], np.uint8).reshape(48, 64)
    assert float(y[8:40, 8:24].mean()) == pytest.approx(63, abs=2)
    assert float(y[8:40, 40:56].mean()) == pytest.approx(173, abs=2)


@pytest.mark.skipif(not HAS_FFMPEG or sys.platform != 'darwin', reason='macOS render CLI integration')
def test_automatic_and_refine_cli_explicit_quality_color_from_original(tmp_path, monkeypatch):
    source = tmp_path / 'original.mkv'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=64x48:rate=30:duration=0.2',
                    '-c:v', 'ffv1', str(source)], check=True)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    class EmptyOCR:
        def __init__(self, scratch): pass
        def read(self, frame): return []
        def close(self): pass
    monkeypatch.setattr(r, 'VisionOCR', EmptyOCR)
    automatic = tmp_path / 'automatic'
    quality = ['--crf', '16', '--preset', 'medium', '--color-space', 'bt709']
    monkeypatch.setattr(sys, 'argv', ['redact_video.py', str(source), '--output-dir', str(automatic), *quality])
    r.main()
    refined = tmp_path / 'refined'
    script = Path(r.__file__).with_name('refine_video.py')
    subprocess.run([sys.executable, str(script), str(source), '--report', str(automatic / 'report.json'),
                    '--output-dir', str(refined), *quality], check=True)
    for output in (automatic, refined):
        report = json.loads((output / 'report.json').read_text())
        assert report['status'] == 'complete' and report['source_sha256'] == before
        assert report['encoding']['crf'] == 16 and report['encoding']['preset'] == 'medium'
        assert report['encoding']['video_encoding_generations'] == 1
        assert report['encoding_verification']['explicit_color_tags_verified']
        assert r.probe(output / 'redacted.mp4')['streams'][0]['nb_frames'] == '6'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_redaction_policy_is_explicit_and_parent_requires_privacy():
    default = r.parse_args(['source.mp4', '--output-dir', 'new'])
    assert default.path_policy == 'identity-prefix' and default.github_policy == 'full'
    explicit = r.parse_args(['source.mp4', '--output-dir', 'new', '--privacy', '--path-policy', 'parent', '--github-policy', 'host'])
    assert explicit.path_policy == 'parent' and explicit.github_policy == 'host'
    with pytest.raises(SystemExit):
        r.parse_args(['source.mp4', '--output-dir', 'new', '--path-policy', 'parent'])
