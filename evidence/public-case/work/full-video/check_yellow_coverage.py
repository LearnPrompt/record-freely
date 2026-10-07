from pathlib import Path
import json,cv2,numpy as np
from stream_capture import StreamCapture
P=Path(__file__).resolve().parent;patch=json.loads((P/'qa_part01_proxy_yellow.json').read_text());c=StreamCapture('/Users/carl/Downloads/带封面.mp4',17805/30,56)
checks=[];proof=[]
for i in range(56):
 ok,a=c.read();assert ok;m=cv2.inRange(cv2.cvtColor(a,cv2.COLOR_BGR2HSV),np.array([18,50,75]),np.array([45,255,255]));ratio=min(i,7)/7;sx=1+.26*ratio
 for k,(ex,ey)in enumerate([(2036+75*ratio,1831+231*ratio),(682-276*ratio,1888+246*ratio)]):
  # Independent reviewed animation ROI: domain glyphs only, no quoted shell suffix.
  left=max(0,int(ex+9*sx));right=min(3840,int(ex+1490*sx));top=max(0,int(ey)-5);bottom=min(2160,int(ey+35+21*ratio)+5)
  x,y,w,h=patch['frames'][str(17805+i)][k]['box'];candidate=m[top:bottom,left:right]>0
  yy,xx=np.where(candidate);inside=(xx+left>=x)&(xx+left<x+w)&(yy+top>=y)&(yy+top<y+h)
  missed=int(np.count_nonzero(~inside));checks.append({'frame':17805+i,'row':k,'yellow_glyph_pixels':len(xx),'outside_mask_pixels':missed});assert missed==0,(17805+i,k,missed)
 if i<8:
  vis=a.copy()
  for r in patch['frames'][str(17805+i)]:
   x,y,w,h=r['box'];cv2.rectangle(vis,(x,y),(x+w,y+h),(0,0,255),3)
  proof.append(cv2.resize(vis[1750:2160],(1280,137)))
c.release();(P/'qa_yellow_coverage.json').write_text(json.dumps({'frames':56,'rows':112,'reviewed_roi_glyph_pixels':sum(r['yellow_glyph_pixels']for r in checks),'outside_mask_pixels':sum(r['outside_mask_pixels']for r in checks),'checks':checks},indent=2));cv2.imwrite(str(P/'qa_yellow_transition_proof.jpg'),np.vstack(proof));print('56 frames / 112 reviewed URI rows: all sampled yellow glyph pixels contained')
