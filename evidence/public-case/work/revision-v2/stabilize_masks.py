"""Offline mask stabilization: static envelopes, bounded moving/scale runs.

Only observed frames are emitted. No hold across missing frames or scene cuts.
Reports contain anonymous geometry; source text is never read or persisted.
"""
from __future__ import annotations
import copy,json,math
from pathlib import Path
import numpy as np


def edges(b):
 x,y,w,h=b
 return np.array([x,y,x+w,y+h],dtype=float)


def union(boxes):
 a=np.array([edges(b) for b in boxes]);l,t=a[:,:2].min(0);r,z=a[:,2:].max(0)
 return [int(math.floor(l)),int(math.floor(t)),int(math.ceil(r)-math.floor(l)),int(math.ceil(z)-math.floor(t))]


def intersect(a,b):
 x,y,w,h=a;u,v,s,t=b
 return max(0,min(x+w,u+s)-max(x,u))*max(0,min(y+h,v+t)-max(y,v))


def same_row(a,b):
 x,y,w,h=a;u,v,s,t=b
 oy=max(0,min(y+h,v+t)-max(y,v));ox=max(0,min(x+w,u+s)-max(x,u))
 return oy>=.5*min(h,t) and ox>=.45*min(w,s) and union([a,b])[2]<=1.6*max(w,s)


def coalesce(record):
 items=[]
 for b,r in zip(record['boxes'],record['regions']):
  r=copy.deepcopy(r);r['source_ids']=r.get('source_ids',[r.get('id','')])
  if r.get('protected_suffix') or r.get('kind') in ('reviewed_path','reviewed_extension'):
   r['preserve_review_bounds']=True
  r['source_origins']=r.get('source_origins',[r.get('origin','')])
  items.append([list(b),r])
 # Reviewed full resource rows/color rows are narrower, source-confirmed masks.
 # They supersede overlapping OCR duplicates, not arbitrary prefix-only patches.
 trusted={'review_resource_geometry','review_color_line'}
 for i,(b,r) in enumerate(items):
  if r.get('origin') not in trusted:continue
  for j,(old,other) in enumerate(items):
   if i==j or other.get('_drop') or other.get('kind')=='reviewed_word':continue
   if other.get('origin') in ('ocr','tracked','backfill') and same_row(b,old) and b[2]>=.8*old[2]:
    r['source_ids']+=other['source_ids'];r['source_origins']+=other['source_origins'];other['_drop']=True
 items=[a for a in items if not a[1].pop('_drop',False)]
 changed=True
 while changed:
  changed=False
  for i in range(len(items)):
   if changed:break
   for j in range(i+1,len(items)):
    a,ar=items[i];b,br=items[j]
    if ar.get('preserve_review_bounds') or br.get('preserve_review_bounds'):continue
    # A strict censored word must never inherit a caption-restoration mask.
    if (ar.get('kind')=='reviewed_word') != (br.get('kind')=='reviewed_word'):continue
    if not same_row(a,b):continue
    nr=copy.deepcopy(ar);nr['source_ids']=sorted(set(ar['source_ids']+br['source_ids']))
    nr['source_origins']=sorted(set(ar['source_origins']+br['source_origins']))
    for flag in ['preserve_orange_caption','preserve_white_caption']:
     nr[flag]=bool(ar.get(flag) or br.get(flag))
    if nr.get('kind')=='reviewed_word':nr['preserve_orange_caption']=nr['preserve_white_caption']=False
    items[i]=[union([a,b]),nr];items.pop(j);changed=True;break
 return items


def track_items(rows):
 tracks=[];active=[]
 for n,items in enumerate(rows):
  active=[k for k in active if tracks[k][-1][0]==n-1]
  pairs=[]
  for i,(b,r) in enumerate(items):
   for k in active:
    _,old,reg=tracks[k][-1]
    if (r.get('kind')=='reviewed_word') != (reg.get('kind')=='reviewed_word'):continue
    if bool(r.get('preserve_white_caption'))!=bool(reg.get('preserve_white_caption')):continue
    if not(.4<=b[2]/old[2]<=2.5 and .45<=b[3]/old[3]<=2.2):continue
    overlap=intersect(b,old)/min(b[2]*b[3],old[2]*old[3])
    distance=math.hypot((b[0]+b[2]/2)-(old[0]+old[2]/2),(b[1]+b[3]/2)-(old[1]+old[3]/2))
    identity=bool(set(r['source_ids'])&set(reg['source_ids']))
    if overlap<.2 and not(identity and distance<max(100,old[3]*2)):continue
    pairs.append((overlap+.25*identity-distance/5000,i,k))
  assigned={};used=set()
  for score,i,k in sorted(pairs,reverse=True):
   if i not in assigned and k not in used:assigned[i]=k;used.add(k)
  next_active=[]
  for i,(b,r) in enumerate(items):
   k=assigned.get(i)
   if k is None:k=len(tracks);tracks.append([])
   tracks[k].append((n,b,r));next_active.append(k)
  active=next_active
 return tracks


