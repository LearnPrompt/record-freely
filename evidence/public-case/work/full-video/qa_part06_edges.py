from pathlib import Path
import cv2,json,tempfile,re,math
import qa_shell_continuation as s
P=Path(__file__).parent
cap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');frames={}
with tempfile.TemporaryDirectory(prefix='qa-six-')as t:
 o=s.Vision(t)
 for n in range(58204,58210):
  cap.set(1,n);ok,a=cap.read();assert ok;roi=a[:250]
  for ob in o.read(roi,maximum_width=3840):
   v=ob['text']
   if 'feishu' not in v.lower() or 'docx' not in v.lower():continue
   x,y,w,h=ob['box'];x*=3840;y*=250;w*=3840;h*=250
   if h>95:continue
   x0=max(0,math.floor(x)-4);y0=max(0,math.floor(y)-4);xx=min(3840,math.ceil(x+w)+4);yy=min(2160,math.ceil(y+h)+4)
   frames.setdefault(str(n),[]).append({'box':[x0,y0,xx-x0,yy-y0],'id':'QA6F001','kind':'url','box_method':'reviewed_uri_word','origin':'review_roi_ocr','review_basis':'Source checked clipped visible Feishu URI at scrolling top boundary; public-host anchor, anonymous geometry.'})
 o.close()
q=json.load(open(P/'qa_part06_false_ids.json'));q['frames']=frames;q['checked_window_frames']=[58204,58210];json.dump(q,open(P/'qa_part06_edges.json','w'),indent=2);print(frames)
