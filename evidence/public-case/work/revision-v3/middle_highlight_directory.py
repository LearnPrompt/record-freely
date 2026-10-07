import json,cv2,subprocess,hashlib
import numpy as np
from pathlib import Path
W=Path('work/revision-v3');D=W/'middle_proof'
P=W/'middle_path_patch.json';A=W/'middle_path_audit.json';patch=json.loads(P.read_text());audit=json.loads(A.read_text());cv2.setNumThreads(2)
im=cv2.imread(str(D/'source_16200.jpg'));tpl=cv2.cvtColor(im[330:365,334:668],cv2.COLOR_BGR2GRAY)
p=subprocess.Popen(['ffmpeg','-v','error','-threads','2','-filter_threads','2','-reinit_filter','0','-ss','530','-i','/Users/carl/Downloads/带封面.mp4','-frames:v','632','-vf','scale=1920:1080','-pix_fmt','bgr24','-f','rawvideo','pipe:1'],stdout=subprocess.PIPE)
fix=[];tails=[]
for a in audit:
 f=a['frame'];buf=p.stdout.read(1920*1080*3);assert len(buf)==1920*1080*3;im=np.frombuffer(buf,np.uint8).reshape(1080,1920,3).copy();g=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
 # Independent unhighlighted identity tail plus Downloads localizes the row.
 resp=cv2.matchTemplate(g[60:1080,75:850],tpl,cv2.TM_CCOEFF_NORMED);matches=[]
 while True:
  _,v,_,loc=cv2.minMaxLoc(resp)
  if v<.80:break
  x,y=loc;x+=75;y+=60;b=[(x-184-2)*2,y*2,368,72];matches.append((v,b))
  dx,dy=loc;resp[max(0,dy-18):dy+19,max(0,dx-100):dx+101]=-1
 for v,b in matches:
  existing=[z for z in patch['frames'].get(str(f),{}).get('add',[])if abs(z['box'][1]-b[1])<20 and abs(z['box'][0]-b[0])<20]
  if not existing:
   z={'box':b,'id':'middle_v3_highlight_home_prefix','origin':'review_v3','kind':'reviewed_path','preserve_review_bounds':True,'preserve_orange_caption':False,'box_method':'unhighlighted_carl_Downloads_source_tail_font_pitch_identity_prefix'}
   patch['frames'][str(f)]['add'].append(z);a['new_boxes'].append(b);a['scores'].append(round(v,5));fix.append({'frame':f,'box':b,'score':round(v,5)})
  tails.append({'frame':f,'box':b,'score':round(v,5),'added':not bool(existing)})
 if f in range(16134,16150):
  cv2.imwrite(str(D/f'highlight_source_{f}.jpg'),im)
  for z in patch['frames'][str(f)]['add']:
   x,y,w,h=[q//2 for q in z['box']];im[y:y+h,x:x+w]=116
  cv2.imwrite(str(D/f'highlight_preview_{f}.jpg'),im)
 assert all(0<=b[0] and 0<=b[1] and b[0]+b[2]<=3840 and b[1]+b[3]<=2160 for b in a['new_boxes'])
p.stdout.close();assert p.wait()==0
P.write_text(json.dumps(patch));A.write_text(json.dumps(audit));(W/'middle_highlight_directory_audit.json').write_text(json.dumps({'source_range':[15900,16531],'added':fix,'all_tail_matches':tails},indent=2));print('ADDED',fix,flush=True)
