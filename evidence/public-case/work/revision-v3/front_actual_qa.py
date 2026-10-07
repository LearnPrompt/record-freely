import cv2,json,numpy as np
from pathlib import Path
from front_decode import Frames
W=Path('work/revision-v3');V=W/'chunks/part-00/redacted.mp4';e=json.load(open(W/'front_candidates.json'));em={x['frame']:x['matches'] for x in e};p=json.load(open(W/'chunks/part-00/report.json'));points=sorted(int(x.stem.split('_')[-1]) for x in W.glob('front_source_*.png'));c=Frames(V,1855,411);checks=[]
for n in range(1855,2266):
 im=c.read()
 if n not in points:continue
 cv2.imwrite(str(W/f'front_actual_{n}.png'),im);s=cv2.imread(str(W/f'front_source_{n}.png'));rows=[]
 for b,r in zip(p['frames'][n]['boxes'],p['frames'][n]['regions']):
  role=0 if 'front_two_path_components_0' in str(r) else 1 if 'front_two_path_components_1' in str(r) else None
  if role is None:continue
  x,y,w,h=b;old=next((r for r in em.get(n,[]) if r['role']==role),None);z=old['scale'] if old else .845
  left=x+w+3;ww=min(round([603,1120][role]*z)-6,3840-left)
  if ww<=0:continue
  a=s[y:y+h,left:left+ww].astype(float);o=im[y:y+h,left:left+ww].astype(float);d=np.abs(a-o)
  rows.append({'role':role,'author_roi':[left,y,ww,h],'source_rgb_mae':round(float(d.mean()),4),'fraction_max_rgb_error_over_35':round(float((d.max(2)>35).mean()),6)})
 checks.append({'frame':n,'time':round(n/30,6),'file':f'front_actual_{n}.png','rows':rows})
c.close()
# Static boundary audit uses every current rendered-report frame, not sampled image inference.
stat={}
for role in [0,1]:
 bs=[]
 for n in range(1856,2168):
  for b,r in zip(p['frames'][n]['boxes'],p['frames'][n]['regions']):
   if f'front_two_path_components_{role}' in str(r):bs.append(b)
 stat[str(role)]={'frames':len(bs),'right_edges':sorted(set(b[0]+b[2] for b in bs)),'left_edges':sorted(set(b[0] for b in bs)),'heights':sorted(set(b[3] for b in bs))}
json.dump({'status':'pending_visual_inspection','actual_video':str(V.resolve()),'decode':'independent FFmpeg -reinit_filter 0 RGB; 1855–2265 inclusive','actual_points':points,'actual_sample_count':len(points),'samples':checks,'static_box_audit':stat,'unresolved':[]},open(W/'front_visual_qa.json','w'),ensure_ascii=False,indent=2)
# Focused masked-only contacts for visual review.
for group,ns in [('head',[1855,1856,1860,2000,2168,2170]),('zoom',[2175,2180,2181,2182,2183,2210]),('cover',[2211,2220,2237,2238,2240,2244]),('tail',[2258,2263,2264,2265])]:
 tiles=[]
 for n in ns:
  im=cv2.imread(str(W/f'front_actual_{n}.png'));f=p['frames'][n];url=[b for b,r in zip(f['boxes'],f['regions']) if 'front_two_path_components_' in str(r)]
  if url:
   y=max(0,min(b[1] for b in url)-30);end=min(2160,max(b[1]+b[3] for b in url)+50);x=max(0,min(b[0] for b in url)-40);crop=im[y:end,x:min(3840,max(b[0]+b[2] for b in url)+1000)]
  else:crop=im[:300,300:2300]
  t=cv2.resize(crop,(1000,220));cv2.putText(t,str(n),(8,210),0,.9,(0,0,255),2);tiles.append(t)
 cv2.imwrite(str(W/f'front_actual_contact_{group}.jpg'),np.vstack(tiles))
print('actual points',len(points),'max author MAE',max(r['source_rgb_mae'] for f in checks for r in f['rows']),stat)
