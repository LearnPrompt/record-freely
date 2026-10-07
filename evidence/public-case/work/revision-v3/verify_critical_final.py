# -*- coding: utf-8 -*-
from pathlib import Path
import json,subprocess
W=Path(__file__).resolve().parent;OUT=W.parents[1]/'outputs/带封面-修正版v3'
m=json.loads((W/'manifest.json').read_text());points=[1856,2264,11808,11809,12003,12012,12013,16100,16137,16139,16140,16144,16147,16178,16179,16190,16191,16192,16193,16194,16531,16532]
def native(path,n):
 start=max(0,n//30-1)
 data=subprocess.check_output(['ffmpeg','-v','error','-nostdin','-threads','4','-ss',str(start),'-reinit_filter','0','-i',str(path),'-an','-vf',f'select=eq(n\\,{n-start*30})','-frames:v','1','-vsync','0','-pix_fmt','yuv420p','-f','rawvideo','pipe:1'])
 assert len(data)==12441600
 return data
rows=[]
for n in points:
 p=next(p for p in m['parts']if p['start_frame']<=n<p['start_frame']+p['frames'])
 equal=native(OUT/'redacted.mp4',n)==native(W/'chunks'/p['name']/'redacted.mp4',n-p['start_frame'])
 assert equal,n;rows.append({'global_frame':n,'seconds':n/30,'chunk':p['name'],'native_yuv_pixel_equal':equal})
proof=OUT/'合并画面验证.json';d=json.loads(proof.read_text());seen={r['global_frame']for r in d['samples']};d['samples']+= [r for r in rows if r['global_frame']not in seen];d['samples'].sort(key=lambda r:r['global_frame']);d['actual_frame_points']=len(d['samples']);d['critical_corrections_in_final_movie']='Skill first/last cropped glyphs, three-row source association highlight missing rows, clipped top identity and protected navigation checked in assembled output';proof.write_text(json.dumps(d,ensure_ascii=False,indent=2));print('CRITICAL FINAL FRAMES PASSED',len(rows),'total',d['actual_frame_points'],flush=True)
