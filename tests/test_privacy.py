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


def test_partial_policy_rejects_shared_word_boxes():
    value='https://github.com/sample/sample-skill'
    obs=observation(value)
    # Native accurate OCR can repeat a single word-wide rectangle. It must
    # not claim precision when a retained suffix occupies that same box.
    for char in obs['chars']:
        char['box']=[.1,.1,.8,.1]
    row=observation_candidates([obs],1000,500,0,github_policy='host')[0]
    assert row['box_method']=='shared_character_boxes'
    assert row['status']=='needs_review'
    assert row['reason']=='retained_suffix_requires_precise_geometry'


@pytest.mark.parametrize('value,suffix',[
    ('/Users/alice/Downloads/demo.mp4','demo.mp4'),
    ('/home/alice/work/synthetic.py','synthetic.py'),
    (r'C:\Users\alice\Downloads\demo.mp4','demo.mp4'),
])
def test_parent_policy_masks_only_identity_rooted_parents(value,suffix):
    row=next(r for r in text_candidates(value,True,path_policy='parent') if r['kind']=='identity_path')
    assert value[row['end']:]==suffix
    actual=observation_candidates([observation(value)],1000,500,4,True,path_policy='parent')
    row=next(r for r in actual if r['kind']=='identity_path')
    assert row['status']=='mask' and row['box_method']=='characters'
    assert row['box'][0]+row['box'][2]<=int((.1+row['span'][1]*.8/len(value))*1000)
    assert not text_candidates('README.md',True,path_policy='parent') or all(
        r['status']=='keep' for r in text_candidates('README.md',True,path_policy='parent'))


@pytest.mark.parametrize('value',[
    'https://github.com/sample/sample-skill',
    'github.com/sample/sample-skill',
    'https：／／github.com／sample／sample-skill',
])
def test_explicit_github_policy_preserves_author_skill_with_precise_geometry(value):
    row=next(r for r in text_candidates(value,github_policy='host') if r['status']=='mask')
    assert 'sample' not in value[row['start']:row['end']]
    assert row['reason']=='github_host_policy'
    default=next(r for r in text_candidates(value) if r['status']=='mask')
    assert default['end']==len(value)
    actual=observation_candidates([observation(value)],1000,500,4,github_policy='host')[0]
    assert actual['status']=='mask' and actual['box_method']=='characters'
    assert actual['box'][0]+actual['box'][2]<=int((.1+actual['span'][1]*.8/len(value))*1000)


@pytest.mark.parametrize('value',[
 'https://github.com.evil.invalid/sample/skill',
 'https://github.com@evil.invalid/sample/skill',
 'https://evil.invalid/github.com/sample/skill',
])
def test_github_policy_never_preserves_impostor_hosts(value):
    row=next(r for r in text_candidates(value,github_policy='host') if r['status']=='mask')
    assert row['end']==len(value) and row['reason']=='visible_address'


def test_fast_observation_does_not_inherit_accurate_line_geometry():
    value='/Users/alice/Downloads/demo.mp4'
    accurate={'text':value,'box':[.1,.1,.8,.1]}
    fast=observation(value)
    fast['geometry_engine']='vision_fast'
    rows=observation_candidates([accurate,fast],1000,500,0,True,path_policy='parent')
    assert len(rows)==1
    assert rows[0]['status']=='mask' and rows[0]['box_method']=='characters'
    assert rows[0]['geometry_engine']=='vision_fast_aligned'
    assert rows[0]['box'][2]<800


def test_fast_host_letter_misread_uses_accurate_semantics_and_real_glyphs():
    value='github.com/sample/sample-skill'
    accurate={'text':value,'box':[.1,.1,.8,.1]}
    fast=observation(value.replace('github','githuh'))
    fast['geometry_engine']='vision_fast'
    rows=observation_candidates([accurate,fast],1000,500,4,github_policy='host')
    assert len(rows)==1 and rows[0]['reason']=='github_host_policy'
    assert rows[0]['status']=='mask' and rows[0]['box'][2]<300


@pytest.mark.parametrize('changed',[
    'githuh,com/sample/sample-skill',
    'github.com/sample/sample-skills',
    'gitlab.com/sample/sample-skill',
])
def test_geometry_alignment_rejects_punctuation_length_or_major_content_change(changed):
    value='github.com/sample/sample-skill'
    accurate={'text':value,'box':[.1,.1,.8,.1]}
    fast=observation(changed);fast['geometry_engine']='vision_fast'
    rows=observation_candidates([accurate,fast],1000,500,4,github_policy='host')
    assert rows[0]['status']=='needs_review'
    assert rows[0].get('geometry_engine')!='vision_fast_aligned'


