#!/usr/bin/env python3
"""Independent synthetic acceptance: link ink removal, preserved normal text, no stale masks.

Usage: python3 verify_fixture.py /absolute/redacted.mp4
Metrics compare decoded source/output pixels. Link ink uses delta >20; normal
text and stale masks use delta >45 to avoid ordinary H.264 noise. This measures
visual change over link ink, not mathematical
irrecoverability; visually review the generated contact sheet as well.
"""
import argparse
import json
import subprocess
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('output',type=Path)
parser.add_argument('--fixture-dir',type=Path,required=True)
parser.add_argument('--report',type=Path,required=True)
parser.add_argument('--contact',type=Path,required=True)
args=parser.parse_args()
ROOT=args.fixture_dir.resolve()
truth=json.loads((ROOT/'truth.json').read_text())
source=cv2.VideoCapture(str(ROOT/'source.mp4'))
output=cv2.VideoCapture(str(args.output))
if not source.isOpened() or not output.isOpened():
    raise SystemExit('Cannot decode source/output')
rows=[]
images=[]
for spec in truth['frames']:
    ok0,a=source.read();ok1,b=output.read()
    if not ok0 or not ok1:
        raise SystemExit(f'Missing frame {spec["frame"]}')
    if a.shape!=b.shape:
        raise SystemExit(f'Changed frame size: {b.shape} versus {a.shape}')
    delta=np.abs(a.astype(np.int16)-b.astype(np.int16)).max(axis=2)
    diff=delta>45
    allowed=np.zeros(diff.shape,dtype=bool)
    link_coverage=[]
    for x,y,w,h in spec['links']:
        allowed[max(0,y-5):min(truth['height'],y+h+5),max(0,x-5):min(truth['width'],x+w+5)]=True
        # OpenCV is BGR. Source text is RGB 36,92,171 with antialiasing.
        patch=a[y:y+h,x:x+w].astype(np.int16)
        ink=(patch[:,:,2]<120)&(patch[:,:,1]<160)&(patch[:,:,0]>120)&((patch[:,:,0]-patch[:,:,2])>55)&((patch[:,:,0]-patch[:,:,1])>20)
        changed=delta[y:y+h,x:x+w]>20
        coverage=float(changed[ink].mean()) if ink.any() else 0.0
        link_coverage.append(coverage)
    normal_pixels=0
    normal_changed=0
    for x,y,w,h in spec['normal']:
        region=diff[y:y+h,x:x+w]
        normal_pixels+=region.size
        normal_changed+=int(region.sum())
    rows.append({'frame':spec['frame'],'link_coverage':link_coverage,'normal_changed_fraction':normal_changed/normal_pixels,'changed_pixels_outside_link_regions':int((diff&~allowed).sum()),'total_changed_pixels':int(diff.sum())})
    if spec['frame'] in (0,25,50,51,52,70,100,112,120):
        rgb=cv2.cvtColor(b,cv2.COLOR_BGR2RGB)
        im=Image.fromarray(rgb)
        draw=ImageDraw.Draw(im)
        for x,y,w,h in spec['links']:draw.rectangle((x,y,x+w,y+h),outline='red',width=2)
        im=im.resize((480,270))
        tile=Image.new('RGB',(480,296),'white');tile.paste(im,(0,26))
        ImageDraw.Draw(tile).text((8,6),f'Frame {spec["frame"]} | expected URL bounds in red',fill='black')
        images.append(tile)
ok_extra,_=output.read()
source.release();output.release()
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(args.output)],text=True))
coverages=[c for row in rows for c in row['link_coverage']]
misses=[r['frame'] for r in rows if r['link_coverage'] and min(r['link_coverage'])<0.98]
normal_bad=[r['frame'] for r in rows if r['normal_changed_fraction']>0.005]
no_link_artifacts=[r['frame'] for r in rows if not r['link_coverage'] and r['total_changed_pixels']>100]
report={'link_ink_delta_threshold':20,'normal_and_stale_mask_delta_threshold':45,'output':args.output.name,'frames':len(rows),'extra_frame':ok_extra,'audio_streams':sum(s['codec_type']=='audio' for s in probe['streams']),'duration':probe['format']['duration'],'mean_link_ink_coverage':float(np.mean(coverages)),'minimum_link_ink_coverage':min(coverages),'link_frames_below_98_percent':misses,'short_url_results':[rows[i] for i in truth['short_url_frames']],'normal_text_frames_with_more_than_0_5_percent_changed':normal_bad,'no_link_frames_with_more_than_100_changed_pixels':no_link_artifacts,'rows':rows}
report['passed']=not misses and not normal_bad and not no_link_artifacts and not ok_extra and report['audio_streams']>0
args.report.write_text(json.dumps(report,indent=2))
args.contact.parent.mkdir(parents=True,exist_ok=True)
canvas=Image.new('RGB',(1440,888),'#ddd')
for i,im in enumerate(images):canvas.paste(im,((i%3)*480,(i//3)*296))
canvas.save(args.contact)
summary={k:v for k,v in report.items() if k!='rows'}
print(json.dumps(summary,indent=2))
print(f'Report: {args.report}')
print(f'Contact: {args.contact}')

if not report["passed"]:
    raise SystemExit("Synthetic fixture acceptance failed; inspect the JSON report")
