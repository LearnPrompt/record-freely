# coding:utf-8
from pathlib import Path
import json,cv2,tempfile,re
import qa_shell_continuation as s
BASE=Path(__file__).parent
cap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4')
ns=[17805,17850,17900,17999]
with tempfile.TemporaryDirectory(prefix='qa-proxy-')as scratch:
 o=s.Vision(scratch)
 for n in ns:
  cap.set(1,n);ok,a=cap.read();assert ok;roi=a[1650:2160]
  rows=s.group_rows(o.read(roi,maximum_width=3840))
  for row in rows:
   matches=list(re.finditer(r'r\s*\.\s*jina\s*\.\s*ai',row['text'],re.I))
   if matches:print(n,'count',len(matches),'center',round(1650+row['center_y']*510),'pieces',[(len(ob['text']),[round(v,4)for v in ob['box']])for _,_,ob in row['pieces']],'HTTP',[(m.start(),m.end())for m in s.HTTP.finditer(row['text'])], 'quotes',[i for i,c in enumerate(row['text'])if c in'\"\''])
 o.close()
# Add complete explicitly repeated public proxy URL words, bridging only
# fragments of that same reviewed row, never a whole paragraph.
def span_box(row,start,end):
 parts=[]
 for begin,stop,ob in row['pieces']:
  a=max(0,start-begin);b=min(end-begin,stop-begin)
  if b<=a:continue
  chars=[c['box'] for c in ob.get('chars',[])if c['start']<b and c['end']>a]
  if chars:parts+=chars
  else:
   x,y,w,h=ob['box'];parts.append([x+w*a/max(1,stop-begin),y,w*(b-a)/max(1,stop-begin),h])
 if not parts:return None
 x=min(b[0]for b in parts)*3840;y=min(b[1]for b in parts)*510
 xx=max(b[0]+b[2]for b in parts)*3840;yy=max(b[1]+b[3]for b in parts)*510
 return[x,y,xx-x,yy-y]
q=json.load(open(BASE/'qa_part01_edges.json')); added=0
with tempfile.TemporaryDirectory(prefix='qa-proxy-')as scratch:
 o=s.Vision(scratch);cap.set(1,17805)
 for n in range(17805,18000):
  ok,a=cap.read();assert ok
  if any(x["id"]=="QE005"for x in q["frames"].get(str(n),[])):continue
  roi=a[1650:2160];rows=s.group_rows(o.read(roi,maximum_width=3840))
  for row in rows:
   proxies=list(re.finditer(r'r\s*\.\s*jina\s*\.\s*ai',row['text'],re.I));http=list(s.HTTP.finditer(row['text']))
   if len(proxies)<2 or not http:continue
   start=http[0].start();quotes=[i for i,c in enumerate(row['text'])if i>start and c in'\"\''];end=quotes[0]if quotes else len(row['text'])
   b=span_box(row,start,end)
   if not b:continue
   original=b; b=s.trim_white_line(roi,b)
   if not b:
    x,y,w,h=original;b=[max(0,int(x)-4),max(0,int(y)-4),min(3840,int(x+w)+5)-max(0,int(x)-4),min(510,int(y+h)+5)-max(0,int(y)-4)]
   b[1]+=1650;q['frames'].setdefault(str(n),[]).append({'box':b,'id':'QE005','kind':'http(s)','box_method':'reviewed_proxy_word','origin':'review_roi_ocr','review_basis':'Source local OCR confirms explicit repeated public proxy URL on same terminal row; merge URL fragments from scheme to matching quote or viewport edge'});added+=1
  if n%30==0:print('reviewed',n,flush=True)
 o.close()
q['notes'].append('Source lower terminal ROI OCR every frame17805..17999; repaired repeated explicit proxy URL fragments only, transient recognized text not persisted.')
(BASE/'qa_part01_edges.json').write_text(json.dumps(q,ensure_ascii=False,indent=2));print('proxy added',added)
