# coding: utf-8
from pathlib import Path
import cv2,json,math
from PIL import Image,ImageDraw,ImageFont
ROOT=Path('/Users/carl/Documents/Codex/2026-10-06/1-openai-gpt-6-1-ultra');BASE=ROOT/'work/full-video';FONT=ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc',22)
times=sorted(set(list(range(375,466,15))+list(range(555,646,15))+list(range(1170,1261,15))+list(range(1980,2086,15))))
cap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');entries=[]
for t in times:
 n=round(t*30);p=BASE/f'qa_source_{n:05d}.jpg'
 if not p.exists():
  cap.set(cv2.CAP_PROP_POS_FRAMES,n);ok,im=cap.read();assert ok;(cv2.imwrite(str(p),im))
 im=Image.open(p).convert('RGB').resize((960,540));entries.append((n,t,im))
cap.release()
for start in range(0,len(entries),6):
 group=entries[start:start+6];sheet=Image.new('RGB',(1920,600*math.ceil(len(group)/2)),'#edf0f4');d=ImageDraw.Draw(sheet)
 for i,(n,t,im) in enumerate(group):
  x=i%2*960;y=i//2*600;d.text((x+12,y+12),f'{t//60:02}:{t%60:02} · frame {n}',font=FONT,fill='#17202a');sheet.paste(im,(x,y+50))
 sheet.save(BASE/f'qa_dense_{start//6:02}.jpg',quality=91)
(BASE/'qa_dense_manifest.json').write_text(json.dumps({'windows':[[375,465],[555,645],[1170,1260],[1980,2085]],'stride_seconds':15,'frames':[{'frame':n,'time':t} for n,t,_ in entries]},indent=2))
print('dense samples',len(entries))
