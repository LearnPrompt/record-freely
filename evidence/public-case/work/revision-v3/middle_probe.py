from pathlib import Path
import subprocess,cv2,json,sys,re
sys.path.insert(0,'work/full-video');from qa_shell_continuation import Vision
W=Path('work/revision-v3');D=W/'middle_proof';D.mkdir(exist_ok=True);v=Vision(D)
for f in [11808,11970,12030,12204,12823,12930,12999,13008,15900,15930,16170,16200,16531]:
 p=D/f'source_{f}.jpg'
 subprocess.run(['ffmpeg','-v','error','-reinit_filter','0','-ss',f'{f/30:.10f}','-i','/Users/carl/Downloads/带封面.mp4','-frames:v','1','-vf','scale=1920:1080','-q:v','2','-y',str(p)],check=True)
 im=cv2.imread(str(p));o=v.read(im);(D/f'ocr_{f}.json').write_text(json.dumps(o,ensure_ascii=False))
 print(f,[(z['text'],z['box'])for z in o if 'clawhub.ai/'in z['text'].lower()or '/Users/carl/'in z['text']],flush=True)
v.close()
