import cv2,json,subprocess,sys
import numpy as np
from pathlib import Path
sys.path.insert(0,'work/full-video');from qa_shell_continuation import Vision
W=Path('work/revision-v3');D=W/'middle_proof';v=Vision(D);a=[]
p=subprocess.Popen(['ffmpeg','-v','error','-reinit_filter','0','-ss','530','-i','/Users/carl/Downloads/带封面.mp4','-frames:v','632','-vf','scale=1920:1080','-pix_fmt','bgr24','-f','rawvideo','pipe:1'],stdout=subprocess.PIPE)
for f in range(15900,16532):
 buf=p.stdout.read(1920*1080*3);assert len(buf)==1920*1080*3;im=np.frombuffer(buf,np.uint8).reshape(1080,1920,3)
 obs=v.read(im[:100].copy());hits=[z for z in obs if 'Users' in z['text'] or 'carl' in z['text'] or 'Downloads' in z['text']];a.append({'frame':f,'ocr':obs,'hits':hits})
 if hits and(f%30==0 or f<16196):cv2.imwrite(str(D/f'top_probe_{f}.jpg'),im[:100])
 if f%60==0:print(f,'hits',len(hits),flush=True)
p.stdout.close();assert p.wait()==0;v.close();(W/'middle_top_source_audit.json').write_text(json.dumps(a,ensure_ascii=False));print('DONE',len(a),flush=True)
