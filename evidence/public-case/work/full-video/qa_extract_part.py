# coding: utf-8
from pathlib import Path
import cv2,json,math,sys
from PIL import Image,ImageDraw,ImageFont
BASE=Path('/Users/carl/Documents/Codex/2026-10-06/1-openai-gpt-6-1-ultra/work/full-video');name=sys.argv[1];part=BASE/'chunks'/name;r=json.loads((part/'report.json').read_text());start=r['source_start_frame'];length=r['processed_frames'];points=json.loads((BASE/'qa_checkpoints.json').read_text())['source_frames'];ns=[n for n in points if start<=n<start+length]
if name=='part-01':ns+= [9000,9001,17999,11690,11710,12140,12160,12600,13050,17540,17550,17560]
if name=='part-02':ns+=[18000,18001,18002,18440,18450,18460,18900,26999]
if name in ['part-03','part-04']:ns+=[n for n in [35100,35550,35880,35905,35906,35907,35908,35909,35910,35940,35970,35999,36000,36010,36011,36020]if start<=n<start+length]
ns+= [start,start+1,start+length-2,start+length-1];ns+=[int(v)for v in sys.argv[2:]];ns=sorted(set(ns));ocap=cv2.VideoCapture(str(part/'redacted.mp4'));scap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');samples=[];font=ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc',22)
for n in ns:
 ocap.set(cv2.CAP_PROP_POS_FRAMES,n-start);ok,im=ocap.read();assert ok,(name,n)
 cv2.imwrite(str(BASE/f'qa_actual_{name}_{n:05}.jpg'),im)
 p=BASE/f'qa_source_{n:05}.jpg'
 if not p.exists():
  scap.set(cv2.CAP_PROP_POS_FRAMES,n);ok,s=scap.read();assert ok;cv2.imwrite(str(p),s)
 samples.append({'global_frame':n,'global_seconds':n/30,'local_frame':n-start,'reported_boxes':r['frames'][n-start]['boxes']})
for k in range(0,len(ns),6):
 group=ns[k:k+6];sheet=Image.new('RGB',(1920,600*math.ceil(len(group)/2)),'#edf0f4');d=ImageDraw.Draw(sheet)
 for i,n in enumerate(group):
  im=Image.open(BASE/f'qa_actual_{name}_{n:05}.jpg').convert('RGB').resize((960,540));x=i%2*960;y=i//2*600;d.text((x+10,y+10),f'{n/30:.3f}s · global f{n}',font=font,fill='black');sheet.paste(im,(x,y+50))
 sheet.save(BASE/f'qa_contact_{name}_{k//6:02}.jpg',quality=91)
(BASE/f'qa_extracted_{name}.json').write_text(json.dumps({'part':name,'actual_samples':samples,'all_samples_decode':'passed','visual_review':'pending'},indent=2));print(name,'actual samples',len(ns),'contact sheets',math.ceil(len(ns)/6))
