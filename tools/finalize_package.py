# -*- coding: utf-8 -*-
"""Freeze formal skill and independent-review files into the complete handoff."""
import argparse,hashlib,json,subprocess,zipfile
from pathlib import Path

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def clone(src,dst):
 if dst.exists():raise ValueError('Snapshot destination already exists')
 dst.parent.mkdir(parents=True,exist_ok=True);subprocess.run(['cp','-cRp',str(src),str(dst)],check=True)
def main():
 a=argparse.ArgumentParser();a.add_argument('--release-root',type=Path,required=True);r=a.parse_args().release_root.resolve();p=r/'record-freely';b=r/'full-review-bundle'
 review=json.loads((p/'evidence/independent-review.json').read_text())
 if review.get('status') not in ['passed','passed_with_limits','passed_after_fixes','passed_after_remediation_with_documented_limits']:raise ValueError('Independent review not passed')
 catalog=json.loads((b/'FILE_CATALOG.json').read_text());rows=catalog['files']
 inputs=[(p,'formal-skill/record-freely'),(r/'review-run','independent-review-run')]
 for src,rel in inputs:
  clone(src,b/rel)
  for q in sorted(src.rglob('*')):
   if not q.is_file():continue
   if q.is_symlink():raise ValueError('Symlink not permitted')
   child=Path(rel)/q.relative_to(src);out=b/child;h=sha(q)
   if q.stat().st_size!=out.stat().st_size or sha(out)!=h:raise ValueError('Final snapshot differs')
   rows.append({'path':str(child),'bytes':q.stat().st_size,'sha256':h,'origin':str(q),'matches_origin':True})
 # Bundle-level prose is a real file and belongs in its catalog too.
 readme=b/'README.md';rows.append({'path':'README.md','bytes':readme.stat().st_size,'sha256':sha(readme),'origin':'bundle-authored','matches_origin':True})
 catalog.update(formal_skill_snapshot_pending=False,file_count=len(rows));(b/'FILE_CATALOG.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2))
 v=json.loads((b/'BUNDLE_VALIDATION.json').read_text());v.update(status='passed',file_count=len(rows),total_logical_bytes=sum(z['bytes']for z in rows),formal_skill_snapshot_pending=False,independent_review_passed=True,independent_reproduction_included=True,catalog_exclusions=['FILE_CATALOG.json','BUNDLE_VALIDATION.json'],all_paths_relative_and_resolvable=True)
 for z in rows:
  q=b/z['path'];assert q.is_file() and not q.is_symlink() and q.stat().st_size==z['bytes']
 (b/'BUNDLE_VALIDATION.json').write_text(json.dumps(v,ensure_ascii=False,indent=2))
 archive=r/'record-freely-1.0.0.zip'
 if archive.exists():raise ValueError('Refusing existing archive')
 with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6)as z:
  for q in sorted(p.rglob('*')):
   if q.is_file():z.write(q,Path('record-freely')/q.relative_to(p))
 with zipfile.ZipFile(archive)as z:assert z.testzip() is None
 manifest={'status':'local_release_candidate_complete','version':'1.0.0','skill_name':'record-freely','display_name':'放心录 · Record Freely','published':False,'formal_skill_archive':{'name':archive.name,'bytes':archive.stat().st_size,'sha256':sha(archive)},'full_review_bundle':{'directory':'full-review-bundle','file_count':v['file_count'],'logical_bytes':v['total_logical_bytes'],'catalog_sha256':sha(b/'FILE_CATALOG.json'),'validation_sha256':sha(b/'BUNDLE_VALIDATION.json'),'source_and_all_work_outputs_included':True},'independent_review_status':review['status'],'large_files_uploaded':False,'pending':['Choose actual publication destination and upload complete media dataset; verify download links.','Codex project-specific allowance/savings remain unmeasured.','Historical 25:41 .html remains unlocated.']}
 (r/'DELIVERY.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));print(json.dumps(manifest,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
