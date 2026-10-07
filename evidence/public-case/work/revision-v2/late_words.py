import cv2,json,subprocess,sys,time,math
from pathlib import Path
sys.path.insert(0,str(Path('work/full-video').resolve()))
from stream_capture import StreamCapture
D=Path('work/revision-v2');SRC='/Users/carl/Downloads/带封面.mp4'
w=subprocess.Popen([str(D/'late_word_vision')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
a,b=1929*30,1973*30+1;cap=StreamCapture(SRC,a/30,b-a);records={};started=time.time()
for f in range(a,b):
 ok,im=cap.read()
 if not ok:raise RuntimeError(f)
 cv2.imwrite(str(D/'late_words_ocr.png'),cv2.resize(im,(2560,1440)))
 w.stdin.write(json.dumps({'path':str((D/'late_words_ocr.png').resolve())})+'\n');w.stdin.flush();obs=json.loads(w.stdout.readline())['observations'];out=[]
 for o in obs:
  for m in o['matches']:
   if not m['target'].startswith('word_'):continue
   x,y,bw,h=m['box'];box=[max(0,math.floor(x*3840)-6),max(0,math.floor(y*2160)-6),math.ceil(bw*3840)+12,math.ceil(h*2160)+12]
   out.append({'target':m['target'],'box':box,'confidence':o['confidence']})
 if out:records[str(f)]=out
 if f%30==0:
  (D/'late_word_detections.json').write_text(json.dumps(records));print(f,len(records),round(time.time()-started),flush=True)
cap.release();w.stdin.close();w.wait();(D/'late_word_detections.json').write_text(json.dumps(records));print('DONE',len(records),flush=True)
