from pathlib import Path
import importlib.util,json,os,sys,time,subprocess
from stream_capture import StreamCapture
import cv2
BASE_CAPTURE=cv2.VideoCapture
ROOT=Path(__file__).resolve().parents[2];W=ROOT/'work/full-video';manifest=json.load(open(W/'manifest.json'));manifest['parts']=[p for p in manifest['parts']if p['index']>=5];SRC=Path(manifest['source']);CH=W/'chunks';CH.mkdir(exist_ok=True)
def log_status(part,stage,**extra):(W/'processing-progress-parallel.json').write_text(json.dumps({'part':part['name'],'start_seconds':part['start_seconds'],'stage':stage,**extra},ensure_ascii=False,indent=2))
for part in manifest['parts']:
 dest=CH/part['name'];completed=dest/'complete.json'
 if completed.exists():continue
 log_status(part,'initializing_stream_decoder')
 assert SRC.stat().st_size==manifest['source_size']and SRC.stat().st_mtime_ns==manifest['source_mtime_ns']
 if dest.exists():raise RuntimeError(f'Incomplete existing chunk {dest}; inspect before retry')
 spec=importlib.util.spec_from_file_location(f'full_engine_{part["index"]}',W/'redact_full_engine.py');r=importlib.util.module_from_spec(spec);sys.modules[spec.name]=r;spec.loader.exec_module(r)
 orig=r.run;cache=Path(part['cache'])
 def cached(command):
  if command[0]=='ffmpeg'and str(command[-1]).endswith('normalized.mkv')and'ffv1'in command:
   assert Path(command[command.index('-i')+1])==SRC
   assert abs(float(command[command.index('-ss')+1])-part['start_seconds'])<1e-8
   assert abs(float(command[command.index('-t')+1])-part['duration_seconds'])<1e-8
   return ''
  return orig(command)
 r.run=cached
 def capture(path):
  if str(path).endswith('normalized.mkv'):
   return StreamCapture(SRC,part['start_seconds'],part['frames'],log=CH/f'{part["name"]}.decode.log')
  return BASE_CAPTURE(path)
 r.cv2.VideoCapture=capture
 log_status(part,'ocr_and_encoding');begin=time.monotonic()
 print('START',part['name'],'source',part['start_seconds'],part['duration_seconds'],flush=True)
 sys.argv=[str(W/'redact_full_engine.py'),str(SRC),'--start',str(part['start_seconds']),'--duration',str(part['duration_seconds']),'--ocr-workers','2','--output-dir',str(dest)]
 r.main();r.cv2.VideoCapture=BASE_CAPTURE;report=json.load(open(dest/'report.json'));assert report['status']=='complete'and report['processed_frames']==part['frames']and len(report['frames'])==part['frames']
 report['decode_backend']='FFmpeg bounded RGB stream; identical CFR normalization without FFV1 cache';report['source_start_frame']=part['start_frame'];report['source_start_seconds']=part['start_seconds'];report['full_video_part']=part['name'];(dest/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 completed.write_text(json.dumps({'part':part['name'],'start_frame':part['start_frame'],'frames':part['frames'],'seconds':part['duration_seconds'],'masked_frames':report['masked_frames'],'elapsed_seconds':round(time.monotonic()-begin,2)}));log_status(part,'complete',frames=part['frames'],masked_frames=report['masked_frames']);print('COMPLETE',part['name'],part['frames'],report['masked_frames'],flush=True)
(W/'tail-chunks-complete.json').write_text(json.dumps({'status':'complete','frames':18871,'parts':3}));print('TAIL CHUNKS COMPLETE',flush=True)
