import cv2,numpy as np,json
from pathlib import Path
D=Path('work/revision-v2')
def hp(im):
 g=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY).astype(np.float32);return g-cv2.GaussianBlur(g,(0,0),6)
seed=cv2.imread(str(D/'late_src_1508.jpg'));template=hp(seed)[332:388,340:655].copy()
def locate(im,box):
 x,y,w,h=box;a=max(0,x-300);b=max(0,y-25);right=min(3840,x+w+350);bottom=min(2160,y+h+25);search=hp(im[b:bottom,a:right]);best=None
 ratio=max(.5,min(3,h/64))
 for sc in sorted(set(list(np.arange(.8,1.231,.04)*ratio)+[1.0])):
  ww,hh=round(template.shape[1]*sc),round(template.shape[0]*sc)
  if ww>=search.shape[1] or hh>=search.shape[0]:continue
  t=cv2.resize(template,(ww,hh));r=cv2.matchTemplate(search,t,cv2.TM_CCOEFF_NORMED);_,val,_,xy=cv2.minMaxLoc(r)
  if best is None or val>best[0]:best=(val,[a+xy[0]-3,b+xy[1]-3,ww+6,hh+6])
 return best
if __name__=='__main__':
 c=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');r=json.load(open(D/'late_detections.json'))
 for f in [44923,45240,49440,51540]:
  c.set(cv2.CAP_PROP_POS_FRAMES,f);ok,im=c.read()
  for v in r.get(str(f),[]):
   m=locate(im,v['box']);print(f,v['box'],m)
   if m:
    x,y,w,h=m[1];cv2.rectangle(im,(x,y),(x+w,y+h),(0,0,255),2)
  cv2.imwrite(str(D/f'late_prefix_matched_{f}.jpg'),im)
