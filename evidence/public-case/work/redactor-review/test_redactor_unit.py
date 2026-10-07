import importlib.util
from pathlib import Path
import os
import sys
import cv2
import numpy as np
import pytest

# Place under scripts/tests/, or set LINK_REDACTOR_SCRIPT when running elsewhere.
MODULE = Path(os.environ.get('LINK_REDACTOR_SCRIPT', Path(__file__).resolve().parents[1] / 'redact_video.py'))
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


@pytest.mark.parametrize('text', ['user@sub.example.com','first.last@example.com','user@foo.co.uk'])
def test_email_spans_excluded(text):
    assert r.url_spans(text)==[]

@pytest.mark.parametrize('text', ['Hello. World', 'Release. Notes', 'Sentence. Another sentence'])
def test_sentence_period_not_a_domain(text):
    assert r.url_spans(text)==[]

@pytest.mark.parametrize('box', [[.1,.1,0,.1], [.1,.1,10,.1], [.1,.1,float('nan'),.1]])
def test_invalid_character_boxes_use_line(box):
    observation={'text':'example.com','box':[.1,.1,.55,.1],
                 'chars':[{'start':0,'end':11,'box':box}]}
    result=r.detection_boxes([observation],1000,1000,0)
    assert result[0][0]==100
    assert result[0][0]+result[0][2]>=650
