import json,cv2,sys,numpy as np
from pathlib import Path
sys.path.insert(0,'work/full-video');from stream_capture import StreamCapture
W=Path('work/revision-v2');p=json.load(open('outputs/带封面-前5分钟/report.json'));patch={};proof=[]
seed=cv2.imread(str(W/'front_62_src.jpg'))
templates=[cv2.cvtColor(seed[888:983,1430:1612],cv2.COLOR_BGR2GRAY),cv2.cvtColor(seed[980:1077,1511:2127],cv2.COLOR_BGR2GRAY)]
templates=[cv2.resize(t,None,fx=.5,fy=.5) for t in templates]
cap=StreamCapture('/Users/carl/Downloads/带封面.mp4',start=1856/30,frames=408,fps=30)
previous={}
for n in range(1856,2264):
 ok,im=cap.read()
 if not ok:raise RuntimeError(n)
 f=p['frames'][n];remove=[i for i,r in enumerate(f['regions']) if r['id'] in ['U001','U002','R001','R002','U003','U004','U005','U006','U007','U008','U009','U010','U011']]
 # Limit modifications to the confirmed repository listing; remove obsolete tracked masks for those same links.
 
 g=cv2.resize(cv2.cvtColor(im[:1800],cv2.COLOR_BGR2GRAY),None,fx=.5,fy=.5)
 added=[];scores=[]
 for k,base in enumerate(templates):
  allowed=({'U001','U003','R001','U007','U011'} if k==0 else {'U002','U004','R002','U005','U006','U008','U009','U010'})
  near=[b for b,r in zip(f['boxes'],f['regions']) if r['id'] in allowed]
  if not near and 2239<=n<=2241 and k==1:near=[[600,100,1500,60]]
  if not near:continue
  if k in previous and n-previous[k][0]<=1 and n>=2170:near.append(previous[k][1])
  lo=max(0,min(b[1] for b in near)-45)//2;hi=min(1800,max(b[1]+b[3] for b in near)+45)//2
  roi=g[lo:hi]
  choices=[(1.0,base)] if n<2170 else [(float(z),cv2.resize(base,None,fx=float(z),fy=float(z))) for z in np.arange(.42,1.061,.025)]
  best=None
  for scale,t0 in choices:
   _,score,_,pos=cv2.minMaxLoc(cv2.matchTemplate(roi,t0,cv2.TM_CCOEFF_NORMED))
   if best is None or score>best[0]:best=(score,pos,scale,t0)
  s,xy,scale,t=best;scores.append(s)
  if s<.50:continue
  x,y=xy[0]*2,(xy[1]+lo)*2
  # Current template is the suffix including slash. Mask all visible prefix on the same row.
  # Left is preceding dash/content indentation; fixed source terminal starts at x=145.
  # Source already contains an embedded gray cursor block; it remains immutable.
  left=max(0,min(round(x-[1195,1276][k]*scale),min(b[0] for b in near)))
  b=[left,y-4,max(1,x-left-3),t.shape[0]*2+8]
  previous[k]=(n,b)
  added.append({'box':b,'id':f'front_skill_prefix_{k}','origin':'review_v2','kind':'reviewed_url','box_method':'source_suffix_template_preserve_last_component','preserve_orange_caption':True,'protected_suffix':True})
 if any(s<.50 for s in scores):proof.append({'frame':n,'scores':scores,'missing':True})
 patch[str(n)]={'remove_indexes':remove,'add':added}
cap.release()
for f in p['frames']:
 n=f['frame'];remove=[]
 for i,(b,r) in enumerate(zip(f['boxes'],f['regions'])):
  if r['id']=='U034' or r['id']=='U058':remove.append(i)
  if r['id']=='M001' and 2997<=n<=3155:remove.append(i)
 if remove:
  old=patch.setdefault(str(n),{'remove_indexes':[],'add':[]});old['remove_indexes'].extend(remove)
model_seed=cv2.imread(str(W/'front_101_src.jpg'))
mt=cv2.resize(cv2.cvtColor(model_seed[1508:1579,367:697],cv2.COLOR_BGR2GRAY),None,fx=.5,fy=.5)
cap=StreamCapture('/Users/carl/Downloads/带封面.mp4',start=2997/30,frames=159,fps=30)
for n in range(2997,3156):
 ok,im=cap.read()
 g=cv2.resize(cv2.cvtColor(im[:1800],cv2.COLOR_BGR2GRAY),None,fx=.5,fy=.5)
 _,score,_,xy=cv2.minMaxLoc(cv2.matchTemplate(g,mt,cv2.TM_CCOEFF_NORMED))
 if score<.62:raise RuntimeError(('models mismatch',n,score))
 x,y=xy[0]*2,xy[1]*2
 old=patch.setdefault(str(n),{'remove_indexes':[],'add':[]})
 old['add'].append({'box':[x,y,330,72],'id':'front_models_label','origin':'review_v2','kind':'reviewed_url','box_method':'source_label_template_fixed_geometry','preserve_orange_caption':True,'protected_suffix':True})
cap.release()
json.dump({'fps':30,'frames':patch},open(W/'front_patch.json','w'),ensure_ascii=False)
json.dump(proof,open(W/'front_template_checks.json','w'))
print('patchframes',len(patch),'template_fail',len(proof),proof[:10])
