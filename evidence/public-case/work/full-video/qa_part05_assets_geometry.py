"""Reviewed resource argument geometry; never retain OCR text."""
from pathlib import Path
import cv2,numpy as np,json
from stream_capture import StreamCapture
P=Path(__file__).resolve().parent;SOURCE='/Users/carl/Downloads/带封面.mp4'
def frame(n):
 c=StreamCapture(SOURCE,n/30,1);ok,a=c.read();c.release();assert ok;return a
seed=frame(46122)
ATTACH=cv2.cvtColor(seed[980:1030,784:1160],cv2.COLOR_BGR2GRAY)
PREFER=cv2.cvtColor(seed[1155:1203,2220:2680],cv2.COLOR_BGR2GRAY)
def locate(gray,template,scales,region=None):
 if region is None:region=[0,0,3840,2160]
 x,y,w,h=region;roi=gray[y:y+h,x:x+w];best=(-1,None)
 for scale in scales:
  t=cv2.resize(template,None,fx=float(scale),fy=float(scale),interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_LINEAR)
  if t.shape[0]>h or t.shape[1]>w:continue
  out=cv2.matchTemplate(roi,t,cv2.TM_CCOEFF_NORMED);_,score,_,pos=cv2.minMaxLoc(out)
  if score>best[0]:best=(score,[x+pos[0],y+pos[1],t.shape[1],t.shape[0],float(scale)])
 return best

HEAD=cv2.cvtColor(seed[980:1030,1187:1850],cv2.COLOR_BGR2GRAY)
SUFFIX=cv2.cvtColor(seed[1155:1203,3310:3710],cv2.COLOR_BGR2GRAY)
cv2.setNumThreads(2)

def bounds(x,y,w,h):
 left=max(0,int(x));top=max(0,int(y));right=min(3840,int(x+w));bottom=min(2160,int(y+h))
 return [left,top,max(1,right-left),max(1,bottom-top)]

def subtract_portrait(box):
 # Source-confirmed fixed overlay, including its rounded border. Coordinates
 # checked on both initial and later source layouts; never mask the face.
 x,y,w,h=box;xx=x+w;yy=y+h;l,t,r,b=2980,1528,3780,2064
 if xx<=l or x>=r or yy<=t or y>=b:return [box]
 out=[]
 if y<t:out.append([x,y,w,t-y])
 if yy>b:out.append([x,b,w,yy-b])
 top=max(y,t);bottom=min(yy,b)
 if x<l:out.append([x,top,l-x,bottom-top])
 if xx>r:out.append([r,top,xx-r,bottom-top])
 return [v for v in out if v[2]>0 and v[3]>0]

