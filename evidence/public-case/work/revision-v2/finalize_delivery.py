from pathlib import Path
import hashlib,json,datetime
W=Path(__file__).resolve().parent;ROOT=W.parents[1];OUT=ROOT/'outputs/带封面-修正版v2'
tech=json.loads((OUT/'技术验证.json').read_text());assert tech['passed'] and all(tech['checks'].values())
combined=json.loads((OUT/'合并画面验证.json').read_text());assert combined['status']=='passed'
summary=json.loads((OUT/'事件摘要.json').read_text());assert summary['full_video_complete'] and summary['processed_frames']==63871
qas={p:json.loads((W/f'{p}_visual_qa.json').read_text())for p in ['front','middle','late']};assert all(q['status']=='passed'for q in qas.values())
m=json.loads((W/'manifest.json').read_text());source=Path(m['source']);old=ROOT/'outputs/带封面-完整版/redacted.mp4'
assert (source.stat().st_size,source.stat().st_mtime_ns)==(m['source_size'],m['source_mtime_ns'])
assert (old.stat().st_size,old.stat().st_mtime_ns)==(m['previous_output_size'],m['previous_output_mtime_ns'])
names=['redacted.mp4','修订说明.md','打码汇报.md','时间轴.csv','事件摘要.json','审阅.html','视觉检查.md','技术验证.json','合并画面验证.json','检查样张-路径与指定词.jpg']
files=[]
for name in names:
 p=OUT/name;assert p.is_file() and p.stat().st_size>0;h=hashlib.sha256()
 with p.open('rb')as f:
  for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
 files.append({'name':name,'bytes':p.stat().st_size,'sha256':h.hexdigest()})
d={'status':'complete_with_one_unlocated_feedback_item','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'video_frames':63871,'video_seconds':63871/30,'technical_checks_passed':True,'visual_review_groups_passed':list(qas),'final_chunk_pixel_identity_points':combined['actual_frame_points'],'source_and_previous_output_unchanged':True,'unresolved':[{'user_time':'25:41','request':'mask .html extension','finding':'Exact source frame shows feather/scales video; extension not found in reviewed surrounding interval. Requires correct time or identifying frame.'}],'visual_limit':'User points, boundaries and difficult scenes sampled; specified word window scanned. No claim of zero missed text across entire movie.','files':files}
(OUT/'交付验证.json').write_text(json.dumps(d,ensure_ascii=False,indent=2));print(json.dumps({'status':d['status'],'files':len(files),'video_bytes':files[0]['bytes']},ensure_ascii=False))
