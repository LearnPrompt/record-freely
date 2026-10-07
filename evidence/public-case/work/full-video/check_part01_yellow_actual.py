"""Inspect delivered H264 pixels of reviewed yellow URI repair, not only report."""
from pathlib import Path
import json,cv2,numpy as np
from stream_capture import StreamCapture
P=Path(__file__).resolve().parent;patch=json.loads((P/'qa_part01_proxy_yellow.json').read_text());video=P/'chunks/part-01/redacted.mp4';evidence=[];images=[]
for n in [17805,17808,17812,17850,17860,17899,17999]:
 src=StreamCapture('/Users/carl/Downloads/带封面.mp4',n/30,1);ok,a=src.read();assert ok;src.release()
 dst=StreamCapture(video,(n-9000)/30,1);ok,b=dst.read();assert ok;dst.release()
 if str(n)in patch['frames']:
  count=bad=0
  for row in patch['frames'][str(n)]:
   x,y,w,h=row['box'];orig=a[y:y+h,x:x+w];actual=b[y:y+h,x:x+w];hsv=cv2.cvtColor(orig,cv2.COLOR_BGR2HSV)
   yellow=cv2.inRange(hsv,np.array([18,130,150]),np.array([45,255,255]));white=cv2.inRange(hsv,np.array([0,0,180]),np.array([179,55,255]));white=cv2.dilate(white,np.ones((5,5),np.uint8))
   wanted=(yellow>0)&(white==0);wanted[:3]=False;wanted[-3:]=False;wanted[:,:3]=False;wanted[:,-3:]=False
   delta=np.max(np.abs(actual.astype(np.int16)-112),axis=2);count+=int(wanted.sum());bad+=int(np.count_nonzero(wanted&(delta>12)))
  assert bad==0,(n,bad,count);evidence.append({'frame':n,'visible_uri_source_pixels':count,'unmasked_uri_pixels':bad})
 crop=lambda im:cv2.resize(im[1700:2160],(960,115))
 images.append(np.hstack([crop(a),crop(b)]))
cv2.imwrite(str(P/'qa_part01_second_actual_proof.jpg'),np.vstack(images));(P/'qa_part01_actual_pixelcheck.json').write_text(json.dumps({'checks':evidence,'status':'passed'},indent=2));print(json.dumps({'status':'passed','checks':evidence}))
