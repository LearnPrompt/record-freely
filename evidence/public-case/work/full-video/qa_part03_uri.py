#!/usr/bin/env python3
"""Review two confirmed Feishu URI shapes; recognized tokens stay transient."""
import argparse
import json
import math
import re
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
import qa_shell_continuation as native

HEADS = {
    'docx': re.compile(r'https?\s*[:：]\s*[/／]{2}\s*www\s*[.．]\s*feishu\s*[.．]\s*cn\s*[/／]\s*docx\s*[/／]', re.I),
    'task': re.compile(r'https?\s*[:：]\s*[/／]{2}\s*applink\s*[.．]\s*feishu\s*[.．]\s*cn\s*[/／]\s*client\s*[/／](?:\s*todo\s*[/／]\s*(?:detail|task_list)\s*[?？])?', re.I),
}
BODY_LENGTH = {'docx': 54, 'task': 86}
PREFIX_LENGTH = {'docx': 27, 'task': 25}
SOURCE = Path('/Users/carl/Downloads/带封面.mp4')
BASE = Path(__file__).resolve().parent
WINDOWS = {'part03': [(34200,34421,0,450), (35340,35521,900,2160), (35521,35732,0,750)],
           'part04': [(39390,39426,0,450)]}


def green_mask(image):
    pixels = image.astype(np.int16)
    b,g,r = cv2.split(pixels)
    # These reviewed terminal rows include green-highlighted and pale-white
    # glyphs. Requiring bright red/blue rejects the dark green background.
    return ((g >= 165) & (r >= 100) & (b >= 80) & (g >= r-25) & (g >= b-25)).astype(np.uint8)*255


def word_geometry(row, start, end, width, height, y0):
    boxes = []
    for begin,stop,observation in row['pieces']:
        a,b = max(0,start-begin), min(stop-begin,end-begin)
        if b <= a:
            continue
        # Vision often returns the same word rectangle for each URI character.
        # Do not treat these rectangles as independent glyph widths.
        chars = [c['box'] for c in observation.get('chars',[]) if c['start'] < b and c['end'] > a]
        if chars:
            boxes.extend(chars)
        else:
            boxes.append(observation['box'])
    if not boxes:
        return None
    x = min(b[0] for b in boxes)*width
    y = min(b[1] for b in boxes)*height+y0
    right = max(b[0]+b[2] for b in boxes)*width
    bottom = max(b[1]+b[3] for b in boxes)*height+y0
    return [x,y,right-x,bottom-y]


def native_anchors(observations, width, height, y0):
    anchors = []
    for row in native.group_rows(observations):
        for kind,pattern in HEADS.items():
            for match in pattern.finditer(row['text']):
                box = word_geometry(row,match.start(),match.end(),width,height,y0)
                if box is None or box[3] > 125 or box[3] < 6:
                    continue
                confidence = min(o.get('confidence',0) for _,_,o in row['pieces'])
                if confidence < .35:
                    continue
                tail = re.match(r'[A-Za-z0-9._~%+/?=&#: -]*',row['text'][match.end():]).group()
                complete_geometry=word_geometry(row,match.start(),match.end()+len(tail),width,height,y0)
                if complete_geometry is not None and 6<=complete_geometry[3]<=125:
                    box=complete_geometry
                recognized_chars = len(re.sub(r'\s+','',row['text'][match.start():match.end()]+tail).rstrip('.,:;'))
                anchors.append({'kind':kind,'box':box,'recognized_chars':recognized_chars,
                                'expected_chars':BODY_LENGTH[kind]+(3 if 'task_list' in match.group().lower() else 0),
                                'ocr_confidence':float(confidence)})
    return anchors


def glyph_extent(image, proposed, expected_width, cell_width, chromatic=False):
    """Stop at a real glyph/word gap; never retain a stale last-frame strip."""
    height,width = image.shape[:2]
    x,y,w,h = proposed
    left = max(0,math.floor(x)-5)
    top = max(0,math.floor(y)-4)
    right = min(width,math.ceil(max(x+w,x+expected_width*1.16+8)))
    bottom = min(height,math.ceil(y+h+5))
    if right <= left or bottom <= top:
        return None
    mask = green_mask(image[top:bottom,left:right])
    if chromatic:
        b,g,r=cv2.split(image[top:bottom,left:right].astype(np.int16))
        mask[((g-r)<10)|((g-b)<5)]=0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask,8)
    clean = np.zeros_like(mask)
    for label in range(1,count):
        sx,sy,sw,sh,area = stats[label]
        if area >= 3 and sw <= max(16,3.2*cell_width) and sh >= 2:
            clean[labels==label] = 255
    columns = np.count_nonzero(clean,axis=0)
    locations = np.flatnonzero(columns)
    if not len(locations):
        return None
    start_candidates = locations[locations <= max(24,cell_width*1.3)]
    if not len(start_candidates):
        return None
    start = int(start_candidates[0])
    maximum_gap = max(12,round(cell_width*1.5)+3)
    end = start
    for location in locations[locations>=start]:
        if location-end > maximum_gap:
            break
        end = int(location)
    seen_width = end-start+1
    required = min(expected_width*.76, max(0,width-x)*.76)
    if seen_width < max(230,required):
        return None
    vertical = np.count_nonzero(clean[:,start:end+1],axis=1)
    active = np.flatnonzero(vertical >= max(3,seen_width*.006))
    if not len(active):
        return None
    # Adjacent terminal rows never share a single tall rectangle.
    bands=[]
    for line in active:
        if bands and line-bands[-1][1] <= 3:
            bands[-1][1] = int(line)
        else:
            bands.append([int(line),int(line)])
    a,b = min(bands,key=lambda band:abs((band[0]+band[1])/2 - len(vertical)/2))
    if b-a < 4:
        return None
    padding=4
    bx=max(0,left+start-padding);by=max(0,top+a-padding)
    ex=min(width,left+end+1+padding);ey=min(height,top+b+1+padding)
    if ey-by > 125:
        return None
    return [int(bx),int(by),int(ex-bx),int(ey-by)]


