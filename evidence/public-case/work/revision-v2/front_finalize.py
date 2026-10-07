import json,cv2,sys,numpy as np
from pathlib import Path
sys.path.insert(0,'work/full-video');from stream_capture import StreamCapture
W=Path('work/revision-v2');q=json.load(open(W/'front_patch.json'));p=json.load(open('outputs/带封面-前5分钟/report.json'))
for key,f in q['frames'].items():
 n=int(key);a=[r for r in f['add'] if r['id'].startswith('front_skill_prefix')]
 if len(a)==2 and a[0]['box'][1]>=a[1]['box'][1]:f['add'].remove(a[0])
 for r in f['add']:
  r['protected_suffix']=True
  if r['id']=='front_skill_prefix_0' and n>=2170:
   x,y,w,h=r['box'];ext=round(h/68*55);r['box']=[max(0,x-ext),y,w+min(x,ext),h]
# Fill three OCR-dropout frames based on current source, not report interpolation.
seed=cv2.imread(str(W/'front_62_src.jpg'));ts=[cv2.resize(cv2.cvtColor(seed[888:983,1430:1612],cv2.COLOR_BGR2GRAY),None,fx=.5,fy=.5),cv2.resize(cv2.cvtColor(seed[980:1077,1511:2127],cv2.COLOR_BGR2GRAY),None,fx=.5,fy=.5)]
cap=StreamCapture('/Users/carl/Downloads/带封面.mp4',start=2239/30,frames=3,fps=30)
for n in range(2239,2242):
 _,im=cap.read();cv2.imwrite(str(W/f'front_proof_{n}.jpg'),im);g=cv2.resize(cv2.cvtColor(im[:1800],cv2.COLOR_BGR2GRAY),None,fx=.5,fy=.5);add=[]
 for k,t in enumerate(ts):
  best=None
  for scale in np.arange(.42,1.061,.025):
   tt=cv2.resize(t,None,fx=float(scale),fy=float(scale));_,s,_,xy=cv2.minMaxLoc(cv2.matchTemplate(g,tt,cv2.TM_CCOEFF_NORMED))
   if best is None or s>best[0]:best=(s,xy,scale)
  score,xy,z=best;assert score>=.62
  x,y=xy[0]*2,xy[1]*2;left=max(0,round(x-[1195,1276][k]*z));h=round([68,67][k]*z);ext=round(h/68*55) if k==0 else 0
  add.append({'box':[max(0,left-ext),y+round([7,2][k]*z),x-left-3+min(left,ext),h],'id':f'front_skill_prefix_{k}','origin':'review_v2','kind':'reviewed_url','box_method':'source_suffix_template_preserve_last_component','preserve_orange_caption':True,'protected_suffix':True})
 if add[0]['box'][1]>=add[1]['box'][1]:add.pop(0)
 # Previously isolated OCR masks belong to this same repository listing, validated in source below.
 f=p['frames'][n];remove=[]
 for i,b in enumerate(f['boxes']):
  for r in add:
   x,y,w,h=r['box'];xx,yy,ww,hh=b
   if min(y+h,yy+hh)>max(y,yy) and min(x+w,xx+ww)>max(x,xx):remove.append(i);break
 q['frames'][str(n)]={'remove_indexes':remove,'add':add}
cap.release();json.dump(q,open(W/'front_patch.json','w'),ensure_ascii=False);print('done',len(q['frames']))
