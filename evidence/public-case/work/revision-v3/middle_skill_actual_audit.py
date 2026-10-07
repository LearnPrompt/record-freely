import json,subprocess
import numpy as np
from pathlib import Path
W=Path('work/revision-v3');p=json.load(open(W/'middle_skill_patch.json'));r=json.load(open(W/'chunks/part-01/report.json'));a=[];e=[]
v=subprocess.Popen(['ffmpeg','-v','error','-threads','2','-filter_threads','2','-reinit_filter','0','-ss',str((11808-9000)/30),'-i',str(W/'chunks/part-01/redacted.mp4'),'-frames:v','1201','-vf','scale=1920:1080','-pix_fmt','bgr24','-f','rawvideo','pipe:1'],stdout=subprocess.PIPE)
for f in range(11808,13009):
 buf=v.stdout.read(1920*1080*3);assert len(buf)==1920*1080*3;im=np.frombuffer(buf,np.uint8).reshape(1080,1920,3)
 if str(f)not in p['frames']:continue
 rr=r['frames'][f-9000];actual=[b for b,z in zip(rr['boxes'],rr['regions'])if z.get('kind')=='reviewed_url'];expected=[z['box']for z in p['frames'][str(f)]['add']];assert sorted(map(tuple,actual))==sorted(map(tuple,expected)),f
 for b in expected:
  x,y,w,h=[q//2 for q in b];patch=im[min(1079,y+2):min(1080,y+h-2),x+3:x+w-3]
  if patch.size:
   white=int((patch.min(axis=2)>180).sum());a.append({'frame':f,'box':b,'interior_white_pixels':white,'std':float(patch.std())})
   if white:e.append((f,white))
v.stdout.close();assert v.wait()==0
(W/'middle_skill_actual_audit.json').write_text(json.dumps({'actual_source_range':[11808,13008],'audited_regions':len(a),'report_geometry_matches_frozen':True,'interior_white_pixel_exceptions':e,'audit':a},indent=2));print('actual audit',len(a),'whiteexceptions',e[:30])
