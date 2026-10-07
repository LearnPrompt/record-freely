"""Same reviewed public URI hosts in the adjacent shell command variant."""
from pathlib import Path
import cv2
import json
from stream_capture import StreamCapture

P = Path(__file__).resolve().parent
anchors=json.loads((P/'qa_shell_variant_anchors.json').read_text())['frames']
# Current source frame 18131: individual URI fields; keep command and flags.
base=[[1370,1076,1238,48], [1008,1121,2832,48], [729,1166,3111,48],
      [729,1211,416,48], [2590,1211,1195,48], [1983,1256,1195,48]]
frames={};proof=[]
capture=StreamCapture('/Users/carl/Downloads/带封面.mp4',18128/30,23)
for n in range(18128,18151):
    ok,a=capture.read();assert ok
    item=anchors[str(n)];ax,ay=item['anchor'];assert item['score']>.9
    dx=ax-3160;dy=ay-1250;rows=[]
    for x,y,w,h in base:
        l=max(0,x+dx);r=min(3840,x+w+dx);t=max(0,y+dy);b=min(2160,y+h+dy)
        if b<=t:continue
        boxes=[]
        if t<120 and r>1080:
            if l<1080:boxes.append([l,t,1080-l,b-t])
            if b>120:boxes.append([max(l,1080),120,r-max(l,1080),b-120])
        else:boxes.append([l,t,r-l,b-t])
        for box in boxes:
            rows.append({'box':box,'id':'QA2V001','kind':'url_continuation','origin':'review_shell_variant',
                'box_method':'reviewed_shell_uri_geometry','anchor_score':item['score'],
                'review_basis':'Adjacent confirmed shell block same public hosts; exact URI fields anchored to public final flags; source confirms true exit',
                'preserve_orange_caption':True})
    frames[str(n)]=rows
    if n in [18128,18131,18140,18150]:
        image=a.copy()
        for row in rows:
            x,y,w,h=row['box'];cv2.rectangle(image,(x,y),(x+w,y+h),(0,0,255),2)
        proof.append(cv2.resize(image,(1280,720)))
capture.release()
out={'frames':frames,'status':'source_geometry_reviewed_frozen','last_visible_frame':18150,'first_absent_frame':18151,
     'exit_source_frames_checked':[18151,18152,18153],'remove_ids':[],'private_text_persisted':False}
(P/'qa_part02_shell_variant.json').write_text(json.dumps(out,indent=2))
cv2.imwrite(str(P/'qa_part02_shell_variant_proof.jpg'),cv2.vconcat(proof))
print(json.dumps({'frames':len(frames),'boxes':sum(map(len,frames.values()))}))
