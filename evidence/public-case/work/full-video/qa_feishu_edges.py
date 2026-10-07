from pathlib import Path
import cv2,json,re,tempfile,math
import qa_shell_continuation as s
P=Path(__file__).parent
HEAD=re.compile(r'https?\s*[:：]\s*[/／]{2}\s*(?:www\s*\.\s*feishu\s*\.\s*cn\s*[/／]\s*docx\s*[/／]|applink\s*\.\s*feishu\s*\.\s*cn\s*[/／]\s*client\s*[/／])',re.I)
URLTAIL=re.compile(r'[A-Za-z0-9._~%+/?=&#: -]*')
def geometry(row,start,end):
 pieces=[]
 for begin,stop,o in row['pieces']:
  a=max(0,start-begin);b=min(end-begin,stop-begin)
  if b<=a:continue
  cs=[c['box']for c in o.get('chars',[])if c['start']<b and c['end']>a]
  if cs:pieces+=cs
  else:
   x,y,w,h=o['box'];pieces.append([x+w*a/max(1,stop-begin),y,w*(b-a)/max(1,stop-begin),h])
 if not pieces:return
 x=min(b[0]for b in pieces);y=min(b[1]for b in pieces);xx=max(b[0]+b[2]for b in pieces);yy=max(b[1]+b[3]for b in pieces)
 return x,y,xx-x,yy-y
windows=[(34200,34421,0,450),(35340,35521,1600,2160),(35521,35731,0,450)]
frames={};cap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4')
with tempfile.TemporaryDirectory(prefix='qa-feishu-')as t:
 o=s.Vision(t)
 for lo,hi,y0,y1 in windows:
  cap.set(1,lo)
  for n in range(lo,hi):
   ok,im=cap.read();assert ok;roi=im[y0:y1];found=[]
   for row in s.group_rows(o.read(roi,maximum_width=3840)):
    for m in HEAD.finditer(row['text']):
     end=m.end()+URLTAIL.match(row['text'][m.end():]).end();b=geometry(row,m.start(),end)
     if b is None:continue
     x,y,w,h=b;x*=3840;y*=y1-y0;w*=3840;h*=y1-y0
     if h>110:continue
     x0=max(0,math.floor(x)-4);yy=max(0,math.floor(y)+y0-4);x1=min(3840,math.ceil(x+w)+4);ye=min(2160,math.ceil(y+h)+y0+4)
     found.append({'box':[x0,yy,x1-x0,ye-yy],'id':'QA3F001','kind':'url','box_method':'reviewed_uri_characters','origin':'review_roi_ocr','review_basis':'Manually confirmed Feishu document/task URL; anchored scheme/public host, exact ASCII URI word; private token text transient.'})
   if found:frames[str(n)]=found
   if n%30==0:print('Feishu edges',n,'found',len(frames),flush=True)
 o.close()
json.dump({'frames':frames,'remove_ids':['U001','U002','U003','U026','U027'],'checked_windows':windows,'notes':['Only previously confirmed terminal heading/body URI locations; clipped URL words retained to visible edge.']},open(P/'qa_part03_edges.json','w'),indent=2)
print('done',len(frames),sum(map(len,frames.values())))
