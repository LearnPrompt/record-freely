# -*- coding: utf-8 -*-
from pathlib import Path
import json,subprocess,time
W=Path(__file__).resolve().parent;OUT=W.parents[1]/'outputs/带封面-修正版v3'
while not (W/'technical-complete.json').exists():time.sleep(10)
assert json.loads((W/'technical-complete.json').read_text())['status']=='passed'
subprocess.run(['python3',str(W/'build_full_report.py'),'--first-report',str(W/'chunks/part-00/report.json'),'--chunks-root',str(W/'chunks'),'--output-dir',str(OUT),'--technical-verification',str(OUT/'技术验证.json')],check=True)
subprocess.run(['python3',str(W/'write_revision_notes.py')],check=True)
subprocess.run(['python3',str(W/'finalize_delivery.py')],check=True)
print('DELIVERY FILES READY FOR FINAL REVIEW',flush=True)
