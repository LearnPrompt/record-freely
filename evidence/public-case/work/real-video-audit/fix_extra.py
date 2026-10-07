exec(open('work/real-video-audit/repair_extra.py').read().split('seeds=')[0])
D=json.load(open(W/'qa-extra-boxes.json'));baseline=json.load(open(ROOT/'outputs/带封面-前5分钟/report.json'))
template=target_template(2185,[770,1535,1006,90])
for n in range(2168,2259):
 im=get(n);search=cv2.resize(white(im)[90:2050,200:2400],(1100,980));best=(-1,None)
 for s in np.arange(.86,2.0,.045):
  t=cv2.resize(template,None,fx=s*.5,fy=s*.5,interpolation=cv2.INTER_NEAREST);scores=cv2.matchTemplate(search,t,cv2.TM_CCOEFF_NORMED);_,score,_,pt=cv2.minMaxLoc(scores)
  if score>best[0]:best=(score,(pt,s))
 score,(pt,s)=best
 D['frames'][str(n)]=[b for b in D['frames'].get(str(n),[])if b['id']not in ['R001','R002']]
 if score>.45:
  x=pt[0]*2+200-6;y=pt[1]*2+90-6
  for ident,w,offset in [('R001',745,0),('R002',1008,45)]:
   box=[x,round(y+offset*s),round(w*s+12),round(55*s+12)]
   D['frames'][str(n)].append({'box':box,'id':ident,'kind':'https','box_method':'reviewed_template','origin':'review_template','tracking_score':round(score,4),'relative_scale':round(float(s),4),'preserve_orange_caption':True})
 if n in [2172,2182,2211,2212,2218,2221]:
  for b in D['frames'][str(n)]:x,y,w,h=b['box'];cv2.rectangle(im,(x,y),(x+w,y+h),(0,0,255),3)
  cv2.imwrite(str(W/f'joint-{n}.jpg'),cv2.resize(im,(1280,720)));print(n,[b['box']for b in D['frames'][str(n)]],round(score,3),flush=True)
# For the reviewed share URL, constrain matching around interpolated OCR y.
anchors=[]
for f in baseline['frames'][3530:3605]:
 for b,d in zip(f['boxes'],f['regions']):
  if d['id']=='U026'and 350<b[0]<600:anchors.append((f['frame'],b[1]))
tpl=target_template(3579,[458,1234,220,47]);na=np.array(anchors)
for n in range(3550,3590):
 expected=float(np.interp(n,na[:,0],na[:,1]));y0=max(50,int(expected)-150);y1=min(2100,int(expected)+150)
 im=get(n);search=white(im)[y0:y1,400:850];best=(-1,None)
 for s in [.94,.97,1,1.03,1.06]:
  t=cv2.resize(tpl,None,fx=s,fy=s,interpolation=cv2.INTER_NEAREST);m=cv2.matchTemplate(search,t,cv2.TM_CCOEFF_NORMED);_,score,_,pt=cv2.minMaxLoc(m)
  if score>best[0]:best=(score,(pt,s))
 score,(pt,s)=best;D['frames'][str(n)]=[b for b in D['frames'].get(str(n),[])if b['id']!='R003']
 if score>.55:
  box=[pt[0]+400-5,pt[1]+y0-5,round(1377*s+10),round(59*s+10)];D['frames'][str(n)].append({'box':box,'id':'R003','kind':'https','box_method':'reviewed_template','origin':'review_template','tracking_score':round(score,4),'preserve_orange_caption':True})
  if n in [3577,3578,3580]:print(n,box,score,flush=True)
for n,regs in D['frames'].items():
 for b in regs:
  if b['id']=='R004'and int(n)<4846:
   x,y,w,h=b['box'];end=x+w;b['box']=[1060,y,end-1060,h]
(W/'qa-extra-boxes.json').write_text(json.dumps(D,ensure_ascii=False,indent=2));cap.release();print('extra corrections ready',flush=True)
