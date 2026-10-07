from pathlib import Path
import json,subprocess

ROOT=Path(__file__).resolve().parents[2];W=ROOT/'work/revision-v3';OUT=ROOT/'outputs/带封面-修正版v3'

def main():
 m=json.loads((W/'manifest.json').read_text());src=Path(m['source'])
 assert (src.stat().st_size,src.stat().st_mtime_ns)==(m['source_size'],m['source_mtime_ns'])
 previous=ROOT/'outputs/带封面-修正版v2/redacted.mp4'
 assert (previous.stat().st_size,previous.stat().st_mtime_ns)==(m['previous_output_size'],m['previous_output_mtime_ns'])
 for phase in ['front','middle']:
  qa=json.loads((W/f'{phase}_visual_qa.json').read_text());assert qa['status']=='passed',phase
 inputs=[]
 for p in m['parts']:
  d=W/'chunks'/p['name'];r=json.loads((d/'report.json').read_text());assert r['status']=='complete' and len(r['frames'])==p['frames']
  assert (d/'complete.json').exists();inputs.append((d/'redacted.mp4',p['frames']))
 assert sum(n for _,n in inputs)==63871
 OUT.mkdir(exist_ok=True);playlist=W/'revision-concat.txt';playlist.write_text(''.join(f"file '{p.resolve()}'\nduration {n/30:.10f}\n"for p,n in inputs))
 stage=W/'revision-stage.mp4'
 with (W/'assemble.log').open('w') as err:
  subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-copyts','-f','concat','-safe','0','-i',str(playlist),'-i',str(src),'-map','0:v:0','-map','1:a?','-c','copy','-avoid_negative_ts','disabled','-map_metadata','-1','-map_chapters','-1','-movflags','+faststart',str(stage)],stderr=err,check=True)
 info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(stage)]));v=next(x for x in info['streams']if x['codec_type']=='video')
 assert int(v['nb_frames'])==63871 and abs(float(v['duration'])-63871/30)<.002 and abs(float(v['start_time']))<.00001
 stage.replace(OUT/'redacted.mp4');print('Revision assembled: 63871 frames, video starts at zero',flush=True)

if __name__=='__main__':main()
