import json,numpy as np
from pathlib import Path
W=Path('work/revision-v3');data=json.load(open(W/'front_candidates.json'));patch={};proof=[]
manual={2181:1150,2182:1159,2183:1178,2239:1187,2240:1184,2241:1182}
for f in data:
 n=f['frame'];rows=f['matches'];good=[r['candidate_boundary'] for r in rows if r['score']>=.65]
 if 1856<=n<=2167:boundary=1005;method='source_confirmed_static_penultimate_slash'
 elif n in manual:boundary=manual[n];method='source_reviewed_zoom_or_clipped_shared_column'
 elif 2211<=n<=2222:boundary=1189;method='source_confirmed_shared_font_column_during_orange_overlay'
 elif good:boundary=int(np.median(good));method='source_author_and_skill_long_template_shared_column'
 elif n==2238:boundary=1189;method='source_confirmed_top_clipped_shared_column'
 elif n==2242:boundary=1180;method='source_confirmed_top_clipped_shared_column'
 else:raise RuntimeError(('needs boundary',n,rows))
 remove=[];add=[]
 for r in rows:
  i,k,b=r['index'],r['role'],r['box'];x,y,w,h=b
  assert 0<x<boundary<x+w and 0<=y<2160
  remove.append(i);add.append({'box':[x,y,boundary-x,h],'id':f'front_two_path_components_{k}','origin':'review_v3','kind':'reviewed_url','box_method':method,'protected_suffix':True,'preserve_orange_caption':True})
 patch[str(n)]={'remove_indexes':remove,'add':add};proof.append({'frame':n,'boundary_x':boundary,'method':method,'source_matches':rows})
# Confirmed URI glyph fragments beneath the opaque chapter overlay; preserve the author-side fragments.
patch['2243']['add'].append({'box':[614,120,1182-614,16],'id':'front_two_path_components_0_sliver','origin':'review_v3','kind':'reviewed_url','box_method':'source_verified_uri_glyph_sliver_under_opaque_navigation','protected_suffix':True,'preserve_orange_caption':True})
patch['2264']={'remove_indexes':[],'add':[{'box':[510,120,1182-510,3],'id':'front_two_path_components_1_exit_sliver','origin':'review_v3','kind':'reviewed_url','box_method':'source_verified_uri_glyph_sliver_under_opaque_navigation','protected_suffix':True,'preserve_orange_caption':True}]}
q={'fps':30,'index_basis':'revision-v2-current','frames':patch};json.dump(q,open(W/'front_patch.json','w'),ensure_ascii=False,indent=2);json.dump({'status':'source_geometry_frozen_waiting_actual_video_qa','frame_range':[1856,2264],'source_decode':'independent FFmpeg -reinit_filter 0; source embedded gray blocks retained','frames':proof,'extra_sliver_frames':{'2243':'first URI visible descendant glyphs120–135','2264':'last URI visible glyph fringe120–121; summary begins132, mask stops123'},'source_only_evidence':'front_source_*.png and front_clipped_boundary_proof.jpg remain work-only'},open(W/'front_notes.json','w'),ensure_ascii=False,indent=2)
print('frozen',len(patch),'remove',sum(len(x['remove_indexes']) for x in patch.values()),'add',sum(len(x['add']) for x in patch.values()))
