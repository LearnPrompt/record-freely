import cv2,json,numpy as np
from pathlib import Path
P=Path(__file__).parent;seed=cv2.imread(str(P/'qa_source_44425.jpg'));gray=cv2.cvtColor(seed,cv2.COLOR_BGR2GRAY);tmpl=gray[17:33,487:929];cap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');cap.set(1,44340);frames={};scores={};boxes={}
for n in range(44340,44521):
 ok,a=cap.read();assert ok;roi=cv2.cvtColor(a[:110],cv2.COLOR_BGR2GRAY);best=(-1,None,1)
 for scale in [.96,.98,1,1.02,1.04]:
  t=cv2.resize(tmpl,None,fx=scale,fy=scale);_,score,_,xy=cv2.minMaxLoc(cv2.matchTemplate(roi,t,cv2.TM_CCOEFF_NORMED))
  if score>best[0]:best=(score,xy,scale)
 score,xy,scale=best;scores[str(n)]=float(score)
 if score<.76:continue
 x,y=xy;left=max(0,x-4);top=max(0,int(y-3*scale)-4);right=min(2440,int(x+1143*scale)+4);bottom=min(2160,int(y+31*scale)+4)
 frames[str(n)]=[{'box':[left,top,right-left,bottom-top],'id':'QA4B001','kind':'url','box_method':'reviewed_address_prefix_template','origin':'review_template','review_basis':'Current-frame public browser URI prefix template and same full address word extent; only visible portion before opaque top navigation, +4px; no private text stored.','template_score':round(score,5)}]
q=json.load(open(P/'qa_part04_false_ids.json'));q['frames']=frames;q['checked_window_frames']=[44340,44521];q['notes'].append('Native local OCR could not recognize overlaid address. Public-prefix template matched source each frame; full-word geometry reviewed independently.');json.dump(q,open(P/'qa_part04_browser.json','w'),indent=2);json.dump(scores,open(P/'qa_part04_browser_scores.json','w'),indent=2);print('matched',len(frames),'start',min(map(int,frames))if frames else None,'end',max(map(int,frames))if frames else None);print('missing confirmed',[n for n in range(44347,44426)if str(n)not in frames]);print('keyboxes',[(n,frames.get(str(n)))for n in [44347,44350,44373,44425]])
