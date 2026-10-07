import cv2,json
from pathlib import Path
W=Path('work/revision-v2');fs=json.load(open(W/'middle_patch.json'))['frames'];SRC='/Users/carl/Downloads/带封面.mp4';c=cv2.VideoCapture(SRC);notes=json.load(open(W/'middle_notes.json'));checks=[]
for kind in ['skill','pathA','pathB','html']:
 rr=notes['target_final_ranges'][kind]
 for label,n in [('begin',rr['first']),('end',rr['last'])]:
  target=next(a['box']for a in fs[str(n)]['add']if a['id'].startswith('middle_'+kind))
  x,y,w,h=target;x=max(0,x-80);y=max(0,y-80);w=min(3840-x,w+240);h=min(2160-y,h+160);tiles=[]
  for f in [n-1,n,n+1]:
   c.set(cv2.CAP_PROP_POS_FRAMES,f);ok,im=c.read();assert ok;original=im[y:y+h,x:x+w].copy()
   for a in fs.get(str(f),{}).get('add',[]):
    xx,yy,ww,hh=a['box'];im[yy:yy+hh,xx:xx+ww]=112
   masked=im[y:y+h,x:x+w];first=cv2.resize(original,(900,round(h*900/w)));second=cv2.resize(masked,first.shape[1::-1]);tile=cv2.vconcat([first,second]);tile=cv2.copyMakeBorder(tile,40,0,0,0,cv2.BORDER_CONSTANT,value=(20,20,20));cv2.putText(tile,str(f),(10,28),cv2.FONT_HERSHEY_SIMPLEX,.8,(255,255,255),2);tiles.append(tile)
  dest=W/f'middle_boundary_{kind}_{label}.jpg';cv2.imwrite(str(dest),cv2.hconcat(tiles));checks.append(str(dest.name))
c.release();notes['boundary_neighbor_source_proof']=checks;(W/'middle_notes.json').write_text(json.dumps(notes,ensure_ascii=False,indent=2))
