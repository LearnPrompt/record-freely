import json,collections
from pathlib import Path
D=Path('work/revision-v2');out={'fps':30,'frames':{}}
def iou(a,b):
 x,y,w,h=a;j,k,u,v=b;z=max(0,min(x+w,j+u)-max(x,j))*max(0,min(y+h,k+v)-max(y,k));return z/max(1,w*h+u*v-z)
for fn in ['late_asset_remove.json','late_path_refined.json','late_partial_prefix.json','late_word_refined.json']:
 p=json.load(open(D/fn))
 for f,change in p['frames'].items():
  d=out['frames'].setdefault(f,{'remove_indexes':[],'add':[]});d['remove_indexes']=sorted(set(d['remove_indexes']+change['remove_indexes']))
  for a in change['add']:
   if a['kind']=='reviewed_path' and any(b['kind']=='reviewed_path' and iou(a['box'],b['box'])>.65 for b in d['add']):continue
   d['add'].append(a)
for fs,d in out['frames'].items():
 assert 0<=int(fs)<63871
 assert len(set(d['remove_indexes']))==len(d['remove_indexes'])
 for a in d['add']:
  x,y,w,h=a['box'];assert 0<=x<3840 and 0<=y<2160 and w>0 and h>0 and x+w<=3840 and y+h<=2160,(fs,a)
(D/'late_patch.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
def ranges(nums):
 out=[]
 for f in sorted(nums):
  if out and f==out[-1][1]+1:out[-1][1]=f
  else:out.append([f,f])
 return out
summary={}
for kind in ['reviewed_path','reviewed_word']:
 nums=[int(f) for f,d in out['frames'].items() if any(a['kind']==kind for a in d['add'])];summary[kind]={'frames':len(nums),'count':sum(a['kind']==kind for d in out['frames'].values() for a in d['add']),'continuous_ranges_inclusive':ranges(nums)}
notes={'status':'frozen','fps':30,'source':'original video global frame','source_unchanged':True,'patch_frames':len(out['frames']),'summary':summary,'user_points':[
 {'point':'25:08 / 27:17 / 28:38','result':'mask identity prefix only; retain directory/file names','methods':['native OCR each source frame for candidate prefix','source-confirmed identity glyph highpass template follows current frame translation/zoom','27:17 clipped under navigation: match only actually visible lower glyphs; stop during horizontal pan when prefix leaves image'],'scanned_windows_frames':[[44895,46210],[48750,49576],[51180,52440]],'actual_point_frames':[45240,49110,51540],'evidence':['late_path_check_45240.jpg','late_prefix_matched_45240.jpg','late_partial_check_49110.jpg','late_prefix_matched_51540.jpg'],'native_geometry_fallback_frames':json.load(open(D/'late_path_refine_proof.json'))['native_fallback_frames']},
 {'point':'25:38','result':'remove overlapping OCR/tracked boxes; retain existing source-confirmed resource geometry','source_geometry_frames':416,'modified_frames':405,'removed_old_box_indexes_count':1361,'protect': 'all original resource geometry and final exit-tail frames46149..46151; no hold across gaps','evidence':['late_asset_46112.jpg','late_asset_46121.jpg','late_asset_remove_proof.json']},
 {'point':'25:41 .html','result':'not found at supplied timestamp; no speculative mask','verified': '25:34..25:55 source every second and 25:00..27:20 source every3seconds; 25:41 is scale/eyeglasses video, no filename','evidence':['late_html_contact.jpg','late_html_probe.json']},
 {'point':'32:09–32:53 B站 小红书 中国','result':'mask each visible instance in screen and subtitles only within requested time window','scanned_frame_window_inclusive':[57870,59190],'native_scanned_frames':1321,'frames_with_words':1277,'boxes_per_word':{'B站':1799,'小红书':1859,'中国':602},'current_frame_template_native_dropout_supplements':30,'caption_restoration_disabled':True,'evidence':['late_word_check_57870.jpg','late_word_check_58350.jpg','late_word_check_58530.jpg'],'boundaries_checked':[57869,57870,59190,59191]}
],'validation':{'all_boxes_in_source_bounds':True,'all_removal_indexes_use_original_chunk_report':True,'no_original_video_or_reports_modified':True,'requires_final_render_visual_qa':True}}
(D/'late_notes.json').write_text(json.dumps(notes,ensure_ascii=False,indent=2));print(json.dumps({'frames':len(out['frames']),'added':sum(len(d['add']) for d in out['frames'].values()),'removed':sum(len(d['remove_indexes']) for d in out['frames'].values()),'counts':summary},ensure_ascii=False))
