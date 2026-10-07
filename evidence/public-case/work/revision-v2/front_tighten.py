import json
from pathlib import Path
W=Path('work/revision-v2');q=json.load(open(W/'front_patch.json'));p=json.load(open('outputs/带封面-前5分钟/report.json'))
for key,f in q['frames'].items():
 n=int(key)
 for r in f['add']:
  r['protected_suffix']=True
  if r['id'].startswith('front_skill_prefix'):
   k=int(r['id'][-1]);x,y,w,h=r['box'];scale=(h-8)/96;right=x+w;end=right+3
   allowed=({'U001','U003','R001','U007','U011'} if k==0 else {'U002','U004','R002','U005','U006','U008','U009','U010'})
   near=[b for b,t in zip(p['frames'][n]['boxes'],p['frames'][n]['regions']) if t['id'] in allowed]
   x0=max(0,round(end-[1195,1276][k]*scale))
   if near:x0=min(x0,min(b[0] for b in near))
   yy=y+4+round([7,2][k]*scale);hh=max(1,round([68,67][k]*scale))
   if yy<120:hh=max(1,yy+hh-120);yy=120
   r['box']=[x0,yy,right-x0,hh]
 a=[r for r in f['add'] if r['id'].startswith('front_skill_prefix')]
 if len(a)==2 and a[0]['box'][1]>=a[1]['box'][1]:f['add'].remove(a[0])
json.dump(q,open(W/'front_patch.json','w'),ensure_ascii=False)
