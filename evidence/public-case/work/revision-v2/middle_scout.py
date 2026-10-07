import cv2,sys,json
from pathlib import Path
sys.path.insert(0,'work/full-video');from qa_shell_continuation import Vision
W=Path('work/revision-v2'); o=Vision(W)
for t in [399,485,537,872,972]:
 for name,path in [('src','/Users/carl/Downloads/带封面.mp4'),('old','outputs/带封面-完整版/redacted.mp4')]:
  c=cv2.VideoCapture(path);c.set(cv2.CAP_PROP_POS_FRAMES,t*30);ok,im=c.read();c.release();cv2.imwrite(str(W/f'middle_{t}_{name}.jpg'),cv2.resize(im,(1920,1080)))
  if name=='src':
   obs=o.read(im);(W/f'middle_{t}_ocr.json').write_text(json.dumps(obs,ensure_ascii=False))
o.close()
