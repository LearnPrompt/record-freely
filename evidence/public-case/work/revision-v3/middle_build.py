import cv2,json,subprocess,math,hashlib,time
import numpy as np
from pathlib import Path
W=Path('work/revision-v3');D=W/'middle_proof';V2=Path('work/revision-v2/chunks/part-01/report.json');report=json.load(open(V2));patch={};audit=[]
cv2.setNumThreads(2)
def source_frames(start,n):
 args=['ffmpeg','-v','error','-threads','2','-filter_threads','2','-reinit_filter','0','-ss',f'{start/30:.10f}','-i','/Users/carl/Downloads/带封面.mp4','-frames:v',str(n),'-vf','scale=1920:1080','-pix_fmt','bgr24','-f','rawvideo','pipe:1']
 p=subprocess.Popen(args,stdout=subprocess.PIPE);size=1920*1080*3
 for f in range(start,start+n):
  buf=p.stdout.read(size);assert len(buf)==size,(f,len(buf));yield f,np.frombuffer(buf,np.uint8).reshape((1080,1920,3)).copy()
 p.stdout.close();assert p.wait()==0
def row(f):return report['frames'][f-9000]
def update(f,rem,adds):
 z=patch.setdefault(str(f),{'remove_indexes':[],'add':[]});z['remove_indexes']=sorted(set(z['remove_indexes']+rem));z['add']+=adds
def anchor_templates(frames,kind):
 out=[]
 for f in frames:
  im=cv2.imread(str(D/f'source_{f}.jpg'));obs=json.load(open(D/f'ocr_{f}.json'))
  for z in obs:
   txt=z['text'];token='https://clawhub.ai' if kind=='skill' else '/Users/carl/';a=txt.find(token)
   if a<0:continue
   if kind=='skill' and f==12823:continue # subtitle truncated URL; use clear font anchors
   x,y,w,h=z['box'];pitch=w*1920/len(txt);xx=x*1920+a*pitch;ww=pitch*len(token);yy=y*1080
   if yy<60:continue
   # Tight domain retains the slash that begins author/skill. Path includes final slash.
   x0=round(xx)-1;y0=math.floor(yy)-2;x1=round(xx+ww)-1;y1=math.ceil(yy+h*1080)+2
   t=cv2.cvtColor(im[y0:y1,x0:x1],cv2.COLOR_BGR2GRAY)
   out.append({'frame':f,'template':t,'x':x0,'y':y0,'w':x1-x0,'h':y1-y0})
 return out
skills=anchor_templates([11808,11970,12030,12204,12930,12999,13008],'skill')
print('skill anchors',len(skills),flush=True)
for f,im in source_frames(11808,1201):
 g=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY);r=row(f);ids=[i for i,z in enumerate(r['regions'])if z.get('kind')=='reviewed_url'];adds=[]
 for i in ids:
  x,y,w,h=r['boxes'][i]
  if 12821<=f<=12985:
   b=[x,y,round((w-8)*18/31+4),h];score=1.
  else:
   sx=max(0,x//2-22);sy=max(60,y//2-28);ex=min(1920,(x+w)//2+30);ey=min(1080,(y+h)//2+28);best=None
   candidates=sorted(skills,key=lambda a:abs(a['h']-h/2))[:6]
   for t in candidates:
    for scale in [1.,.97,1.03,.94,1.06,.9,1.1]:
     tw=round(t['w']*scale);th=round(t['h']*scale)
     if tw>ex-sx or th>ey-sy:continue
     tt=cv2.resize(t['template'],(tw,th));result=cv2.matchTemplate(g[sy:ey,sx:ex],tt,cv2.TM_CCOEFF_NORMED);_,v,_,loc=cv2.minMaxLoc(result)
     if best is None or v>best[0]:best=(v,loc,tw,th)
     if v>.97:break
    if best and best[0]>.97:break
   assert best and best[0]>.6,(f,i,best[0]if best else None)
   score,(dx,dy),tw,th=best;b=[(sx+dx)*2,(sy+dy)*2,tw*2,th*2]
  adds.append({'box':b,'id':'middle_v3_skill_host','origin':'review_v3','kind':'reviewed_url','protected_suffix':True,'preserve_review_bounds':True,'preserve_orange_caption':True,'box_method':'source_host_pixels_two_path_segments_retained'})
  audit.append({'frame':f,'target':'skill','old_index':i,'old_box':r['boxes'][i],'new_box':b,'score':round(score,5)})
 if ids:update(f,ids,adds)
 if f in [11808,11970,12030,12204,12821,12822,12823,12907,12913,12920,12930,12985,12999,13008]:
  prev=im.copy()
  for z in adds:
   x,y,w,h=[v//2 for v in z['box']];prev[y:y+h,x:x+w]=[116,116,116]
  cv2.imwrite(str(D/f'skill_preview_{f}.jpg'),prev)
 if f%300==0:print('skill',f,flush=True)
(W/'middle_skill_patch.json').write_text(json.dumps({'fps':30,'index_basis':'revision-v2-current','report_sha256':hashlib.sha256(V2.read_bytes()).hexdigest(),'frames':patch}));(W/'middle_skill_audit.json').write_text(json.dumps(audit));print('skill frozen',len(patch),len(audit),flush=True)