def make_banks(capture, ocr):
    banks = {}
    for kind,number,y0,y1 in [('docx',34300,0,450),('task',35400,900,2160)]:
        capture.set(cv2.CAP_PROP_POS_FRAMES,number)
        ok,image=capture.read()
        if not ok:
            raise RuntimeError('Could not load URI reference frame')
        anchors=native_anchors(ocr.read(image[y0:y1],maximum_width=3840),image.shape[1],y1-y0,y0)
        candidates=[a for a in anchors if a['kind']==kind and a['recognized_chars']>=BODY_LENGTH[kind]-2]
        if not candidates:
            raise RuntimeError('Full confirmed reference URI could not be recognized')
        candidate=min(candidates,key=lambda a:abs(a['recognized_chars']-BODY_LENGTH[kind]))
        x,y,w,h=candidate['box']
        cell=w/BODY_LENGTH[kind]
        pw=round(cell*PREFIX_LENGTH[kind])
        patch=green_mask(image[max(0,round(y)):min(image.shape[0],round(y+h)),round(x):round(x)+pw])
        if patch.size==0 or patch.std()<5:
            raise RuntimeError('URI prefix reference lacks glyph evidence')
        banks[kind]={'template':patch,'body_width':w,'body_height':h,'cell':cell,
                     'reference_frame':number,'prefix_width':pw}
    return banks


def prefix_match(image, bank, state, y0,y1, number):
    if not state or number-state['frame'] > 12:
        return None
    height,width=image.shape[:2]
    template=bank['template']
    sx0,sy0=state['scale_x'],state['scale_y']
    left=max(0,round(state['x'])-500)
    right=min(width,round(state['x']+bank['prefix_width']*sx0)+500)
    top=max(y0,round(state['y'])-150)
    bottom=min(y1,round(state['y']+bank['body_height']*sy0)+150)
    if bottom-top<12 or right-left<50:
        return None
    search=green_mask(image[top:bottom,left:right])
    best=None
    crops=(0,.25,.45,.65,.78) if state['y']<y0+140 else (0,)
    for sx in (sx0*.96,sx0,sx0*1.04):
        for sy in (sy0*.96,sy0,sy0*1.04):
            tw=max(30,round(template.shape[1]*sx));th=max(12,round(template.shape[0]*sy))
            resized=cv2.resize(template,(tw,th),interpolation=cv2.INTER_NEAREST)
            for crop in crops:
                cut=round(th*crop);test=resized[cut:]
                if min(test.shape)<9 or test.shape[1]>search.shape[1] or test.shape[0]>search.shape[0] or test.std()<5:
                    continue
                response=cv2.matchTemplate(search,test,cv2.TM_CCOEFF_NORMED)
                _,score,_,location=cv2.minMaxLoc(response)
                if score>=.72 and (best is None or score>best['tracking_score']):
                    best={'x':left+location[0],'y':top+location[1]-cut,'scale_x':sx,'scale_y':sy,
                          'tracking_score':float(score),'top_crop_fraction':crop}
    return best


