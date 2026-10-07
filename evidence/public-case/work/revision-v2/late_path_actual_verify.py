import cv2,json,numpy as np,subprocess,sys
from pathlib import Path
D=Path('work/revision-v2');patch=json.load(open(D/'late_patch.json'))['frames'];frames=[44922,44923,44925,44926,44927,44928,45000,45239,45240,45241,45635,45636,45690,45714,45811,46080,46107,46112,46120,46121,46125,46140,46148,46149,46150,46151,46152,46200,46201,48941,48942,48992,48993,49040,49078,49079,49109,49110,49111,49225,49226,49280,49349,49350,49369,49370,49371,49440,49554,49555,51379,51380,51454,51455,51456,51539,51540,51541,51684,51685,51686,51687,51742,51743,51744,52108,52109]
records=[];reports={};caps={};w=subprocess.Popen([str(D/'late_vision')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
for f in frames:
 p='part-04' if f<45000 else 'part-05';offset=36000 if p=='part-04' else 45000
 if p not in caps:caps[p]=cv2.VideoCapture(str(D/'chunks'/p/'redacted.mp4'));reports[p]=json.load(open(D/'chunks'/p/'report.json'))
 cap=caps[p];cap.set(cv2.CAP_PROP_POS_FRAMES,f-offset);ok,im=cap.read()
 if not ok:raise RuntimeError(f)
 word=reports[p]['frames'][f-offset];pathboxes=[b for b,reg in zip(word['boxes'],word['regions']) if reg['kind']=='reviewed_path'];maskstats=[]
 for b in pathboxes:
  x,y,bw,h=b;delta=np.abs(im[y+3:y+h-3,x+3:x+bw-3].astype(np.int16)-112);maskstats.append({'box':b,'gray_fraction':float((delta.max(axis=2)<=8).mean()),'mean_abs_gray_error':float(delta.mean())})
 cv2.imwrite(str(D/f'late_actual_path_{f}.jpg'),im)
 if f in [45240,49110,51540,49440,46140]:
  cv2.imwrite(str(D/'late_actual_path_ocr.png'),cv2.resize(im,(1920,1080)));w.stdin.write(json.dumps({'path':str((D/'late_actual_path_ocr.png').resolve())})+'\n');w.stdin.flush();obs=json.loads(w.stdout.readline())['observations'];left=[m['target'] for o in obs for m in o['matches'] if m['target']=='path']
 else:left=None
 records.append({'frame':f,'time':f/30,'path_masks':len(pathboxes),'mask_stats':maskstats,'native_identity_prefix_leaks':left});print(f,len(pathboxes),left,flush=True)
for cap in caps.values():cap.release()
w.stdin.close();w.wait();(D/'late_path_actual_qa.json').write_text(json.dumps({'source':'actual revision-v2 part04/05','samples':records,'still_requires_human_visual_checks':True},indent=2));print('DONE',len(records),flush=True)
