import json
from pathlib import Path
D=Path('work/revision-v2');r=json.load(open('work/full-video/chunks/part-05/report.json'));g=json.load(open('work/full-video/qa_part05_assets_geometry.json'))['frames'];frames={};kept={};stats={}
for fs,vals in g.items():
 f=int(fs);d=r['frames'][f-45000];remove=[];geometry=[b for b,reg in zip(d['boxes'],d['regions']) if reg.get('origin')=='review_resource_geometry']
 assert geometry
 for i,(b,reg) in enumerate(zip(d['boxes'],d['regions'])):
  if reg.get('origin')=='review_resource_geometry':continue
  x,y,w,h=b
  intersections=[]
  for q in geometry:
   a,c,u,v=q;area=max(0,min(x+w,a+u)-max(x,a))*max(0,min(y+h,c+v)-max(y,c));intersections.append(area)
  if sum(intersections)/(w*h)>=.45 and reg.get('origin') in ['ocr','tracked','backfilled']:
   remove.append(i);stats[reg['id']]=stats.get(reg['id'],0)+1
 if remove:frames[fs]={'remove_indexes':remove,'add':[]}
 kept[fs]={'kept_geometry_count':len(geometry),'removed_indexes':remove}
(D/'late_asset_remove.json').write_text(json.dumps({'fps':30,'frames':frames},indent=2));(D/'late_asset_remove_proof.json').write_text(json.dumps({'reviewed_source_geometry_frames':len(g),'changed_frames':len(frames),'removed_count':sum(len(d['remove_indexes']) for d in frames.values()),'id_counts':stats,'per_frame':kept},indent=2));print(len(frames),sum(len(d['remove_indexes']) for d in frames.values()),stats)
