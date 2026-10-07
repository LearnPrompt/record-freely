from pathlib import Path
import cv2,json,numpy as np
ROOT=Path(__file__).resolve().parents[2];W=ROOT/'work/real-video-audit';SRC='/Users/carl/Downloads/带封面.mp4'
cap=cv2.VideoCapture(SRC)
def get(n):
 cap.set(1,n);ok,im=cap.read();assert ok;return im

def white(im):
 b,g,r=cv2.split(im);return (((np.minimum(np.minimum(b,g),r)>115)&(np.maximum(np.maximum(b,g),r).astype(int)-np.minimum(np.minimum(b,g),r)<70))*255).astype(np.uint8)

def target_template(n,box):
 im=get(n);x,y,w,h=box;return white(im[y:y+h,x:x+w])
seeds=[('R001',target_template(2185,[770,1535,230,43]),745,55,range(2168,2259)),('R002',target_template(2185,[775,1580,225,42]),1008,54,range(2168,2259)),('R003',target_template(3579,[458,1234,220,47]),1377,59,range(3550,3590))]
frames={};proof=[]
for ident,template,fullw,fullh,window in seeds:
 for n in window:
  im=get(n);binary=white(im);search=cv2.resize(binary[90:2050,200:2400],(1100,980));best=(-1,None)
  scales=np.arange(.86,2.0,.045) if ident!='R003' else [.94,.97,1,1.03,1.06]
  for scale in scales:
   t=cv2.resize(template,None,fx=scale*.5,fy=scale*.5,interpolation=cv2.INTER_NEAREST)
   scores=cv2.matchTemplate(search,t,cv2.TM_CCOEFF_NORMED);_,score,_,pt=cv2.minMaxLoc(scores)
   if score>best[0]:best=(score,(pt,scale))
  score,(pt,s)=best
  if score<.52:continue
  x=pt[0]*2+200-5;y=pt[1]*2+90-5;box=[x,y,round(fullw*s+8),round(fullh*s+8)]
  # Prefixes are near-identical, so use the first result only for URL 1,
  # second row is anchored by its longer reviewed path and template.
  reg={'box':box,'id':ident,'kind':'https','box_method':'reviewed_template','origin':'review_template','tracking_score':round(score,4),'relative_scale':round(float(s),4),'preserve_orange_caption':True}
  frames.setdefault(str(n),[]).append(reg)
  if n in [2172,2182,2211,2212,2218,2221,3577,3578,3580]:proof.append((n,im.copy(),reg))
# Reviewed blue hyperlink row news 10. Color selection handles white captions
# obscuring OCR and the visible URL tail during transition.
for n in range(4710,4850):
 im=get(n);roi=im[1500:2040,750:2900];b,g,r=cv2.split(roi);sel=((b.astype(int)-r>15)&(b.astype(int)-g>3)&(b>70)).astype(np.uint8)
 rows=sel.sum(1);groups=[];on=False
 for y,v in enumerate(rows):
  if v>40 and not on:a=y;on=True
  if on and (v<=40 or y==len(rows)-1):
   z=y if v<=40 else y+1
   if z-a>8:groups.append((a,z,int(rows[a:z].sum())))
   on=False
 if not groups:continue
 a,z,_=max(groups,key=lambda q:q[2]);ys,xs=np.where(sel[max(0,a-5):min(540,z+5)]>0)
 if len(xs)<100:continue
 # Target line must stay near the known 1597 row (or initially 1899).
 yy=1500+a
 if not (1570<yy<1660 or n<4715 and 1850<yy<1980):continue
 x=int(xs.min())+750;end=int(xs.max())+750
 if end-x<900:continue
 box=[x-8,yy-8,end-x+17,z-a+17]
 frames.setdefault(str(n),[]).append({'box':box,'id':'R004','kind':'https','box_method':'reviewed_color_line','origin':'review_color_line'})
 if n in [4800,4847,4848,4849]:proof.append((n,im.copy(),frames[str(n)][-1]))
cap.release()
(W/'qa-extra-boxes.json').write_text(json.dumps({'frames':frames,'notes':['Reviewed source template reacquisition for GitHub and share links; preserve orange foreground captions.','Reviewed news source blue-line segmentation to extend masks to URL tail.']},ensure_ascii=False,indent=2))
for n,im,reg in proof:
 x,y,w,h=reg['box'];cv2.rectangle(im,(x,y),(x+w,y+h),(0,0,255),3)
 cv2.imwrite(str(W/f'extra-box-{n}-{reg["id"]}.jpg'),cv2.resize(im,(1280,720)))
print('frames',len(frames),'boxes',sum(map(len,frames.values())));print([(n,r['id'],r['box'],r.get('tracking_score'))for n,_,r in proof])
