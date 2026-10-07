from pathlib import Path
import json,cv2,numpy as np,subprocess,time,shutil
ROOT=Path(__file__).resolve().parents[2];W=ROOT/'work/real-video-audit';OUT=ROOT/'outputs/带封面-前5分钟';BACK=W/'first-pass';BACK.mkdir(exist_ok=True)
for name in ['report.json','redacted.mp4']:
 if not (BACK/name).exists():shutil.copy2(OUT/name,BACK/name)
r=json.loads((BACK/'report.json').read_text()); removed=0;added=0
for f in r['frames']:
 keep=[i for i,d in enumerate(f['regions']) if d['id']not in {'U012','U015','U083','U133'}];removed+=len(f['boxes'])-len(keep)
 for key in ['boxes','regions','origins']:f[key]=[f[key][i]for i in keep]
for file in ['qa-models-boxes.json','qa-extra-boxes.json']:
 extra=json.loads((W/file).read_text())
 for key,regions in extra['frames'].items():
  f=r['frames'][int(key)]
  for d in regions:
   b=d['box'];x,y,w,h=b;b=[max(0,x),max(0,y),min(w,3840-max(0,x)),min(h,2160-max(0,y))]
   if min(b[2:])<=0:continue
   # Skip a reviewed word if it is already entirely enclosed by a valid box.
   if d['id']=='M001'and any(a<=b[0]and c<=b[1]and a+ww>=b[0]+b[2]and c+hh>=b[1]+b[3]for a,c,ww,hh in f['boxes']):continue
   f['boxes'].append(b);f['origins'].append(d['origin']);f['regions'].append({k:v for k,v in d.items()if k!='box'});added+=1
r['masked_frames']=sum(bool(f['boxes'])for f in r['frames']);r['repairs']={'false_positive_regions_removed':removed,'reviewed_regions_added':added,'removed_id_reasons':{'U012':'local filename follow.opml','U015':'Python module urllib.parse','U083':'chapter navigation','U133':'HOME transition text'},'methods':['local ROI OCR for visually reviewed Models.dev','source template reacquisition for URL prefixes and dynamic size','reviewed blue URL row segmentation for long tails'],'caption_compositing':'Orange foreground caption pixels and 2px edges are preserved over the repaired rectangular URL masks.'}
(W/'final-report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print('report ready',r['masked_frames'],removed,added,flush=True)
# Render directly from original lossless-normalized frames, preserving source
# pixels when removing incorrect first-pass masks. Copy already verified audio.
cap=cv2.VideoCapture(str(W/'normalized-first300.mkv'));err=open(W/'repair-encode.log','w');silent=W/'final-silent.mp4'
enc=subprocess.Popen(['ffmpeg','-v','error','-nostdin','-y','-f','rawvideo','-pix_fmt','bgr24','-s','3840x2160','-r','30','-i','pipe:0','-an','-c:v','libx264','-threads','8','-crf','18','-preset','fast','-pix_fmt','yuv420p','-map_metadata','-1',str(silent)],stdin=subprocess.PIPE,stderr=err)
started=time.monotonic()
try:
 for n,f in enumerate(r['frames']):
  ok,im=cap.read();assert ok,(n,'decode incomplete');original=im.copy() if any(d.get('preserve_orange_caption') for d in f['regions']) else None
  for b,d in zip(f['boxes'],f['regions']):
   x,y,w,h=b
   if d.get('preserve_orange_caption'):
    if original is None:original=im.copy()
    roi=original[y:y+h,x:x+w];hsv=cv2.cvtColor(roi,cv2.COLOR_BGR2HSV)
    fg=cv2.inRange(hsv,np.array([3,120,110]),np.array([32,255,255]));fg=cv2.dilate(fg,np.ones((5,5),np.uint8))
    im[y:y+h,x:x+w]=112;im[y:y+h,x:x+w][fg>0]=roi[fg>0]
   else:im[y:y+h,x:x+w]=112
  enc.stdin.write(im.tobytes())
  if n%900==0:print('render',n,'elapsed',round(time.monotonic()-started),flush=True)
 enc.stdin.close();assert enc.wait()==0,'encode failure'
finally:
 cap.release();err.close()
stage=W/'final-redacted.mp4'
subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-i',str(silent),'-i',str(BACK/'redacted.mp4'),'-map','0:v','-map','1:a?','-c','copy','-t','300','-map_metadata','-1','-map_chapters','-1','-movflags','+faststart',str(stage)],check=True)
shutil.move(stage,OUT/'redacted.mp4');shutil.copy2(W/'final-report.json',OUT/'report.json');print('FINAL OUTPUT READY',round(time.monotonic()-started),flush=True)
