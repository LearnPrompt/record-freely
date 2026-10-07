from pathlib import Path
import json,cv2,numpy as np,subprocess,time,shutil
ROOT=Path(__file__).resolve().parents[2];W=ROOT/'work/real-video-audit';OUT=ROOT/'outputs/带封面-前5分钟';FULL=OUT/'redacted.mp4';r=json.load(open(W/'trim-patch-report.json'))
raw=subprocess.check_output(['ffprobe','-v','error','-skip_frame','nokey','-select_streams','v:0','-show_frames','-show_entries','frame=pts_time','-of','json',str(FULL)])
keys=[float(f['pts_time'])for f in json.loads(raw)['frames']];t=next(t for t in keys if t>=76);n=round(t*30);print('prefix cut',t,n,flush=True)
cap=cv2.VideoCapture(str(W/'normalized-first300.mkv'));prefix=W/'trimmed-prefix.mp4';err=open(W/'trim-encode.log','w');started=time.monotonic()
enc=subprocess.Popen(['ffmpeg','-v','error','-nostdin','-y','-f','rawvideo','-pix_fmt','bgr24','-s','3840x2160','-r','30','-i','pipe:0','-an','-c:v','libx264','-threads','8','-crf','18','-preset','fast','-pix_fmt','yuv420p','-map_metadata','-1',str(prefix)],stdin=subprocess.PIPE,stderr=err)
for k in range(n):
 ok,im=cap.read();assert ok;f=r['frames'][k];original=im.copy()if any(d.get('preserve_orange_caption')for d in f['regions'])else None
 for b,d in zip(f['boxes'],f['regions']):
  x,y,w,h=b
  if d.get('preserve_orange_caption'):
   roi=original[y:y+h,x:x+w];hsv=cv2.cvtColor(roi,cv2.COLOR_BGR2HSV);fg=cv2.inRange(hsv,np.array([3,120,110]),np.array([32,255,255]));fg=cv2.dilate(fg,np.ones((5,5),np.uint8));im[y:y+h,x:x+w]=112;im[y:y+h,x:x+w][fg>0]=roi[fg>0]
  else:im[y:y+h,x:x+w]=112
 enc.stdin.write(im.tobytes())
 if k%900==0:print('trim prefix',k,round(time.monotonic()-started),flush=True)
enc.stdin.close();assert enc.wait()==0;err.close();cap.release()
tail=W/'unchanged-tail.mp4';subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-ss',str(t),'-i',str(FULL),'-an','-c:v','copy','-t',str(300-t),str(tail)],check=True)
def frames(p):
 j=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=nb_frames,duration','-of','json',str(p)]));return int(j['streams'][0]['nb_frames'])
assert frames(prefix)==n;(print('tail frames',frames(tail),flush=True));assert frames(tail)==9000-n
playlist=W/'trim-concat.txt';playlist.write_text(f"file '{prefix}'\nduration {n/30:.10f}\nfile '{tail}'\nduration {(9000-n)/30:.10f}\n")
stage=W/'trim-final.mp4';subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-f','concat','-safe','0','-i',str(playlist),'-i',str(FULL),'-map','0:v:0','-map','1:a?','-c','copy','-t','300','-map_metadata','-1','-map_chapters','-1','-movflags','+faststart',str(stage)],check=True)
assert frames(stage)==9000
r['repairs']['prefix_reencode']={'cut_frame':n,'cut_seconds':n/30,'remaining_video_stream_copied':True,'all_audio_stream_copied':True};shutil.move(stage,FULL);(OUT/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));(W/'final-report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print('FINAL TRIM OUTPUT READY',round(time.monotonic()-started),flush=True)
