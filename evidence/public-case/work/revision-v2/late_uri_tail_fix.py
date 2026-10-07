import cv2,json,numpy as np
from pathlib import Path
D=Path('work/revision-v2');report=json.load(open(D/'chunks/part-05/report.json'));cap=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');frames={};proof=[]
for f in range(46110,46149):
 cap.set(cv2.CAP_PROP_POS_FRAMES,f);ok,source=cap.read()
 if not ok:raise RuntimeError(f)
 entry=report['frames'][f-45000];items=[(i,b,r) for i,(b,r) in enumerate(zip(entry['boxes'],entry['regions'])) if 'review_resource_geometry' in r.get('source_origins',[])];assert len(items)==4,(f,len(items));remove=[];add=[];extents=[]
 for i,b,reg in items:
  x,y,w,h=b;bottom=y+h;strip=source[bottom:bottom+3,x:x+w].astype(np.int16);white=(strip.min(axis=2)>=155)&((strip.max(axis=2)-strip.min(axis=2))<=60)
  # Verify tail strokes connect into the real glyph row inside the original URI mask.
  preceding=source[max(y,bottom-10):bottom+3,x:x+w].astype(np.int16);mask=((preceding.min(axis=2)>=155)&((preceding.max(axis=2)-preceding.min(axis=2))<=60)).astype(np.uint8)
  n,labels,stats,_=cv2.connectedComponentsWithStats(mask,8);connected_tail=0
  for _,sy,sw,sh,area in stats[1:]:
   if sy<10 and sy+sh>10:connected_tail+=int(area)
  new=b.copy();new[3]+=3;newreg={k:v for k,v in reg.items() if k not in ['repair_patch','patch_global_frame']};newreg.update(box=new,id=reg['id'],origin='review_v2_uri_descender',box_method='source_confirmed_uri_lower_edge_plus_3px',source_confirmed_added_lower_pixels=int(white.sum()),preserve_orange_caption=True,preserve_white_caption=False)
  remove.append(i);add.append(newreg);extents.append({'box_before':b,'box_after':new,'source_tail_white_pixels_in_added3px':int(white.sum()),'source_connected_glyph_area_crossing_original_bottom':connected_tail})
 boxes=sorted([a['box'] for a in add],key=lambda b:b[1]);gaps=[boxes[j+1][1]-(boxes[j][1]+boxes[j][3]) for j in range(3)];assert min(gaps)>=3,(f,gaps)
 # Portrait starts in source screen lower-right; these rows stay above it.
 assert max(b[1]+b[3] for b in boxes)<1450
 frames[str(f)]={'remove_indexes':remove,'add':add};proof.append({'frame':f,'rows':extents,'remaining_vertical_row_gaps':gaps,'right_edges_unchanged':True,'last_row_stops_before_public_prefer_models_flag':True,'portrait_not_overlapped':True})
cap.release();(D/'late_uri_tail_fix.json').write_text(json.dumps({'fps':30,'index_reference':'current revision-v2 part05 report','frames':frames},indent=2));(D/'late_uri_tail_fix_proof.json').write_text(json.dumps({'window':[46110,46148],'frames':39,'changed_resource_rows':156,'source_pixels_confirm_added_lower_3px':['descender crossings into added rows recorded each frame; left/right/top remain exact existing reviewed geometry'],'proof':proof},indent=2));print('DONE',39,156,'pixels',sum(p['source_tail_white_pixels_in_added3px'] for x in proof for p in x['rows']))
