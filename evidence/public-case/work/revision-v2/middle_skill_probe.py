import cv2,json,sys
from pathlib import Path
sys.path.insert(0,'work/full-video');from qa_shell_continuation import Vision
W=Path('work/revision-v2');D=W/'middle_skill_extra';D.mkdir(exist_ok=True);o=Vision(D)
for f in [12180,12204]:
 c=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');c.set(cv2.CAP_PROP_POS_FRAMES,f);ok,im=c.read();assert ok;c.release();cv2.imwrite(str(D/f'source_{f}.jpg'),cv2.resize(im,(1920,1080)));obs=o.read(im[1800:2160],maximum_width=3840);(D/f'ocr_{f}.json').write_text(json.dumps(obs,ensure_ascii=False));print(f,[(z['text'],z['box'])for z in obs if 'claw' in z['text'].lower()or 'ffmpeg' in z['text'].lower()])
c=cv2.VideoCapture(str(W/'chunks/part-01/redacted.mp4'));c.set(cv2.CAP_PROP_POS_FRAMES,12204-9000);ok,im=c.read();assert ok;cv2.imwrite(str(W/'middle_current_12204.jpg'),cv2.resize(im,(1920,1080)));c.release();o.close()
