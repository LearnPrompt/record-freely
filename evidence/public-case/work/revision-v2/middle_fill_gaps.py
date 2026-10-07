import json,cv2,sys,re
from pathlib import Path
sys.path.insert(0,'work/full-video');from qa_shell_continuation import Vision
W=Path('work/revision-v2');d=json.loads((W/'middle_patch.json').read_text());fs=d['frames'];notes=json.loads((W/'middle_notes.json').read_text());gapframes={}
for kind in ['skill','pathA','pathB','html']:
 vals=sorted(int(f)for f,r in fs.items()if any(a['id'].startswith('middle_'+kind)for a in r['add']))
 for a,b in zip(vals,vals[1:]):
  if 1<b-a<=9:
   for f in range(a+1,b):gapframes[f]=kind
c=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');o=Vision(W);added=[]
try:
 for f,kind in gapframes.items():
  c.set(cv2.CAP_PROP_POS_FRAMES,f);ok,im=c.read();assert ok;obs=o.read(im);regions=[]
  for z in obs:
   pat=r'https?://clawhub\.ai/[^\s/]+/'if kind=='skill'else(r'\.html\b'if kind=='html'else r'/Users/carl/');m=re.search(pat,z['text'],re.I)
   if not m:continue
   x,y,w,h=z['box'];a,b=m.span();L=len(z['text']);xx=round((x+w*a/L)*3840)-6;yy=round(y*2160)-6;ww=round(w*(b-a)/L*3840)+8;hh=round(h*2160)+12
   if yy<120:continue
   if kind=='html':xx+=4;ww-=4
   box=[max(0,xx),max(0,yy),ww,hh]
   if box[0]+ww>3840 or box[1]+hh>2160:continue
   neighbors=[]
   for delta in range(1,10):
    for nf in [f-delta,f+delta]:neighbors += [a for a in fs.get(str(nf),{}).get('add',[])if a['id'].startswith('middle_'+kind)]
   if not any(abs((r['box'][1]+r['box'][3]/2)-(yy+hh/2))<60 and abs(r['box'][0]-xx)<100 for r in neighbors):continue
   regions.append({'box':box,'id':'middle_'+kind+'_ocr_gap','origin':'review_v2','kind':{'skill':'reviewed_url','html':'reviewed_extension'}.get(kind,'reviewed_path'),'box_method':'current_source_frame_native_ocr_verified_short_gap','preserve_orange_caption':True,**({'protected_suffix':True}if kind=='skill'else{})})
  if regions:fs.setdefault(str(f),{'remove_indexes':[],'add':[]})['add']+=regions;added.append(f)
finally:o.close();c.release()
notes['short_gaps_current_frame_ocr_verified']=added
for kind in ['skill','pathA','pathB','html']:
 vals=sorted(int(f)for f,r in fs.items()if any(a['id'].startswith('middle_'+kind)for a in r['add']));runs=[]
 for f in vals:
  if not runs or f>runs[-1][1]+1:runs.append([f,f])
  else:runs[-1][1]=f
 notes['target_final_ranges'][kind]={'first':min(vals),'last':max(vals),'frames':len(vals),'continuous_runs':runs}
(W/'middle_patch.json').write_text(json.dumps(d,ensure_ascii=False));(W/'middle_notes.json').write_text(json.dumps(notes,ensure_ascii=False,indent=2));print('gap',len(gapframes),'added',len(added),'frames',len(fs),flush=True)
