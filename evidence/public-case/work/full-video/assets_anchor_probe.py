import qa_part05_assets_geometry as s
import cv2,numpy as np,json
seed=s.seed
head=cv2.cvtColor(seed[980:1030,1187:1850],cv2.COLOR_BGR2GRAY)
model=cv2.cvtColor(seed[1155:1203,3030:3430],cv2.COLOR_BGR2GRAY)
p=json.load(open(s.P/'qa_part05_assets.json'))['frames']
for n,sc in [(45636,.775),(45668,.775),(45811,1.125),(46122,1.)]:
 a=s.frame(n);g=cv2.cvtColor(a,cv2.COLOR_BGR2GRAY);ys=[r['box'][1]for r in p[str(n)]];yy=min(ys)
 for name,t,reg in [('prefer',s.PREFER,[0,max(0,yy-100),3840,min(2160,max(ys)+220)-max(0,yy-100)]),('model',model,[0,max(0,yy-100),3840,min(2160,max(ys)+220)-max(0,yy-100)]),('head',head,[0,max(0,yy-120),3840,min(2160,yy+120)-max(0,yy-120)])]:
  print(n,name,s.locate(g,t,[sc-.015,sc,sc+.015],reg),flush=True)
 strip=np.min(a[900:2160,2995:3020],axis=2).mean(1)>135
 ix=np.where(strip)[0];groups=np.split(ix,np.where(np.diff(ix)>1)[0]+1);runs=[(int(z[0])+900,int(z[-1])+900)for z in groups if len(z)>30];print(n,'bright_face_edge',runs,flush=True)