def build(mode='part03',output=None):
    output=Path(output or BASE/('qa_part03_uri.json' if mode=='part03' else 'qa_part04_feishu.json'))
    capture=cv2.VideoCapture(str(SOURCE))
    if not capture.isOpened():
        raise RuntimeError('Could not open the original video')
    records,observations_log,states={},[],{}
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='qa-feishu-uri-') as scratch:
        ocr=native.Vision(scratch)
        try:
            banks=make_banks(capture,ocr)
            for first,last,y0,y1 in WINDOWS[mode]:
                capture.set(cv2.CAP_PROP_POS_FRAMES,first)
                for number in range(first,last):
                    ok,image=capture.read()
                    if not ok:
                        raise RuntimeError('Source frame decode failed')
                    anchors=native_anchors(ocr.read(image[y0:y1],maximum_width=3840),image.shape[1],y1-y0,y0)
                    accepted=[]
                    previous_states={kind:list(values) for kind,values in states.items()}
                    current_states={kind:[] for kind in banks}
                    for anchor in anchors:
                        kind=anchor['kind'];bank=banks[kind]
                        x,y,w,h=anchor['box']
                        cell=w/max(PREFIX_LENGTH[kind],anchor['recognized_chars'])
                        expected=cell*anchor['expected_chars']
                        box=glyph_extent(image,[x,y,w,h],expected,cell)
                        if box is None:
                            continue
                        accepted.append({'box':box,'id':'CU03D' if kind=='docx' else 'CU03T',
                                         'kind':'http(s)','origin':'review_url_continuation',
                                         'box_method':'reviewed_uri_glyphs','ocr_confidence':anchor['ocr_confidence'],
                                         'reference_frame':bank['reference_frame'],
                                         'review_basis':'Confirmed Feishu URI in reviewed terminal window; native public-prefix anchor, current-frame bright terminal glyph extent to token end; word-level Vision geometry is not independent character geometry'})
                        current_states[kind].append({'x':x,'y':y,'scale_x':box[2]/bank['body_width'],
                                      'scale_y':h/bank['body_height'],'frame':number})
                    for kind,state in [(kind,s) for kind,values in previous_states.items() for s in values]:
                        bank=banks[kind]
                        # Keep simultaneous copies separate: a lower OCR row
                        # must not replace the top-clipped instance's evidence.
                        if any(abs(s['x']-state['x'])<180 and abs(s['y']-state['y'])<100
                               for s in current_states[kind]):
                            continue
                        match=prefix_match(image,bank,state,y0,y1,number)
                        if match is None:
                            continue
                        x,y=match['x'],match['y'];sx,sy=match['scale_x'],match['scale_y']
                        proposed=[x,y,bank['body_width']*sx,bank['body_height']*sy]
                        box=glyph_extent(image,proposed,proposed[2],bank['cell']*sx)
                        if box is None or any(abs(box[0]-a['box'][0])<30 and abs(box[1]-a['box'][1])<30 for a in accepted):
                            continue
                        accepted.append({'box':box,'id':'CU03D' if kind=='docx' else 'CU03T',
                                         'kind':'http(s)','origin':'review_url_continuation',
                                         'box_method':'reviewed_uri_prefix_template','tracking_score':match['tracking_score'],
                                         'relative_scale':round(sx,6),'relative_vertical_scale':round(sy,6),
                                         'reference_frame':bank['reference_frame'],
                                         'review_basis':'Same confirmed public-URI prefix matched in current frame, including top clipping; actual bright terminal glyph/token extent supplies the narrow cover; no blind position hold'})
                        current_states[kind].append({'x':x,'y':y,'scale_x':sx,'scale_y':sy,'frame':number})
                    states={kind:current_states[kind]+[s for s in previous_states.get(kind,[])
                            if number-s['frame']<=12 and not any(abs(n['x']-s['x'])<180 and abs(n['y']-s['y'])<100
                            for n in current_states[kind])] for kind in banks}
                    if accepted:
                        records[str(number)]=accepted
                    observations_log.append({'frame':number,'native_anchor_count':len(anchors),'accepted_region_count':len(accepted)})
                    if number%30==0:
                        print(json.dumps({'frame':number,'patched_frames':len(records),'boxes':len(accepted)}),flush=True)
        finally:
            ocr.close();capture.release()
    if mode=='part04':
        for regions in records.values():
            for region in regions:
                region['id']=region['id'].replace('CU03','CU04')
    result={'schema_version':1,'status':'frozen_for_visual_review','fps':30,
            'time_reference':'Original video global frames','checked_windows':WINDOWS[mode],
            'reference_frames':{'docx':34300,'task':35400},'frames':records,
            'frame_evidence':observations_log,'patch_count':sum(map(len,records.values())),
            'patched_frame_count':len(records),'elapsed_seconds':round(time.monotonic()-started,2),
            'notes':['Public Feishu document/task URI shapes only; private strings never logged or persisted.',
                     'Each accepted frame requires current-frame native prefix or matched prefix glyphs; actual visible bright terminal-word extent is used.',
                     'Rows lacking valid evidence are left unpatched for visual review; no full-window static banners.']}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'file':output.name,'patched_frames':len(records),'patches':result['patch_count'],
                      'elapsed_seconds':result['elapsed_seconds']}),flush=True)
    return result


