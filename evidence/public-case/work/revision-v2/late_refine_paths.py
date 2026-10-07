import json,cv2,sys,time
from pathlib import Path
sys.path.insert(0,str(Path('work/full-video').resolve()));sys.path.insert(0,str(Path('work/revision-v2').resolve()))
from stream_capture import StreamCapture
from late_prefix_match import locate
D=Path('work/revision-v2');SRC='/Users/carl/Downloads/带封面.mp4'
while 'DONE' not in (D/'late_extra.log').read_text():time.sleep(2)
r=json.load(open(D/'late_detections.json'));r.update(json.load(open(D/'late_extra_detections.json')));r={k:[d for d in v if d['target']=='path'] for k,v in r.items()};r={k:v for k,v in r.items() if v};frames={};uncertain=[];started=time.time()
def iou(a,b):
 x,y,w,h=a;j,k,u,v=b;z=max(0,min(x+w,j+u)-max(x,j))*max(0,min(y+h,k+v)-max(y,k));return z/max(1,w*h+u*v-z)
for a,b in [(44895,46210),(48870,49576),(51180,52440)]:
 cap=StreamCapture(SRC,a/30,b-a)
 for f in range(a,b):
  ok,im=cap.read()
  if not ok:raise RuntimeError(f)
  rows=[];candidates=r.get(str(f),[])
  if not candidates:
   for delta in [1,-1,2,-2,3,-3]:
    if str(f+delta) in r:candidates=r[str(f+delta)];break
   fill=True
  else:fill=False
  for d in candidates:
   best=locate(im,d['box']);method='current_frame_identity_glyph_template'
   if best and best[0]>=(.84 if fill else .66):box=best[1];score=round(best[0],4)
   elif not fill and d['box'][2]<500 and d['box'][3]<140:box=d['box'];score=None;method='native_shared_word_ascii_geometry';uncertain.append(f)
   else:continue
   x,y,w,h=box;box=[max(0,x),max(0,y),min(3840,x+w)-max(0,x),min(2160,y+h)-max(0,y)]
   if any(iou(box,p['box'])>.7 for p in rows):continue
   rows.append({'box':box,'id':'late_path_identity','origin':'review_v2','kind':'reviewed_path','box_method':method,'template_score':score,'preserve_orange_caption':True,'preserve_white_caption':False})
  if rows:frames[str(f)]={'remove_indexes':[],'add':rows}
  if f%60==0:print(f,len(frames),round(time.time()-started),flush=True)
 cap.release()
(D/'late_path_refined.json').write_text(json.dumps({'fps':30,'frames':frames},indent=2));(D/'late_path_refine_proof.json').write_text(json.dumps({'scanned_windows':[[44895,46210],[48870,49576],[51180,52440]],'native_fallback_frames':sorted(set(uncertain)),'frame_count':len(frames),'count':sum(len(v['add']) for v in frames.values())},indent=2));print('DONE',len(frames),flush=True)
