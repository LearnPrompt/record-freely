from pathlib import Path
import json,subprocess,time

W=Path(__file__).resolve().parent;ROOT=W.parents[1];OUT=ROOT/'outputs/带封面-修正版v2'
def ready(phase):
 try:return json.loads((W/f'{phase}_visual_qa.json').read_text())['status']=='passed'
 except(FileNotFoundError,KeyError,json.JSONDecodeError):return False
while not all(ready(p)for p in ['front','middle','late']):time.sleep(10)
for name in ['assemble_revision.py','verify_full.py']:
 print('RUN',name,flush=True);subprocess.run(['python3',str(W/name)],check=True)
print('FULL VIDEO AND AUDIO DECODE',flush=True)
log=W/'full-decode.log'
with log.open('w')as err:
 subprocess.run(['ffmpeg','-v','error','-nostdin','-threads','4','-i',str(OUT/'redacted.mp4'),'-map','0:v:0','-map','0:a?','-f','null','-'],stderr=err,check=True)
assert not log.read_text().strip()
p=OUT/'技术验证.json';d=json.loads(p.read_text());d['checks']['full_video_and_audio_codec_decode']=True
m=json.loads((W/'manifest.json').read_text());old=ROOT/'outputs/带封面-完整版/redacted.mp4'
d['checks']['previous_full_version_unchanged']=(old.stat().st_size,old.stat().st_mtime_ns)==(m['previous_output_size'],m['previous_output_mtime_ns'])
d['passed']=all(d['checks'].values());assert d['passed'];d['limits']='全片技术完整性、音轨一致性与完整解码通过。视觉按用户反馈点、首尾和转折抽查；不代表零漏检。'
p.write_text(json.dumps(d,ensure_ascii=False,indent=2));(W/'technical-complete.json').write_text(json.dumps({'status':'passed','frames':63871,'video_seconds':63871/30},indent=2));print('REVISION TECHNICAL VERIFICATION COMPLETE',flush=True)
