import json,cv2,sys,re
from pathlib import Path
sys.path.insert(0,'work/full-video');from qa_shell_continuation import Vision
from stream_capture import StreamCapture
W=Path('work/revision-v2');patch={};o=Vision(W);c=StreamCapture('/Users/carl/Downloads/带封面.mp4',26214/30,240);seen=[];proof=[]
try:
 for f in range(26214,26454):
  ok,im=c.read();assert ok
  crop=im[600:1300];obs=o.read(crop,maximum_width=3840);add=[]
  for z in obs:
   txt=z['text'];m=re.search(r'(?i)review\s*[.]\s*htm[l1iI]',txt)
   if not m:continue
   ext=re.search(r'(?i)[.]\s*htm[l1iI]',txt[m.start():m.end()]);a=m.start()+ext.start();b=m.start()+ext.end();x,y,w,h=z['box'];L=len(txt)
   xx=round((x+w*a/L)*3840)-2;yy=round(y*700)+600-4;ww=round(w*(b-a)/L*3840)+4;hh=round(h*700)+8
   box=[max(0,xx),max(0,yy),ww,hh];assert xx+ww<=3840 and yy+hh<=2160
   add.append({'box':box,'id':'middle_html_tail','origin':'review_v2','kind':'reviewed_extension','box_method':'current_source_frame_full_resolution_ocr_confirmed_review_html_tail','preserve_orange_caption':True})
  if add:patch[str(f)]={'remove_indexes':[],'add':add};seen.append(f)
  if f in [26214,26215,26220,26230,26250,26280,26300,26330,26360,26400]:
   cv2.imwrite(str(W/f'middle_html_tail_source_{f}.jpg'),cv2.resize(im,(1920,1080)));proof.append(f)
  if f%30==0:print(f,len(add),flush=True)
finally:o.close();c.release()
(W/'middle_html_tail_patch.json').write_text(json.dumps({'fps':30,'frames':patch},ensure_ascii=False));(W/'middle_html_tail_notes.json').write_text(json.dumps({'status':'frozen','first':min(seen)if seen else None,'last':max(seen)if seen else None,'frames':len(seen),'source_proof_frames':proof},indent=2));print('frozen',len(seen),min(seen)if seen else None,max(seen)if seen else None,flush=True)
