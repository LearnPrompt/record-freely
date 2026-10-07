from pathlib import Path
import subprocess,time,json
W=Path(__file__).resolve().parent
jobs=[('part-02','qa_shell_boxes.json'),('part-03','qa_calendar_boxes.json'),('part-04','qa_calendar_boxes.json')]
for name,patch in jobs:
 d=W/'chunks'/name
 while not (d/'complete.json').exists():time.sleep(5)
 marker=d/'review-repair-complete.json'
 if marker.exists():continue
 qa=d/'qa-complete.json'
 if qa.exists():
  r=json.loads(qa.read_text());r['status']='needs_repair';r['pending_review_patch']=patch;qa.write_text(json.dumps(r,ensure_ascii=False,indent=2))
 print('REPAIR START',name,patch,flush=True)
 subprocess.run(['python3',str(W/'apply_repairs.py'),name,str(W/patch)],check=True)
 marker.write_text(json.dumps({'status':'complete','part':name,'patch':patch},ensure_ascii=False,indent=2))
 print('REPAIR COMPLETE',name,flush=True)
print('ALL PENDING REPAIRS COMPLETE',flush=True)
