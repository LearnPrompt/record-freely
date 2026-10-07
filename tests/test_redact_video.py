"""Regression tests for visual URL redaction; synthetic video QA is separate."""
import sys

import cv2
import numpy as np
import pytest

import redact_video as r


@pytest.mark.parametrize("text", [
    "https://example.com/a", "www.example.com", "example.ai/a", "go.example.org",
    "示例 example.com，继续", "example . com/private", "https://192.168.1.1/path",
    "skills.sh/tools", "example.zip/path", "example.com (官网)", "example.com(官网)",
])
def test_url_detection(text):
    assert r.url_spans(text)


@pytest.mark.parametrize("text", [
    "video.mp4", "screen.png", "module.py", "v1.2.3", "ordinary words",
    "A hard cut. No links on this screen.", "Read this. Next sentence.",
    "user@sub.example.com", "first.last@example.com", "user@foo.co.uk",
    "glob.glob", "json.load(open(path))", "feeds/follow.example.opml", "2.skillskill",
])
def test_non_urls(text):
    assert r.url_spans(text) == []


def test_url_span_excludes_adjacent_normal_text():
    text = "继续 https://example.com/a 观看"
    assert [text[a:b] for a, b in r.url_spans(text)] == ["https://example.com/a"]


@pytest.mark.parametrize("text, expected", [
    ("访问example.com", "example.com"),
    ("网址https://example.com", "https://example.com"),
])
def test_chinese_text_can_touch_url(text, expected):
    assert [text[a:b] for a, b in r.url_spans(text)] == [expected]


def test_missing_or_invalid_character_boxes_use_containing_line():
    observation = {"text": "example.com", "box": [.1, .1, .55, .1],
                   "chars": [{"start": i, "end": i + 1, "box": [.1 + i * .05, .1, .05, .1]}
                             for i in range(10)]}
    assert r.detection_boxes([observation], 1000, 1000, 0) == [[100, 100, 550, 100]]
    observation["chars"].append({"start": 10, "end": 11, "box": [0, 0, 0, 0]})
    assert r.detection_boxes([observation], 1000, 1000, 0) == [[100, 100, 550, 100]]


def test_low_confidence_bare_domain_is_not_masked_but_explicit_url_is():
    line = {"text": "example.com", "box": [.1, .1, .5, .1], "confidence": .3}
    assert not r.detection_boxes([line], 1000, 1000, 4)
    line["text"] = "https://example.com"
    assert r.detection_boxes([line], 1000, 1000, 4)


def text_frame(x=100, y=120, scale=1):
    patch = np.full((40, 230), 240, np.uint8)
    cv2.putText(patch, "example.com", (5, 27), cv2.FONT_HERSHEY_SIMPLEX, .8, 20, 2, cv2.LINE_AA)
    patch = cv2.resize(patch, None, fx=scale, fy=scale)
    frame = np.full((400, 700), 240, np.uint8)
    frame[y:y + patch.shape[0], x:x + patch.shape[1]] = patch
    return frame, [x, y, patch.shape[1], patch.shape[0]]


def test_tracking_movement_disappearance_and_progressive_zoom():
    first, box = text_frame()
    second, new_box = text_frame(130, 135)
    track = r.make_track(first, box)
    assert r.move_track(track, second).box == new_box
    assert r.move_track(track, np.full_like(first, 240)) is None
    zoomed = r.move_track(track, text_frame(scale=1.06)[0])
    assert zoomed is not None
    assert r.move_track(zoomed, text_frame(scale=1.12)[0]) is not None


def test_mask_only_changes_selected_region_and_preserves_source():
    frame = np.zeros((10, 20, 3), np.uint8)
    masked = r.cover(frame, [[5, 2, 4, 3]], "solid")
    assert not np.any(frame)
    assert np.all(masked[2:5, 5:9] == 112)
    masked[2:5, 5:9] = 0
    assert not np.any(masked)


def test_scene_cut_and_normal_motion():
    before = np.full((400, 700), 240, np.uint8)
    after = before.copy()
    after[120:360, 80:650] = 210
    assert r.scene_changed(before, after)
    frame, _ = text_frame()
    moved, _ = text_frame(105, 125)
    assert not r.scene_changed(frame, moved)


@pytest.mark.parametrize("flag", ["--start", "--duration", "--hold-seconds"])
@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_nonfinite_times_rejected(monkeypatch, flag, value):
    monkeypatch.setattr(sys, "argv", ["redact_video.py", "source.mp4", "--output-dir", "new", f"{flag}={value}"])
    with pytest.raises(SystemExit):
        r.parse_args()


class FakeOCR:
    def __init__(self,scratch): pass
    def read(self,frame): return []
    def close(self): pass

