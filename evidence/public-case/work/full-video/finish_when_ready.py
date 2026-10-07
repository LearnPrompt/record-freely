from pathlib import Path
import json,subprocess,time
W=Path(__file__).resolve().parent;ROOT=W.parents[1];OUT=ROOT/'outputs/带封面-完整版'
m=json.loads((W/'manifest.json').read_text())
def ready(p):
 d=W/'chunks'/p['name']
 try:return (d/'complete.json').exists() and json.loads((d/'qa-complete.json').read_text()).get('status')in('passed','complete')
 except(FileNotFoundError,json.JSONDecodeError):return False
while not all(ready(p)for p in m['parts']):time.sleep(10)
print('ALL SEVEN CHUNKS QA READY',flush=True)
for name in ['assemble_full.py','verify_full.py']:
 print('RUN',name,flush=True);subprocess.run(['python3',str(W/name)],check=True)
video=OUT/'redacted.mp4';log=W/'full-decode.log'
print('FULL CODEC DECODE',flush=True)
with open(log,'w')as err:subprocess.run(['ffmpeg','-v','error','-nostdin','-threads','4','-i',str(video),'-map','0:v:0','-map','0:a?','-f','null','-'],stderr=err,check=True)
assert not log.read_text().strip(),'Final movie has codec decoding errors'
p=OUT/'技术验证.json';result=json.loads(p.read_text());result['checks']['full_video_and_audio_codec_decode']=True;result['passed']=all(result['checks'].values());result['limits']='Full codec decoding passed. Visual review is sampled; technical integrity does not establish zero missed URLs.';p.write_text(json.dumps(result,ensure_ascii=False,indent=2))
(W/'full-technical-complete.json').write_text(json.dumps({'status':'passed','frames':63871,'video_seconds':63871/30,'requires_final_visual_review':True},ensure_ascii=False,indent=2));print('FULL TECHNICAL VERIFICATION COMPLETE',flush=True)
