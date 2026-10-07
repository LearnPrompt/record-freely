from pathlib import Path
import cv2,json, numpy as np
from PIL import Image,ImageDraw,ImageFont
P=Path(__file__).parent;OUT=P.parents[1]/'outputs'/'带封面-完整版'
ns=sorted(set([1800,4260,4800,8999,9000,17999,18000,26999,27000,35999,36000,44999,45000,53999,54000,62999,63000,63870,11700,17850,18065,20041,35906,46122,58207,34326,35533,39432,45720]))
cap=cv2.VideoCapture(str(OUT/'redacted.mp4'));results=[]
for n in ns:
 cap.set(cv2.CAP_PROP_POS_FRAMES,n);ok,a=cap.read();assert ok,('full',n)
 if n<9000: ref=P.parents[1]/'outputs'/'带封面-前5分钟'/'redacted.mp4';local=n
 else:
  k=min(7,(n-9000)//9000+1);ref=P/'chunks'/f'part-{k:02}'/'redacted.mp4';local=n-k*9000
 rc=cv2.VideoCapture(str(ref));rc.set(cv2.CAP_PROP_POS_FRAMES,local);ok,b=rc.read();assert ok,('ref',n);rc.release()
 diff=np.abs(a.astype(np.int16)-b.astype(np.int16));results.append({'global_frame':n,'seconds':n/30,'source_of_comparison':ref.name if n<9000 else f'part-{k:02}','max_pixel_difference':int(diff.max()),'mean_pixel_difference':float(diff.mean()),'status':'passed' if np.array_equal(a,b) else 'different'})
 cv2.imwrite(str(P/f'qa_full_actual_{n:05}.jpg'),a)
cap.release();assert all(r['status']=='passed' for r in results)
font=ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc',25)
def read(n):return Image.open(P/f'qa_full_actual_{n:05}.jpg').convert('RGB')
def timecode(n):return f'{int(n/1800):02}:{n/30%60:06.3f}'
frames=[11700,17850,18065,20041,35906,36000,46122,58207];sheet=Image.new('RGB',(1920,2400),'#f5f5f5');d=ImageDraw.Draw(sheet)
for i,n in enumerate(frames):
 x=i%2*960;y=i//2*600;d.text((x+15,y+10),timecode(n),font=font,fill='#202020');sheet.paste(read(n).resize((960,540)),(x,y+50))
sheet.save(OUT/'检查样张01-实际成片场景.jpg',quality=94)
rows=[(17850,(0,1450,3840,2160),'代理网址与白字幕交叠'),(20041,(2600,500,3840,1280),'小截图位置与尺寸变化'),(36000,(640,850,2400,1500),'蓝色文档链接及8字符折行尾部'),(46122,(100,890,3840,1310),'四行资源参数网址'),(58207,(0,0,2500,220),'网址出画时与顶部章节重叠')]
sheet=Image.new('RGB',(1600,1600),'#f5f5f5');d=ImageDraw.Draw(sheet)
for i,(n,roi,label)in enumerate(rows):
 y=i*320;d.text((15,y+8),f'{timecode(n)}  {label}',font=font,fill='#202020');im=read(n).crop(roi);im.thumbnail((1570,265));sheet.paste(im,(15,y+45))
sheet.save(OUT/'检查样张02-局部折行与边缘.jpg',quality=95)
json.dump({'status':'passed','actual_full_movie_sample_count':len(ns),'all_decoded_pixels_match_approved_first5_or_final_chunks':True,'results':results,'limits':'Fixed known scene samples, segment boundaries, accepted first5 and last frame. Not every-frame human viewing.'},open(P/'qa_full_actual_check.json','w'),ensure_ascii=False,indent=2)
print('full actual comparison passed',len(ns),'frames')
