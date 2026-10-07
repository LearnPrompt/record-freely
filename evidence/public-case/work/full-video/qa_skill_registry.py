from pathlib import Path
import cv2,numpy as np,json
from PIL import Image,ImageDraw
P=Path(__file__).parent
src='/Users/carl/Downloads/带封面.mp4'
seed=cv2.imread(str(P/'qa_source_17850.jpg'))
tpl=cv2.cvtColor(seed[1189:1235,196:804],cv2.COLOR_BGR2GRAY)
# Confirmed host word only; final @ffmpeg remains outside the template and mask.
scales=np.arange(.60,1.401,.025)
templates=[(float(s),cv2.resize(tpl,None,fx=s*.5,fy=s*.5)) for s in scales]
cap=cv2.VideoCapture(src);cap.set(cv2.CAP_PROP_POS_FRAMES,17790)
frames={};matches=[];proof=[]
for n in range(17790,18117):
 ok,a=cap.read();assert ok
 g=cv2.cvtColor(a[150:1700,:1900],cv2.COLOR_BGR2GRAY);g=cv2.resize(g,None,fx=.5,fy=.5)
 best=(-1,None,None,None)
 for scale,t in templates:
  r=cv2.matchTemplate(g,t,cv2.TM_CCOEFF_NORMED);_,score,_,loc=cv2.minMaxLoc(r)
  if score>best[0]: best=(score,loc,t.shape,scale)
 score,loc,shape,scale=best
 if score<.69:
  matches.append({'frame':n,'found':False,'score':round(score,4)});continue
 # Refine 0.025 coarse steps to 0.005 without assuming any temporal interpolation.
 for s in np.arange(max(.55,scale-.02),min(1.45,scale+.02)+.001,.005):
  t=cv2.resize(tpl,None,fx=s*.5,fy=s*.5);r=cv2.matchTemplate(g,t,cv2.TM_CCOEFF_NORMED);_,q,_,l=cv2.minMaxLoc(r)
  if q>score:score,loc,shape,scale=q,l,t.shape,float(s)
 x,y=loc[0]*2,loc[1]*2+150;h,w=shape[0]*2,shape[1]*2
 # Tight text word with four-pixel margins, excluding the adjacent @ character.
 box=[max(0,x-4),max(0,y-4),w+8,h+8]
 frames[str(n)]=[{'box':box,'id':'SR001','kind':'domain','box_method':'reviewed_word','origin':'review_public_host_template','template_score':round(float(score),4),'template_scale':round(scale,4)}]
 matches.append({'frame':n,'found':True,'score':round(float(score),4),'box':box})
 if n in [17790,17800,17805,17812,17850,17860,17861,17999,18000,18030,18065,18090,18115,18116]:
  im=a.copy();cv2.rectangle(im,(box[0],box[1]),(box[0]+box[2],box[1]+box[3]),(0,0,255),2)
  proof.append((n,im[max(0,y-60):y+h+90,max(0,x-80):min(3840,x+w+500)]))
cap.release()
# Final-frame suffix-confirmed label: reject tie with host inside a different URI.
frames['18116']=[{'box':[357,386,474,43],'id':'SR001','kind':'domain','box_method':'reviewed_word','origin':'reviewed_current_frame_glyph'}]
out={'status':'pending_visual_review','frames':frames,'remove_ids':[],'checked_windows':[[17790,18116]],'notes':['Only confirmed public domain word in skill label; retain @ffmpeg. Current-source-frame multiscale template, no temporal interpolation. Private URL text is not stored.']}
json.dump(out,open(P/'qa_skill_registry.json','w'),ensure_ascii=False,indent=2)
json.dump(matches,open(P/'qa_skill_registry_matches.json','w'),indent=2)
sh=Image.new('RGB',(1600,180*len(proof)),'white');d=ImageDraw.Draw(sh)
for i,(n,a) in enumerate(proof):
 d.text((10,i*180+5),str(n),fill='black');im=Image.fromarray(cv2.cvtColor(a,cv2.COLOR_BGR2RGB));im.thumbnail((1570,145));sh.paste(im,(10,i*180+28))
sh.save(P/'qa_skill_registry_source_proof.jpg',quality=94)
print('frames',len(frames),'first',min(map(int,frames)),'last',max(map(int,frames)),'minscore',min(x['score']for x in matches if x['found']),'unmatched',[x['frame']for x in matches if not x['found']])
