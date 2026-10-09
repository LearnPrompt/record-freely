"""Classification and geometry regressions from publication review gaps."""
import json
import pytest
import redact_video as engine
from review_candidates import text_candidates, observation_candidates

@pytest.mark.parametrize('value,kind',[('demo@example.com','email'),('13812345678','phone'),
 ('电话：010-12345678','phone'),('/Users/alice/Downloads/demo.mp4','identity_path'),
 (r'C:\Users\alice\Downloads\demo.mp4','identity_path')])
def test_privacy_is_explicit_opt_in(value,kind):
    assert not any(r['kind']==kind for r in text_candidates(value))
    assert any(r['kind']==kind and r['status']=='mask' for r in text_candidates(value,True))

@pytest.mark.parametrize('value',['2. AI Coding','3. ai 工作流','2.ai'])
def test_numbered_heading_is_not_automatically_masked(value):
    rows=text_candidates(value)
    assert rows and rows[0]['status']=='needs_review'
    assert engine.url_spans(value)==[]


def observation(text,confidence=1):
    return {'text':text,'confidence':confidence,'box':[.1,.1,.8,.1],
        'chars':[{'start':i,'end':i+1,'box':[.1+i*.8/len(text),.1,.8/len(text),.1]} for i in range(len(text))]}


def test_original_offsets_preserve_cjk_and_fullwidth_url_geometry():
    text='继续 https：／／example.com/a 讲解'
    row=text_candidates(text)[0]
    assert text[row['start']:row['end']]=='https：／／example.com/a'
    boxes=engine.detection_boxes([observation(text)],1000,500,0)
    assert len(boxes)==1 and boxes[0][0]>100 and boxes[0][0]+boxes[0][2]<900


def test_low_confidence_is_reviewed_without_automatic_mask():
    ledger=[]
    assert not engine.detection_boxes([observation('example.com',.3)],1000,500,0,review=ledger)
    assert ledger[0]['status']=='needs_review' and ledger[0]['reason']=='low_ocr_confidence'


def test_privacy_ledger_does_not_store_recognized_content():
    value='demo@example.com'
    ledger=[];details=[]
    boxes=engine.detection_boxes([observation(value)],1000,500,0,metadata=details,
                                 identities={},privacy=True,review=ledger)
    assert boxes and details[0]['kind']=='email'
    saved=json.dumps({'candidates':ledger,'regions':details})
    assert value not in saved and 'example.com' not in saved and 'text' not in saved
    assert ledger[0]['status']=='mask'


def test_identity_prefix_keeps_purpose_and_filename_with_character_geometry():
    value='/Users/alice/Downloads/demo.mp4'
    row=observation_candidates([observation(value)],1000,500,0,True)[0]
    assert row['kind']=='identity_path' and row['status']=='mask'
    assert row['box'][0]+row['box'][2]<900
    assert value[row['span'][1]:]=='Downloads/demo.mp4'


def test_identity_prefix_with_only_line_geometry_is_pending():
    value='/Users/alice/Downloads/demo.mp4'
    row=observation_candidates([{'text':value,'box':[.1,.1,.8,.1]}],1000,500,0,True)[0]
    assert row['status']=='needs_review'
    assert row['reason']=='identity_prefix_requires_precise_geometry'


def test_qr_box_is_opt_in_and_payload_free():
    qr={'kind':'qr_code','text':'','box':[.1,.2,.3,.3],'confidence':1}
    assert observation_candidates([qr],1000,500)==[]
    rows=observation_candidates([qr],1000,500,0,True)
    assert rows[0]['box']==[100,100,300,150] and rows[0]['status']=='mask'
    assert 'payload' not in json.dumps(rows)


def test_labelled_phone_not_order_id_and_original_offsets():
    assert not any(r['kind']=='phone' for r in text_candidates('订单 12345678901234567890',True))
    text='客服 phone: +1 (212) 555-0199 服务'
    row=next(r for r in text_candidates(text,True) if r['kind']=='phone')
    assert text[row['start']:row['end']]=='+1 (212) 555-0199'


def test_split_address_uses_spatial_context_and_never_auto_masks():
    fragments=[{'text':'https://','box':[.1,.1,.1,.04]},
               {'text':'example.com','box':[.1,.15,.2,.04]}]
    rows=observation_candidates(fragments,1000,500)
    splits=[r for r in rows if r['kind']=='split_address']
    assert splits and splits[0]['status']=='needs_review'
    fragments[1]['box']=[.8,.8,.2,.04]
    assert not any(r['kind']=='split_address' for r in observation_candidates(fragments,1000,500))


def test_spoken_domains_and_numbers_are_only_review_hints():
    text='联系我，一三八一二三四五六七八，example dot com'
    rows=text_candidates(text,True,channel='audio')
    assert {'phone','contact_cue','spoken_address'} <= {r['kind'] for r in rows}
    assert all(r['status']=='needs_review' for r in rows)
    assert not text_candidates('example dot com',channel='screen_text')
