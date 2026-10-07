import cv2,json,subprocess,time
from pathlib import Path
D=Path('work/revision-v2');w=subprocess.Popen([str(D/'late_word_vision')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
im=cv2.imread(str(D/'late_src_1929.jpg'))
for width in [1920,2560,3840,1920,2560,3840]:
 t=time.time();small=cv2.resize(im,(width,int(width*9/16)));cv2.imwrite(str(D/'late_benchmark.png'),small)
 w.stdin.write(json.dumps({'path':str((D/'late_benchmark.png').resolve())})+'\n');w.stdin.flush();r=json.loads(w.stdout.readline());print(width,round(time.time()-t,2),[(m['target'],m['box']) for o in r['observations'] for m in o['matches']],flush=True)
w.stdin.close();w.wait()
