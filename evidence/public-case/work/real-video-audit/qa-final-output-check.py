import cv2,json,numpy as np
from pathlib import Path
ROOT=Path('/Users/carl/Documents/Codex/2026-10-06/1-openai-gpt-6-1-ultra');BASE=ROOT/'work/real-video-audit';OUT=ROOT/'outputs/带封面-前5分钟'
NS=sorted(set([int(p.stem.rsplit('f',1)[-1])for p in BASE.glob('qa-source-f*.jpg')])|set([2172,2182,2211,2212,2218,2221,3577,3578,3580,4848,4849,4850]))
r=json.load(open(OUT/'report.json'));cap=cv2.VideoCapture(str(OUT/'redacted.mp4'));samples=[]
for n in NS:
 cap.set(cv2.CAP_PROP_POS_FRAMES,n);ok,im=cap.read();assert ok,n
 cv2.imwrite(str(BASE/f'qa-final-actual-{n:04d}.jpg'),im)
 f=r['frames'][n];gray_regions=[]
 for box,d in zip(f['boxes'],f['regions']):
  if d.get('preserve_orange_caption'):continue
  x,y,w,h=box
  if w>16 and h>16:
   patch=im[y+6:y+h-6,x+6:x+w-6];gray_regions.append(float(np.abs(patch.astype(np.float32)-112).mean()))
 samples.append({'frame':n,'time':n/30,'region_count':len(f['boxes']),'max_gray_core_mean_deviation':max(gray_regions,default=None)})
cap.release();(BASE/'qa-final-output-check.json').write_text(json.dumps({'sample_count':len(NS),'samples':samples,'note':'Gray pixel checks confirm rendering at reported boxes; they do not prove missed-link absence.'},indent=2))
print('actual_samples',len(NS),'gray_check_max_deviation',max((s['max_gray_core_mean_deviation']or 0)for s in samples))
