"""Run only after independent visual review of all final chunks is passed."""
from pathlib import Path
import json,cv2
from PIL import Image,ImageDraw,ImageFont
P=Path(__file__).parent;OUT=P.parents[1]/'outputs'/'带封面-完整版';OUT.mkdir(parents=True,exist_ok=True)
markers=[]
for k in range(1,8):
 m=json.load(open(P/'chunks'/f'part-{k:02}'/'qa-complete.json'));assert m['status']=='passed';markers.append(m)
font=ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc',25)
def timecode(n):
 t=n/30;return f'{int(t//60):02}:{t%60:06.3f}'
def read(n):
 k=min(7,(n-9000)//9000+1);cap=cv2.VideoCapture(str(P/'chunks'/f'part-{k:02}'/'redacted.mp4'));cap.set(1,n-(k*9000));ok,a=cap.read();assert ok;cap.release();return Image.fromarray(cv2.cvtColor(a,cv2.COLOR_BGR2RGB))
ns=[11700,17850,18065,20041,35906,36000,46122,58207];sheet=Image.new('RGB',(1920,600*4),'#f5f5f5');d=ImageDraw.Draw(sheet)
for i,n in enumerate(ns):
 x=i%2*960;y=i//2*600;d.text((x+15,y+10),timecode(n),font=font,fill='#202020');sheet.paste(read(n).resize((960,540)),(x,y+50))
sheet.save(OUT/'检查样张01-实际成片场景.jpg',quality=94)
rows=[(17850,(0,1450,3840,2160),'代理网址与白字幕交叠'),(20041,(2600,500,3840,1280),'小截图位置与尺寸变化'),(36000,(640,850,2400,1500),'蓝色文档链接及8字符折行尾部'),(46122,(100,890,3840,1310),'四行资源参数网址'),(58207,(0,0,2500,220),'网址出画时与顶部章节重叠')]
sheet=Image.new('RGB',(1600,1600),'#f5f5f5');d=ImageDraw.Draw(sheet)
for i,(n,roi,label)in enumerate(rows):
 y=i*320;d.text((15,y+8),f'{timecode(n)}  {label}',font=font,fill='#202020');im=read(n).crop(roi);im.thumbnail((1570,265));sheet.paste(im,(15,y+45))
sheet.save(OUT/'检查样张02-局部折行与边缘.jpg',quality=95)
ns=sorted({n for m in markers for n in m['actual_reviewed_global_frames']});json.dump({'source_scene_points':55,'actual_final_chunk_reviewed_unique_frames':len(ns),'actual_final_chunk_reviewed_global_frames':ns,'limitations':['Scene and known-defect sampling, not every-frame human viewing.','Local OCR/template frame counts are separate from human visual-review frame counts.'],'parts':markers},open(P/'qa_final_review_manifest.json','w'),ensure_ascii=False,indent=2)
print('deliverable samples ready',len(ns),'actual unique frames')
