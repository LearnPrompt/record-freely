# coding: utf-8
"""Reviewed calendar URL rows: local source evidence, anonymous coordinates only."""
from pathlib import Path
import argparse,json
import cv2,numpy as np
BASE=Path('/Users/carl/Documents/Codex/2026-10-06/1-openai-gpt-6-1-ultra/work/full-video')
SOURCE='/Users/carl/Downloads/带封面.mp4'
SEED=BASE/'qa_source_36000.jpg'
# Public URL prefix only; private path excluded from the tracking template.
PUBLIC_PREFIX_ROI=(843,1126,350,39)

def templates():
 im=cv2.imread(str(SEED));x,y,w,h=PUBLIC_PREFIX_ROI;gray=cv2.cvtColor(cv2.resize(im,(1920,1080)),cv2.COLOR_BGR2GRAY);tpl=gray[y//2:(y+h+1)//2,x//2:(x+w+1)//2]
 return [(s,cv2.resize(tpl,(round(tpl.shape[1]*s),round(tpl.shape[0]*s))))for s in sorted(set(np.arange(.16,1.61,.02).round(3))|{1.0})]

def locate(frame,tmpls):
 gray=cv2.cvtColor(cv2.resize(frame,(frame.shape[1]//2,frame.shape[0]//2)),cv2.COLOR_BGR2GRAY);best=None
 for s,t in tmpls:
  if t.shape[0]<4:continue
  res=cv2.matchTemplate(gray,t,cv2.TM_CCOEFF_NORMED);_,score,_,p=cv2.minMaxLoc(res)
  if best is None or score>best['score']:best={'score':float(score),'anchor':[p[0]*2,p[1]*2-round(6*s)],'scale':float(s),'h':round(57*s)}
 return best

def blue_mask(im):
 return cv2.inRange(cv2.cvtColor(im,cv2.COLOR_BGR2HSV),np.array([85,20,25]),np.array([125,255,235]))

def split_runs(active):
 edges=np.diff(np.r_[False,active,False].astype(np.int8));return list(zip(np.flatnonzero(edges==1),np.flatnonzero(edges==-1)))

def blue_rows(frame,anchor):
 x,y=anchor['anchor'];h=anchor['h'];mask=blue_mask(frame)
 # Match establishes public URL head; require two nearby blue rows left-aligned.
 x0=max(0,x-round(.15*h));x1=min(frame.shape[1],x+round(32*h));y0=max(0,y-round(.35*h));y1=min(frame.shape[0],y+round(3.5*h))
 roi=mask[y0:y1,x0:x1];rows=split_runs(np.count_nonzero(roi,axis=1)>max(6,round(h*.15)))
 merged=[]
 for a,b in rows:
  if merged and a-merged[-1][1]<max(3,round(h*.15)):merged[-1][1]=b
  else:merged.append([a,b])
 boxes=[]
 for a,b in merged:
  ys,yb=y0+a,y0+b
  if yb-ys<max(5,.15*h):continue
  active=(np.count_nonzero(roi[a:b],axis=0)>1).astype(np.uint8)
  active=cv2.morphologyEx(active.reshape(1,-1),cv2.MORPH_CLOSE,np.ones((1,max(5,round(h*.6))),np.uint8)).ravel()>0
  groups=[(lo,hi) for lo,hi in split_runs(active) if hi-lo>.6*h and abs(lo+x0-x)<.6*h]
  if not groups:continue
  lo,hi=min(groups,key=lambda ab:abs(ab[0]+x0-x));cols=np.flatnonzero(np.any(roi[a:b,lo:hi]>0,axis=0));lo,hi=int(lo+cols[0]+x0),int(lo+cols[-1]+1+x0)
  if abs(lo-x)>h*.6:continue
  boxes.append([lo,ys,hi-lo,yb-ys])
 if not boxes:return []
 head=min(boxes,key=lambda b:abs(b[1]-y))
 if abs(head[1]-y)>h*.6 or head[2]<6*h:return []
 tail=[]
 for b in boxes:
  gap=b[1]-(head[1]+head[3])
  if 0<gap<1.3*h and abs(b[0]-head[0])<.45*h and .7*h<b[2]<head[2]*.65:
   # Confirm ASCII fragment using reviewed line width and native dark glyphs.
   lx=max(0,head[0]-round(.1*h));rx=min(frame.shape[1],head[0]+round(254*anchor['scale']+.25*h));ly=max(0,b[1]-round(.2*h));ry=min(frame.shape[0],b[1]+b[3]+round(.2*h))
   gray=cv2.cvtColor(frame[ly:ry,lx:rx],cv2.COLOR_BGR2GRAY);gy,gx=np.where(gray<190)
   if len(gx):b=[int(lx+gx.min()),int(ly+gy.min()),int(gx.max()-gx.min()+1),int(gy.max()-gy.min()+1)]
   tail.append(b)
 # Require the reviewed short continuation, not an unrelated later blue row.
 if not tail:return []
 return [head]+tail[:1]

def scan():
 ts=templates();cap=cv2.VideoCapture(SOURCE);data=[]
 for sec in range(1170,1231):
  cap.set(cv2.CAP_PROP_POS_FRAMES,sec*30);ok,im=cap.read();assert ok
  a=locate(im,ts);boxes=blue_rows(im,a) if a['score']>.72 else []
  data.append({'frame':sec*30,'time':sec,'match_score':round(a['score'],4),'scale':round(a['scale'],2),'anchor':a['anchor'],'boxes':boxes})
 cap.release();(BASE/'qa_calendar_scan.json').write_text(json.dumps(data,indent=2))
 print(json.dumps([d for d in data if d['match_score']>.72],indent=2))
def reviewed_fade_boxes(im,a):
 # Source-verified fade frames: dark ASCII glyph extents inside reviewed word geometry.
 x,y=a['anchor'];s=a['scale'];result=[]
 for dy,w,h in [(3,1295,51),(96,254,40)]:
  x0=max(0,int(x-6*s));y0=max(0,int(y+(dy-3)*s));x1=min(im.shape[1],int(x+(w+10)*s));y1=min(im.shape[0],int(y+(dy+h+4)*s))
  gray=cv2.cvtColor(im[y0:y1,x0:x1],cv2.COLOR_BGR2GRAY);gy,gx=np.where(gray<235)
  if len(gx)<30:return []
  result.append([int(x0+gx.min()),int(y0+gy.min()),int(gx.max()-gx.min()+1),int(gy.max()-gy.min()+1)])
 return result

def batch():
 ts=templates();cap=cv2.VideoCapture(SOURCE);start,end=35880,36045;cap.set(cv2.CAP_PROP_POS_FRAMES,start);frames={};evidence=[]
 for n in range(start,end):
  ok,im=cap.read();assert ok,n
  # Source scout established this calendar block's screen area; track each real frame.
  a=locate(im[700:2160,600:1800],ts);a['anchor']=[a['anchor'][0]+600,a['anchor'][1]+700]
  boxes=blue_rows(im,a) if a['score']>.72 else []
  if 35906<=n<=35909 and a['score']>.72:boxes=reviewed_fade_boxes(im,a)
  if boxes:
   regs=[]
   for i,b in enumerate(boxes):
    x,y,w,h=map(int,b);pad=4;box=[max(0,x-pad),max(0,y-pad),min(im.shape[1],x+w+pad)-max(0,x-pad),min(im.shape[0],y+h+pad)-max(0,y-pad)]
    regs.append({'box':box,'id':'C001','kind':'url' if i==0 else 'continuation','box_method':'reviewed_fade_glyph'if 35906<=n<=35909 else'reviewed_color_glyph','origin':'review_color_continuation','review_match_score':round(a['score'],4),'role':'head' if i==0 else 'tail','preserve_orange_caption':False})
   frames[str(n)]=regs
  evidence.append({'frame':n,'prefix_score':round(a['score'],4),'regions':len(boxes),'scale':round(a['scale'],3)})
 cap.release();data={'frames':frames,'checked_windows':[{'start_frame':start,'end_frame_exclusive':end,'start_seconds':start/30,'end_seconds_exclusive':end/30,'method':'Per-frame reviewed public-prefix matching plus adjacent color/glyph projection'}],'notes':['Source-only repair candidates, actual-output verification pending.','Two-row ASCII continuation is visually confirmed; private URL text is neither printed nor persisted.','Require real current-frame public URL prefix, left alignment, neighboring baseline and reviewed fragment geometry; no blanket blue-text masking.','Current-frame projected glyph bounds plus 4 pixels; positions and sizes follow zoom/scroll.','19:30 and 19:45 terminal URLs are white, excluded from this blue-calendar repair.','Frames 35906–35909 calendar fades weaken blue saturation; current-source prefix match plus native reviewed glyph extent restores both rows without blind interpolation.'],'evidence':evidence}
 (BASE/'qa_calendar_boxes.json').write_text(json.dumps(data,indent=2))
 print('checked',len(evidence),'repair_frames',len(frames),'first_last',([min(map(int,frames)),max(map(int,frames))]if frames else []))
 for n in [35910,35940,35970,36000]:print(n,frames.get(str(n),[]))

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--scan',action='store_true');args=ap.parse_args()
 if args.scan:scan()
 else:batch()