def supplement_top_doc(output=None):
    """Reviewed clipped doc row, using a same-scene public-prefix fragment."""
    output=Path(output or BASE/'qa_part03_uri.json')
    result=json.loads(output.read_text())
    capture=cv2.VideoCapture(str(SOURCE))
    capture.set(cv2.CAP_PROP_POS_FRAMES,34328);ok,reference=capture.read()
    if not ok:raise RuntimeError('Reference decode failed')
    template=green_mask(reference[104:129,650:1270])
    added=0
    for number in range(34328,34421):
        capture.set(cv2.CAP_PROP_POS_FRAMES,number);ok,image=capture.read()
        if not ok:raise RuntimeError('Frame decode failed')
        search=green_mask(image[:180,400:1500]);best=None
        for scale in np.arange(.85,1.251,.025):
            resized=cv2.resize(template,(round(template.shape[1]*scale),round(template.shape[0]*scale)),interpolation=cv2.INTER_NEAREST)
            for crop in (0,.25,.45,.65):
                cut=round(resized.shape[0]*crop);test=resized[cut:]
                if test.shape[0]<8:continue
                _,score,_,point=cv2.minMaxLoc(cv2.matchTemplate(search,test,cv2.TM_CCOEFF_NORMED))
                if score>=.78 and (best is None or score>best[0]):best=(score,scale,cut,point)
        if best is None:continue
        score,scale,cut,point=best
        x=400+point[0];y=point[1]-cut-14*scale
        # The fixed black chapter panel actually occludes the right part when
        # the URI is clipped above it; no mask is needed for invisible text.
        visible=image[:,:1945] if y+43*scale<=105 else image
        box=glyph_extent(visible,[x,y,1600*scale,43*scale],1600*scale,1600*scale/54)
        if box is None:continue
        regions=result['frames'].setdefault(str(number),[])
        if any(abs(r['box'][0]-box[0])<40 and abs(r['box'][1]-box[1])<40 for r in regions):continue
        regions.append({'box':box,'id':'CU03D','kind':'http(s)','origin':'review_url_continuation',
                        'box_method':'reviewed_uri_source_prefix','tracking_score':float(score),
                        'relative_scale':round(float(scale),6),'reference_frame':34328,
                        'review_basis':'Human-confirmed same document URI; current frame matches a public-prefix-only lower-glyph template from the same scene; visible glyph extent stops at actual clipping/occlusion'})
        added+=1
    capture.release()
    result['patch_count']=sum(map(len,result['frames'].values()))
    result['patched_frame_count']=len(result['frames'])
    result['source_prefix_supplement_count']=added
    result['status']='frozen_for_visual_review'
    result['notes'].append('The clipped document row uses an explicitly reviewed same-scene public-prefix fragment; pixels hidden by the fixed chapter panel are excluded.')
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'supplemented_boxes':added,'patched_frames':result['patched_frame_count'],'patches':result['patch_count']}))
    return result


def supplement_partial_task(output=None):
    """Native public-host anchor survives OCR errors later in the same URI."""
    output=Path(output or BASE/'qa_part03_uri.json');result=json.loads(output.read_text())
    capture=cv2.VideoCapture(str(SOURCE));added=0
    with tempfile.TemporaryDirectory(prefix='qa-feishu-partial-') as scratch:
        ocr=native.Vision(scratch)
        try:
            for number in range(35340,35521):
                capture.set(cv2.CAP_PROP_POS_FRAMES,number);ok,image=capture.read()
                if not ok:raise RuntimeError('Frame decode failed')
                anchors=native_anchors(ocr.read(image[900:],maximum_width=3840),3840,1260,900)
                regions=result['frames'].setdefault(str(number),[])
                for a in anchors:
                    if a['kind']!='task':continue
                    x,y,w,h=a['box'];cell=w/max(25,a['recognized_chars'])
                    box=glyph_extent(image,a['box'],cell*a['expected_chars'],cell)
                    if box is None or any(abs(r['box'][0]-box[0])<40 and abs(r['box'][1]-box[1])<40 for r in regions):continue
                    regions.append({'box':box,'id':'CU03T','kind':'http(s)','origin':'review_url_continuation',
                                    'box_method':'reviewed_uri_glyphs','ocr_confidence':a['ocr_confidence'],
                                    'reference_frame':35400,'review_basis':'Human-confirmed task-list/detail URI window; current native public host/client prefix survives later OCR loss; actual terminal glyph extent covers the visible private tail'})
                    added+=1
        finally:ocr.close()
    # Remove chapter-white contamination from the green highlighted doc row.
    for number,regions in list(result['frames'].items()):
        if not 34200<=int(number)<34421:continue
        capture.set(cv2.CAP_PROP_POS_FRAMES,int(number));ok,image=capture.read()
        if not ok:raise RuntimeError('Frame decode failed')
        for region in regions:
            x,y,w,h=region['box'];visible=image[:,:1945] if y+h<=105 else image
            box=glyph_extent(visible,[x,y,w,h],w,w/54,chromatic=True)
            if box is not None:region['box']=box
    capture.release()
    result['frames']={n:rs for n,rs in result['frames'].items() if rs}
    result['patch_count']=sum(map(len,result['frames'].values()));result['patched_frame_count']=len(result['frames'])
    result['partial_host_supplement_count']=added
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'partial_host_added':added,'frames':result['patched_frame_count'],'patches':result['patch_count']}))
    return result


