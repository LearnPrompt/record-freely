import json,cv2,numpy as np,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path('work/full-video').resolve()))
from stream_capture import StreamCapture
D=Path('work/revision-v2');part=D/'chunks/part-06';report=json.load(open(part/'report.json'))
patch=json.load(open(D/'late_word_refined.json'))['frames'];drop=[int(f) for f,d in patch.items() if any('dropout' in a['box_method'] for a in d['add'])]
scouts=sorted(set(list(range(57870,59191,60))+[57869,57870,57871,57900,57959,57960,58000,58349,58350,58351,58529,58530,58531,58999,59000,59003,59006,59007,59059,59060,59065,59077,59078,59120,59121,59125,59128,59129,59177,59178,59179,59190,59191]+drop))
cap=StreamCapture(part/'redacted.mp4',(57869-54000)/30,59192-57869);tests=[];bad=[];sample_records=[];w=subprocess.Popen([str(D/'late_word_vision')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
for f in range(57869,59192):
 ok,im=cap.read()
 if not ok:raise RuntimeError(f)
 record=report['frames'][f-54000];wordcount=0
 for box,reg in zip(record['boxes'],record['regions']):
  if reg['kind']!='reviewed_word':continue
  x,y,b,h=box;inner=im[y+3:y+h-3,x+3:x+b-3]
  delta=np.abs(inner.astype(np.int16)-112);fraction=float((delta.max(axis=2)<=8).mean());mean=float(delta.mean());wordcount+=1
  if fraction<.98 or mean>3:bad.append({'frame':f,'box':box,'gray_fraction':fraction,'mean':mean})
 tests.append({'frame':f,'word_boxes':wordcount})
 if f in scouts:
  cv2.imwrite(str(D/f'late_actual_word_{f}.jpg'),im)
  cv2.imwrite(str(D/'late_actual_ocr.png'),cv2.resize(im,(2560,1440)));w.stdin.write(json.dumps({'path':str((D/'late_actual_ocr.png').resolve())})+'\n');w.stdin.flush();obs=json.loads(w.stdout.readline())['observations'];visible=[m['target'] for o in obs for m in o['matches'] if m['target'].startswith('word_')]
  inside=57870<=f<=59190
  sample_records.append({'frame':f,'time':f/30,'word_boxes':wordcount,'detected_target_words_after_redaction':visible,'within_requested_word_window':inside})
  print('sample',f,wordcount,visible,flush=True)
cap.release();w.stdin.close();w.wait()
result={'scope':'actual revision-v2 part06; all target word mask regions every frame plus fixed/boundary/zoom/dropout OCR scouts','all_word_window_frames_decoded':1321,'word_masks_tested':sum(x['word_boxes'] for x in tests),'mask_gray_test_failures':bad,'word_scout_frames':scouts,'native_dropout_source_frames':drop,'ocr_scout_results':sample_records,'inside_window_target_leaks':[d for d in sample_records if d['within_requested_word_window'] and d['detected_target_words_after_redaction']],'unmodified_outside_boundary_frames':[57869,59191]}
(D/'late_word_actual_qa.json').write_text(json.dumps(result,indent=2));print('DONE',sum(x['word_boxes'] for x in tests),len(bad),len(result['inside_window_target_leaks']),flush=True)
