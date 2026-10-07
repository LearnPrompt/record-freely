import qa_part05_assets_geometry as s
import cv2,numpy as np,json
p=json.load(open(s.P/'qa_part05_assets.json'))['frames']
suffix=cv2.cvtColor(s.seed[1155:1203,3310:3710],cv2.COLOR_BGR2GRAY)
cv2.imwrite(str(s.P/'qa_assets_public_suffix_seed.jpg'),s.seed[1155:1203,3310:3710])
for n,sc in [(45636,.775),(45668,.775),(45811,1.125),(46122,1.)]:
 a=s.frame(n);g=cv2.cvtColor(a,cv2.COLOR_BGR2GRAY);ys=[r['box'][1]for r in p[str(n)]];yy=min(ys)
 print(n,s.locate(g,suffix,[sc-.015,sc,sc+.015],[0,max(0,yy+90),3840,min(2160,max(ys)+220)-max(0,yy+90)]),flush=True)
