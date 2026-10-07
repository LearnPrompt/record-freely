"""Nine reviewed missing white proxy frames, fixed public prefix only."""
from pathlib import Path
import cv2,json,numpy as np
from stream_capture import StreamCapture
P=Path(__file__).resolve().parent;targets={18021,18023,18024,18027,18028,18029,18030,18031,18065}
c=StreamCapture('/Users/carl/Downloads/带封面.mp4',18020/30,46);ok,seed=c.read();assert ok
seeds=[[2498,1840,1342,58],[794,1912,1986,56]]
templates=[cv2.cvtColor(seed[y:y+h,x:x+400],cv2.COLOR_BGR2GRAY)for x,y,w,h in seeds]
patch={'frames':{},'notes':['Nine reviewed proxy gaps matched only to two public URI prefix templates; narrow row boxes, no OCR text retained.']};proof=[]
for n in range(18020,18066):
 if n==18020:a=seed
 else:ok,a=c.read();assert ok
 if n not in targets:continue
 gray=cv2.cvtColor(a,cv2.COLOR_BGR2GRAY);regions=[];vis=a.copy()
 for k,(template,(x0,y0,w,h))in enumerate(zip(templates,seeds)):
  left=x0-25;top=1580;roi=gray[top:2010,left:x0+425]
  out=cv2.matchTemplate(roi,template,cv2.TM_CCOEFF_NORMED);_,score,_,pos=cv2.minMaxLoc(out)
  assert score>.7,(n,k,score)
  box=[left+pos[0],top+pos[1],w,h]
  regions.append({'box':box,'id':f'QWG00{k+1}','kind':'http(s)','box_method':'reviewed_public_prefix_template','origin':'review_white_proxy_gap','template_score':round(score,4),'review_basis':'Neighbor reviewed public URI prefix; only missing individual glyph row'})
  x,y,w,h=box;cv2.rectangle(vis,(x,y),(min(3839,x+w),y+h),(0,0,255),3)
 patch['frames'][str(n)]=regions;proof.append(cv2.resize(vis[1550:2010],(960,115)))
 print(n,[(r['box'],r['template_score'])for r in regions],flush=True)
c.release();(P/'qa_part02_proxy_gaps.json').write_text(json.dumps(patch,indent=2));cv2.imwrite(str(P/'qa_part02_proxy_gaps_proof.jpg'),np.vstack(proof))
