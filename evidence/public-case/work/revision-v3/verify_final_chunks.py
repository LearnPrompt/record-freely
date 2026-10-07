# -*- coding: utf-8 -*-
from pathlib import Path
import json,sys,numpy as np,subprocess
W=Path(__file__).resolve().parent;sys.path.insert(0,str(W));from verify_full import frame_rgb
OUT=W.parents[1]/'outputs/带封面-修正版v3'
m=json.loads((W/'manifest.json').read_text())
points={round(t*30)for t in [62,101,112,123,158,399,485,537,540,872,972,1181,1508,1538,1541,1637,1718,1929,1950,1973]}
points.update([2181,2182,2183,12821,12822,12823,12906,12907,12908,12985,26214,29150,29213,46110,46148,57870,59190])
for p in m['parts']:points.add(p['start_frame']);points.add(p['start_frame']+p['frames']-1)
def native_frame(path,n):
 start=max(0,n//30-1)
 raw=subprocess.check_output(['ffmpeg','-v','error','-nostdin','-threads','4','-ss',str(start),'-reinit_filter','0','-i',str(path),'-an','-vf',f'select=eq(n\\,{n-start*30})','-frames:v','1','-vsync','0','-pix_fmt','yuv420p','-f','rawvideo','pipe:1'])
 assert len(raw)==3840*2160*3//2
 return raw
rows=[]
for n in sorted(points):
 p=next(p for p in m['parts']if p['start_frame']<=n<p['start_frame']+p['frames'])
 a=native_frame(OUT/'redacted.mp4',n);b=native_frame(W/'chunks'/p['name']/'redacted.mp4',n-p['start_frame'])
 equal=a==b;rows.append({'global_frame':n,'seconds':n/30,'chunk':p['name'],'native_yuv_pixel_equal':equal});assert equal,(n,p['name'])
result={'status':'passed','actual_frame_points':len(rows),'method':'Independent accurate FFmpeg frame extraction; final concatenated movie native YUV420 pixels exactly match reviewed chunks. Native comparison avoids RGB conversion differences from input color metadata.','samples':rows}
(OUT/'合并画面验证.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print('FINAL CHUNK PIXEL IDENTITY PASSED',len(rows),flush=True)
