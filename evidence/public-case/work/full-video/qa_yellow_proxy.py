# coding:utf-8
from pathlib import Path
import cv2,json,tempfile,re,numpy as np
import qa_shell_continuation as s
P=Path(__file__).parent;cap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4')
with tempfile.TemporaryDirectory(prefix='qa-yellow-')as scratch:
 o=s.Vision(scratch)
 for n in [17805,17808,17812,17850]:
  cap.set(1,n);ok,a=cap.read();assert ok;roi=a[1650:2160];hsv=cv2.cvtColor(roi,cv2.COLOR_BGR2HSV);m=cv2.inRange(hsv,np.array([18,50,75]),np.array([45,255,255]));mono=cv2.cvtColor(255-m,cv2.COLOR_GRAY2BGR);cv2.imwrite(str(P/f'qa_proxy_yellow_binary_{n}.png'),mono)
  for row in s.group_rows(o.read(mono,maximum_width=3840)):
   hits=list(re.finditer(r'r\s*\.\s*jina\s*\.\s*ai',row['text'],re.I));http=list(s.HTTP.finditer(row['text']))
   if hits:print(n,'hits',len(hits),'rows',[[len(ob['text']),ob['box']]for _,_,ob in row['pieces']],'http',[m.start()for m in http],'quotes',[i for i,c in enumerate(row['text'])if c in'\"\''])
 o.close()
