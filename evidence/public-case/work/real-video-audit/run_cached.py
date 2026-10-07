from pathlib import Path
import importlib.util,json,os,sys
root=Path(__file__).resolve().parent
manifest=json.loads((root/'cache-manifest.json').read_text())
source=Path(manifest['source'])
assert source.stat().st_size==manifest['size'] and source.stat().st_mtime_ns==manifest['mtime_ns']
assert manifest['start']==0 and manifest['duration']==300
spec=importlib.util.spec_from_file_location('redactor','/Users/carl/.codex/skills/video-link-redactor/scripts/redact_video.py')
r=importlib.util.module_from_spec(spec);sys.modules[spec.name]=r;spec.loader.exec_module(r)
original_run=r.run
cache=root/'normalized-first300.mkv'
def cached_run(command):
 if command[0]=='ffmpeg' and command[-1].endswith('normalized.mkv') and 'ffv1' in command:
  assert command[command.index('-i')+1]==str(source)
  assert command[command.index('-ss')+1]=='0'
  assert command[command.index('-t')+1]=='300.0'
  os.link(cache,command[-1])
  return ''
 return original_run(command)
r.run=cached_run
sys.argv=['redact_video.py',str(source),'--duration','300','--ocr-workers','3','--output-dir',str(root.parent.parent/'outputs/带封面-前5分钟')]
r.main()
