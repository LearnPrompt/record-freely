import cv2,json,numpy as np,sys
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path('/Users/carl/Documents/Codex/2026-10-06/1-openai-gpt-6-1-ultra');BASE=ROOT/'work/real-video-audit';R=json.load(open(BASE/('trim-patch-report.json' if '--trim' in sys.argv else 'final-report.json')))
NS=[2172,2182,2211,2212,2218,2221,2240,2682,2774,3060,3138,3155,3577,3578,3580,3660,3810,4260,4410,4560,4800,4847,4848,4849,4850,6782,7031,7611,8850]
cap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4')
for n in NS:
 cap.set(cv2.CAP_PROP_POS_FRAMES,n);ok,im=cap.read();assert ok
 original=im.copy();f=R['frames'][n]
 for box,d in zip(f['boxes'],f['regions']):
  x,y,w,h=box
  if d.get('preserve_orange_caption'):
   roi=original[y:y+h,x:x+w];hsv=cv2.cvtColor(roi,cv2.COLOR_BGR2HSV);fg=cv2.inRange(hsv,np.array([3,120,110]),np.array([32,255,255]));fg=cv2.dilate(fg,np.ones((5,5),np.uint8));im[y:y+h,x:x+w]=112;im[y:y+h,x:x+w][fg>0]=roi[fg>0]
  else:im[y:y+h,x:x+w]=112
 cv2.imwrite(str(BASE/f'qa-final-expected-{n:04d}.jpg'),im)
 if n in [4848,4849,4850]:cv2.imwrite(str(BASE/f'qa-final-source-{n:04d}.jpg'),original)
 for kind,data in [('expected',im)]:
  roi=(0,0,3840,2160)
  if n in [2172]:roi=(200,350,2200,850)
  elif n in [2182,2211,2212,2218,2221]:roi=(600,1220,2200,1550)
  elif n in [3577,3578,3580]:roi=(350,950,2300,1550)
  elif n in [4260,4410]:roi=(2700,760,3450,960)
  elif n==4560:roi=(0,180,2900,1720)
  elif 4800<=n<=4850:roi=(400,1300,3300,1850)
  elif n in [6782,7031]:roi=(1800,0,3250,140)
  elif n==7611:roi=(2350,350,3200,650)
  x0,y0,x1,y1=roi;cv2.imwrite(str(BASE/f'qa-final-crop-{n:04d}.jpg'),data[y0:y1,x0:x1])
cap.release();print('expected mask samples',len(NS))
