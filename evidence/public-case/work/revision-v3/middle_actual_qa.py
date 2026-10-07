import subprocess,json,concurrent.futures
from pathlib import Path
from PIL import Image,ImageDraw
W=Path('work/revision-v3');D=W/'middle_proof';V=W/'chunks/part-01/redacted.mp4'
frames=[11808,11809,11832,11847,11848,12003,12012,12013,11970,12204,12820,12821,12822,12823,12985,12999,13008,15907,15908,15909,15944,16100,16136,16137,16139,16140,16144,16147,16148,16178,16179,16194,16200,16531]
def get(f):
 path=D/f'actual_{f}.jpg'
 subprocess.run(['ffmpeg','-v','error','-threads','2','-filter_threads','2','-reinit_filter','0','-ss',format((f-9000)/30,'.10f'),'-i',str(V),'-frames:v','1','-vf','scale=1920:1080','-q:v','2','-y',str(path)],check=True)
 return f
with concurrent.futures.ThreadPoolExecutor(max_workers=4)as p:list(p.map(get,frames))
for label,fs in [('skill',[11808,11970,12204,12820,12821,12822,12823,12985,12999,13008]),('path',[15907,15908,15909,15944,16100,16136,16137,16139,16140,16144,16147,16148,16178,16179,16194,16200,16531])]:
 for offset in range(0,len(fs),6):
  subset=fs[offset:offset+6];canvas=Image.new('RGB',(1920,len(subset)*290));draw=ImageDraw.Draw(canvas)
  for k,f in enumerate(subset):
   im=Image.open(D/f'actual_{f}.jpg');y=700 if f<=13008 else 480
   if f in [11970,12204]:y=650
   if f in [12999,13008]:y=380
   if f>=16194:y=300
   if f in [15907,15908,15909,15944]:y=750
   canvas.paste(im.crop((0,y,1920,y+260)),(0,k*290+30));draw.text((0,k*290),str(f),fill='white')
  canvas.save(D/f'actual_{label}_sheet_{offset}.jpg')
print('captured',len(frames))
