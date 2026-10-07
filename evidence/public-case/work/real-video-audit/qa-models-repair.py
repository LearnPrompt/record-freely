#!/usr/bin/env python3
"""Reviewed public domain ROI repair. Never prints or persists other OCR text."""
import sys, json, re, tempfile, cv2, math, importlib.util
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PIL import ImageFont
FONT=ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf",100)
def units(ch):
    return 100.0 if ord(ch)>0x2fff else max(.01,FONT.getlength(ch))
def fractional_box(box,text,outer_a,outer_z,a,z):
    # In reviewed white-document words, adjacent Chinese glyphs occasionally
    # become Latin OCR hallucinations. A suffix fused to the reviewed domain
    # is Chinese prose here, so allocate native full-width glyph space.
    url_group=any(c in '/:' for c in text[outer_a:outer_z])
    weights=[(100.0 if c.isalpha() and (i>=z or (i<a and not url_group)) else units(c)) for i,c in enumerate(text) if outer_a<=i<outer_z]
    total=sum(weights)
    before=sum(weights[:a-outer_a])
    span=sum(weights[a-outer_a:z-outer_a])
    x,y,w,h=box
    return [x+w*before/total,y,w*span/total,h]
ROOT=Path('/Users/carl/Documents/Codex/2026-10-06/1-openai-gpt-6-1-ultra')
SRC=Path('/Users/carl/Downloads/带封面.mp4')
SCRIPT=Path('/Users/carl/.codex/skills/video-link-redactor/scripts/redact_video.py')
spec=importlib.util.spec_from_file_location('qa_models_redactor',SCRIPT); mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
MATCH=re.compile(r'models\s*[.．]\s*dev',re.I)
WINDOWS=[(2985,3160),(4020,4875)]
KEYS=[3060,4260,4410,4560]

def detect(ocr,im,extra=False):
    # Exclude permanent navigation and retain all text underneath. Resize only
    # for OCR, map exact character subranges back into original 4K coordinates.
    if extra:
        ox,oy,cw,ch=extra if isinstance(extra,tuple) else (500,1000,3340,1160)
        crop=im[oy:oy+ch,ox:ox+cw];small=crop
    else:
        crop=im[130:2160,:];small=cv2.resize(crop,(1920,1015));cw,ch,ox,oy=3840,2030,0,130
    obs=ocr.read(small)
    boxes=[]
    for ob in obs:
        for match in MATCH.finditer(ob['text']):
            a,z=match.span();cs=[c for c in ob.get('chars',[]) if c['start']<z and c['end']>a and any(not ob['text'][i].isspace() for i in range(max(a,c['start']),min(z,c['end'])))]
            complete=all(any(c['start']<=i<c['end'] for c in cs) for i in range(a,z) if not ob['text'][i].isspace())
            parts=[];method='reviewed_characters'
            for c in cs:
                b=c['box'];same=[d for d in ob.get('chars',[]) if all(abs(v-u)<1e-6 for v,u in zip(b,d['box']))]
                ga=min(d['start']for d in same);gz=max(d['end']for d in same)
                ma=max(ga,a);mz=min(gz,z)
                if ga<a or gz>z:
                    # Vision sometimes assigns every character the entire word
                    # rectangle. Clip that reviewed word by native glyph widths,
                    # keeping the adjacent Chinese text outside the mask.
                    parts.append(fractional_box(b,ob['text'],ga,gz,ma,mz));method='reviewed_word'
                else:parts.append(b)
            if parts and complete and all(b[2]>0 and b[3]>0 for b in parts):
                x,y,w,h=mod.union(parts)
            else:
                x,y,w,h=fractional_box(ob['box'],ob['text'],0,len(ob['text']),a,z);method='reviewed_word'
            box=mod.clamp([x*cw+ox-4,y*ch+oy-4,w*cw+8,h*ch+8],3840,2160)
            if not any(mod.overlap(box,d['box'])>.8 for d in boxes):
                boxes.append({'box':box,'id':'M001','kind':'domain','box_method':method,'origin':'review_roi_ocr','ocr_confidence':float(ob.get('confidence',0)),'review_basis':'visually confirmed public domain; no confidence filtering'})
    return boxes

