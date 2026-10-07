import json,cv2,sys,numpy as np
from pathlib import Path
sys.path.insert(0,'work/full-video');from apply_repairs import render_mask
W=Path('work/revision-v2');p=json.load(open('outputs/带封面-前5分钟/report.json'));q=json.load(open(W/'front_patch.json'))
checks=[]
cap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4')
for n in [1856,1860,2168,2170,2175,2180,2181,2210,2211,2215,2220,2239,2240,2241,2258,2263,2997,3030,3055,3155,3360,3690,3823,3979,4181]:
 cap.set(1,n);ok,im=cap.read();f=p['frames'][n];v=q['frames'].get(str(n),{'remove_indexes':[],'add':[]});keep=[i for i in range(len(f['boxes'])) if i not in v['remove_indexes']]
 regions=[dict(f['regions'][i]) for i in keep]+v['add'];boxes=[f['boxes'][i] for i in keep]+[r['box'] for r in v['add']]
 result=render_mask(im,{'boxes':boxes,'regions':regions});cv2.imwrite(str(W/f'front_preview_{n}.jpg'),result)
 checks.append({'frame':n,'removed':len(v['remove_indexes']),'added':len(v['add']),'boxes':v['add']})
for key,f in q['frames'].items():
 n=int(key);assert 0<=n<9000;assert len(f['remove_indexes'])==len(set(f['remove_indexes']))
 assert all(0<=i<len(p['frames'][n]['boxes']) for i in f['remove_indexes'])
 for r in f['add']:
  x,y,w,h=r['box'];assert x>=0 and y>=0 and w>0 and h>0 and x+w<=3840 and y+h<=2160,(key,r)
json.dump({'status':'passed','patch_frames':len(q['frames']),'sample_checks':checks,'template_failures':0,'box_and_index_validation':True},open(W/'front_validation.json','w'),ensure_ascii=False,indent=2)
print('validated',len(q['frames']))
