import json,cv2,subprocess
import numpy as np
from pathlib import Path
from PIL import Image,ImageDraw
W=Path('work/revision-v3');D=W/'middle_proof';patch=json.load(open(W/'middle_top_patch.json'));report=json.load(open(W/'chunks/part-01/report.json'));asset=cv2.imread(str(W/'middle_nav_glyphs.png'),cv2.IMREAD_UNCHANGED)
nav=np.zeros((1080,1920),np.uint8);nav[19:54,205:490]=cv2.resize(asset[:,:,3],(285,35));nav=cv2.dilate(nav,np.ones((3,3),np.uint8));audit=[]
p=subprocess.Popen(['ffmpeg','-v','error','-threads','2','-filter_threads','2','-reinit_filter','0','-ss',str((16190-9000)/30),'-i',str(W/'chunks/part-01/redacted.mp4'),'-frames:v','342','-vf','scale=1920:1080','-pix_fmt','bgr24','-f','rawvideo','pipe:1'],stdout=subprocess.PIPE)
for f in range(16190,16532):
 buf=p.stdout.read(1920*1080*3);assert len(buf)==1920*1080*3;im=np.frombuffer(buf,np.uint8).reshape(1080,1920,3);z=patch['frames'][str(f)]['add'][0];b=z['box'];actual=[bb for bb,r in zip(report['frames'][f-9000]['boxes'],report['frames'][f-9000]['regions'])if r.get('box_method')==z['box_method']];assert b in actual,(f,actual)
 x,y,w,h=[q//2 for q in b];roi=im[y+1:y+h-1,x+2:x+w-2];allow=nav[y+1:y+h-1,x+2:x+w-2] if f<=16193 else np.zeros(roi.shape[:2],np.uint8);white=int(((roi.min(axis=2)>180)&(allow==0)).sum());assert white==0,(f,white);audit.append({'frame':f,'box':b,'non_navigation_identity_white_pixels':white})
 if f in [16190,16191,16192,16193,16194,16195,16200,16531]:cv2.imwrite(str(D/f'top_actual_{f}.jpg'),im[:100])
p.stdout.close();assert p.wait()==0
fs=[16190,16191,16192,16193,16194,16195,16200,16531];out=Image.new('RGB',(1000,len(fs)*120));d=ImageDraw.Draw(out)
for k,f in enumerate(fs):out.paste(Image.open(D/f'top_actual_{f}.jpg').crop((0,0,1000,100)),(0,k*120+20));d.text((0,k*120),str(f),fill='white')
out.save(D/'top_actual_sheet.jpg');(W/'middle_top_actual_audit.json').write_text(json.dumps({'frame_count':342,'range':[16190,16531],'actual_report_geometry_matches':True,'identity_white_pixels_outside_fixed_nav_glyph_mask':0,'audit':audit},indent=2));print('342 actual checks passed')
