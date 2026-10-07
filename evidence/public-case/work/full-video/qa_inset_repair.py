# coding:utf-8
from pathlib import Path
import cv2,json,math
P=Path(__file__).parent;q=json.load(open(P/'qa_part02_edges.json'));seed=cv2.imread(str(P/'qa_source_20043.jpg'));tpl=cv2.cvtColor(seed[912:936,3130:3470],cv2.COLOR_BGR2GRAY);cap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');cap.set(1,20001);found=[]
for key in list(q['frames']):
 q['frames'][key]=[b for b in q['frames'][key]if b['id']!='QI001']
 if not q['frames'][key]:del q['frames'][key]
for n in range(20001,20351):
 ok,a=cap.read();assert ok;gray=cv2.cvtColor(a[500:1200,2300:3840],cv2.COLOR_BGR2GRAY);best=(0,None,1)
 for scale in ([.6+i*.02 for i in range(27)]if n<20043 else[.8,.9,1,1.1]):
  t=cv2.resize(tpl,(round(340*scale),round(24*scale)));_,score,_,loc=cv2.minMaxLoc(cv2.matchTemplate(gray,t,cv2.TM_CCOEFF_NORMED))
  if score>best[0]:best=score,loc,scale
 if best[0]>.90:
  score,loc,s=best;x,y=loc[0]+2300,loc[1]+500;box=[max(0,x-4),max(0,y-4),3840-max(0,x-4),math.ceil(24*s)+8];q['frames'].setdefault(str(n),[]).append({'box':box,'id':'QI001','kind':'http(s)','box_method':'reviewed_prefix_template','origin':'review_source_template','template_score':round(score,4),'review_basis':'Human confirmed explicit public Skills URL in right embedded source screenshot; current-frame prefix determines position/scale; URL extends to right image edge'});found.append((n,box,score));
  if n in[20001,20020,20030,20036,20042,20043,20246,20290,20300,20350]:cv2.imwrite(str(P/f'qa_source_{n}.jpg'),a)
q['notes'].append('Targeted embedded screenshot URL prefix templates in source19950..20279; current-frame source evidence, entire URI to right edge, no URL text persisted.')
(P/'qa_part02_edges.json').write_text(json.dumps(q,ensure_ascii=False,indent=2));print('found',len(found),'first',found[:2],'last',found[-2:])
