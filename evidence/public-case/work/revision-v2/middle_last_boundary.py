import cv2,json,hashlib
from pathlib import Path
W=Path('work/revision-v2');D=W/'middle_extra_proof';P={};proof=[]
anchor=cv2.imread(str(D/'source_12823.jpg'));template=cv2.cvtColor(anchor[1017:1048,110:685],cv2.COLOR_BGR2GRAY)
j=json.load(open(W/'chunks/part-01/report.json'))
normal=cv2.cvtColor(cv2.imread(str(W/'middle_skill_anchor_12930.jpg'))[503:526,415:762],cv2.COLOR_BGR2GRAY)
fs=sorted({k+9000 for k,row in enumerate(j['frames'])for z in row['regions']if z['id'] in ['U027','U028','U051']})
for f in fs:
 cap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');cap.set(cv2.CAP_PROP_POS_FRAMES,f);ok,im=cap.read();assert ok;cap.release();im=cv2.resize(im,(1920,1080));g=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY);row=j['frames'][f-9000];ids=[i for i,(b,z)in enumerate(zip(row['boxes'],row['regions']))if z['id'] in ['U027','U028','U051']];assert len(ids)==1
 i=ids[0];x,y,w,h=row['boxes'][i];sx=max(0,x//2-80);sy=max(60,y//2-40);ex=min(1920,(x+w)//2+20);ey=min(1080,(y+h)//2+40);best=None
 for tpl in [template,normal]:
  for scale in [q/100 for q in range(55,156)]:
   tt=cv2.resize(tpl,(round(tpl.shape[1]*scale),round(tpl.shape[0]*scale)))
   if f==12822:tt=tt[:16,:]
   if tt.shape[0]>ey-sy or tt.shape[1]>ex-sx:continue
   r=cv2.matchTemplate(g[sy:ey,sx:ex],tt,cv2.TM_CCOEFF_NORMED);_,v,_,loc=cv2.minMaxLoc(r)
   if best is None or v>best[0]:best=(v,loc,scale,tpl.shape)
 v,loc,scale,shape=best;assert v>.6,(f,v);tx=sx+loc[0];ty=sy+loc[1];b=[tx*2-4,ty*2-4,round(shape[1]*2*scale),min(round(shape[0]*2*scale)+8,2160-(ty*2-4))];P[str(f)]={'remove_indexes':[i],'add':[{'box':b,'id':'middle_skill_asc_boundary','origin':'review_v2','kind':'reviewed_url','box_method':'source_prefix_pixels_scaled_boundary_template','protected_suffix':True,'preserve_orange_caption':True}]};cv2.imwrite(str(D/f'source_{f}.jpg'),im);xx,yy,ww,hh=[z//2 for z in b];im[yy:yy+hh,xx:xx+ww]=[116,116,116];cv2.imwrite(str(D/f'preview_{f}.jpg'),im);proof.append({'frame':f,'score':v,'box':b})
j=json.load(open(W/'chunks/part-03/report.json'));falseframes=[]
for k,row in enumerate(j['frames']):
 f=k+27000
 if 29150<=f<=29213:
  ids=[i for i,(b,r)in enumerate(zip(row['boxes'],row['regions']))if 1000<b[1]<1320 and r.get('kind')=='domain']
  if ids:P[str(f)]={'remove_indexes':ids,'add':[]};falseframes.append(f)
assert len(falseframes)==55
for f in [29149,29150,29174,29213,29214]:
 cap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');cap.set(cv2.CAP_PROP_POS_FRAMES,f);ok,im=cap.read();assert ok;cap.release();cv2.imwrite(str(D/f'source_{f}.jpg'),cv2.resize(im,(1920,1080)))
(W/'middle_last_boundary_patch.json').write_text(json.dumps({'fps':30,'index_basis':'revision-v2-current','frames':P,'report_sha256':{str(i):hashlib.sha256((W/f'chunks/part-{i:02d}/report.json').read_bytes()).hexdigest()for i in [1,3]}}));(W/'middle_last_boundary_notes.json').write_text(json.dumps({'skill_boundary':proof,'same_false_source_line_frames':falseframes},indent=2));print('FROZEN',len(P),proof)
