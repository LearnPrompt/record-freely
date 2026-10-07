import json,cv2,numpy as np
from pathlib import Path
W=Path('work/revision-v2');V=W/'chunks/part-00/redacted.mp4';q=json.load(open(W/'front_validation.json'));p=json.load(open(W/'chunks/part-00/report.json'));c=cv2.VideoCapture(str(V));samples=[]
points=[x['frame'] for x in q['sample_checks']];points += [4710,4720,4730,4740,4750,4760,4770,4800,4830,4846,4848]
for n in points:
 c.set(1,n);ok,im=c.read();assert ok;cv2.imwrite(str(W/f'front_actual_{n}.jpg'),im);samples.append({'frame':n,'time':round(n/30,6),'file':f'front_actual_{n}.jpg'})
ims=[]
for n in points[:25]:
 im=cv2.imread(str(W/f'front_actual_{n}.jpg'));t=cv2.resize(im,(640,360));cv2.putText(t,str(n),(8,350),0,.8,(0,0,255),2);ims.append(t)
while len(ims)%6:ims.append(np.zeros((360,640,3),np.uint8))
for j in range(0,len(ims),6):cv2.imwrite(str(W/f'front_actual_montage_{j}.jpg'),np.vstack([np.hstack(ims[j:j+3]),np.hstack(ims[j+3:j+6])]))
ims=[]
for n in points[25:]:
 im=cv2.imread(str(W/f'front_actual_{n}.jpg'));crop=im[910:1720,970:2810];t=cv2.resize(crop,(920,405));cv2.putText(t,str(n),(8,390),0,1,(0,0,255),2);ims.append(t)
while len(ims)%4:ims.append(np.zeros((405,920,3),np.uint8))
for j in range(0,len(ims),4):cv2.imwrite(str(W/f'front_actual_stability_{j}.jpg'),np.vstack([np.hstack(ims[j:j+2]),np.hstack(ims[j+2:j+4])]))
ids=[]
for n in range(4697,4849):
 f=p['frames'][n];rs=[]
 for b,r in zip(f['boxes'],f['regions']):
  if any(x in str(r) for x in ['U120','R004','U117']):rs.append({'box':b,'region':r})
 ids.append({'frame':n,'regions':rs})
json.dump({'status':'pending_visual_inspection','samples':samples,'samples_actual':len(points),'stability_records':ids},open(W/'front_visual_qa.json','w'),ensure_ascii=False,indent=2)
print('samples',len(points))
