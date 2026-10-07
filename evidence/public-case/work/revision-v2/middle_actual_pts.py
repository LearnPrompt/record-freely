from pathlib import Path
import subprocess,json
W=Path('work/revision-v2');frames=[11807,11808,11970,12030,12204,12256,12270,12823,12999,13008,13009,14189,14550,15881,15900,16110,16531,16532,25590,25642,26160,26213,26214,26215,29158,29160,29162]
for f in frames:
 p=1 if f<18000 else(2 if f<27000 else 3);start=p*9000;src=W/f'chunks/part-{p:02d}/redacted.mp4';dest=W/f'middle_pts_actual_{f}.jpg'
 subprocess.run(['ffmpeg','-v','error','-threads','2','-ss',f'{(f-start)/30:.10f}','-i',str(src),'-frames:v','1','-vf','scale=1920:1080','-q:v','2','-y',str(dest)],check=True)
(W/'middle_pts_images_ready.json').write_text(json.dumps({'status':'ready','decode':'independent_ffmpeg_accurate_pts_seek','frames':frames}));print('ready',frames)
