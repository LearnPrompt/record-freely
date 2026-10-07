# -*- coding: utf-8 -*-
"""Materialize complete local video-review inputs, then verify all file bytes.

APFS clones share disk blocks but are independent regular files, not symlinks.
Existing destination is refused. Source working files are not modified.
"""
import argparse,hashlib,json,subprocess,time
from pathlib import Path

def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def clone(src,dst):
 dst.parent.mkdir(parents=True,exist_ok=True)
 subprocess.run(['cp','-cRp',str(src),str(dst)],check=True)
def main():
 p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--original-skill',type=Path,required=True);p.add_argument('--bundle',type=Path,required=True);a=p.parse_args()
 if a.bundle.exists():raise SystemExit('Refusing existing review bundle')
 a.bundle.mkdir(parents=True)
 items=[(a.source,'source/'+a.source.name),(a.workspace/'work','workspace/work'),(a.workspace/'outputs','workspace/outputs'),(a.original_skill,'original-skill/video-link-redactor')]
 rows=[];total=0;start=time.monotonic()
 for src,rel in items:
  print('SNAPSHOT',rel,flush=True);clone(src,a.bundle/rel)
  files=[src]if src.is_file() else sorted(q for q in src.rglob('*')if q.is_file())
  for i,q in enumerate(files):
   if q.is_symlink():raise ValueError('Unexpected symlink: '+str(q))
   child=Path(rel)if src.is_file()else Path(rel)/q.relative_to(src);out=a.bundle/child
   sig=(q.stat().st_size,q.stat().st_mtime_ns);h=digest(q)
   if (q.stat().st_size,q.stat().st_mtime_ns)!=sig:raise ValueError('Input changed during snapshot')
   if out.is_symlink()or out.stat().st_size!=sig[0]or digest(out)!=h:raise ValueError('Snapshot mismatch')
   rows.append({'path':str(child),'bytes':sig[0],'sha256':h,'origin':str(q),'matches_origin':True});total+=sig[0]
   if i%300==0:print('VERIFIED',len(rows),round(total/1e9,2),'GB',flush=True)
 (a.bundle/'FILE_CATALOG.json').write_text(json.dumps({'version':1,'files':rows,'formal_skill_snapshot_pending':True},ensure_ascii=False,indent=2))
 (a.bundle/'BUNDLE_VALIDATION.json').write_text(json.dumps({'status':'passed_for_source_workspace_original_skill','file_count':len(rows),'total_logical_bytes':total,'all_regular_files':True,'all_sha256_equal_to_origin':True,'source_video_included':True,'all_workspace_work_and_outputs_included':True,'formal_skill_snapshot_pending':True,'elapsed_seconds':round(time.monotonic()-start,2)},indent=2))
 print('FULL SOURCE SNAPSHOT PASSED',len(rows),total,flush=True)
if __name__=='__main__':main()
