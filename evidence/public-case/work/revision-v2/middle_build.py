import sys,json,re,cv2,numpy as np,tempfile,time
from pathlib import Path
sys.path.insert(0,'work/full-video');from qa_shell_continuation import Vision
from stream_capture import StreamCapture
W=Path('work/revision-v2');SRC='/Users/carl/Downloads/带封面.mp4'
WINDOWS=[('skill',375,442),('pathA',440,530),('pathB',530,570),('html',840,898),('wrong',940,1010)]
def targets(obs,kind):
 out=[]
 for o in obs:
  txt=o['text'];match=None
  if kind=='skill': match=re.search(r'https?://clawhub\.ai/[^\s/]+/',txt,re.I)
  elif kind in ['pathA','pathB','wrong']:match=re.search(r'/Users/carl/',txt,re.I)
  else: match=re.search(r'\.html\b',txt,re.I)
  if not match:continue
  # These source-confirmed terminal tokens use a monospaced font. Ignore
  # Vision's per-character boxes when all are duplicates of the whole word.
  x,y,w,h=o['box'];a,b=match.span()
  txtlen=len(txt);x=x+w*a/txtlen;w=w*(b-a)/txtlen
  out.append({'box':[round(x*1920)-3,round(y*1080)-3,round(w*1920)+6,round(h*1080)+6],'kind':kind})
 return out
ocr=Vision(W);allanchors={};notes=[]
try:
 for kind,lo,hi in WINDOWS:
  c=cv2.VideoCapture(SRC);anchors=[]
  for f in range(lo*30,hi*30,30):
   c.set(cv2.CAP_PROP_POS_FRAMES,f);ok,im=c.read()
   if not ok:raise RuntimeError('Source seek failed')
   im=cv2.resize(im,(1920,1080)); obs=ocr.read(im);ts=targets(obs,kind)
   if ts:
    entries=[]
    for t in ts:
     x,y,w,h=t['box'];x=max(0,x);y=max(0,y);w=min(w,1920-x);h=min(h,1080-y)
     if y<60:continue # opaque chapter overlay obscures underlying terminal glyphs
     if w<8 or h<8:continue
     t['box']=[x,y,w,h];t['template']=cv2.cvtColor(im[y:y+h,x:x+w],cv2.COLOR_BGR2GRAY);entries.append(t)
    if entries:anchors.append((f,entries));cv2.imwrite(str(W/f'middle_{kind}_anchor_{f}.jpg'),im)
  c.release()
  if kind in ['pathA','pathB']:
   groups=[]
   for a in anchors:
    if not groups or a[0]-groups[-1][-1][0]>90:groups.append([])
    groups[-1].append(a)
   focus={'pathA':485*30,'pathB':537*30}[kind]
   anchors=min(groups,key=lambda g:min(abs(focus-a[0])for a in g))
  allanchors[kind]=anchors
  print(kind,[(a,len(b))for a,b in anchors],flush=True)
finally:ocr.close()
# Track full target patch using nearest OCR geometry, source pixels each frame.
reports=[]
for p in range(1,8):
 r=json.load(open(f'work/full-video/chunks/part-{p:02d}/report.json'));reports.append((r['source_start_frame'],r['frames']))
def old(f):
 for start,rs in reports:
  if start<=f<start+len(rs):return rs[f-start]
 raise RuntimeError(f'No report {f}')
patch={};proof={}
for kind,lo,hi in WINDOWS:
 anchors=allanchors[kind]
 if not anchors:continue
 # Expand scout-positive bounds by 2 sec; the adjacent source frame match
 # decides appearance/disappearance, rather than an inherited static bar.
 first=max(lo*30,anchors[0][0]-60);last=min(hi*30,anchors[-1][0]+90)
 cap=StreamCapture(SRC,first/30,last-first)
 found=[];scores=[]
 for f in range(first,last):
  ok,im=cap.read()
  if not ok:raise RuntimeError('Decode failed')
  im=cv2.cvtColor(cv2.resize(im,(1920,1080)),cv2.COLOR_BGR2GRAY); nearest=sorted(anchors,key=lambda a:abs(a[0]-f))[:2];add=[]
  for af,entries in nearest:
   for idx,t in enumerate(entries):
    x,y,w,h=t['box'];sx=max(0,x-100);sy=max(60,y-120);ex=min(1920,x+w+100);ey=min(1080,y+h+120)
    region=im[sy:ey,sx:ex];tpl=t['template'];best=None
    for scale in [1.,.97,1.03,.94,1.06]:
     if best is not None and best[0]>.88:break
     tt=cv2.resize(tpl,(max(1,round(w*scale)),max(1,round(h*scale))))
     if region.shape[0]<tt.shape[0]or region.shape[1]<tt.shape[1]:continue
     result=cv2.matchTemplate(region,tt,cv2.TM_CCOEFF_NORMED);_,v,_,loc=cv2.minMaxLoc(result)
     if best is None or v>best[0]:best=(v,loc,tt.shape)
    if best is None or best[0]<.62:continue
    v,(dx,dy),(bh,bw)=best;box=[(sx+dx)*2,(sy+dy)*2,bw*2,bh*2]
    if any(abs(box[0]-a['box'][0])<15 and abs(box[1]-a['box'][1])<15 for a in add):continue
    add.append({'box':box,'id':f'middle_{kind}_{idx}','origin':'review_v2','kind':{'skill':'reviewed_url','html':'reviewed_extension'}.get(kind,'reviewed_path'),'box_method':'source_confirmed_monospace_prefix_then_per_frame_template','preserve_orange_caption':True});scores.append(v)
  remove=[];rec=old(f)
  if kind=='skill':
   for i,b in enumerate(rec['boxes']):
    if any(abs((b[1]+b[3]/2)-(a['box'][1]+a['box'][3]/2))<25 and b[0]<a['box'][0]+a['box'][2]+20 for a in add):remove.append(i)
  elif kind=='wrong':
   for i,b in enumerate(rec['boxes']):
    if any(b[0]<a['box'][0]+120 and abs((b[1]+b[3]/2)-(a['box'][1]+a['box'][3]/2))<70 for a in add):remove.append(i)
  if add or remove:
   recp=patch.setdefault(str(f),{'remove_indexes':[],'add':[]});recp['remove_indexes']=sorted(set(recp['remove_indexes']+remove));recp['add']+=add;found.append(f)
  if f%300==0:print(kind,f,len(add),flush=True)
  if f%300==0:(W/'middle_progress.json').write_text(json.dumps({'kind':kind,'frame':f,'last':last}))
 cap.release()
 if found:proof[kind]={'first_frame':min(found),'last_frame':max(found),'frames':len(found),'regions':sum(len(patch[str(f)]['add'])for f in found),'template_min_confidence':min(scores),'scout_window':[lo,hi],'source_proof_files':[f'middle_{kind}_anchor_{a}.jpg'for a,_ in anchors]}
(W/'middle_patch.json').write_text(json.dumps({'fps':30,'frames':patch},ensure_ascii=False))
(W/'middle_notes.json').write_text(json.dumps({'status':'frozen','targets':proof,'wrong_mask_evidence':'16:12 old mask covers local .hermes skill directory and its heading. Remove this false URL region and replace with home identity prefixes on two local paths.','source_ocr_text_not_published':True},ensure_ascii=False,indent=2))
print('FROZEN',len(patch),proof,flush=True)
