import cv2,json,sys,time,numpy as np
from pathlib import Path
sys.path.insert(0,str(Path('work/full-video').resolve()));sys.path.insert(0,str(Path('work/revision-v2').resolve()))
from stream_capture import StreamCapture
from late_prefix_match import hp
D=Path('work/revision-v2');im=cv2.imread(str(D/'late_src_1637.jpg'));t=hp(im)[95:137,391:850];records={};started=time.time();cap=StreamCapture('/Users/carl/Downloads/带封面.mp4',1625,750)
for f in range(48750,49500):
 ok,im=cap.read()
 if not ok:raise RuntimeError(f)
 search=hp(im[:600,:1800]);r=cv2.matchTemplate(search,t,cv2.TM_CCOEFF_NORMED);_,score,_,xy=cv2.minMaxLoc(r)
 if score>=.86:
  x,y=xy;box=[x-4,y-4,t.shape[1]+8,t.shape[0]+8];records[str(f)]={'remove_indexes':[],'add':[{'box':box,'id':'late_path_identity','origin':'review_v2','kind':'reviewed_path','box_method':'current_frame_visible_lower_glyph_template','template_score':round(score,4),'preserve_orange_caption':True}]}
 if f%90==0:print(f,len(records),round(time.time()-started),flush=True)
cap.release();(D/'late_partial_prefix.json').write_text(json.dumps({'fps':30,'frames':records},indent=2));print('DONE',len(records),flush=True)