@pytest.mark.skipif(sys.platform != "darwin" or not __import__("shutil").which("ffmpeg"), reason="macOS FFmpeg integration test")
def test_functional_export_clips_keeps_audio_and_source(tmp_path, monkeypatch):
    import hashlib
    import json
    import subprocess
    source=tmp_path/'source.mkv'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=96x64:rate=30:duration=2',
                    '-itsoffset','0.5','-f','lavfi','-i','sine=frequency=800:duration=1.5',
                    '-map','0:v','-map','1:a','-c:v','ffv1','-c:a','pcm_s16le',str(source)],check=True)
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    output=tmp_path/'out'
    monkeypatch.setattr(r,'VisionOCR',FakeOCR)
    monkeypatch.setattr(sys,'argv',['redact_video.py',str(source),'--output-dir',str(output),'--start','.4','--duration','.8'])
    r.main()
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    report=json.loads((output/'report.json').read_text())
    assert report['status']=='complete'
    assert report['processed_frames']==24
    assert report['audio_streams']==1
    video=r.probe(output/'redacted.mp4')
    vs=next(s for s in video['streams'] if s['codec_type']=='video')
    aus=next(s for s in video['streams'] if s['codec_type']=='audio')
    assert abs(float(vs['duration'])-.8)<.034
    # Source sound starts at .5; .4 preview should retain .1 offset.
    pcm=subprocess.check_output(['ffmpeg','-v','error','-i',str(output/'redacted.mp4'),'-map','0:a:0','-f','f32le','-ac','1','-ar','48000','pipe:1'])
    signal=np.frombuffer(pcm,np.float32)
    active=np.flatnonzero(np.abs(signal)>.01)
    audible_start=float(aus['start_time']) + active[0]/48000
    assert abs(audible_start-.1)<.025
    assert (output/'preview.jpg').exists()

def test_input_output_directory_reuse_rejected_without_changes(tmp_path,monkeypatch):
    source=tmp_path/'source.mp4'
    source.write_bytes(b'unchanged input')
    output=tmp_path/'existing'
    output.mkdir()
    marker=output/'keep.txt'
    marker.write_text('existing work')
    monkeypatch.setattr(sys,'argv',['redact_video.py',str(source),'--output-dir',str(output)])
    with pytest.raises(RuntimeError,match='already exists'):
        r.main()
    assert source.read_bytes()==b'unchanged input'
    assert marker.read_text()=='existing work'
    assert list(output.iterdir())==[marker]

@pytest.mark.skipif(sys.platform != "darwin" or not __import__("shutil").which("ffmpeg"), reason="macOS FFmpeg integration test")
def test_odd_dimensions_no_audio_export(tmp_path,monkeypatch):
    import subprocess
    source=tmp_path/'odd.mkv'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc=size=95x63:rate=25:duration=0.4',
                    '-c:v','ffv1','-pix_fmt','bgr0',str(source)],check=True)
    output=tmp_path/'out'
    monkeypatch.setattr(r,'VisionOCR',FakeOCR)
    monkeypatch.setattr(sys,'argv',['redact_video.py',str(source),'--output-dir',str(output)])
    r.main()
    info=r.probe(output/'redacted.mp4')
    video=next(s for s in info['streams'] if s['codec_type']=='video')
    assert (video['width'],video['height']) == (96,64)
    assert video['pix_fmt']=='yuv420p'
    assert int(video['nb_frames'])==10
    assert not any(s['codec_type']=='audio' for s in info['streams'])

@pytest.mark.skipif(sys.platform != "darwin" or not __import__("shutil").which("ffmpeg"), reason="macOS FFmpeg integration test")
def test_source_audio_outside_selected_window_is_silent_export(tmp_path,monkeypatch):
    import subprocess
    source=tmp_path/'late-audio.mkv'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=96x64:rate=30:duration=2',
                    '-itsoffset','0.5','-f','lavfi','-i','sine=frequency=800:duration=1.5',
                    '-map','0:v','-map','1:a','-c:v','ffv1','-c:a','pcm_s16le',str(source)],check=True)
    output=tmp_path/'out'
    monkeypatch.setattr(r,'VisionOCR',FakeOCR)
    monkeypatch.setattr(sys,'argv',['redact_video.py',str(source),'--output-dir',str(output),'--duration','.2'])
    r.main()
    info=r.probe(output/'redacted.mp4')
    assert sum(s['codec_type']=='audio' for s in info['streams'])==1
    pcm=subprocess.check_output(['ffmpeg','-v','error','-i',str(output/'redacted.mp4'),'-map','0:a:0','-f','f32le','-ac','1','-ar','48000','pipe:1'])
    assert np.max(np.abs(np.frombuffer(pcm,np.float32)))==0
