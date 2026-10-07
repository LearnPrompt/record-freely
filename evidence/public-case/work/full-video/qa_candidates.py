# coding:utf-8
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import cv2,json,collections,sys
p=Path(__file__).parent;name=sys.argv[1];r=json.load(open(p/'chunks'/name/'report.json'));ids=collections.defaultdict(list)
for f in r['frames']:
 for b,g in zip(f['boxes'],f['regions']):
  if b[1]<135 or g.get('ocr_confidence',1)<.8:ids[g['id']].append((f['frame']+r['source_start_frame'],b))
cap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');outcap=cv2.VideoCapture(str(p/'chunks'/name/'redacted.mp4'));samples=[]
for id,vs in ids.items():
 for n,b in [vs[0],vs[-1]]if len(vs)>1 else[vs[0]]:
  samples.append((id,n,b))
for page in range(0,len(samples),10):
 sheet=Image.new('RGB',(1600,300*len(samples[page:page+10])),'white');d=ImageDraw.Draw(sheet)
 for i,(id,n,b)in enumerate(samples[page:page+10]):
  x,y,w,h=b;extent=[max(0,x-80),max(0,y-40),min(3840,x+w+80),min(2160,y+h+40)];d.text((5,i*300),f'{id} f{n} box{b}',fill='black')
  for j,c in enumerate([cap,outcap]):
   c.set(1,n if j==0 else n-r['source_start_frame']);ok,a=c.read();assert ok;im=Image.fromarray(cv2.cvtColor(a,cv2.COLOR_BGR2RGB)).crop(extent);im.thumbnail((790,260));sheet.paste(im,(j*800,i*300+30))
 sheet.save(p/f'qa_candidates_{name}_{page//10:02}.jpg')
(p/f'qa_candidates_{name}.json').write_text(json.dumps({'candidates':{id:vs for id,vs in ids.items()}},indent=2));print(name,len(samples),'source/actual pairs',flush=True)
