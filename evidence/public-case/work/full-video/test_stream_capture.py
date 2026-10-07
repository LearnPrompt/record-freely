import io,sys
from pathlib import Path
import pytest,cv2
sys.path.insert(0,str(Path(__file__).parent))
import stream_capture as s
class Fake:
 def __init__(self,data):self.stdout=io.BytesIO(data);self.closed=False
 def wait(self,timeout=None):return 0
 def terminate(self):self.closed=True

def test_bounded_pipe_counts_exact_rgb_frames_and_preserves_bytes(monkeypatch):
 p=Fake(bytes(range(12)));commands=[]
 def popen(command,**kwargs):commands.append(command);return p
 monkeypatch.setattr(s.subprocess,'Popen',popen)
 cap=s.StreamCapture('source.mp4',300,2,width=2,height=1)
 a,first=cap.read();b,second=cap.read();assert a and b
 assert first.tolist()==[[[0,1,2],[3,4,5]]]
 assert second.tolist()==[[[6,7,8],[9,10,11]]]
 assert cap.get(cv2.CAP_PROP_FRAME_COUNT)==2 and cap.get(cv2.CAP_PROP_POS_FRAMES)==2
 assert cap.read()==(False,None)
 assert commands[0][commands[0].index('-ss')+1]=='300'
 cap.release();cap.release();assert not cap.isOpened()

def test_incomplete_rgb_frame_cannot_silently_pass(monkeypatch):
 monkeypatch.setattr(s.subprocess,'Popen',lambda *args,**kwargs:Fake(b'12345'))
 cap=s.StreamCapture('source.mp4',0,1,width=2,height=1)
 with pytest.raises(RuntimeError,match='Partial RGB'):cap.read()
 cap.release()
