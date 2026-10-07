import cv2,json,sys,time,numpy as np
from pathlib import Path
sys.path.insert(0,str(Path('work/full-video').resolve()));sys.path.insert(0,str(Path('work/revision-v2').resolve()))
from stream_capture import StreamCapture
from late_prefix_match import hp
D=Path('work/revision-v2');SRC='/Users/carl/Downloads/带封面.mp4'
while 'DONE' not in (D/'late_words.log').read_text():time.sleep(2)
r=json.load(open(D/'late_word_detections.json'));records={};tracks=[];extra=0
cap=StreamCapture(SRC,1929,1321)
def iou(a,b):
 x,y,w,h=a;j,k,u,v=b;z=max(0,min(x+w,j+u)-max(x,j))*max(0,min(y+h,k+v)-max(y,k));return z/max(1,w*h+u*v-z)
for f in range(57870,59191):
 ok,im=cap.read()
 if not ok:raise RuntimeError(f)
 rows=[]
 for d in r.get(str(f),[]):
  x,y,w,h=d['box'];box=[max(0,x),max(0,y),min(3840,x+w)-max(0,x),min(2160,y+h)-max(0,y)]
  rows.append({'box':box,'id':'late_'+d['target'],'origin':'review_v2','kind':'reviewed_word','box_method':'native_zh_hans_exact_substring_each_frame','preserve_orange_caption':False,'preserve_white_caption':False})
 for tr in tracks:
  if any(d['id']==tr['id'] and iou(d['box'],tr['box'])>.2 for d in rows):continue
  x,y,w,h=tr['box'];a=max(0,x-150);b=max(0,y-140);right=min(3840,x+w+150);bottom=min(2160,y+h+140);search=hp(im[b:bottom,a:right]);templ=tr['template']
  if search.shape[0]<templ.shape[0] or search.shape[1]<templ.shape[1]:continue
  resp=cv2.matchTemplate(search,templ,cv2.TM_CCOEFF_NORMED);_,score,_,xy=cv2.minMaxLoc(resp)
  if score<.9:continue
  box=[a+xy[0],b+xy[1],templ.shape[1],templ.shape[0]]
  if any(iou(box,d['box'])>.2 for d in rows):continue
  rows.append({'box':box,'id':tr['id'],'origin':'review_v2','kind':'reviewed_word','box_method':'current_frame_word_glyph_template_for_native_dropout','template_score':round(score,4),'preserve_orange_caption':False,'preserve_white_caption':False,'_age':tr['age']+1});extra+=1
 new=[]
 for d in rows:
  x,y,w,h=d['box'];age=d.pop('_age',0)
  if age<3 and y+h<2160 and x+w<3840:new.append({'box':d['box'],'id':d['id'],'age':age,'template':hp(im[max(0,y-25):min(2160,y+h+25),max(0,x-25):min(3840,x+w+25)])[min(25,y):min(25,y)+h,min(25,x):min(25,x)+w].copy()})
 tracks=new
 if rows:records[str(f)]={'remove_indexes':[],'add':rows}
 if f%120==0:print(f,len(records),extra,flush=True)
cap.release();(D/'late_word_refined.json').write_text(json.dumps({'fps':30,'frames':records},indent=2));print('DONE',len(records),extra,flush=True)
