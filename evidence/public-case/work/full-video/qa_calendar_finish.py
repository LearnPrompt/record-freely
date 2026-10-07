# coding: utf-8
import sys,cv2,json,numpy as np
from pathlib import Path
sys.path.insert(0,'work/full-video');import qa_calendar_continuation as q
base=Path('work/full-video');r=json.loads((base/'qa_calendar_boxes.json').read_text());cap=cv2.VideoCapture(q.SOURCE);ts=q.templates()
for n in [35906,35907,35908,35909]:
 cap.set(cv2.CAP_PROP_POS_FRAMES,n);ok,im=cap.read();assert ok
 a=q.locate(im[700:2160,600:1800],ts);a['anchor']=[a['anchor'][0]+600,a['anchor'][1]+700];x,y=a['anchor'];s=a['scale'];regs=[]
 for role,dy,w,h in [('head',3,1295,51),('tail',96,254,40)]:
  x0=max(0,int(x-6*s));y0=max(0,int(y+(dy-3)*s));x1=min(im.shape[1],int(x+(w+10)*s));y1=min(im.shape[0],int(y+(dy+h+4)*s))
  patch=cv2.cvtColor(im[y0:y1,x0:x1],cv2.COLOR_BGR2GRAY);gy,gx=np.where(patch<235)
  assert len(gx)>30,n
  lx,ly=int(x0+gx.min()),int(y0+gy.min());rx,ry=int(x0+gx.max()+1),int(y0+gy.max()+1);box=[lx-4,ly-4,rx-lx+8,ry-ly+8]
  regs.append({'box':box,'id':'C001','kind':'url'if role=='head'else'continuation','box_method':'reviewed_fade_glyph','origin':'review_color_continuation','review_match_score':round(a['score'],4),'role':role,'preserve_orange_caption':False})
 r['frames'][str(n)]=regs
 r['evidence'][n-35880]['regions']=2
 print(n,[reg['box']for reg in regs])
 cv2.imwrite(str(base/f'qa_calendar_src_{n}.jpg'),im)
 for reg in regs:
  lx,ly,w,h=reg['box'];im[ly:ly+h,lx:lx+w]=112
 cv2.imwrite(str(base/f'qa_calendar_expected_{n}.jpg'),im)
r['notes'].append('Frames 35906–35909 calendar fades weaken blue saturation and split the header color run. Actual native source prefix match plus reviewed glyph geometry and dark-pixel extent were used; no blind interpolation.')
(base/'qa_calendar_boxes.json').write_text(json.dumps(r,indent=2));cap.release()
