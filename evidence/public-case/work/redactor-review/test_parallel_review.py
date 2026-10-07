import importlib.util,sys,json,time,threading
from pathlib import Path
import numpy as np
import pytest
SPEC=importlib.util.spec_from_file_location('parallel_review_redactor',Path('/Users/carl/.codex/skills/video-link-redactor/scripts/redact_video.py'))
r=importlib.util.module_from_spec(SPEC);sys.modules[SPEC.name]=r;SPEC.loader.exec_module(r)

@pytest.mark.parametrize('workers',[1,2,3])
def test_parallel_ocr_worker_exclusive_and_frames_ordered(tmp_path,monkeypatch,workers,scenario="normal"):
    frame_count=17
    frames=[np.full((24,40,3),i,np.uint8) for i in range(frame_count)]
    calls=[];instances=[];lock=threading.Lock();outputs=[]
    class OCR:
        def __init__(self,scratch):
            self.scratch=scratch;self.active=False;self.closed=False;instances.append(self)
        def read(self,frame):
            with lock:
                assert not self.active, 'same OCR worker read called concurrently'
                assert not self.closed
                self.active=True
            value=int(frame[0,0,0])
            if scenario != 'normal' and value==0:
                with lock:self.active=False
                raise RuntimeError('OCR worker failed')
            time.sleep(.001*(3-value%3))
            with lock:
                calls.append((self.scratch,value));self.active=False
            return [{'value':value}]
        def close(self):
            assert not self.active
            assert not self.closed
            if scenario == "close_error" and self is instances[0]:
                raise BrokenPipeError("worker pipe closed")
            self.closed=True
    class Capture:
        def __init__(self,p):self.index=0
        def isOpened(self):return True
        def get(self,field):return {r.cv2.CAP_PROP_FRAME_WIDTH:40,r.cv2.CAP_PROP_FRAME_HEIGHT:24,r.cv2.CAP_PROP_FRAME_COUNT:frame_count}.get(field,0)
        def read(self):
            if self.index==frame_count:return False,None
            f=frames[self.index];self.index+=1;return True,f
        def release(self):pass
    class Pipe:
        def write(self,data):outputs.append(int(np.frombuffer(data,np.uint8)[0]))
        def close(self):pass
    class Encoder:
        def __init__(self,*a,**kw):self.stdin=Pipe();self.running=True
        def wait(self):self.running=False;return 0
        def poll(self):return None if self.running else 0
        def kill(self):self.running=False
    def probe(path):
        if path.name=='redacted.mp4':return {'streams':[{'codec_type':'video','nb_frames':str(frame_count),'duration':str(frame_count/30)}]}
        return {'streams':[{'index':0,'codec_type':'video','avg_frame_rate':'30/1'}]}
    def detection(obs,w,h,pad,details,identities):
        details.append({'id':str(obs[0]['value'])})
        return [[obs[0]['value'],2,1,1]]
    def run(command):
        Path(command[-1]).write_bytes(b'fake-output')
        return ''
    source=tmp_path/'source.mp4';source.write_bytes(b'original')
    output=tmp_path/'out'
    monkeypatch.setattr(r,'VisionOCR',OCR)
    monkeypatch.setattr(r.cv2,'VideoCapture',Capture)
    monkeypatch.setattr(r.subprocess,'Popen',Encoder)
    monkeypatch.setattr(r,'probe',probe)
    monkeypatch.setattr(r,'detection_boxes',detection)
    monkeypatch.setattr(r,'run',run)
    monkeypatch.setattr(r,'move_track',lambda *args:None)
    monkeypatch.setattr(sys,'argv',['redact_video.py',str(source),'--output-dir',str(output),'--ocr-workers',str(workers)])
    if scenario != 'normal':
        with pytest.raises(Exception):
            r.main()
        assert all(o.closed for o in instances[1:]), 'extra OCR workers leaked'
        assert (output/'report.json').exists(), 'failure report was not written'
        assert json.loads((output/'report.json').read_text())['status']=='failed'
        return
    r.main()
    report=json.loads((output/'report.json').read_text())
    assert outputs==list(range(frame_count))
    assert [f['frame'] for f in report['frames']]==list(range(frame_count))
    assert [f['regions'][0]['id'] for f in report['frames']]==list(map(str,range(frame_count)))
    assert sorted(value for _,value in calls)==list(range(frame_count))
    assert len(instances)==workers and all(o.closed for o in instances)
    assert len({o.scratch for o in instances})==workers

@pytest.mark.parametrize('text',['example.org (官网)','example.co.uk (官方网站)','skills.sh/tools','example.zip/path'])
def test_domain_false_negative_current_behavior(text):
    assert r.url_spans(text)==[]


def test_parallel_worker_read_error_closes_other_workers(tmp_path,monkeypatch):
    test_parallel_ocr_worker_exclusive_and_frames_ordered(tmp_path,monkeypatch,3,'ocr_error')

def test_worker_close_error_still_cleans_up_and_reports(tmp_path,monkeypatch):
    test_parallel_ocr_worker_exclusive_and_frames_ordered(tmp_path,monkeypatch,3,'close_error')
