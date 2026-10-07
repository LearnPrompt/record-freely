"""Source-confirmed original shell URI block exit; keep shell fields."""
from pathlib import Path
import cv2
import json

P = Path(__file__).resolve().parent
seed = cv2.imread(str(P/'qa_shell_exit_full_18120.jpg'))
template = cv2.cvtColor(seed[408:453,960:1184],cv2.COLOR_BGR2GRAY)
base = [[1385,274,2455,46], [729,320,3111,46], [729,365,789,45], [2233,365,1190,45], [1182,410,1180,46]]
frames = {}
proof = []
for n in range(18119,18129):
    a = cv2.imread(str(P/f'qa_shell_exit_full_{n}.jpg'))
    gray = cv2.cvtColor(a,cv2.COLOR_BGR2GRAY)
    best=(-1,None)
    for scale in [.975,1,1.025,1.05]:
        t=cv2.resize(template,None,fx=scale,fy=scale)
        _,q,_,pos=cv2.minMaxLoc(cv2.matchTemplate(gray[:650],t,cv2.TM_CCOEFF_NORMED))
        if q>best[0]:best=(q,[*pos,scale])
    q, anchor=best
    if n==18128:
        assert q<.8
        continue
    assert q>.9
    ax,ay,s=anchor;rows=[]
    for x,y,w,h in base:
        l=max(0,round(ax+(x-960)*s));t=max(0,round(ay+(y-408)*s))
        r=min(3840,round(ax+(x+w-960)*s));b=min(2160,round(ay+(y+h-408)*s))
        if b<=t or r<=l:continue
        # The confirmed opaque black navigation panel hides URI pixels itself.
        boxes=[]
        if t<120 and r>1080:
            if l<1080:boxes.append([l,t,1080-l,b-t])
            if b>120:boxes.append([max(l,1080),120,r-max(l,1080),b-120])
        else:boxes.append([l,t,r-l,b-t])
        for box in boxes:
            rows.append({'box':box,'id':'QA2S001','kind':'url_continuation','origin':'review_shell_exit',
                'box_method':'reviewed_shell_uri_geometry','anchor_score':round(float(q),4),
                'review_basis':'Confirmed original for-url URI display rows only; preserve echo/curl flags and opaque navigation',
                'preserve_orange_caption':True})
    frames[str(n)]=rows
    if n in [18119,18120,18124,18127]:
        image=a[:650].copy()
        for row in rows:
            x,y,w,h=row['box'];cv2.rectangle(image,(x,y),(x+w,y+h),(0,0,255),2)
        proof.append(cv2.resize(image,(1920,325)))
out={'frames':frames,'status':'source_geometry_reviewed_frozen','last_visible_frame':18127,'first_absent_frame':18128,'remove_ids':[]}
(P/'qa_part02_shell_exit.json').write_text(json.dumps(out,indent=2))
cv2.imwrite(str(P/'qa_part02_shell_exit_proof.jpg'),cv2.vconcat(proof))
print(json.dumps({'frames':len(frames),'boxes':sum(map(len,frames.values()))}))