def build_reviewed_part04(output=None):
    """Only the reviewed task URI, through its actual source-frame exit."""
    output=Path(output or BASE/'qa_part04_feishu.json')
    capture=cv2.VideoCapture(str(SOURCE))
    def chromatic(image):
        b,g,r=cv2.split(image.astype(np.int16))
        return ((g>=130)&(r>=90)&(b>=70)&(g-r>=10)&(g-b>=5)).astype(np.uint8)*255
    capture.set(cv2.CAP_PROP_POS_FRAMES,39406);ok,reference=capture.read()
    if not ok:raise RuntimeError('Reference decode failed')
    template=chromatic(reference[85:98,1080:1280])
    records={};scores=[]
    for number in range(39406,39431):
        capture.set(cv2.CAP_PROP_POS_FRAMES,number);ok,image=capture.read()
        if not ok:raise RuntimeError('Frame decode failed')
        search=chromatic(image[30:140,600:1500]);best=None
        for scale in (.9,.95,1,1.05,1.1):
            test=cv2.resize(template,(round(200*scale),round(13*scale)),interpolation=cv2.INTER_NEAREST)
            _,score,_,point=cv2.minMaxLoc(cv2.matchTemplate(search,test,cv2.TM_CCOEFF_NORMED))
            if score>=.45 and (best is None or score>best[0]):best=(score,scale,point)
        if best is None:raise RuntimeError('Confirmed part04 URI prefix lacks current-frame evidence')
        score,scale,point=best;x=600+point[0]-10*scale
        # The chapter bar is a real occluder after x=2200. Measure the visible
        # pale-green URI band, rejecting the white chapter letters themselves.
        y=30+point[1]-31*scale
        left=max(0,math.floor(x));top=max(0,math.floor(y)-4);right=2200;bottom=min(105,math.ceil(y+44*scale)+4)
        mask=chromatic(image[top:bottom,left:right])
        rows=np.flatnonzero(np.count_nonzero(mask,axis=1)>=8)
        cols=np.flatnonzero(np.count_nonzero(mask,axis=0)>=2)
        if len(rows)<6 or len(cols)<150:raise RuntimeError('Confirmed URI row lacks visible glyph evidence')
        bx=max(0,left+int(cols.min())-4);by=max(0,top+int(rows.min())-4)
        ex=min(2200,left+int(cols.max())+5);ey=min(105,top+int(rows.max())+5)
        box=[bx,by,ex-bx,ey-by]
        records[str(number)]=[{'box':box,'id':'CU04T','kind':'http(s)','origin':'review_url_continuation',
                              'box_method':'reviewed_uri_source_prefix','tracking_score':float(score),
                              'relative_scale':scale,'reference_frame':39406,
                              'review_basis':'Human-confirmed same task URI through its actual exit at39431; current public-prefix-only pale-green lower-glyph match and visible row projection; private text/URI not stored; narrow strip overlaps chapter lettering'}]
        scores.append(float(score))
    # Immediately after the task URI exits, the already confirmed document
    # URI crosses the chapter bar for one frame. A narrow crop below the bar
    # recovers its complete native word geometry, without logging its token.
    capture.set(cv2.CAP_PROP_POS_FRAMES,39432);ok,image=capture.read()
    if not ok:raise RuntimeError('Reviewed document edge frame decode failed')
    with tempfile.TemporaryDirectory(prefix='qa-feishu04-docx-') as scratch:
        ocr=native.Vision(scratch)
        try:anchors=native_anchors(ocr.read(image[100:190],maximum_width=3840),3840,90,100)
        finally:ocr.close()
    candidates=[a for a in anchors if a['kind']=='docx' and a['recognized_chars']==54]
    if not candidates:raise RuntimeError('Reviewed one-frame document URI lacks native evidence')
    anchor=max(candidates,key=lambda a:a['ocr_confidence']);cell=anchor['box'][2]/54
    box=glyph_extent(image,anchor['box'],cell*54,cell)
    if box is None:raise RuntimeError('Reviewed document URI glyph extent missing')
    records['39432']=[{'box':box,'id':'CU04D','kind':'http(s)','origin':'review_url_continuation',
                      'box_method':'reviewed_uri_glyphs','ocr_confidence':anchor['ocr_confidence'],
                      'reference_frame':39432,'review_basis':'Human-confirmed same Feishu document URI crosses top chapter bar for one source frame; narrow native OCR below chapter text and current glyph extent; no private token stored'}]
    capture.release()
    result={'schema_version':1,'status':'frozen_for_visual_review','fps':30,'time_reference':'Original video global frames',
            'checked_windows':[[39390,39443,0,450]],'reviewed_patch_window':[39406,39431],
            'additional_document_patch_window':[39432,39433],
            'frames':records,'patched_frame_count':26,'patch_count':26,'reference_frames':{'task':39406,'docx':39432},
            'verification':{'all_25_confirmed_frames_have_current_prefix_evidence':True,'minimum_prefix_score':min(scores),
                            'last_visible_task_uri_source_frame':39430,'first_task_uri_absent_source_frame':39431,
                            'source_exit_neighbors_visually_checked':[39430,39431,39432,39433,39434,39435,39436,39437,39438,39439,39440,39441,39442]},
            'notes':['Source-specific repair of confirmed top task URI only; no static mask where the URI is absent.',
                     'Fixed black chapter panel hides the remainder; only visible URI row is covered. A narrow gray strip also covers overlapping chapter lettering for0.833seconds.',
                     'Old OCR candidate ending at39422 was not treated as actual URI disappearance; same task URI remains visible through39430, then scrolls out at39431.',
                     'A separate known document URI flashes across the top bar at39432 only;39431 has an existing complete lower document mask,39433 no longer shows the document URI.',
                     'No white-caption restoration is used because it could restore the pale-green URI.']}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'file':output.name,'frames':26,'patches':26,'minimum_prefix_score':min(scores)}))
    return result


