import json,cv2,hashlib
from pathlib import Path
W=Path('work/revision-v2');p=W/'chunks/part-01/report.json';r=json.loads(p.read_text());patch={};records=[]
def overlap(a,b):
 x=max(a[0],b[0]);y=max(a[1],b[1]);rr=min(a[0]+a[2],b[0]+b[2]);bb=min(a[1]+a[3],b[1]+b[3]);return max(0,rr-x)*max(0,bb-y)
for rec in r['frames']:
 targets=[(i,b,reg)for i,(b,reg)in enumerate(zip(rec['boxes'],rec['regions']))if 'middle_path' in reg['id']and reg['kind']=='reviewed_path'];remove=set();pairs=[]
 for i,a,ra in targets:
  for j,b,rb in targets:
   if i==j or ra['id']!=rb['id']:continue
   if a[3]<=b[3]*1.20:continue
   if not .83<=a[2]/b[2]<=1.2:continue
   if overlap(a,b)/(b[2]*b[3])<.90:continue
   # Same identity + same source position. Higher stale OCR box only adds
   # blank margin; retain the independently matched tighter source glyph band.
   remove.add(i);pairs.append({'remove':i,'keep':j,'removed_box':a,'kept_box':b})
 if remove:
  f=r['source_start_frame']+rec['frame'];patch[str(f)]={'remove_indexes':sorted(remove),'add':[]};records.append({'frame':f,'pairs':pairs})
# Guarantee the narrowing never deletes every home-prefix mask in a frame.
for k,v in patch.items():
 rec=r['frames'][int(k)-r['source_start_frame']];assert all(i<len(rec['boxes'])for i in v['remove_indexes']);assert any('middle_path'in g['id']and i not in v['remove_indexes']for i,g in enumerate(rec['regions']))
d={'fps':30,'index_basis':'revision-v2-current','report_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'frames':patch};(W/'middle_dedupe_patch.json').write_text(json.dumps(d,ensure_ascii=False));(W/'middle_dedupe_notes.json').write_text(json.dumps({'status':'source_proof_pending','frames':len(patch),'removed_boxes':sum(len(v['remove_indexes'])for v in patch.values()),'records':records,'index_basis':'revision-v2-current','base_report_sha256':d['report_sha256']},indent=2))
# Contact proofs span the affected frames, preserving source exclusively in work.
samples=sorted(set([records[i]['frame']for i in range(0,len(records),max(1,len(records)//10))]+([14550]if '14550'in patch else [])));c=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4')
for f in samples:
 c.set(cv2.CAP_PROP_POS_FRAMES,f);ok,im=c.read();assert ok;rec=r['frames'][f-r['source_start_frame']];pr=next(v for v in records if v['frame']==f)['pairs'][0];b=pr['removed_box'];x=max(0,b[0]-40);y=max(0,b[1]-30);ww=min(3840-x,b[2]+100);hh=min(2160-y,b[3]+60);src=im[y:y+hh,x:x+ww].copy()
 for i,box in enumerate(rec['boxes']):
  if i in patch[str(f)]['remove_indexes']:continue
  xx,yy,w,h=box;im[yy:yy+h,xx:xx+w]=112
 out=im[y:y+hh,x:x+ww];cv2.imwrite(str(W/f'middle_dedupe_sourceproof_{f}.jpg'),cv2.vconcat([src,out]))
c.release();print(len(patch),sum(len(v['remove_indexes'])for v in patch.values()),samples,flush=True)
