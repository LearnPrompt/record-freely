import cv2,json,sys,numpy as np
from pathlib import Path
sys.path.insert(0,'work/full-video');from apply_repairs import render_mask
W=Path('work/revision-v3');p=json.load(open('work/revision-v2/chunks/part-00/report.json'));q=json.load(open(W/'front_patch.json'));checks=[]
for path in sorted(W.glob('front_source_*.png')):
 n=int(path.stem.split('_')[-1]);im=cv2.imread(str(path));f=p['frames'][n];v=q['frames'].get(str(n),{'remove_indexes':[],'add':[]});keep=[i for i in range(len(f['boxes'])) if i not in v['remove_indexes']];rs=[f['regions'][i] for i in keep]+v['add'];bs=[f['boxes'][i] for i in keep]+[r['box'] for r in v['add']];out=render_mask(im,{'boxes':bs,'regions':rs});cv2.imwrite(str(W/f'front_preview_{n}.jpg'),out);checks.append({'frame':n,'regions':v['add']})
for key,f in q['frames'].items():
 n=int(key);assert len(set(f['remove_indexes']))==len(f['remove_indexes']);assert all(i<len(p['frames'][n]['boxes']) for i in f['remove_indexes'])
 for r in f['add']:
  x,y,w,h=r['box'];assert min(x,y)>=0 and min(w,h)>0 and x+w<=3840 and y+h<=2160
json.dump({'status':'source_geometry_validated_waiting_actual_video_qa','frame_index_validation':True,'box_bounds_validation':True,'preview_points':checks},open(W/'front_validation.json','w'),ensure_ascii=False,indent=2)
