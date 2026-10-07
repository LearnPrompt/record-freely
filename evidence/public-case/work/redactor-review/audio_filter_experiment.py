from pathlib import Path
import subprocess,json
import numpy as np
BASE=Path(__file__).resolve().parent/'audio-filter-experiment'
BASE.mkdir(exist_ok=True)
def run(args):
    result=subprocess.run(['ffmpeg','-v','error','-nostdin','-y',*args],capture_output=True,text=True)
    if result.returncode: raise RuntimeError(result.stderr)
source=BASE/'source.mkv'
run(['-f','lavfi','-i','testsrc2=size=96x64:rate=30:duration=2',
     '-itsoffset','0.5','-f','lavfi','-i','sine=frequency=800:duration=1.5',
     '-map','0:v','-map','1:a','-c:v','ffv1','-c:a','pcm_s16le',str(source)])
results=[]
for name,start,duration in [('silent',0,.2),('offset',.4,.8)]:
    silent=BASE/(name+'-video.mp4')
    run(['-ss',str(start),'-i',str(source),'-t',str(duration),'-map','0:v','-an','-c:v','libx264','-pix_fmt','yuv420p',str(silent)])
    output=BASE/(name+'-mux.mp4')
    run(['-i',str(silent),'-ss',str(start),'-i',str(source),'-map','0:v:0','-map','1:a?',
         '-c:v','copy','-c:a','aac','-b:a','192k','-af',f'aresample=48000:async=1:first_pts=0,apad=whole_dur={duration}',
         '-t',str(duration),'-map_metadata','-1','-map_chapters','-1',str(output)])
    info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(output)]))
    audio=[s for s in info['streams'] if s['codec_type']=='audio']
    result={'case':name,'audio_streams':len(audio),'audio_start':audio[0].get('start_time') if audio else None,
            'audio_duration':audio[0].get('duration') if audio else None}
    if audio:
        pcm=subprocess.check_output(['ffmpeg','-v','error','-i',str(output),'-map','0:a:0','-f','f32le','-ac','1','-ar','48000','pipe:1'])
        signal=np.frombuffer(pcm,np.float32)
        result['samples']=len(signal)
        if name=='silent': result['peak']=float(np.max(np.abs(signal)))
        else:
            # AAC can smear transients around block edges, so use quiet pre-roll
            # and established tone windows instead of one-sample onset.
            result['rms_before_0.075']=float(np.sqrt(np.mean(signal[:3600]**2)))
            result['rms_0.125_to_0.175']=float(np.sqrt(np.mean(signal[6000:8400]**2)))
            active=np.flatnonzero(np.abs(signal)>.01)
            result['first_active_seconds']=float(active[0]/48000) if len(active) else None
    results.append(result)
print(json.dumps(results,indent=2))
(BASE/'results.json').write_text(json.dumps(results,indent=2))
