from pathlib import Path
import json,subprocess,time,os
ROOT=Path(__file__).resolve().parents[2];W=ROOT/'work/full-video';SRC=Path('/Users/carl/Downloads/带封面.mp4');C=W/'cache';C.mkdir(exist_ok=True)
old=json.load(open(ROOT/'work/real-video-audit/cache-manifest.json'));assert SRC.stat().st_size==old['size']and SRC.stat().st_mtime_ns==old['mtime_ns']
manifest={'source':str(SRC),'source_size':SRC.stat().st_size,'source_mtime_ns':SRC.stat().st_mtime_ns,'fps':30,'source_frames':63871,'approved_first_frames':9000,'parts':[]}
for i,startframe in enumerate(range(9000,63871,9000),1):
 frames=min(9000,63871-startframe);part={'index':i,'name':f'part-{i:02}','start_frame':startframe,'frames':frames,'start_seconds':startframe/30,'duration_seconds':frames/30,'cache':str(C/f'part-{i:02}.mkv')};manifest['parts'].append(part)
(W/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));begin=time.monotonic()
for part in manifest['parts']:
 dest=Path(part['cache']);done=dest.with_suffix('.ready.json')
 if done.exists()and dest.exists():continue
 stage=dest.with_suffix('.partial.mkv')
 (W/'normalize-progress.json').write_text(json.dumps({'part':part['name'],'start_seconds':part['start_seconds'],'stage':'normalizing','elapsed_seconds':round(time.monotonic()-begin,1)}))
 print('normalizing',part['name'],part['start_seconds'],part['frames'],flush=True)
 command=['ffmpeg','-v','error','-nostdin','-y','-ss',str(part['start_seconds']),'-i',str(SRC),'-t',str(part['duration_seconds']),'-map','0:v:0','-an','-vf','fps=30','-c:v','ffv1','-threads','4','-pix_fmt','bgr0','-map_metadata','-1',str(stage)]
 with open(C/f'{part["name"]}.normalize.log','w')as err:subprocess.run(command,stderr=err,check=True)
 info=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_packets','-select_streams','v:0','-show_entries','stream=nb_read_packets,width,height,r_frame_rate','-of','json',str(stage)]))['streams'][0];assert int(info['nb_read_packets'])==part['frames'],info
 stage.replace(dest);done.write_text(json.dumps({'frames':part['frames'],'width':info['width'],'height':info['height'],'size':dest.stat().st_size}));print('normalized ready',part['name'],'elapsed',round(time.monotonic()-begin),flush=True)
print('all normalization complete',flush=True)
