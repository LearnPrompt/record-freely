import subprocess
from pathlib import Path
from PIL import Image, ImageDraw
base=Path('work/real-video-audit')
times=[58,61,65,70,75,98,102,107,112,117,122,127,132,137,142,147,152,157,160,292,295,298]
for t in times:
 p=base/f'qa-exact-{t:03d}.jpg'
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-ss',str(t),'-i','/Users/carl/Downloads/带封面.mp4','-frames:v','1','-vf','scale=1280:-1',str(p)],check=True)
for group in range((len(times)+5)//6):
 subset=times[group*6:group*6+6]
 out=Image.new('RGB',(2560,756*3),(30,30,30));d=ImageDraw.Draw(out)
 for i,t in enumerate(subset):
  x=(i%2)*1280;y=(i//2)*756
  out.paste(Image.open(base/f'qa-exact-{t:03d}.jpg'),(x,y+36));d.text((x+10,y+7),f'{t}s',fill='white')
 out.save(base/f'qa-exact-contact-{group}.jpg')
