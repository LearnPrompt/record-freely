import cv2,json,subprocess,math,hashlib
import numpy as np
from pathlib import Path
W=Path('work/revision-v3');D=W/'middle_proof';V2=Path('work/revision-v2/chunks/part-01/report.json');j=json.load(open(V2));cv2.setNumThreads(2);patch={};audit=[]
templates=[]
for f in [15900,15930,16200]:
 im=cv2.imread(str(D/f'source_{f}.jpg'));obs=json.load(open(D/f'ocr_{f}.json'))
 obs=[z for z in obs if '/Users/carl/'in z['text'] and z['box'][1]*1080>60]
 z=obs[0];txt=z['text'];a=txt.index('/Users/carl/');x,y,w,h=z['box'];pitch=w*1920/len(txt);x0=round(x*1920+pitch*a)-1;x1=round(x*1920+pitch*(a+12))-1;y0=math.floor(y*1080)-2;y1=math.ceil((y+h)*1080)+2
 t=cv2.cvtColor(im[y0:y1,x0:x1],cv2.COLOR_BGR2GRAY);templates.append((t,x1-x0,y1-y0));print('anchor',f,(x0,y0,x1-x0,y1-y0),flush=True)
def iou(a,b):
 x=max(a[0],b[0]);y=max(a[1],b[1]);r=min(a[0]+a[2],b[0]+b[2]);d=min(a[1]+a[3],b[1]+b[3]);inter=max(0,r-x)*max(0,d-y);return inter/max(1,min(a[2]*a[3],b[2]*b[3]))
args=['ffmpeg','-v','error','-threads','2','-filter_threads','2','-reinit_filter','0','-ss',str(15900/30),'-i','/Users/carl/Downloads/带封面.mp4','-frames:v','632','-vf','scale=1920:1080','-pix_fmt','bgr24','-f','rawvideo','pipe:1'];p=subprocess.Popen(args,stdout=subprocess.PIPE);size=1920*1080*3
last=[]
for f in range(15900,16532):
 buf=p.stdout.read(size);assert len(buf)==size,(f,len(buf));im=np.frombuffer(buf,np.uint8).reshape(1080,1920,3).copy();g=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY);r=j['frames'][f-9000];ids=[i for i,z in enumerate(r['regions'])if z.get('kind')=='reviewed_path'];old=[r['boxes'][i]for i in ids];cands=[]
 preferred=float(np.median([b[2]/2 for b in old])) if old else (last[0][2] if last else 138)
 # All rows in this source terminal share font size. Use it only to select search
 # scales; every visible prefix must independently match source pixels.
 for tpl,tw,th in templates:
  base=preferred/tw
  for scale in sorted(set([1.,round(base,3),round(base*.97,3),round(base*1.03,3)])):
   if not .65<scale<1.4:continue
   tt=cv2.resize(tpl,(round(tw*scale),round(th*scale)));resp=cv2.matchTemplate(g[60:1080,75:850],tt,cv2.TM_CCOEFF_NORMED)
   while True:
    _,v,_,loc=cv2.minMaxLoc(resp)
    if v<.72:break
    dx,dy=loc;box=[75+dx,60+dy,tt.shape[1],tt.shape[0]];cands.append((v,box));xx=max(0,dx-tt.shape[1]//2);yy=max(0,dy-tt.shape[0]//2);resp[yy:min(resp.shape[0],dy+tt.shape[0]//2+1),xx:min(resp.shape[1],dx+tt.shape[1]//2+1)]=-1
 chosen=[]
 for v,b in sorted(cands,reverse=True):
  if not any(iou(b,z[1])>.35 for z in chosen):chosen.append((v,b))
 chosen.sort(key=lambda z:z[1][1]);adds=[];new=[]
 for k,(v,b)in enumerate(chosen):
  x,y,w,h=b
  # A canonical font envelope avoids OCR-anchor-dependent tall/short rectangles.
  hh=round(w/182*36);cy=y+h/2;h=hh;y=round(cy-h/2);box=[x*2,y*2,w*2,h*2];new.append(box)
  adds.append({'box':box,'id':f'middle_v3_home_prefix_{k}','origin':'review_v3','kind':'reviewed_path','preserve_review_bounds':True,'preserve_orange_caption':True,'box_method':'per_frame_source_identity_template_canonical_font_height'})
 if ids or adds:patch[str(f)]={'remove_indexes':ids,'add':adds}
 uncovered=[b for b in new if not any(iou(b,o)>.85 for o in old)];audit.append({'frame':f,'old_boxes':old,'new_boxes':new,'scores':[round(v,5)for v,_ in chosen],'old_not_covering_new':uncovered});last=[b for _,b in chosen]
 if f in [15900,15930,16050,16089,16100,16170,16185,16186,16194,16200,16230,16300,16531]:
  prev=im.copy()
  for z in adds:
   x,y,w,h=[v//2 for v in z['box']];prev[y:y+h,x:x+w]=[116,116,116]
  cv2.imwrite(str(D/f'path_preview_{f}.jpg'),prev);cv2.imwrite(str(D/f'path_source_{f}.jpg'),im)
 if f%60==0:print('path',f,'old',len(old),'new',len(new),flush=True)
p.stdout.close();assert p.wait()==0
(W/'middle_path_patch.json').write_text(json.dumps({'fps':30,'index_basis':'revision-v2-current','report_sha256':hashlib.sha256(V2.read_bytes()).hexdigest(),'frames':patch}));(W/'middle_path_audit.json').write_text(json.dumps(audit));print('FROZEN',len(patch),sum(len(z['add'])for z in patch.values()),flush=True)