def build_gap_addendum(output=None):
    """Only six confirmed residual instances and their short continuities."""
    output=Path(output or BASE/'qa_part03_uri_addendum.json')
    existing=json.loads((BASE/'chunks/part-03/report.json').read_text())['frames']
    capture=cv2.VideoCapture(str(SOURCE));records={};evidence=[]
    def chromatic(image):
        b,g,r=cv2.split(image.astype(np.int16))
        return ((g>=145)&(r>=85)&(b>=65)&(g-r>=8)&(g-b>=4)).astype(np.uint8)*255
    def chapter_edge(image):
        fraction=(image[:105].max(axis=2)<10).mean(axis=0)
        columns=np.flatnonzero((np.arange(image.shape[1])>1700)&(fraction>.55))
        return int(columns[0]) if len(columns) else image.shape[1]
    def add(number,image,box,identity,method,meta,preserve=False):
        x,y,w,h=box
        if min(w,h)<=0 or h>125:return
        cover=np.zeros((h,w),np.uint8)
        previous=existing[number-27000]['boxes']+[r['box'] for r in records.get(str(number),[])]
        for px,py,pw,ph in previous:
            a,b=max(x,px),min(x+w,px+pw);c,d=max(y,py),min(y+h,py+ph)
            if a<b and c<d:cover[c-y:d-y,a-x:b-x]=1
        glyph=green_mask(image[y:y+h,x:x+w])>0
        missing=np.count_nonzero(glyph & (cover==0))
        if missing<3:return
        region={'box':box,'id':identity,'kind':'http(s)','origin':'review_url_continuation',
                'box_method':method,'review_basis':'Six visually confirmed same-URI gaps and neighboring continuous frames; current native/public-prefix evidence plus actual visible glyph band; no URI/token text stored',**meta}
        if preserve:region['preserve_orange_caption']=True
        records.setdefault(str(number),[]).append(region)
        evidence.append({'frame':number,'id':identity,'uncovered_bright_glyph_pixels_before_patch':int(missing)})
    # Public-prefix fragments only. Orange caption splits a real URI into
    # visible pieces, so the reviewed complete word span is kept between them.
    specs=[
      (34222,(985,860,1213,43),(985,860,300,43),(34218,34223),(700,0,1600,1100),.75,'CAG1',True),
      (34223,(985,990,1213,43),(985,990,230,43),(34223,34267),(700,650,1600,1300),.70,'CAG2',True),
      (34262,(950,82,1230,48),(1110,85,220,40),(34261,34267),(600,0,1600,210),.55,'CAG3',False),
      (34329,(633,44,1800,75),(990,50,220,45),(34329,34336),(400,0,1600,170),.70,'CAG4',False),
      (35713,(216,111,2414,52),(216,111,400,52),(35709,35716),(150,0,1100,200),.43,'CAT1',False)]
    for ref_number,body,prefix,window,search_box,threshold,identity,preserve in specs:
        capture.set(cv2.CAP_PROP_POS_FRAMES,ref_number);ok,reference=capture.read()
        if not ok:raise RuntimeError('Gap reference decode failed')
        px,py,pw,ph=prefix;template=chromatic(reference[py:py+ph,px:px+pw])
        for number in range(*window):
            capture.set(cv2.CAP_PROP_POS_FRAMES,number);ok,image=capture.read()
            if not ok:raise RuntimeError('Gap source decode failed')
            left,top,right,bottom=search_box;search=chromatic(image[top:bottom,left:right]);best=None
            for scale in (.95,1,1.05,1.1):
                resized=cv2.resize(template,(round(pw*scale),round(ph*scale)),interpolation=cv2.INTER_NEAREST)
                for a,b in ((0,1),(0,.7),(.3,1),(.5,1)):
                    cut=round(len(resized)*a);test=resized[cut:round(len(resized)*b)]
                    if test.shape[0]<8 or test.std()<5:continue
                    _,score,_,point=cv2.minMaxLoc(cv2.matchTemplate(search,test,cv2.TM_CCOEFF_NORMED))
                    if score>=threshold and (best is None or score>best[0]):best=(score,scale,cut,point)
            if best is None:continue
            score,scale,cut,point=best
            x=left+point[0]-(px-body[0])*scale;y=top+point[1]-cut-(py-body[1])*scale
            h=body[3]*scale;w=body[2]*scale
            bx=max(0,math.floor(x)-4);by=max(0,math.floor(y)-4)
            ex=min(3840,math.ceil(x+w)+4);ey=min(2160,math.ceil(y+h)+4)
            if y+h<=118:ex=min(ex,chapter_edge(image))
            mask=chromatic(image[by:ey,bx:ex]);rows=np.flatnonzero(np.count_nonzero(mask,axis=1)>=6)
            if len(rows)<6:continue
            y0=max(0,by+int(rows.min())-4);y1=min(2160,by+int(rows.max())+5)
            add(number,image,[bx,y0,ex-bx,y1-y0],identity,'reviewed_uri_source_prefix',
                {'tracking_score':float(score),'relative_scale':scale,'reference_frame':ref_number},preserve)
    # Native full-frame reading captures the additional same task instance
    # outside the earlier top-only ROI, and ordinary copies of these URIs.
    windows=[(34218,34229),(34256,34269),(34324,34337),(35525,35541),(35706,35719)]
    with tempfile.TemporaryDirectory(prefix='qa-feishu-gap-native-') as scratch:
        ocr=native.Vision(scratch)
        try:
            for first,last in windows:
                capture.set(cv2.CAP_PROP_POS_FRAMES,first)
                for number in range(first,last):
                    ok,image=capture.read()
                    if not ok:raise RuntimeError('Gap native decode failed')
                    anchors=native_anchors(ocr.read(image,maximum_width=3840),3840,2160,0)
                    for anchor in anchors:
                        x,y,w,h=anchor['box'];cell=w/max(25,anchor['recognized_chars'])
                        box=glyph_extent(image,anchor['box'],cell*anchor['expected_chars'],cell)
                        if box is None:continue
                        add(number,image,box,'CAN_D' if anchor['kind']=='docx' else 'CAN_T',
                            'reviewed_uri_glyphs',{'ocr_confidence':anchor['ocr_confidence'],'reference_frame':number})
        finally:ocr.close()
    capture.release()
    result={'schema_version':1,'status':'frozen_for_visual_review','fps':30,'time_reference':'Original video global frames',
            'frames':records,'patched_frame_count':len(records),'patch_count':sum(map(len,records.values())),
            'checked_native_windows':windows,'public_prefix_windows':[s[3] for s in specs],
            'reviewed_gap_frames':[34222,34223,34262,34330,35531,35712],'glyph_coverage_evidence':evidence,
            'notes':['Only residual instances in the previously confirmed Feishu URI scene; existing actual masks are checked before adding boxes.',
                     'Public prefix templates use source-confirmed fragments and current-frame scores; actual glyph bands supply height, fixed black navigation occlusion supplies visible right boundary.',
                     'For the confirmed green URI behind orange caption only, existing orange-caption preservation is enabled; no white-caption restoration.']}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'file':output.name,'frames':len(records),'patches':result['patch_count'],
                      'key_counts':{n:len(records.get(str(n),[])) for n in result['reviewed_gap_frames']}}))
    return result


