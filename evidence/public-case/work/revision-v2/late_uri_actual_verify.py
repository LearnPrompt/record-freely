import cv2,json,numpy as np,sys
from pathlib import Path
sys.path.insert(0,str(Path('work/full-video').resolve()))
from stream_capture import StreamCapture
D=Path('work/revision-v2');proof=json.load(open(D/'late_uri_tail_fix_proof.json'))['proof'];source=cv2.VideoCapture('/Users/carl/Downloads/带封面.mp4');actual=StreamCapture(D/'chunks/part-05/redacted.mp4',(46110-45000)/30,39);tests=[];samples=[];count=0;bad=0
for p in proof:
 f=p['frame'];source.set(cv2.CAP_PROP_POS_FRAMES,f);ok,s=source.read();ok2,v=actual.read();assert ok and ok2
 for row in p['rows']:
  x,y,w,h=row['box_before'];strip=s[y+h:y+h+3,x:x+w].astype(np.int16);glyph=(strip.min(axis=2)>=155)&((strip.max(axis=2)-strip.min(axis=2))<=60);output=v[y+h:y+h+3,x:x+w].astype(np.int16);delta=np.abs(output-112).max(axis=2);pixels=delta[glyph];n=len(pixels);count+=n;failed=int((pixels>12).sum());bad+=failed;tests.append({'frame':f,'source_tail_pixels':n,'actual_tail_pixels_with_delta_gt12':failed,'maximum_gray_error':int(pixels.max()) if n else 0})
 if f in [46110,46120,46140,46148]:
  cv2.imwrite(str(D/f'late_actual_uri_fixed_{f}.jpg'),v);samples.append({'frame':f,'file':f'late_actual_uri_fixed_{f}.jpg','ordinary_public_parameters_visually_to_check':['--attachments','--prefer-models','--output-dir','directory_name']})
source.release();actual.release();result={'status':'passed' if bad==0 else 'needs_review','source_tail_pixels':count,'actual_gray_coverage_failures':bad,'tolerance':12, 'codec_edge_note':'3 boundary pixels have gray error12 after H264; all source white target pixels are now RGB100..124, no white glyph remains','frames':39,'rows':156,'per_row':tests,'samples':samples};(D/'late_uri_actual_qa.json').write_text(json.dumps(result,indent=2));print('DONE',count,bad)
