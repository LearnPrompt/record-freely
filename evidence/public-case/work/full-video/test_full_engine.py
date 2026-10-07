import importlib.util
import sys
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('full_redactor',Path(__file__).with_name('redact_full_engine.py'))
r=importlib.util.module_from_spec(spec);sys.modules[spec.name]=r;spec.loader.exec_module(r)


def shared_word(text,confidence=1,y=.3):
    return {'text':text,'confidence':confidence,'box':[.1,y,.7,.03],
            'chars':[{'start':i,'end':i+1,'box':[.1,y,.7,.03]} for i in range(len(text))]}


def test_shared_word_geometry_does_not_mask_surrounding_chinese():
    ob=shared_word('访问example.com继续')
    details=[]
    box=r.detection_boxes([ob],1000,1000,0,details)[0]
    assert box[0]>100
    assert box[0]+box[2]<800
    assert 300<box[2]<600
    assert details[0]['box_method']=='glyph_width_word'


def test_shared_word_uses_real_glyph_widths_not_character_count():
    text='中文Models.dev继续'
    box=r.fractional_box([0,0,1,.1],text,0,len(text),2,12,True)
    expected=sum(r.glyph_width(c) for c in 'Models.dev')
    assert box[0]==pytest.approx(200/(400+expected))
    assert box[2]==pytest.approx(expected/(400+expected))


@pytest.mark.parametrize('host',['Models.dev','skills.sh','FFHub.io'])
def test_reviewed_public_hosts_survive_low_confidence_with_compact_boxes(host):
    ob=shared_word('访问'+host+'继续',.3)
    details=[]
    boxes=r.detection_boxes([ob],1000,1000,0,details)
    assert len(boxes)==1
    assert boxes[0][0]>100 and boxes[0][0]+boxes[0][2]<800
    assert details[0]['rule_source']=='manual_review_confirmed'
    assert details[0]['box_method']=='glyph_width_word'


@pytest.mark.parametrize('text',['urllib.parse','urllib.parse(data)','follow.opml','feeds/follow.opml','bash skills.sh','./skills.sh','/tmp/skills.sh','open("skills.sh")'])
def test_confirmed_code_fields_and_local_files_excluded(text):
    assert r.detection_boxes([shared_word(text)],1000,1000,0)==[]


@pytest.mark.parametrize('text',['skills.sh','skills.sh/tools','curl skills.sh','https://skills.sh','clawhub.ai','vc.feishu.cn','applink.feishu.cn'])
def test_known_domains_and_explicit_urls_remain(text):
    assert r.detection_boxes([shared_word(text)],1000,1000,0)


def test_navigation_exclusion_is_exact_and_position_limited():
    nav=shared_word('3.把多个Skills组合成工作流',1,.02)
    assert r.detection_boxes([nav],3840,2160,4)==[]
    nav['box'][1]=.3
    # Same content below the reviewed top bar is handled by normal detection.
    assert not r.reviewed_navigation(nav,2160)
    real=shared_word('https://example.com',1,.02)
    assert r.detection_boxes([real],3840,2160,4)


def test_confirmed_domains_do_not_reintroduce_emails_or_larger_urls():
    assert not r.detection_boxes([shared_word('user@models.dev',.3)],1000,1000,0)
    assert not r.detection_boxes([shared_word('models.development',.3)],1000,1000,0)
    ob=shared_word('https://example.com/models.dev/path',.3)
    boxes=r.detection_boxes([ob],1000,1000,0)
    assert boxes==[[100,300,700,30]]


def test_assets_resolve_to_installed_worker_and_tld_snapshot():
    assert (r.ENGINE_ASSETS/'vision_ocr.swift').is_file()
    assert r.TLD_FILE.parent==r.ENGINE_ASSETS


