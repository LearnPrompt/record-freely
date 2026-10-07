from pathlib import Path
import cv2,json,numpy as np
ROOT=Path(__file__).resolve().parents[2];W=ROOT/'work/real-video-audit';r=json.load(open(W/'final-report.json'));c=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');count=0
for f in r['frames']:
 targets=[i for i,d in enumerate(f['regions'])if d['id']in ['R001','R002']]
 if not targets:continue
 c.set(1,f['frame']);ok,im=c.read();assert ok
 for i in targets:
  x,y,w,h=f['boxes'][i];z=im[y:y+h,x:x+w].astype(int);m=(z.min(2)>115)&(z.max(2)-z.min(2)<70);s=m.sum(1);groups=[];on=False
  for k,v in enumerate(s):
   if v>15 and not on:a=k;on=True
   if on and(v<=15 or k==h-1):
    if k-a>=12:groups.append([a,k])
    on=False
  if groups:
   a,z=groups[0];f['boxes'][i]=[x,y+max(0,a-4),w,min(h,z+4)-max(0,a-4)];f['regions'][i]['vertical_trim']='reviewed URL glyph row +4px';count+=1
c.release();r['repairs']['glyph_row_trim_regions']=count;r['repairs']['methods'].append('Reviewed URL mask height trimmed to first white glyph row plus 4px to preserve following Chinese line.')
(W/'trim-patch-report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print('trimmed',count)
