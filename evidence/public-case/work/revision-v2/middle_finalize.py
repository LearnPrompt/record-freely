import json,cv2,hashlib
from pathlib import Path
W=Path('work/revision-v2');p=W/'middle_patch.json';d=json.loads(p.read_text());fs=d['frames'];notes=json.loads((W/'middle_notes.json').read_text());reports=[]
for f in list(fs):
 if any(a['id'].startswith('middle_wrong')for a in fs[f]['add']):
  fs[f]['add']=[a for a in fs[f]['add']if not a['id'].startswith('middle_wrong')]
  fs[f]['remove_indexes']=[]
  if not fs[f]['add']:del fs[f]
for n in range(1,8):
 r=json.load(open(f'work/full-video/chunks/part-{n:02d}/report.json'));reports.append(r)
def old(f):
 for r in reports:
  s=r['source_start_frame']
  if s<=f<s+len(r['frames']):return r['frames'][f-s]
 raise ValueError(f)
# Remove every original mask for the three confirmed skill URI identities,
# including frames where OCR/track had a gap. Fallback strips only the same
# source-confirmed terminal URI prefix in existing geometry.
fallback=[];ratios={'U005':31/37,'U006':27/44,'U007':26/38}
r=reports[0]
for rec in r['frames']:
 f=r['source_start_frame']+rec['frame']
 for i,reg in enumerate(rec['regions']):
  if reg['id'] not in ratios:continue
  ent=fs.setdefault(str(f),{'remove_indexes':[],'add':[]});ent['remove_indexes']=sorted(set(ent['remove_indexes']+[i]));b=rec['boxes'][i]
  if not any(a['id'].startswith('middle_skill')and abs((a['box'][1]+a['box'][3]/2)-(b[1]+b[3]/2))<35 for a in ent['add']):
   bb=[b[0],b[1],round((b[2]-8)*ratios[reg['id']]+8),b[3]]
   ent['add'].append({'box':bb,'id':'middle_skill_fallback_'+reg['id'],'origin':'review_v2','kind':'reviewed_url','box_method':'source_confirmed_same_skill_url_existing_geometry_prefix_fraction','preserve_orange_caption':True});fallback.append(f)
# Source confirms the erroneously covered region is a local skill directory,
# never a network link. Remove all three frames of that exact region.
r=reports[2]
for rec in r['frames']:
 for i,reg in enumerate(rec['regions']):
  if reg['id']=='U011':
   f=r['source_start_frame']+rec['frame'];ent=fs.setdefault(str(f),{'remove_indexes':[],'add':[]});ent['remove_indexes']=sorted(set(ent['remove_indexes']+[i]))
for k,rec in fs.items():
 for a in rec['add']:
  b=a['box']
  if a['kind']=='reviewed_url':a['protected_suffix']=True
  if a['kind']in ['reviewed_path','reviewed_url']:b[2]-=4
  elif a['kind']=='reviewed_extension':b[0]+=4;b[2]-=4
  assert b[0]>=0 and b[1]>=0 and b[2]>0 and b[3]>0 and b[0]+b[2]<=3840 and b[1]+b[3]<=2160
 assert all(0<=i<len(old(int(k))['boxes'])for i in rec['remove_indexes'])
notes['wrong_mask_evidence']='16:12 only removes the local directory false mask U011 on global frames 29159–29161; no additional identity masking is added in the 16-minute scene.'
notes['skill_fallback_frames']=fallback;notes['skill_fallback_count']=len(fallback);notes['validation']={'all_boxes_in_4k_bounds':True,'all_removal_indexes_in_original_report':True,'false_U011_removed_frames':[29159,29160,29161],'suffix_guard':'Prefix right edge reduced 4 full-resolution pixels; html left edge moved 4 full-resolution pixels to preserve adjacent filename glyph.'}
notes['target_final_ranges']={}
for kind in ['skill','pathA','pathB','html','wrong']:
 frames=sorted(int(k)for k,v in fs.items()if any(a['id'].startswith('middle_'+kind)for a in v['add']));runs=[]
 for f in frames:
  if not runs or f>runs[-1][1]+1:runs.append([f,f])
  else:runs[-1][1]=f
 notes['target_final_ranges'][kind]={'first':frames[0]if frames else None,'last':frames[-1]if frames else None,'frames':len(frames),'continuous_runs':runs}
p.write_text(json.dumps(d,ensure_ascii=False));(W/'middle_notes.json').write_text(json.dumps(notes,ensure_ascii=False,indent=2))
# Source-derived mask previews, never published outside work.
c=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4')
for f in [11970,12999,14550,16110,26160,29160]:
 c.set(cv2.CAP_PROP_POS_FRAMES,f);ok,im=c.read();assert ok
 rec=old(f);e=fs[str(f)]
 for i,b in enumerate(rec['boxes']):
  if i not in e['remove_indexes']:x,y,w,h=b;im[y:y+h,x:x+w]=112
 for a in e['add']:x,y,w,h=a['box'];im[y:y+h,x:x+w]=112
 cv2.imwrite(str(W/f'middle_final_preview_{f}.jpg'),cv2.resize(im,(1920,1080)))
c.release()
print(json.dumps({'status':'frozen','frames':len(fs),'fallback_count':len(fallback),'ranges':notes['target_final_ranges']},ensure_ascii=False))
