import cv2,sys,json
from pathlib import Path
sys.path.insert(0,'work/full-video');from qa_shell_continuation import Vision
W=Path('work/revision-v2');D=W/'middle_extra_proof';D.mkdir(exist_ok=True);ocr=Vision(D)
for f in [12823,12840,12870,12900,29158,29162,29186]:
 cap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');cap.set(cv2.CAP_PROP_POS_FRAMES,f);ok,im=cap.read();assert ok;cap.release();cv2.imwrite(str(D/f'source_{f}.jpg'),cv2.resize(im,(1920,1080)))
 if f<27000:
  crop=im[1750:2160];obs=ocr.read(crop,maximum_width=3840);(D/f'ocr_{f}.json').write_text(json.dumps(obs,ensure_ascii=False));print(f,[(o['text'],o['box'])for o in obs if 'clawhub' in o['text'].lower()],flush=True)
ocr.close()
