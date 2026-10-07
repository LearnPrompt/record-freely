# coding: utf-8
from pathlib import Path
import cv2,json,math
from PIL import Image,ImageDraw,ImageFont
ROOT=Path('/Users/carl/Documents/Codex/2026-10-06/1-openai-gpt-6-1-ultra');BASE=ROOT/'work/full-video'
FONT=ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc',24)
cap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4')
times=list(range(300,2101,60))+[2128]
entries=[]
for t in times:
 n=round(t*30);cap.set(cv2.CAP_PROP_POS_FRAMES,n);ok,im=cap.read();assert ok,(n,t)
 cv2.imwrite(str(BASE/f'qa_source_{n:05d}.jpg'),im)
 entries.append((n,t,Image.fromarray(cv2.cvtColor(im,cv2.COLOR_BGR2RGB)).resize((960,540))))
cap.release()
for start in range(0,len(entries),6):
 group=entries[start:start+6];sheet=Image.new('RGB',(1920,600*math.ceil(len(group)/2)),'#edf0f4');d=ImageDraw.Draw(sheet)
 for i,(n,t,im) in enumerate(group):
  x=(i%2)*960;y=(i//2)*600
  d.text((x+14,y+9),f'{int(t)//60:02}:{int(t)%60:02} · frame {n}',font=FONT,fill='#17202a');sheet.paste(im,(x,y+50))
 sheet.save(BASE/f'qa_scout_{start//6:02}.jpg',quality=91)
(BASE/'qa_scout_manifest.json').write_text(json.dumps({'range':[300,2129.033333],'stride_seconds':60,'frames':[{'frame':n,'time':t}for n,t,_ in entries]},indent=2))
print('source samples',len(entries))
