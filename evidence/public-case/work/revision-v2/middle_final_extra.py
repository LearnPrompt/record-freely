import json,copy,cv2,sys,hashlib
from pathlib import Path
sys.path.insert(0,'work/full-video');from stream_capture import StreamCapture
W=Path('work/revision-v2');D=W/'middle_extra_proof';p={};notes={}
j=json.load(open(W/'chunks/part-01/report.json'))
anchor=cv2.imread(str(D/'source_12823.jpg'));tpl=cv2.cvtColor(anchor[1017:1048,110:685],cv2.COLOR_BGR2GRAY)
c=StreamCapture('/Users/carl/Downloads/带封面.mp4',12823/30,84);scores=[]
for f in range(12823,12907):
 ok,im=c.read();assert ok;im=cv2.resize(im,(1920,1080));g=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY);row=j['frames'][f-9000]
 ids=[i for i,(b,z) in enumerate(zip(row['boxes'],row['regions'])) if b[0]<300 and b[2]>1200 and z.get('kind')=='reviewed_url'];assert len(ids)==1
 i=ids[0];x,y,w,h=row['boxes'][i];sx=max(0,x//2-40);sy=max(60,y//2-40);ex=min(1920,(x+w)//2+30);ey=min(1080,(y+h)//2+30)
 best=None
 for scale in [1.,.97,.94,1.03,1.06]:
  t=cv2.resize(tpl,(round(575*scale),round(31*scale)));r=cv2.matchTemplate(g[sy:ey,sx:ex],t,cv2.TM_CCOEFF_NORMED);_,v,_,loc=cv2.minMaxLoc(r)
  if best is None or v>best[0]:best=(v,loc,scale)
 v,loc,scale=best;assert v>.7,(f,v);scores.append(v)
 tx=sx+loc[0];ty=sy+loc[1];b=[tx*2-4,ty*2-4,round(1150*scale),round(70*scale)]
 z=copy.deepcopy(row['regions'][i]);z.update(box=b,id='middle_skill_asc_suffix',origin='review_v2',kind='reviewed_url',box_method='source_prefix_pixels_per_frame_template_caption_excluded',protected_suffix=True,preserve_orange_caption=True)
 for key in ['repair_patch','patch_global_frame']:z.pop(key,None)
 p[str(f)]={'remove_indexes':[i],'add':[z]}
 if f in [12823,12840,12870,12900,12906]:
  cv2.imwrite(str(D/f'source_{f}.jpg'),im);prev=im.copy();xx,yy,ww,hh=[int(z/2)for z in b];prev[yy:yy+hh,xx:xx+ww]=[116,116,116];cv2.imwrite(str(D/f'preview_{f}.jpg'),prev)
c.release();notes['skill']={'frames':84,'range':[12823,12906],'template_min_score':min(scores),'suffix':'ffmpeg-cli','reason':'OCR merged orange/black subtitle with bottom URL and inferred overly long prefix; pixel template excludes subtitle'}
j=json.load(open(W/'chunks/part-03/report.json'));bad=[]
for k,row in enumerate(j['frames']):
 ids=[i for i,z in enumerate(row['regions'])if z['id'] in ['U010','U012']]
 if ids:p[str(k+27000)]={'remove_indexes':ids,'add':[]};bad.append(k+27000)
assert bad==[29158,29162,29163,29164,29185,29186];notes['wrong']={'additional_false_mask_frames':bad,'source_verified':'same local Skill source line and its heading, not a URL','source_proof':[29158,29162,29186]}
obj={'fps':30,'index_basis':'revision-v2-current','frames':p,'report_sha256':{str(i):hashlib.sha256((W/f'chunks/part-{i:02d}/report.json').read_bytes()).hexdigest()for i in [1,3]}}
(W/'middle_final_extra_patch.json').write_text(json.dumps(obj));(W/'middle_final_extra_notes.json').write_text(json.dumps(notes,ensure_ascii=False,indent=2));print('FROZEN',len(p),notes)
