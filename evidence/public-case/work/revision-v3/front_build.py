import cv2,json,numpy as np,sys
from pathlib import Path
from front_decode import Frames
W=Path('work/revision-v3');p=json.load(open('work/revision-v2/chunks/part-00/report.json'));seed=cv2.imread(str(W/'front_seed_1860.png'))
base=[cv2.resize(cv2.cvtColor(seed[895:963,1005:1608],cv2.COLOR_BGR2GRAY),None,fx=.5,fy=.5),cv2.resize(cv2.cvtColor(seed[983:1049,1005:2125],cv2.COLOR_BGR2GRAY),None,fx=.5,fy=.5)]
patch={};evidence=[];cap=Frames('/Users/carl/Downloads/带封面.mp4',1855,411)
for n in range(1855,2266):
 im=cap.read();f=p['frames'][n]
 if n in [1855,1856,1860,2000,2168,2170,2175,2180,2181,2182,2183,2210,2211,2220,2237,2238,2239,2240,2241,2242,2243,2244,2258,2263,2264,2265]:cv2.imwrite(str(W/f'front_source_{n}.png'),im)
 if not 1856<=n<=2263:continue
 g=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY);matches=[]
 for i,(b,r) in enumerate(zip(f['boxes'],f['regions'])):
  k=0 if 'front_skill_prefix_0' in str(r) else 1 if 'front_skill_prefix_1' in str(r) else None
  if k is None:continue
  x,y,w,h=b;lo=max(120,y-50);hi=min(1800,y+h+50);xx=max(0,x-20);end=min(3840,x+w+700)
  roi=cv2.resize(g[lo:hi,xx:end],None,fx=.5,fy=.5);best=None
  for z in np.arange(.42,1.071,.025):
   t=cv2.resize(base[k],None,fx=float(z),fy=float(z))
   if t.shape[0]>roi.shape[0] or t.shape[1]>roi.shape[1]:continue
   _,score,_,pos=cv2.minMaxLoc(cv2.matchTemplate(roi,t,cv2.TM_CCOEFF_NORMED))
   if best is None or score>best[0]:best=(score,pos,z)
  if best is None:raise RuntimeError((n,k,'no fit'))
  score,pos,z=best;boundary=xx+pos[0]*2-2
  matches.append({'index':i,'role':k,'box':b,'score':round(score,4),'candidate_boundary':boundary,'candidate_y':lo+pos[1]*2,'scale':round(float(z),4)})
 evidence.append({'frame':n,'matches':matches})
cap.close();json.dump(evidence,open(W/'front_candidates.json','w'),ensure_ascii=False,indent=2)
print('rows',sum(len(f['matches']) for f in evidence),'weak',[(f['frame'],r['role'],r['score']) for f in evidence for r in f['matches'] if r['score']<.65][:50])