def first_uri_anchor(gray, scale, native_y, footer_y, early):
    left=max(0,int(native_y)-170);bottom=min(2160,int(native_y)+145)
    roi=gray[left:bottom]
    definitions=[(ATTACH,403,.64,'public_attachments'),(HEAD[:,:233],0,.72,'public_scheme'),(HEAD[:,:117],0,.82,'public_http_clipped'),(cv2.cvtColor(seed[980:1030,1478:1795],cv2.COLOR_BGR2GRAY),-291,.70,'public_host_tail')]
    choices=[]
    for template,offset,threshold,name in definitions:
        t=cv2.resize(template,None,fx=scale,fy=scale,interpolation=cv2.INTER_LINEAR)
        out=cv2.matchTemplate(roi,t,cv2.TM_CCOEFF_NORMED)
        for _ in range(12):
            _,score,_,pos=cv2.minMaxLoc(out)
            if score<threshold:break
            x,y=pos;choices.append((y+left,x+offset*scale,score,name))
            out[max(0,y-t.shape[0]//2):min(out.shape[0],y+t.shape[0]//2+1),max(0,x-t.shape[1]//2):min(out.shape[1],x+t.shape[1]//2+1)]=-1
    if not choices:return None
    top=min(v[0]for v in choices);same=[v for v in choices if abs(v[0]-top)<8*scale]
    return min(same,key=lambda v:v[1])

def build(only_early=False):
 native=json.loads((P/'qa_part05_assets.json').read_text())['frames']
 result={'frames':{},'notes':['Reviewed two source resource-block runs only. Public argument/template anchors, row geometry, 6px padding; no private OCR text or URLs retained. Fixed source portrait overlay subtracted. Orange title pixels preserved. Last three top-edge frames already repaired by approved qa_part05_edges.'],'checked_window_frames':[45636,46152]}
 uncertainty=[];proof=[];prev=None
 if only_early:
  prior=json.loads((P/'qa_part05_assets_geometry.json').read_text());result['frames']={n:rows for n,rows in prior['frames'].items()if int(n)>=45811}
 for start,end in ([(45636,45714)]if only_early else [(45636,45714),(45811,46149)]):
  cap=StreamCapture(SOURCE,start/30,end-start);prev=None
  for n in range(start,end):
   ok,a=cap.read();assert ok;g=cv2.cvtColor(a,cv2.COLOR_BGR2GRAY)
   candidates=native.get(str(n),[]);ys=[r['box'][1]for r in candidates]
   default=.775 if n<45811 else 1.125
   scales=[default-.015,default,default+.015]if prev is None else [prev[2]-.03,prev[2]-.015,prev[2],prev[2]+.015,prev[2]+.03]
   if prev:
    px,py,ps=prev;region=bounds(px-160,py-210,460*ps+320,48*ps+420)
   elif ys:region=bounds(0,min(ys)-100,3840,max(ys)-min(ys)+340)
   else:region=[0,0,3840,2160]
   score,pref=locate(g,PREFER,scales,region)
   method='public_prefer_models_template'
   if score<.7:
    suffix_region=bounds(prev[0]+1090*prev[2]-180,prev[1]-210,400*prev[2]+360,48*prev[2]+420)if prev else region
    suffix_score,suffix=locate(g,SUFFIX,scales,suffix_region)
    if suffix_score>score:
     score=suffix_score;x,y,w,h,s=suffix;pref=[x-1090*s,y,460*s,48*s,s];method='public_model_suffix_template'
   if score<.62:
    wide=bounds(0,min(ys)-140,3840,max(ys)-min(ys)+430)if ys else [0,0,3840,2160]
    all_scales=[.76,.775,.79,.98,1.,1.02,1.11,1.125,1.14]
    score,pref=locate(g,PREFER,all_scales,wide);method='public_prefer_models_template'
    if score<.7:
     ss,suffix=locate(g,SUFFIX,all_scales,wide)
     if ss>score:
      score=ss;x,y,w,h,s=suffix;pref=[x-1090*s,y,460*s,48*s,s];method='public_model_suffix_template'
   if score>=.62:
    px,py,_,_,scale=pref;prev=(px,py,scale);first_y=py-175*scale
    native_y=min(ys)if ys else first_y
    first=first_uri_anchor(g,scale,native_y,py,n<45811)
    if first and n<45811 and px>2000 and first[0]>first_y+25:
     first=None
    if first:
     first_y,first_x,hs,first_method=first
    elif n<45811 and px>2000:
     first_x=1500;first_method='reviewed_orange_occluded_first_uri'
    elif n>=45811:
     first_x=143;first_method='reviewed_clipped_asset_continuation'
    else:
     uncertainty.append(n);continue
    left=735 if n<45811 else 143;right=3788 if n<45811 else 3840
    if first_x>=right:
     first_x=left;first_y+=58*scale
    first_x=max(left,first_x)
    last_x=px-15*scale
    # In this confirmed early command layout, include-tools repeats the model
    # token after the preferred-model token. Orange hides the first copy.
    if method=='public_model_suffix_template'and 45680<=n<=45713 and first_x>2500:
     last_x-=49*(376/13)*scale
    row_count=round((py-first_y)/(58*scale))+1
    if not 3<=row_count<=6:
     uncertainty.append(n);continue
   else:
    # Footer below viewport: current public host still supplies a visible row.
    wide=bounds(0,min(ys)-180,3840,260)if ys else [0,0,3840,2160]
    hs,head=locate(g,HEAD,[default-.015,default,default+.015],wide)
    if hs<.68:uncertainty.append(n);continue
    first_x,first_y,_,_,scale=head;first_method='public_asset_host_visible_footer_clipped'
    left=735 if n<45811 else 143;right=3788 if n<45811 else 3840;last_x=right;row_count=4
   rows=[]
   for k in range(row_count):
    x0=first_x if k==0 else left;x1=last_x if k==row_count-1 else right
    y0=first_y+(58*k+8)*scale-6;y1=first_y+(58*k+44)*scale+6
    if y1<=0 or y0>=2160 or x1<=x0:continue
    box=bounds(x0-6,y0,x1-x0+12,y1-y0)
    for part in subtract_portrait(box):
     rows.append({'box':part,'id':'QA5G001','kind':'url_continuation','box_method':'reviewed_asset_argument_geometry','origin':'review_resource_geometry','review_basis':'Two manually reviewed resource runs; public anchor localization, individual URI rows, preserve subsequent public flags and portrait','anchor_method':method,'anchor_score':round(float(score),4),'first_row_method':first_method,'preserve_orange_caption':True,'preserve_white_caption':n<=45661})
   if not rows:uncertainty.append(n);continue
   result['frames'][str(n)]=rows
   if n in [45636,45652,45658,45659,45668,45690,45713,45811,45816,45825,45850,45949,46050,46122,46148]:
    vis=a.copy()
    for r in rows:
     x,y,w,h=r['box'];cv2.rectangle(vis,(x,y),(x+w,y+h),(0,0,255),3)
    proof.append(cv2.resize(vis,(1280,720)))
   if n%15==0:print(json.dumps({'frame':n,'masked':len(result['frames']),'score':round(float(score),3),'first':[round(first_x),round(first_y)],'last':round(last_x),'scale':round(scale,3),'method':method}),flush=True)
  cap.release()
 result['unconfirmed_frames']=uncertainty
 (P/'qa_part05_assets_geometry.json').write_text(json.dumps(result,indent=2))
 for i in range(0,len(proof),3):cv2.imwrite(str(P/f'qa_part05_assets_geometry_proof_{"early_"if only_early else""}{i//3:02}.jpg'),np.vstack(proof[i:i+3]))
 print(json.dumps({'status':'needs_visual_review','frames':len(result['frames']),'boxes':sum(map(len,result['frames'].values())),'unconfirmed_frames':uncertainty}),flush=True)

if __name__=='__main__':
 import sys
 build('--only-early'in sys.argv)
