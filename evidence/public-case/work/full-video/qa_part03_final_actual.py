from pathlib import Path
import json, cv2
from PIL import Image,ImageDraw,ImageFont
P=Path(__file__).parent
ns=json.loads((P/'qa_part03_neighbors_review_frames.json').read_text())
cap=cv2.VideoCapture(str(P/'chunks'/'part-03'/'redacted.mp4'))
font=ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc',22)
for n in ns:
 cap.set(cv2.CAP_PROP_POS_FRAMES,n-27000);ok,a=cap.read();assert ok,n
 cv2.imwrite(str(P/f'qa_actual_part-03_{n:05}.jpg'),a)
cap.release()
for k in range(0,len(ns),6):
 group=ns[k:k+6];im=Image.new('RGB',(1920,600*((len(group)+1)//2)),'#f0f0f0');d=ImageDraw.Draw(im)
 for i,n in enumerate(group):
  x=i%2*960;y=i//2*600;d.text((x+10,y+9),f'FINAL {n/30:.3f}s f{n}',font=font,fill='black');im.paste(Image.open(P/f'qa_actual_part-03_{n:05}.jpg').resize((960,540)),(x,y+50))
 im.save(P/f'qa_part03_neighbors_final_actual_{k//6}.jpg',quality=96)
rows=[(34326,(1850,0,3840,950)),(34329,(1850,0,3840,950)),(35533,(300,60,3380,1020))]
im=Image.new('RGB',(1990,1100),'#f0f0f0');d=ImageDraw.Draw(im)
for i,(n,roi) in enumerate(rows):
 a=Image.open(P/f'qa_actual_part-03_{n:05}.jpg').crop(roi);a.thumbnail((1960,305));y=i*365;d.text((15,y+9),f'FINAL f{n}',font=font,fill='black');im.paste(a,(15,y+42))
im.save(P/'qa_part03_last_two_instances_actual.jpg',quality=97)
print('fixed final neighbors decoded',len(ns))
