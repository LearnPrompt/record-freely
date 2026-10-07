import cv2,json,tempfile,re,math
from pathlib import Path
import qa_shell_continuation as s
P=Path(__file__).parent;cap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');frames={}
HEAD=re.compile(r'lovart\s*\.\s*ai\s*[/／]\s*canvas',re.I)
END=re.compile(r'[A-Za-z0-9._~%+/?=&#: -]*')
with tempfile.TemporaryDirectory(prefix='qa-browser-')as t:
 o=s.Vision(t);cap.set(1,44340)
 for n in range(44340,44432):
  ok,a=cap.read();assert ok
  roi=a[:190]
  for ob in o.read(roi,maximum_width=3840):
   m=HEAD.search(ob['text'])
   if not m:continue
   # Address bar observed as a single ASCII URI word. Do not log/persist text.
   end=m.end()+END.match(ob['text'][m.end():]).end();cs=[c['box']for c in ob.get('chars',[])if c['start']<end and c['end']>m.start()]
   if cs:x=min(b[0]for b in cs);y=min(b[1]for b in cs);xx=max(b[0]+b[2]for b in cs);yy=max(b[1]+b[3]for b in cs);w=xx-x;h=yy-y
   else:x,y,w,h=ob['box']
   x*=3840;w*=3840;y*=190;h*=190
   if h>60:continue
   x0=max(0,math.floor(x)-4);y0=max(0,math.floor(y)-4);xx=min(3840,math.ceil(x+w)+4);yy=min(2160,math.ceil(y+h)+4)
   frames.setdefault(str(n),[]).append({'box':[x0,y0,xx-x0,yy-y0],'id':'QA4B001','kind':'url','box_method':'reviewed_address_word','origin':'review_roi_ocr','review_basis':'Manually confirmed browser project URL including private project query; exact public-host anchor, anonymous geometry, no confidence gate.'})
  if n%30==0:print('browser',n,'found',len(frames),flush=True)
 o.close()
json.dump({'frames':frames,'remove_ids':['U020','U036','U037'],'checked_window_frames':[44340,44432]},open(P/'qa_part04_browser.json','w'),indent=2);print('done',len(frames))