def test_geometry_alignment_requires_same_observed_row_and_keeps_good_geometry():
    value='github.com/sample/sample-skill'
    good=observation(value)
    fast=observation(value);fast['geometry_engine']='vision_fast'
    fast['box']=[.1,.5,.8,.1]
    rows=observation_candidates([good,fast],1000,500,4,github_policy='host')
    assert rows[0]['status']=='mask' and not rows[0].get('geometry_engine')
    incomplete={'text':value,'box':[.1,.1,.8,.1]}
    rows=observation_candidates([incomplete,fast],1000,500,4,github_policy='host')
    assert rows[0]['status']=='needs_review'


def test_geometry_alignment_can_ignore_misread_separator_before_address():
    accurate={'text':'/github.com/sample/skill','box':[.1,.1,.8,.1]}
    fast=observation('Igithub.com/sample/skill');fast['geometry_engine']='vision_fast'
    rows=observation_candidates([accurate,fast],1000,500,4,github_policy='host')
    assert len(rows)==1 and rows[0]['status']=='mask'
    assert rows[0]['reason']=='github_host_policy'
    assert rows[0]['box'][2]<450


@pytest.mark.parametrize('value',['sp.read_text()','sp.read_text','module.read_text()',
                                  'foo.download_file(path)','sp . read_text()'])
def test_code_identifier_with_underscore_cannot_be_truncated_into_domain(value):
    assert not engine.url_spans(value)
    assert not any(r['status']=='mask' for r in text_candidates(value))


def test_explicit_address_can_still_have_underscore_in_resource_path():
    value='https://example.com/read_text/file_name.py'
    assert engine.url_spans(value)==[(0,len(value))]


def test_nearly_shared_word_boxes_cannot_overwrite_a_retained_suffix():
    value='github.com/sample/skill'
    obs=observation(value)
    for n,c in enumerate(obs['chars']):
        c['box']=[.1+n*.00001,.1,.7,.1]
    row=observation_candidates([obs],1000,500,4,github_policy='host')[0]
    assert row['status']=='needs_review'
    assert row['box_method']=='overlapping_character_boxes'


def test_unpaired_fast_misread_cannot_automatically_mask_readme():
    accurate=observation('README.md')
    fast=observation('README.ml');fast['geometry_engine']='vision_fast'
    rows=observation_candidates([accurate,fast],1000,500,0)
    assert rows[0]['status']=='keep'
    assert not any(r['status']=='mask' for r in rows)
    assert rows[1]['status']=='needs_review'
    assert rows[1]['reason']=='independent_geometry_requires_review'


@pytest.mark.parametrize('start,end',[(-1,10),(0,99),(True,10),(0,False),(0,10.5)])
def test_invalid_character_ranges_cannot_mask_retained_filename(start,end):
    value='/Users/alice/demo.mp4'
    obs={'text':value,'box':[.1,.1,.8,.1],
         'chars':[{'start':start,'end':end,'box':[.1,.1,.8,.1]}]}
    row=observation_candidates([obs],1000,500,0,True,path_policy='parent')[0]
    assert row['status']=='needs_review' and row['box_method']!='characters'


def test_single_word_range_crossing_policy_boundary_cannot_mask_retained_filename():
    value='/Users/alice/demo.mp4'
    obs={'text':value,'box':[.1,.1,.8,.1],
         'chars':[{'start':0,'end':len(value),'box':[.1,.1,.8,.1]}]}
    row=observation_candidates([obs],1000,500,0,True,path_policy='parent')[0]
    assert row['status']=='needs_review' and row['box_method']=='crossing_character_range'


@pytest.mark.parametrize('value',['github . com/sample/skill','www . github.com/sample/skill',
                                  'https://github . com/sample/skill'])
def test_ocr_spaces_in_canonical_github_host_do_not_mask_resource_suffix(value):
    row=next(r for r in text_candidates(value,github_policy='host') if r['status']=='mask')
    assert value[row['end']:]=='/sample/skill'
    assert row['reason']=='github_host_policy'


def test_ocr_space_instead_of_code_underscore_is_reviewed_not_masked():
    rows=text_candidates('sp.read text()')
    assert rows and rows[0]['status']=='needs_review'
    assert rows[0]['reason']=='possible_spaced_code_call'


@pytest.mark.parametrize('value',['/Users/alice/Downloads/My Clip/demo.mp4',
                                  '/Users/alice/ .npm-global/bin/tool'])
def test_parent_path_with_uncertain_space_continuation_is_not_claimed_complete(value):
    rows=text_candidates(value,True,path_policy='parent')
    row=next(r for r in rows if r['kind']=='identity_path')
    assert row['status']=='needs_review'
    assert row['reason']=='identity_path_continuation_requires_review'
