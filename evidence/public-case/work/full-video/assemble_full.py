from pathlib import Path
import json,subprocess
ROOT=Path(__file__).resolve().parents[2];W=ROOT/'work/full-video';SRC=Path('/Users/carl/Downloads/带封面.mp4');OUT=ROOT/'outputs/带封面-完整版'
def main():
 m=json.load(open(W/'manifest.json'));assert SRC.stat().st_size==m['source_size']and SRC.stat().st_mtime_ns==m['source_mtime_ns']
 inputs=[(ROOT/'outputs/带封面-前5分钟/redacted.mp4',9000)]
 for p in m['parts']:
  d=W/'chunks'/p['name'];r=json.load(open(d/'report.json'));assert r['status']=='complete'and len(r['frames'])==p['frames']
  assert (d/'qa-complete.json').is_file(),f'{p["name"]} visual sample review not complete'
  qa=json.load(open(d/'qa-complete.json'));assert qa.get('status') in ('passed','complete'),f'{p["name"]} visual QA has unresolved issues: {qa.get("status")}'
  inputs.append((d/'redacted.mp4',p['frames']))
 assert sum(n for _,n in inputs)==63871
 OUT.mkdir(exist_ok=True);playlist=W/'full-concat.txt';playlist.write_text(''.join(f"file '{p}'\nduration {n/30:.10f}\n"for p,n in inputs))
 stage=W/'full-stage.mp4';cmd=['ffmpeg','-v','error','-nostdin','-y','-copyts','-f','concat','-safe','0','-i',str(playlist),'-i',str(SRC),'-map','0:v:0','-map','1:a?','-c','copy','-avoid_negative_ts','disabled','-map_metadata','-1','-map_chapters','-1','-movflags','+faststart',str(stage)]
 with open(W/'assemble.log','w')as err:subprocess.run(cmd,stderr=err,check=True)
 probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(stage)]));v=next(a for a in probe['streams']if a['codec_type']=='video');assert int(v['nb_frames'])==63871 and abs(float(v['duration'])-63871/30)<1/30
 stage.replace(OUT/'redacted.mp4');(OUT/'progress.json').write_text(json.dumps({'stage':'assembled_waiting_final_verification','frames':63871,'video_seconds':63871/30,'original_audio_copied':True},ensure_ascii=False,indent=2));print('full movie assembled',v['nb_frames'],v['duration'])
if __name__=='__main__':main()
