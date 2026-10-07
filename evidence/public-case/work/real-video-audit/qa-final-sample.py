import cv2,json
from pathlib import Path
from PIL import Image,ImageDraw
base=Path('work/real-video-audit'); outdir=Path('outputs/带封面-前5分钟')
report=json.load(open(outdir/'report.json'))
frames=[1855,1856,1950,2100,2166,2168,2172,2173,2182,2183,2211,2223,2240,2241,2263,2264,2682,2760,2774,2995,2996,3060,3137,3138,3155,3156,3210,3360,3510,3578,3579,3660,3810,3960,4022,4023,4026,4110,4182,4183,4260,4410,4446,4447,4500,4560,4710,4800,4847,4848,6782,7031,7611,8760,8850,8940]
a=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');b=cv2.VideoCapture(str(outdir/'redacted.mp4'))
for n in frames:
 for cap,kind in [(a,'source'),(b,'redacted')]:
  cap.set(cv2.CAP_PROP_POS_FRAMES,n);ok,im=cap.read()
  if not ok:raise RuntimeError(n)
  cv2.imwrite(str(base/f'qa-{kind}-f{n:04d}.jpg'),im)
for i in range(0,len(frames),6):
 ns=frames[i:i+6];dst=Image.new('RGB',(2560,756*len(ns)),(30,30,30));d=ImageDraw.Draw(dst)
 for j,n in enumerate(ns):
  for col,kind in enumerate(['source','redacted']):
   im=Image.open(base/f'qa-{kind}-f{n:04d}.jpg');im.thumbnail((1280,720));dst.paste(im,(col*1280,j*756+36))
   d.text((col*1280+10,j*756+7),f'{kind} frame {n} t={n/30:.3f} '+str(report['frames'][n]['origins']),fill='white')
 dst.save(base/f'qa-final-contact-{i//6:02d}.jpg')
print('saved',len(frames),'paired source/output samples')
