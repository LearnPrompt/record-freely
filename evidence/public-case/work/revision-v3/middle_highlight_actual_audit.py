import subprocess,json,cv2
import numpy as np
from pathlib import Path
from PIL import Image,ImageDraw
W=Path('work/revision-v3');D=W/'middle_proof'
def stream(path,ss):
 return subprocess.Popen(['ffmpeg','-v','error','-threads','2','-filter_threads','2','-reinit_filter','0','-ss',str(ss),'-i',str(path),'-frames:v','79','-vf','scale=1920:1080','-pix_fmt','bgr24','-f','rawvideo','pipe:1'],stdout=subprocess.PIPE)
src=stream('/Users/carl/Downloads/带封面.mp4',16100/30);out=stream(W/'chunks/part-01/redacted.mp4',(16100-9000)/30);audit=[];sheet=Image.new('RGB',(1100,11*100));draw=ImageDraw.Draw(sheet)
for f in range(16100,16179):
 images=[]
 for p in [src,out]:
  buf=p.stdout.read(1920*1080*3);assert len(buf)==1920*1080*3;images.append(np.frombuffer(buf,np.uint8).reshape(1080,1920,3))
 a,b=images;inner=b[558:586,152:329];taildiff=float(np.mean(np.abs(a[553:590,334:750].astype(float)-b[553:590,334:750].astype(float))));std=float(inner.std());white=int((inner.min(axis=2)>180).sum());assert white==0,(f,white);assert std<4,(f,std)
 audit.append({'frame':f,'box':[296,1108,368,72],'interior_gray_std':std,'white_pixels_inside':white,'preserved_directory_mean_pixel_delta':taildiff})
 if 16137<=f<=16147:
  k=f-16137;draw.text((0,k*100),str(f),fill='white')
  for i,im in enumerate(images):sheet.paste(Image.fromarray(cv2.cvtColor(im[548:592,140:690],cv2.COLOR_BGR2RGB)),(i*550,k*100+20))
for p in [src,out]:p.stdout.close();assert p.wait()==0
sheet.save(D/'highlight_actual_all_11.jpg');(W/'middle_highlight_actual_audit.json').write_text(json.dumps({'frames':[16100,16178],'frame_count':79,'all_identity_interiors_no_white_pixels':True,'max_gray_std':max(z['interior_gray_std']for z in audit),'max_directory_pixel_delta':max(z['preserved_directory_mean_pixel_delta']for z in audit),'audit':audit},indent=2));print('79 actual passed',max(z['interior_gray_std']for z in audit))