def main():
    output=ROOT/'work/real-video-audit/qa-models-boxes.json'
    frames={};seeds={}
    with tempfile.TemporaryDirectory(prefix='qa-models-') as td:
        p=Path(td);d0=p/'w0';d1=p/'w1';d0.mkdir();d1.mkdir();ocr0=mod.VisionOCR(d0);ocr1=mod.VisionOCR(d1)
        cap=cv2.VideoCapture(str(SRC))
        try:
            for n in KEYS:
                cap.set(cv2.CAP_PROP_POS_FRAMES,n);ok,im=cap.read();assert ok
                seeds[n]=detect(ocr0,im);print(json.dumps({'key_frame':n,'boxes':[b['box']for b in seeds[n]]}),flush=True)
            if any(not seeds[n] for n in KEYS):raise RuntimeError('Reviewed key frame had no target recognition')
            with ThreadPoolExecutor(max_workers=2) as pool:
                for start,end in WINDOWS:
                    cap.set(cv2.CAP_PROP_POS_FRAMES,start);queue=[]
                    for n in range(start,end):
                        ok,im=cap.read();assert ok
                        worker=[ocr0,ocr1][(n-start)%2]
                        queue.append((n,pool.submit(detect,worker,im)))
                        if len(queue)>=2:
                            k,f=queue.pop(0);b=f.result()
                            if b:frames[str(k)]=b
                        if (n-start)%120==119: print(f'checked frame {n}',flush=True)
                    for k,f in queue:
                        b=f.result()
                        if b:frames[str(k)]=b
        finally:
            cap.release();ocr0.close();ocr1.close()
    result={'frames':frames,'checked_windows':[{'start_frame':a,'end_frame_exclusive':b,'start_seconds':a/30,'end_seconds':b/30}for a,b in WINDOWS],'notes':['Local Vision ROI OCR on source 3840x2160. Exact reviewed public-domain matching; no generic URL detection.','Navigation excluded. Four-pixel padding. OCR text is not persisted.','No confidence filter on this visually confirmed domain.','No temporal interpolation added; this file records direct target detections.'],'key_frames':{str(n):frames.get(str(n),[])for n in KEYS},'processed_frames':sum(b-a for a,b in WINDOWS)}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2));print('saved',str(output),'frames_with_boxes',len(frames),flush=True)
def lower_only():
    output=ROOT/'work/real-video-audit/qa-models-boxes.json'
    result=json.loads(output.read_text());frames=result['frames'];cap=cv2.VideoCapture(str(SRC))
    with tempfile.TemporaryDirectory(prefix='qa-models-lower-') as td:
        ocr=mod.VisionOCR(Path(td))
        try:
            cap.set(cv2.CAP_PROP_POS_FRAMES,4500)
            for n in range(4500,4640):
                ok,im=cap.read();assert ok
                added=[]
                for y in (1000,1280,1560,1840):
                    added.extend(detect(ocr,im,extra=(1000,y,2400,min(360,2160-y))))
                existing=frames.setdefault(str(n),[])
                for b in added:
                    if not any(mod.overlap(b['box'],old['box'])>.6 for old in existing):existing.append(b)
                if not existing:frames.pop(str(n),None)
            result['notes'].append('Native-resolution lower-document ROI additionally checked on frames 4500-4639 for the domain inside the workflow sentence.')
            result['key_frames']={str(n):frames.get(str(n),[]) for n in KEYS}
            output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
            print(json.dumps({'final_key_frames':{str(n):[b['box']for b in frames.get(str(n),[])]for n in KEYS}},ensure_ascii=False),flush=True)
        finally:ocr.close();cap.release()


def tighten_native_words():
    """Review-confirmed regular-font glyph template limits adjacent Chinese."""
    import numpy as np
    output=ROOT/'work/real-video-audit/qa-models-boxes.json';r=json.loads(output.read_text());cap=cv2.VideoCapture(str(SRC))
    cap.set(cv2.CAP_PROP_POS_FRAMES,4560);ok,seed=cap.read();assert ok
    # Human-checked complete Models.dev glyphs, excluding neighboring 把/接.
    template=cv2.cvtColor(seed[1486:1562,1624:1952],cv2.COLOR_BGR2GRAY)
    count=0;cap.set(cv2.CAP_PROP_POS_FRAMES,4500)
    for n in range(4500,4640):
        ok,im=cap.read();assert ok
        gray=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
        for b in r['frames'].get(str(n),[]):
            x,y,w,h=b['box']
            if not (x>1000 and y>1000 and 250<w<650):continue
            x0,y0=max(0,x-80),max(0,y-50);x1,y1=min(3840,x+w+80),min(2160,y+h+50)
            search=gray[y0:y1,x0:x1];best=None
            for scale in np.linspace(.65,1.35,29):
                tw,th=round(template.shape[1]*scale),round(template.shape[0]*scale)
                if tw>search.shape[1] or th>search.shape[0]:continue
                t=cv2.resize(template,(tw,th));score=cv2.matchTemplate(search,t,cv2.TM_CCOEFF_NORMED);_,v,_,p=cv2.minMaxLoc(score)
                if best is None or v>best[0]:best=(v,p,tw,th)
            if best and best[0]>.76:
                v,p,tw,th=best;b['box']=mod.clamp([x0+p[0]-4,y0+p[1]-4,tw+8,th+8],3840,2160)
                b.update(box_method='reviewed_word',origin='review_glyph_template',tracking_score=float(v));count+=1
    cap.release();r['key_frames']={str(n):r['frames'].get(str(n),[])for n in KEYS}
    r['notes'].append('Regular-font lower-page domain boxes refined with a human-confirmed native glyph template to retain adjacent Chinese words.')
    r['template_refined_boxes']=count;output.write_text(json.dumps(r,ensure_ascii=False,indent=2));print('refined',count,'key4560',[b['box']for b in r['frames']['4560']],flush=True)

if __name__=='__main__':
    if '--lower-only' not in sys.argv:main()
    lower_only()
    tighten_native_words()
