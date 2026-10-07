import cv2,json,subprocess,sys,time,math
from pathlib import Path
sys.path.insert(0,str(Path('work/full-video').resolve()))
from stream_capture import StreamCapture
from redact_full_engine import union
import unicodedata
D=Path('work/revision-v2');SRC='/Users/carl/Downloads/带封面.mp4'
w=subprocess.Popen([str(D/'late_vision')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
def detect(im):
 im=cv2.resize(im,(1920,1080));cv2.imwrite(str(D/'late_ocr.png'),im)
 w.stdin.write(json.dumps({'path':str((D/'late_ocr.png').resolve())})+'\n');w.stdin.flush();r=json.loads(w.stdout.readline());return r['observations']
def boxes(obs,keys):
 out=[]
 for o in obs:
  for m in o['matches']:
   if m['target'] not in keys:continue
   start,end=m['start'],m['end'];allchars=o['chars'];parts=[];seen=set()
   for ch in allchars:
    if ch['start']>=end or ch['end']<=start:continue
    sig=tuple(round(v,6) for v in ch['box'])
    if sig in seen:continue
    seen.add(sig);same=[d for d in allchars if tuple(round(v,6) for v in d['box'])==sig]
    a,z=min(d['start'] for d in same),max(d['end'] for d in same);x,y,b,h=ch['box']
    weights=[2 if unicodedata.east_asian_width(c) in ('W','F') else 1 for c in o['text'][a:z]]
    left=sum(weights[:max(0,start-a)])/sum(weights);wide=sum(weights[max(0,start-a):min(z,end)-a])/sum(weights)
    parts.append([x+b*left,y,b*wide,h])
   x,y,b,h=union(parts) if parts else m['box'];out.append({'target':m['target'],'box':[max(0,math.floor(x*3840)-4),max(0,math.floor(y*2160)-4),math.ceil(b*3840)+8,math.ceil(h*2160)+8],'confidence':o['confidence']})
 return out
c=cv2.VideoCapture(SRC)
windows=json.loads((D/'late_windows.json').read_text())
records={};start=time.time()
for a,b,keys in windows:
 cap=StreamCapture(SRC,a/30,b-a)
 for f in range(a,b):
  ok,im=cap.read()
  if not ok:raise RuntimeError(f)
  out=boxes(detect(im),keys)
  if out:records[str(f)]=out
  if f%30==0:
   (D/'late_detections.json').write_text(json.dumps(records))
   print('scan',f,'records',len(records),'elapsed',round(time.time()-start),flush=True)
 cap.release()
w.stdin.close();w.wait();(D/'late_detections.json').write_text(json.dumps(records));print('DONE',len(records),flush=True)