def build_final_continuity(output=None):
    """Continuous public-head cover for the last two confirmed instances."""
    output=Path(output or BASE/'qa_part03_continuity_final.json')
    report=json.loads((BASE/'chunks/part-03/report.json').read_text())['frames']
    capture=cv2.VideoCapture(str(SOURCE));records={};checked=[]
    http=re.compile(r'https?\s*[:：]\s*[/／]{2}',re.I)
    def add(number,box,identity,basis):
        x,y,w,h=box
        x=max(0,math.floor(x));y=max(0,math.floor(y));w=min(3840-x,math.ceil(w));h=min(2160-y,math.ceil(h))
        if w<=0 or not 0<h<=125:return
        cover=np.zeros((h,w),np.uint8)
        for px,py,pw,ph in report[number-27000]['boxes']+[r['box'] for r in records.get(str(number),[])]:
            a,b=max(x,px),min(x+w,px+pw);c,d=max(y,py),min(y+h,py+ph)
            if a<b and c<d:cover[c-y:d-y,a-x:b-x]=1
        if np.count_nonzero(cover)>=.995*w*h:return
        records.setdefault(str(number),[]).append({'box':[x,y,w,h],'id':identity,'kind':'http(s)',
            'origin':'review_url_continuation','box_method':'reviewed_public_prefix_ocr',
            'reference_frame':number,'review_basis':basis})
    with tempfile.TemporaryDirectory(prefix='qa-feishu-continuity-') as scratch:
        ocr=native.Vision(scratch)
        try:
            capture.set(cv2.CAP_PROP_POS_FRAMES,35531)
            for number in range(35531,35732):
                ok,image=capture.read()
                if not ok:raise RuntimeError('Task continuity frame decode failed')
                anchors=native_anchors(ocr.read(image[:1300,100:1600],maximum_width=3840),1500,1300,0)
                count=0
                for anchor in anchors:
                    if anchor['kind']!='task':continue
                    x,y,w,h=anchor['box'];x+=100
                    add(number,[x-8,y-8,w+16,h+16],'CTF_TASK',
                        'Previously confirmed task URI instances; local current-frame native public host/client prefix geometry, conservatively padded, joins the existing body/token mask; continuous scan until the source instance exits')
                    count+=1
                checked.append({'frame':number,'task_public_prefix_count':count})
            # The clarify paragraph's same document URI is occluded by the
            # portrait. Only its visible head and right-side remnant are masked.
            capture.set(cv2.CAP_PROP_POS_FRAMES,34324)
            for number in range(34324,34421):
                ok,image=capture.read()
                if not ok:raise RuntimeError('Document continuity frame decode failed')
                roi=image[:650,1800:2980]
                observations=ocr.read(cv2.resize(roi,None,fx=2,fy=2),maximum_width=3840)
                heads=[]
                for row in native.group_rows(observations):
                    match=http.search(row['text'])
                    if not match:continue
                    geometry=word_geometry(row,match.start(),len(row['text']),1180,650,0)
                    if geometry is None:continue
                    x,y,w,h=geometry;x+=1800
                    if y<140 or h>105:continue
                    if x<2100:
                        # Native character boxes are unavailable when the
                        # cropped public text has no dot: use the reviewed
                        # terminal's equal-cell row to locate the URI start.
                        whole=word_geometry(row,0,len(row['text']),1180,650,0)
                        x=1800+whole[0]+whole[2]*match.start()/max(1,len(row['text']))
                    if x<2100:continue
                    box=glyph_extent(image[:,:2980],[x,y,2980-x,h],2980-x,max(20,h*.55))
                    if box is None:
                        # The head may become very short against the portrait;
                        # a source-confirmed word box still covers that public
                        # fragment with a small safety margin.
                        box=[x-10,y-6,2980-x+10,h+12]
                    else:
                        box=[box[0]-8,box[1]-4,min(2980,box[0]+box[2]+8)-(box[0]-8),box[3]+8]
                    box=[box[0]-32,box[1],box[2]+32,box[3]]
                    add(number,box,'CTF_DOC_HEAD',
                        'Same human-confirmed Feishu document URI inside the clarify paragraph; native cropped HTTP head at the portrait edge, current visible glyph band, only the public-head fragment is covered')
                    # This same long token is partly visible to the portrait's
                    # right. It stays aligned with the current URI glyph row.
                    add(number,[3744,box[1],96,box[3]],'CTF_DOC_TAIL',
                        'Same confirmed inline document URI; tiny visible continuation to the right of the portrait, aligned with the current HTTP head; portrait pixels are excluded')
                    heads.append([round(x),round(y)])
                checked.append({'frame':number,'inline_document_head_positions':heads})
        finally:ocr.close()
    capture.release()
    result={'schema_version':1,'status':'frozen_for_visual_review','fps':30,'time_reference':'Original video global frames',
        'frames':records,'patched_frame_count':len(records),'patch_count':sum(map(len,records.values())),
        'checked_windows':[[35531,35732,100,0,1600,1300],[34324,34421,1800,0,2980,650]],
        'frame_evidence':checked,'notes':['Only the last two confirmed residual URI instances; native OCR is localized, not a repeat of full-window OCR.',
            'Existing actual region coverage is checked; public-prefix masks conservatively join existing complete token/body masks.',
            'Inline paragraph URI is split into visible strips on either side of the portrait; no blanket paragraph or portrait mask.']}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'file':output.name,'frames':len(records),'patches':result['patch_count'],
        'critical_regions':{n:[r['box'] for r in records.get(str(n),[])] for n in ['34326','34329','35533']}}))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=WINDOWS,default='part03')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--supplement-top-doc',action='store_true')
    parser.add_argument('--supplement-partial-task',action='store_true')
    parser.add_argument('--gap-addendum',action='store_true')
    parser.add_argument('--final-continuity',action='store_true')
    args=parser.parse_args()
    if args.final_continuity:build_final_continuity(args.output)
    elif args.gap_addendum:build_gap_addendum(args.output)
    elif args.supplement_top_doc:supplement_top_doc(args.output)
    elif args.supplement_partial_task:supplement_partial_task(args.output)
    elif args.mode=='part04':build_reviewed_part04(args.output)
    else:
        build(args.mode,args.output)
        supplement_top_doc(args.output)
        supplement_partial_task(args.output)


if __name__=='__main__':
    main()
