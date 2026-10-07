import json,time,cv2
from pathlib import Path
W=Path('work/revision-v2');logs=[W/f'render-part{i:02d}.log'for i in [1,2]]+[W/'render-part03-middle.log']
while True:
 if all(p.exists()and '"status": "patched"'in p.read_text()for p in logs):break
 time.sleep(15)
frames=[11807,11808,11970,12030,12204,12823,12999,13008,13009,14189,14550,15881,15900,16110,16531,16532,25590,25642,26160,26213,26214,29158,29160,29162];written=[]
for n in [1,2,3]:
 p=W/f'chunks/part-{n:02d}';r=json.loads((p/'report.json').read_text());start=r['source_start_frame'];c=cv2.VideoCapture(str(p/'redacted.mp4'))
 for f in frames:
  if not start<=f<start+len(r['frames']):continue
  c.set(cv2.CAP_PROP_POS_FRAMES,f-start);ok,im=c.read();assert ok
  dest=W/f'middle_actual_{f}.jpg';cv2.imwrite(str(dest),cv2.resize(im,(1920,1080)));written.append(f)
 c.release()
(W/'middle_actual_images_ready.json').write_text(json.dumps({'status':'ready','frames':written}));print(written,flush=True)
