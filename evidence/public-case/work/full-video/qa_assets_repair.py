# coding:utf-8
from pathlib import Path
import cv2,json,re,tempfile,math
import qa_shell_continuation as s
P=Path(__file__).parent
HEAD=re.compile(r'(?:https?\s*[:：]\s*[/／]{2})?assets\s*[-−]\s*persist\s*\.\s*lovart\s*\.\s*ai\s*[/／]',re.I)
END=re.compile(r'\.\s*p\s*n\s*g(?=$|\s|[\'\"])',re.I)
TAIL=re.compile(r'[A-Za-z0-9._~%+/-]{8,}')
def geometry(row,start,end):
 parts=[]
 for begin,stop,ob in row['pieces']:
  a=max(0,start-begin);b=min(end-begin,stop-begin)
  if b<=a:continue
  chars=[c['box']for c in ob.get('chars',[])if c['start']<b and c['end']>a]
  if chars:parts+=chars
  else:
   x,y,w,h=ob['box'];parts.append([x+w*a/max(1,stop-begin),y,w*(b-a)/max(1,stop-begin),h])
 if not parts:return
 x=min(b[0]for b in parts);y=min(b[1]for b in parts);xx=max(b[0]+b[2]for b in parts);yy=max(b[1]+b[3]for b in parts)
 return[x,y,xx-x,yy-y]
def find(rows,roi):
 found=[];prev=None
 for row in rows:
  text=row['text'];starts=[m.start()for m in HEAD.finditer(text)]
  continuation=False
  if prev and prev['active'] and row['left']<.13 and TAIL.match(text):
   gap=row['center_y']-prev['row']['center_y'];mh=max(row['height'],prev['row']['height'])
   continuation=.45*mh<gap<1.8*mh
  if continuation:starts=[0]+starts
  active=False
  for start in sorted(set(starts)):
   endmatch=END.search(text,start);nexthead=next((v for v in starts if v>start),len(text));end=min(endmatch.end()if endmatch else len(text),nexthead)
   b=geometry(row,start,end)
   if b is None:continue
   pixels=[b[0]*roi.shape[1],b[1]*roi.shape[0],b[2]*roi.shape[1],b[3]*roi.shape[0]]
   if pixels[3]>115 or pixels[2]<20:continue
   x,y,w,h=pixels;pad=4;x0=max(0,math.floor(x)-pad);y0=max(0,math.floor(y)-pad);x1=min(roi.shape[1],math.ceil(x+w)+pad);y1=min(roi.shape[0],math.ceil(y+h)+pad)
   found.append([x0+600,y0,x1-x0,y1-y0])
   active=(end==len(text)and not endmatch and row['right']>.985)
  prev={'active':active,'row':row}
 return found
cap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');frames={};cap.set(1,45600)
with tempfile.TemporaryDirectory(prefix='qa-assets-')as scratch:
 o=s.Vision(scratch)
 for n in range(45600,46153):
  ok,a=cap.read();assert ok
  found=find(s.group_rows(o.read(a[:,600:3840],maximum_width=3840)),a[:,600:3840])
  if found:frames[str(n)]=[{'box':b,'id':'QA5A001','kind':'url_continuation','box_method':'reviewed_asset_uri_word','origin':'review_roi_ocr','review_basis':'Manually confirmed resource argument block; exact public asset-host anchor or adjacent ASCII URI tail ending .png; no confidence gate; only same linked URI word'}for b in found]
  if n%30==0:print('asset review',n,'frames',len(frames),flush=True)
 o.close()
q={'frames':frames,'checked_window_frames':[45600,46153],'notes':['Source URI argument block only; native OCR text transient, anonymous URL fields. Source continues private resource URLs through .png filename suffix, excluded ordinary local files without anchored predecessor.']};(P/'qa_part05_assets.json').write_text(json.dumps(q,ensure_ascii=False,indent=2));print('complete',len(frames),'frames',sum(map(len,frames.values())),'boxes')