@pytest.mark.parametrize('old_id,new_id,old_box,new_box,forward_calls',[
    ('U001','U001',[10,10,30,8],[12,10,30,8],0),
    ('U001','U002',[10,10,30,8],[12,10,30,8],1),
    (None,None,[10,10,30,8],[12,10,30,8],1),
    ('','',[10,10,30,8],[12,10,30,8],1),
    ('U001','U001',[10,10,30,8],[85,10,30,8],1),
    ('U001','U001',[10,10,27,8],[23,10,27,8],1),
    ('U001',None,[10,10,30,8],None,1),
])
def test_main_skips_only_fresh_same_id_overlapping_ocr(tmp_path,monkeypatch,
                                                        old_id,new_id,old_box,new_box,forward_calls):
    import json
    import numpy as np
    # Two-frame main pipeline, with current-frame pixels distinct from pending
    # look-back pixels. This measures actual forward template calls, not merely
    # the decision helper, and verifies that fresh OCR rebuilding still happens.
    frames=[np.full((36,128,3),i,np.uint8) for i in range(2)]
    forwarded=[];rebuilt=[]
    class OCR:
        def __init__(self,scratch):pass
        def read(self,frame):return [{'index':int(frame[0,0,0])}]
        def close(self):pass
    class Capture:
        def __init__(self,path):self.index=0
        def isOpened(self):return True
        def get(self,field):
            return {r.cv2.CAP_PROP_FRAME_WIDTH:128,r.cv2.CAP_PROP_FRAME_HEIGHT:36,
                    r.cv2.CAP_PROP_FRAME_COUNT:2}.get(field,0)
        def read(self):
            if self.index==2:return False,None
            frame=frames[self.index];self.index+=1;return True,frame
        def release(self):pass
    class Pipe:
        def write(self,data):pass
        def close(self):pass
    class Encoder:
        def __init__(self,*args,**kwargs):self.stdin=Pipe();self.running=True
        def wait(self):self.running=False;return 0
        def poll(self):return None if self.running else 0
        def kill(self):self.running=False
    def detect(obs,width,height,padding,details,identities):
        index=obs[0]['index']
        box=old_box if index==0 else new_box
        if box is None:return []
        details.append({'id':old_id if index==0 else new_id})
        return [box]
    real_make=r.make_track
    def make(gray,box,details=None):
        rebuilt.append((int(gray[0,0]),list(box)))
        return real_make(gray,box,details)
    def move(track,gray,*args,**kwargs):
        if gray[0,0]==1:forwarded.append(track)
        return None
    def probe(path):
        if path.name=='redacted.mp4':
            return {'streams':[{'codec_type':'video','nb_frames':'2','duration':str(2/30)}]}
        return {'streams':[{'codec_type':'video','index':0,'avg_frame_rate':'30/1'}]}
    def run(command):
        Path(command[-1]).write_bytes(b'mocked-media')
        return ''
    source=tmp_path/'source.mp4';source.write_bytes(b'original')
    output=tmp_path/'output'
    monkeypatch.setattr(r,'VisionOCR',OCR)
    monkeypatch.setattr(r.cv2,'VideoCapture',Capture)
    monkeypatch.setattr(r.subprocess,'Popen',Encoder)
    monkeypatch.setattr(r,'detection_boxes',detect)
    monkeypatch.setattr(r,'make_track',make)
    monkeypatch.setattr(r,'move_track',move)
    monkeypatch.setattr(r,'probe',probe)
    monkeypatch.setattr(r,'run',run)
    monkeypatch.setattr(sys,'argv',['redact_full_engine.py',str(source),'--output-dir',str(output),
                                 '--ocr-workers','3'])
    r.main()
    assert len(forwarded)==forward_calls
    report=json.loads((output/'report.json').read_text())
    assert report['ocr_workers']==3
    assert report['processed_frames']==2
    assert report['frames'][1]['boxes']==([new_box] if new_box is not None else [])
    if new_box is not None:
        assert (1,new_box) in rebuilt
    assert source.read_bytes()==b'original'


@pytest.mark.parametrize('text',['d e cogitat ing.np.','cogitat ing.np','D E COGITAT ING.NP.'])
def test_only_confirmed_cogitating_status_is_excluded(text):
    assert r.url_spans(text)==[]


@pytest.mark.parametrize('text',['ing.np','https://ing.np','www.ing.np','ing.np/path','ing.np:8080',
                                'other.np','cogitat ing.np/path','cogitat ing.np:80',
                                'cogitat ing.np 官网','cogitating.np'])
def test_confirmed_status_rule_preserves_real_domain_forms_and_other_prose(text):
    assert r.url_spans(text)


@pytest.mark.parametrize('text',['| 3.BZ†SkillsBâI','3.bz†skillsbâi','｜ 3. BZ † Skills BâI |'])
def test_confirmed_top_navigation_hallucination_seed_excluded(text):
    assert r.detection_boxes([shared_word(text,1,.02)],3840,2160,4)==[]
    # Location is essential: the same OCR fragment elsewhere is not blanketed.
    assert not r.reviewed_navigation(shared_word(text,1,.3),2160)


@pytest.mark.parametrize('text',['3.bz','3.bz Skills','12.bz','https://3.bz','www.3.bz','3.bz/path','3.bz:80'])
def test_navigation_seed_rule_preserves_real_numeric_domains(text):
    assert r.detection_boxes([shared_word(text,1,.02)],3840,2160,4)
