# coding: utf-8
import cv2,json
from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
base=Path('work/full-video');r=json.loads((base/'qa_calendar_boxes.json').read_text());cap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');ns=[35895,35900,35905,35907,35908,35910,35940,35970,36000,36010,36011,36020];font=ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc',22)
for start in range(0,len(ns),4):
 sheet=Image.new('RGB',(1920,1200),'#eee');d=ImageDraw.Draw(sheet)
 for i,n in enumerate(ns[start:start+4]):
  cap.set(cv2.CAP_PROP_POS_FRAMES,n);ok,im=cap.read();assert ok
  cv2.imwrite(str(base/f'qa_calendar_src_{n}.jpg'),im)
  for q in r['frames'].get(str(n),[]):
   x,y,w,h=q['box'];im[y:y+h,x:x+w]=112
  cv2.imwrite(str(base/f'qa_calendar_expected_{n}.jpg'),im)
  pil=Image.fromarray(cv2.cvtColor(im,cv2.COLOR_BGR2RGB)).resize((960,540));x=i%2*960;y=i//2*600;d.text((x+10,y+10),f'f{n} · {n/30:.3f}s · boxes {len(r["frames"].get(str(n),[]))}',font=font,fill='black');sheet.paste(pil,(x,y+50))
 sheet.save(base/f'qa_calendar_check_{start//4}.jpg',quality=93)
cap.release()
