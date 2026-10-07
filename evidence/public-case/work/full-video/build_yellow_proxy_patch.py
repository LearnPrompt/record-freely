"""Reviewed 56-frame yellow public-proxy rows; narrow local glyph template."""
from pathlib import Path
import json,cv2,numpy as np
from stream_capture import StreamCapture
P=Path(__file__).resolve().parent
cap=StreamCapture('/Users/carl/Downloads/带封面.mp4',17805/30,56)
ok,seed=cap.read();assert ok
def yellow(a):return cv2.inRange(cv2.cvtColor(a,cv2.COLOR_BGR2HSV),np.array([18,50,75]),np.array([45,255,255]))
base=yellow(seed)[1831:1845,2036:2340]
patch={'frames':{},'notes':['Only two reviewed repeated public proxy URI rows. Prefix search constrained to reviewed animation geometry; anonymous coordinates only. White subtitle glyphs preserve source pixels.']};proof=[]
for i in range(56):
 if i==0:a=seed
 else:ok,a=cap.read();assert ok
 m=yellow(a);ratio=min(i,7)/7;scale=1+.26*ratio
 boxes=[];scores=[]
 for row,(sx,sy,ex,ey) in enumerate([(scale,1+.6*ratio,2036+75*ratio,1831+231*ratio),(scale,1+.6*ratio,682-276*ratio,1888+246*ratio)]):
  best=(-1,None)
  for dy in [-.12,0,.12]:
   t=cv2.resize(base,None,fx=sx,fy=sy+dy,interpolation=cv2.INTER_LINEAR)
   left=max(0,int(ex)-18);top=max(0,int(ey)-15);right=min(3840,int(ex)+t.shape[1]+20);bottom=min(2160,int(ey)+t.shape[0]+18)
   t=t[:min(t.shape[0],bottom-top-15)]
   result=cv2.matchTemplate(m[top:bottom,left:right],t,cv2.TM_CCOEFF_NORMED);_,score,_,xy=cv2.minMaxLoc(result)
   if score>best[0]:best=(score,(xy[0]+left,xy[1]+top))
  score,(x,y)=best;scores.append(score)
  x0=max(0,int(np.floor(x+9*sx))-5);x1=min(3840,int(np.ceil(x+1516*sx))+6)
  # Ink projection gives full row including descendant, unaffected by white overlay.
  scan_top=max(0,int(round(ey))-8)
  scan_bottom=min(2160,int(round(ey+35+21*ratio))+8)
  rr=m[scan_top:scan_bottom,x0:x1]
  ys=np.where(np.count_nonzero(rr,axis=1)>3)[0]
  assert len(ys)>0
  y0=max(0,scan_top+int(ys[0])-4);y1=min(2160,scan_top+int(ys[-1])+5)
  boxes.append([x0,y0,x1-x0,y1-y0])
 patch['frames'][str(17805+i)]=[{'box':b,'id':f'QY00{k+1}','kind':'http(s)','box_method':'reviewed_animation_geometry_glyph_projection','origin':'review_yellow_proxy','template_score':round(float(s),4),'preserve_white_caption':True,'review_basis':'Confirmed public repeated URI; constrained prefix and visible glyph projection'}for k,(b,s)in enumerate(zip(boxes,scores))]
 if i in [0,3,7,15,25,35,45,55]:
  canvas=a.copy()
  for bx,by,bw,bh in boxes:cv2.rectangle(canvas,(bx,by),(bx+bw,by+bh),(0,0,255),3)
  proof.append(cv2.resize(canvas[1700:2160],(960,115)))
 print(17805+i,[round(float(s),3)for s in scores],boxes,flush=True)
cap.release();(P/'qa_part01_proxy_yellow.json').write_text(json.dumps(patch,indent=2));cv2.imwrite(str(P/'qa_part01_yellow_template_proof.jpg'),np.vstack(proof))
