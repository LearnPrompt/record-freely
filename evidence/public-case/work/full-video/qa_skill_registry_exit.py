import cv2,numpy as np,json
from pathlib import Path
from PIL import Image,ImageDraw
P=Path(__file__).parent;a=cv2.imread(str(P/'qa_source_17850.jpg'));t=cv2.cvtColor(a[1189:1248,196:1081],cv2.COLOR_BGR2GRAY);ts=[(float(s),cv2.resize(t,None,fx=s*.5,fy=s*.5))for s in np.arange(.60,1.25,.01)]
c=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');c.set(1,18117);fs={};checks=[];pr=[]
for n in range(18117,18131):
 ok,a=c.read();assert ok;g=cv2.resize(cv2.cvtColor(a[:1700,:2000],cv2.COLOR_BGR2GRAY),None,fx=.5,fy=.5);best=(-1,None,None)
 for s,t2 in ts:
  _,q,_,l=cv2.minMaxLoc(cv2.matchTemplate(g,t2,cv2.TM_CCOEFF_NORMED))
  if q>best[0]:best=(q,l,s)
 q,l,s=best;box=None
 if q>.70 and n<=18118:
  x,y=l[0]*2,l[1]*2;box=[x-4,y-4,int(round(608*s))+8,int(round(45*s))+8];fs[str(n)]=[{'box':box,'id':'SR002','kind':'domain','box_method':'reviewed_word','origin':'review_public_host_suffix_template','template_score':round(q,4)}];cv2.rectangle(a,(box[0],box[1]),(box[0]+box[2],box[1]+box[3]),(0,0,255),2);roi=a[max(0,y-55):y+int(59*s)+60,max(0,x-60):x+int(885*s)+50]
 else:roi=a[:750,:2500]
 im=Image.fromarray(cv2.cvtColor(roi,cv2.COLOR_BGR2RGB));im.thumbnail((1550,170));pr.append((n,q,im));checks.append({'frame':n,'score':round(q,4),'box':box})
c.release();json.dump({'status':'pending_source_review','frames':fs,'checked_windows':[[18117,18130]],'notes':['Existing skill-label exit only; suffix-confirmed host word, retain @ffmpeg.']},open(P/'qa_skill_registry_exit.json','w'),indent=2);json.dump(checks,open(P/'qa_skill_registry_exit_checks.json','w'),indent=2);sh=Image.new('RGB',(1600,len(pr)*200),'white');d=ImageDraw.Draw(sh)
for i,(n,q,im)in enumerate(pr):d.text((10,i*200+5),f'{n} score{q:.3f}',fill='black');sh.paste(im,(10,i*200+28))
sh.save(P/'qa_skill_registry_exit_sourceproof.jpg',quality=94);print(checks)
