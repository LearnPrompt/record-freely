import sys,json,cv2
from pathlib import Path
sys.path.insert(0,'work/full-video');from redact_full_engine import VisionOCR
w=Path('work/revision-v2');o=VisionOCR(w)
for t in [62,101,102,112,123,158]:
 im=cv2.imread(str(w/f'front_{t}_src.jpg'))
 if im is None:
  cap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');cap.set(1,t*30);_,im=cap.read();cap.release();cv2.imwrite(str(w/f'front_{t}_src.jpg'),im)
 obs=o.read(im);json.dump(obs,open(w/f'front_{t}_ocr.json','w'))
 for x in obs:
  if any(s in x['text'].lower() for s in ['github','models','检查ai','lark-cli','microsoft']):print(t,x['text'],x['box'])
o.close()