def runs(track):
 """Separate substantial motion/scale from stationary OCR edge jitter."""
 result=[];start=0
 while start<len(track):
  anchor=track[start][1];end=start+1
  while end<len(track):
   b=track[end][1]
   # An entire static plateau gets one envelope, not changing block windows.
   if abs(b[0]-anchor[0])>10 or abs(b[1]-anchor[1])>8 or not(.80<=b[3]/anchor[3]<=1.25):break
   if not(.62<=b[2]/anchor[2]<=1.60):break
   end+=1
  if end-start>=6:
   result.append(('static',track[start:end]));start=end;continue
  # The moving run ends when six subsequent observations form a new plateau.
  end=start+1
  while end<len(track):
   b=track[end][1]
   if not(.88<=b[3]/anchor[3]<=1.12) or not(.65<=b[2]/anchor[2]<=1.55):break
   tail=track[end:end+6]
   if len(tail)==6 and max(v[1][0] for v in tail)-min(v[1][0] for v in tail)<=6 and max(v[1][1] for v in tail)-min(v[1][1] for v in tail)<=6:break
   end+=1
  result.append(('moving',track[start:max(end,start+1)]));start=max(end,start+1)
 return result


def stabilize_records(records,width,height):
 rows=[coalesce(f) for f in records];tracks=track_items(rows)
 output=[[] for _ in records];stats={'tracks':len(tracks),'static_runs':0,'moving_runs':0,'source_regions':sum(len(f['boxes'])for f in records),'coalesced_regions':sum(len(r)for r in rows)}
 for k,track in enumerate(tracks):
  for mode,run in runs(track):
   stats[mode+'_runs']+=1
   if mode=='static':stable=union([b for _,b,_ in run])
   else:
    target_w=max(b[2] for _,b,_ in run);target_h=max(b[3]for _,b,_ in run)
   for j,(n,b,r) in enumerate(run):
    if r.get('preserve_review_bounds'):box=list(b)
    elif mode=='static':box=list(stable)
    else:
     neighbors=run[max(0,j-2):j+3];centers=[(v[1][0]+v[1][2]/2,v[1][1]+v[1][3]/2)for v in neighbors]
     cx,cy=np.median(centers,axis=0)
     # Clamp the smooth position so every current reviewed rectangle is covered.
     left=min(b[0],max(b[0]+b[2]-target_w,int(round(cx-target_w/2))))
     top=min(b[1],max(b[1]+b[3]-target_h,int(round(cy-target_h/2))))
     box=[left,top,target_w,target_h]
    x,y,w,h=box;right=min(width,x+w);bottom=min(height,y+h);x=max(0,x);y=max(0,y);box=[x,y,right-x,bottom-y]
    region=copy.deepcopy(r);region.update(id=f'S{k:05}',origin='review_v2_stabilized',box_method=f'coverage_safe_{mode}',stability_mode=mode)
    output[n].append((box,region))
 result=copy.deepcopy(records)
 for n,items in enumerate(output):
  # Strict word masks are rendered last; URL caption preservation cannot undo them.
  items.sort(key=lambda a:a[1].get('kind')=='reviewed_word')
  result[n]['boxes']=[b for b,_ in items];result[n]['regions']=[r for _,r in items];result[n]['origins']=[r['origin']for _,r in items]
 stats['final_regions']=sum(len(f['boxes'])for f in result)
 return result,stats


def apply_review_ops(report,part,patches):
 result=copy.deepcopy(report)
 for patch in patches:
  for key,ops in patch['frames'].items():
   n=int(key)-part['start_frame']
   if not 0<=n<len(result['frames']):continue
   f=result['frames'][n];indices=set(ops.get('remove_indexes',[]))
   if any(not isinstance(i,int) or i<0 or i>=len(report['frames'][n]['boxes'])for i in indices):raise ValueError('Invalid original rectangle index')
   # Ownership is disjoint by global scene. Multiple overlapping review patches
   # are rejected instead of shifting another patch's baseline indexes.
   if f.get('_review_applied'):raise ValueError('Two review patches modify the same baseline frame')
   f['_review_applied']=True
   for field in ['boxes','regions','origins']:f[field]=[v for i,v in enumerate(f[field])if i not in indices]
   for row in ops.get('add',[]):
    r=copy.deepcopy(row);b=r.pop('box');assert len(b)==4 and b[2]>0 and b[3]>0
    f['boxes'].append(b);f['regions'].append(r);f['origins'].append(r.get('origin','review_v2'))
 for f in result['frames']:f.pop('_review_applied',None)
 return result


def make_final_patch(report,part,review_patches,stabilize_ranges=None):
 revised=apply_review_ops(report,part,review_patches)
 stable=copy.deepcopy(revised['frames']);stats={'ranges':[]}
 if stabilize_ranges is None:stabilize_ranges=[(part['start_frame'],part['start_frame']+part['frames'])]
 for left,right in stabilize_ranges:
  a=max(0,left-part['start_frame']);z=min(part['frames'],right-part['start_frame'])
  if a>=z:continue
  current,evidence=stabilize_records(revised['frames'][a:z],report['width'],report['height'])
  stable[a:z]=current;stats['ranges'].append({'global_frames':[part['start_frame']+a,part['start_frame']+z],**evidence})
 frames={}
 for n,(old,new)in enumerate(zip(report['frames'],stable)):
  flags=lambda f:[(bool(r.get('preserve_orange_caption')),bool(r.get('preserve_white_caption')))for r in f['regions']]
  if old['boxes']==new['boxes'] and flags(old)==flags(new):continue
  rows=[]
  for b,r in zip(new['boxes'],new['regions']):rows.append({'box':b,**r})
  frames[str(part['start_frame']+n)]={'replace':True,'add':rows}
 return {'fps':30,'frames':frames,'stability_statistics':stats},stats
