from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parents[2]
W=ROOT/'work/full-video'
OUT=ROOT/'outputs/带封面-完整版'
m=json.loads((W/'manifest.json').read_text())
tech=json.loads((OUT/'技术验证.json').read_text())
assert tech['passed'] and tech['checks']['full_video_and_audio_codec_decode']
assert not (W/'full-decode.log').read_text().strip()
src=Path(m['source'])
assert src.stat().st_size==m['source_size'] and src.stat().st_mtime_ns==m['source_mtime_ns']
qa=json.loads((W/'qa_final_review_manifest.json').read_text())
assert all(p['status']=='passed' for p in qa['parts'])
names=['redacted.mp4','打码汇报.md','时间轴.csv','事件摘要.json','审阅.html','视觉检查.md','技术验证.json','检查样张01-实际成片场景.jpg','检查样张02-局部折行与边缘.jpg']
files=[]
for name in names:
 p=OUT/name
 assert p.is_file() and p.stat().st_size>0,name
 h=hashlib.sha256()
 with p.open('rb') as f:
  while data:=f.read(8*1024*1024):h.update(data)
 files.append({'file':name,'bytes':p.stat().st_size,'sha256':h.hexdigest()})
result={'status':'complete','source_unchanged':True,'source_frames':63871,'video_seconds':63871/30,'approved_first_seconds_preserved':300,'processed_remainder_seconds':54871/30,'original_audio_copied':True,'technical_checks_passed':True,'actual_final_chunk_reviewed_unique_frames':qa['actual_final_chunk_reviewed_unique_frames'],'visual_limit':'人工视觉核验采用场景与已知缺陷抽样，不代表每一帧人工检查或零漏检。','files':files}
(OUT/'交付验证.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
(OUT/'progress.json').write_text(json.dumps({'stage':'complete','frames':63871,'video_seconds':63871/30,'original_audio_copied':True},ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='files'},ensure_ascii=False,indent=2))
