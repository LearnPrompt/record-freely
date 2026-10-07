import importlib.util
from pathlib import Path
import sys
import cv2
import numpy as np
import pytest

MODULE = Path('/Users/carl/.codex/skills/video-link-redactor/scripts/redact_video.py')
spec = importlib.util.spec_from_file_location('review_redactor', MODULE)
r = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = r
spec.loader.exec_module(r)

@pytest.mark.parametrize('text', ['video.mp4','screen.png','module.py','a@example.com','ordinary words','hello@foo.com'])
def test_common_non_url_cases(text):
    assert r.url_spans(text) == []

@pytest.mark.parametrize('text', ['https://example.com/a','www.example.com','example.ai/a','示例 example.com，继续'])
def test_common_url_cases(text):
    assert r.url_spans(text)

def test_missing_character_box_falls_back_to_complete_line():
    # URL is 11 characters, but Vision can return nil bbox for a character.
    observation = {'text':'example.com', 'box':[0.1,0.1,0.55,0.1],
                   'chars':[{'start':i,'end':i+1,'box':[0.1+i*0.05,0.1,0.05,0.1]} for i in range(10)]}
    result = r.detection_boxes([observation],1000,1000,0)
    assert result[0][:2] == [100,100]
    assert result[0][0] + result[0][2] >= 650  # final URL character remains masked

def patch():
    gray=np.full((40,230),240,np.uint8)
    cv2.putText(gray,'example.com',(5,27),cv2.FONT_HERSHEY_SIMPLEX,.8,20,2,cv2.LINE_AA)
    return gray

def frame_at(x=100,y=120,scale=1):
    p=patch()
    if scale != 1: p=cv2.resize(p,None,fx=scale,fy=scale)
    f=np.full((400,700),240,np.uint8)
    f[y:y+p.shape[0],x:x+p.shape[1]]=p
    return f,[x,y,p.shape[1],p.shape[0]]

def test_tracking_normal_motion():
    first,box=frame_at()
    second,newbox=frame_at(130,135)
    moved=r.move_track(r.make_track(first,box),second)
    assert moved is not None
    assert moved.box == newbox

def test_tracking_disappearance():
    first,box=frame_at()
    assert r.move_track(r.make_track(first,box),np.full_like(first,240)) is None

def test_tracking_large_motion_misses():
    first,box=frame_at()
    second,_=frame_at(250,120)
    assert r.move_track(r.make_track(first,box),second) is None

def test_tracking_cumulative_zoom_tracks_updated_template():
    first,box=frame_at()
    track=r.make_track(first,box)
    moved=r.move_track(track,frame_at(scale=1.06)[0])
    assert moved is not None
    zoomed=r.move_track(moved,frame_at(scale=1.12)[0])
    assert zoomed is not None
    assert zoomed.box[2] > moved.box[2]

def test_cut_with_persistent_chrome_detected():
    first,box=frame_at()
    # A quarter of the content panel changes while the old patch remains.
    # Global mean remains below the old cut threshold of 38.
    second=first.copy()
    second[20:250,350:650]=100
    assert np.mean(cv2.absdiff(first,second)) < 38
    assert r.scene_changed(first,second)
    assert r.move_track(r.make_track(first,box),second) is not None

def test_cover_source_unchanged_and_mask_bounds():
    frame=np.zeros((10,20,3),np.uint8)
    original=frame.copy()
    masked=r.cover(frame,[[5,2,4,3]],'solid')
    assert np.array_equal(frame,original)
    assert np.all(masked[2:5,5:9]==112)
    assert not np.any(masked[:2])

def test_clamp_boundaries():
    assert r.clamp([-5,-4,10,10],100,100)==[0,0,5,6]
    assert r.clamp([99,99,10,10],100,100)==[99,99,1,1]
    assert r.clamp([150,150,10,10],100,100)[2:]==[0,0]

@pytest.mark.parametrize('flag', ['--duration','--start','--hold-seconds'])
@pytest.mark.parametrize('value', ['nan','inf','-inf'])
def test_nonfinite_arguments_rejected(monkeypatch,flag,value):
    monkeypatch.setattr(sys,'argv',['redact_video.py','input.mp4','--output-dir','new',flag+'='+value])
    with pytest.raises(SystemExit):
        r.parse_args()

class FakeOCR:
    def __init__(self,scratch): pass
    def read(self,frame): return []
    def close(self): pass

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

@pytest.mark.parametrize('text', ['user@sub.example.com','first.last@example.com','user@foo.co.uk'])
def test_email_spans_excluded(text):
    assert r.url_spans(text)==[]

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
