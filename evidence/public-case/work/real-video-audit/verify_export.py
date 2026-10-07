from pathlib import Path
import cv2,json,subprocess,numpy as np
ROOT=Path(__file__).resolve().parent.parent.parent
OUT=ROOT/'outputs/带封面-前5分钟'
SOURCE=Path('/Users/carl/Downloads/带封面.mp4')
VIDEO=OUT/'redacted.mp4'
def probe(path):
 return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))
def audio(path,t):
 raw=subprocess.check_output(['ffmpeg','-v','error','-nostdin','-ss',str(t),'-i',str(path),'-t','2','-map','0:a:0','-f','f32le','-ac','1','-ar','16000','pipe:1'])
 return np.frombuffer(raw,np.float32).astype(float)
s=probe(SOURCE);o=probe(VIDEO);report=json.loads((OUT/'report.json').read_text());manifest=json.loads((ROOT/'work/real-video-audit/cache-manifest.json').read_text())
v=next(x for x in o['streams'] if x['codec_type']=='video')
checks={'duration_300_seconds':abs(float(v['duration'])-300)<1/30,'frames_9000':int(v['nb_frames'])==9000,'size_3840x2160':(v['width'],v['height'])==(3840,2160),'fps_30':v['avg_frame_rate']=='30/1','audio_tracks_preserved':sum(x['codec_type']=='audio' for x in o['streams'])==sum(x['codec_type']=='audio' for x in s['streams']),'report_complete':report['status']=='complete','report_frames_9000':len(report['frames'])==9000,'region_metadata_consistent':all(len(f['boxes'])==len(f['regions'])==len(f['origins']) for f in report['frames']),'source_size_and_mtime_unchanged':SOURCE.stat().st_size==manifest['size'] and SOURCE.stat().st_mtime_ns==manifest['mtime_ns']}
audio_samples=[]
for t in [2,66,142,215,296]:
 a,b=audio(SOURCE,t),audio(VIDEO,t);n=min(len(a),len(b));a,b=a[:n],b[:n]
 size=1<<(2*n-1).bit_length();corr=np.fft.irfft(np.fft.rfft(a,size)*np.conj(np.fft.rfft(b,size)),size)
 lags=np.arange(-160,161);lag=int(lags[np.argmax(corr[lags%size])])
 if lag>=0: x,y=a[lag:],b[:n-lag]
 else: x,y=a[:n+lag],b[-lag:]
 coefficient=float(np.dot(x,y)/max(1e-12,np.linalg.norm(x)*np.linalg.norm(y)))
 audio_samples.append({'start_seconds':t,'duration_seconds':2,'correlation':round(coefficient,6),'best_lag_ms':round(lag/16,4)})
checks['sampled_audio_alignment_within_5_ms']=all(abs(x['best_lag_ms'])<=5 and x['correlation']>.95 for x in audio_samples)
source_cap=cv2.VideoCapture(str(SOURCE));out_cap=cv2.VideoCapture(str(VIDEO));picture_samples=[]
for t in [15,65,72.4,81.1,81.133333,81.166667,110,147,250,295]:
 frame_number=round(t*30);source_cap.set(cv2.CAP_PROP_POS_FRAMES,frame_number);out_cap.set(cv2.CAP_PROP_POS_FRAMES,frame_number)
 ok1,a=source_cap.read();ok2,b=out_cap.read()
 if not ok1 or not ok2: checks['sampled_images_readable']=False;continue
 mask=np.zeros(a.shape[:2],np.uint8)
 for x,y,w,h in report['frames'][frame_number]['boxes']:mask[y:y+h,x:x+w]=255
 mask=cv2.dilate(mask,np.ones((13,13),np.uint8))
 diff=np.abs(a.astype(np.int16)-b.astype(np.int16));outside=diff[mask==0]
 picture_samples.append({'time_seconds':t,'mask_count':len(report['frames'][frame_number]['boxes']),'outside_mask_mean_absolute_rgb_error':round(float(outside.mean()),4),'outside_mask_rgb_pixel_fraction_above_30':round(float(np.mean(outside.max(axis=1)>30)),6)})
source_cap.release();out_cap.release()
result={'checks':checks,'passed':all(checks.values()),'output_video':{k:v[k] for k in ['width','height','duration','avg_frame_rate','nb_frames','codec_name','pix_fmt']},'audio_alignment_samples':audio_samples,'outside_mask_image_samples':picture_samples,'limits':'Image/audio comparison is sampled; cannot prove no missed URL or semantic false positive. Full codec decoding is checked separately.'}
(OUT/'技术验证.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
if not result['passed']:raise SystemExit(1)
