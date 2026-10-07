from pathlib import Path
import json,subprocess,cv2,numpy as np,hashlib
ROOT=Path(__file__).resolve().parents[2];W=ROOT/'work/revision-v2';OUT=ROOT/'outputs/带封面-修正版v2';SRC=Path('/Users/carl/Downloads/带封面.mp4');VIDEO=OUT/'redacted.mp4'
def probe(p):return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)]))
def audio(p,t):
 raw=subprocess.check_output(['ffmpeg','-v','error','-nostdin','-ss',str(t),'-i',str(p),'-t','2','-map','0:a:0','-f','f32le','-ac','1','-ar','16000','pipe:1']);return np.frombuffer(raw,np.float32).astype(float)
def audio_packet_hashes(p):
 j=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','a:0','-show_packets','-show_data_hash','sha256','-show_entries','packet=data_hash','-of','json',str(p)]));h=hashlib.sha256()
 for item in j['packets']:h.update(item['data_hash'].encode('ascii'))
 return len(j['packets']),h.hexdigest()
def frame_rgb(path,n):
 start=max(0,n//30-1);relative=n-start*30
 raw=subprocess.check_output(['ffmpeg','-v','error','-nostdin','-threads','4','-ss',str(start),'-reinit_filter','0','-i',str(path),'-map','0:v:0','-an','-vf',f'select=eq(n\\,{relative})','-frames:v','1','-vsync','0','-pix_fmt','bgr24','-f','rawvideo','pipe:1'])
 assert len(raw)==3840*2160*3,'Exact frame extraction incomplete'
 return np.frombuffer(raw,np.uint8).reshape(2160,3840,3)
def main():
 s,o=probe(SRC),probe(VIDEO);m=json.load(open(W/'manifest.json'));v=next(x for x in o['streams']if x['codec_type']=='video');sa=[x for x in s['streams']if x['codec_type']=='audio'];oa=[x for x in o['streams']if x['codec_type']=='audio'];checks={'video_frames_63871':int(v['nb_frames'])==63871,'video_duration_preserved':abs(float(v['duration'])-63871/30)<.002,'video_3840x2160_30fps':(v['width'],v['height'],v['avg_frame_rate'])==(3840,2160,'30/1'),'audio_tracks_preserved':len(sa)==len(oa),'audio_codec_and_sample_rate_preserved':[(x['codec_name'],x['sample_rate'])for x in sa]==[(x['codec_name'],x['sample_rate'])for x in oa],'source_unchanged':SRC.stat().st_size==m['source_size']and SRC.stat().st_mtime_ns==m['source_mtime_ns']}
 first=json.load(open(W/'chunks/part-00/report.json'));parts={p['index']:json.load(open(W/'chunks'/p['name']/'report.json'))for p in m['parts'] if p['index']>0}
 checks['all_frame_reports_complete']=first['status']=='complete'and all(parts[p['index']]['status']=='complete'and len(parts[p['index']]['frames'])==p['frames']for p in m['parts'] if p['index']>0)
 checks['combined_frame_reports_63871']=len(first['frames'])+sum(len(r['frames'])for r in parts.values())==63871
 packets=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_packets','-show_entries','packet=pts_time','-of','json',str(VIDEO)]))['packets'];pts=sorted(float(p['pts_time'])for p in packets);checks['all_video_frame_pts_continuous']=len(pts)==63871 and all(abs(t-n/30)<.00001 for n,t in enumerate(pts))
 checks['full_container_duration_preserved']=abs(float(o['format']['duration'])-float(s['format']['duration']))<.002
 def frame(n):return first['frames'][n]if n<9000 else parts[(n-9000)//9000+1]['frames'][(n-9000)%9000]
 packet_source,packet_output=audio_packet_hashes(SRC),audio_packet_hashes(VIDEO);checks['original_audio_packet_payloads_identical']=packet_source==packet_output
 samples=[]
 for t in [2,66,296,301,600,899,1199,1201,1501,1801,2101,2126]:
  a,b=audio(SRC,t),audio(VIDEO,t);n=min(len(a),len(b));a,b=a[:n],b[:n];size=1<<(2*n-1).bit_length();cc=np.fft.irfft(np.fft.rfft(a,size)*np.conj(np.fft.rfft(b,size)),size);lags=np.arange(-3200,3201);lag=int(lags[np.argmax(cc[lags%size])]);x,y=(a[lag:],b[:n-lag])if lag>=0 else(a[:n+lag],b[-lag:]);cor=float(np.dot(x,y)/max(1e-12,np.linalg.norm(x)*np.linalg.norm(y)));samples.append({'seconds':t,'best_lag_ms':lag/16,'correlation':cor})
 checks['audio_alignment_sampled_within_5ms']=all(abs(x['best_lag_ms'])<=5 and x['correlation']>.95 for x in samples)
 pictures=[];front=[]
 points=[62,101,112,123,158,399,485,537,872,972,1181,1508,1538,1541,1637,1718,1929,1950,1973,65,142,299.966667,300,300.033333,390,600,600.033333,900,900.033333,1170,1200,1200.033333,1500,1500.033333,1800,1800.033333,2100,2100.033333,2129]
 point_frames={round(t*30)for t in points}
 baseline_counts=json.load(open(W/'baseline-repair-counts.json'))
 for part in m['parts']:
  current=first if part['index']==0 else parts[part['index']]
  for repair in current.get('review_repairs',[])[baseline_counts[part['name']]:]:
   windows=repair.get('global_render_windows',[repair['global_render_window']])
   for left,right in windows:
    point_frames.update(n for edge in [left,right]for n in [edge-1,edge,edge+1]if 0<=n<63871)
 for n in sorted(point_frames):
  t=n/30;im=frame_rgb(SRC,n);om=frame_rgb(VIDEO,n)
  mask=np.zeros(im.shape[:2],np.uint8)
  for x,y,w,h in frame(n)['boxes']:mask[y:y+h,x:x+w]=255
  mask=cv2.dilate(mask,np.ones((13,13),np.uint8));diff=np.abs(im.astype(np.int16)-om.astype(np.int16))[mask==0];pictures.append({'seconds':t,'frame':n,'outside_mean_rgb_error':float(diff.mean()),'outside_fraction_above_30':float(np.mean(diff.max(1)>30))})
  if n<9000:
   old=frame_rgb(W/'chunks/part-00/redacted.mp4',n);front.append({'frame':n,'pixel_equal_to_revised_first5':bool(np.array_equal(old,om))})
 checks['sampled_frame_identity_and_boundaries']=all(x['outside_mean_rgb_error']<7 and x['outside_fraction_above_30']<.002 for x in pictures);checks['revised_first5_matches_final_chunk_pixels']=all(x['pixel_equal_to_revised_first5']for x in front)
 result={'checks':checks,'passed':all(checks.values()),'video':{k:v[k]for k in ['width','height','duration','avg_frame_rate','nb_frames','codec_name','pix_fmt']},'audio_packet_count':packet_source[0],'audio_samples':samples,'image_and_splice_samples':pictures,'approved_front_samples':front,'limits':'Codec decoding is checked separately. Visual review is sampled; technical integrity cannot establish zero missed URLs.'};(OUT/'技术验证.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({'checks':checks,'passed':result['passed']},ensure_ascii=False,indent=2));assert result['passed']
if __name__=='__main__':main()
