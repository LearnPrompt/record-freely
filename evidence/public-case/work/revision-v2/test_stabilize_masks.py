import unittest
from stabilize_masks import stabilize_records,apply_review_ops

def frame(n,boxes,kind='url',origin='ocr'):
 return {'frame':n,'boxes':boxes,'origins':[origin]*len(boxes),'regions':[{'id':str(i),'origin':origin,'kind':kind}for i in range(len(boxes))]}

class StabilityTests(unittest.TestCase):
 def covered(self,b,old):
  self.assertLessEqual(b[0],old[0]);self.assertLessEqual(b[1],old[1]);self.assertGreaterEqual(b[0]+b[2],old[0]+old[2]);self.assertGreaterEqual(b[1]+b[3],old[1]+old[3])
 def test_stationary_jitter_has_one_constant_rectangle(self):
  fs=[frame(n,[[100+n%3,200+n%2,350+n%5,40+n%3]])for n in range(30)]
  out,s=stabilize_records(fs,1920,1080)
  self.assertEqual(len({tuple(f['boxes'][0])for f in out}),1)
  for f,o in zip(out,fs):self.covered(f['boxes'][0],o['boxes'][0])
 def test_moving_target_has_fixed_size_and_current_coverage(self):
  fs=[frame(n,[[100+20*n,100+4*n,240+n%3,40]])for n in range(20)]
  out,s=stabilize_records(fs,1920,1080)
  self.assertEqual(len({tuple(f['boxes'][0][2:])for f in out}),1)
  for f,o in zip(out,fs):self.covered(f['boxes'][0],o['boxes'][0])
 def test_scale_change_follows_without_enveloping_whole_path(self):
  fs=[frame(n,[[100,200,int(250*(1+n*.05)),int(40*(1+n*.05))]])for n in range(20)]
  out,s=stabilize_records(fs,1920,1080)
  for f,o in zip(out,fs):self.covered(f['boxes'][0],o['boxes'][0])
  self.assertLess(out[0]['boxes'][0][2],out[-1]['boxes'][0][2])
 def test_overlapping_duplicate_not_two_flickering_rectangles(self):
  fs=[frame(n,[[100,200,500,60],[105,205,500,48]])for n in range(12)]
  out,s=stabilize_records(fs,1920,1080)
  self.assertTrue(all(len(f['boxes'])==1 for f in out))
 def test_different_rows_and_missing_frames_do_not_join(self):
  fs=[frame(0,[[100,200,500,45],[100,300,500,45]]),frame(1,[]),frame(2,[[100,200,500,45]])]
  out,s=stabilize_records(fs,1920,1080)
  self.assertEqual([len(f['boxes'])for f in out],[2,0,1]);self.assertEqual(s['tracks'],3)
 def test_word_mask_does_not_inherit_caption_restore(self):
  f=frame(0,[[100,200,300,50],[100,200,100,50]])
  f['regions'][0]['preserve_orange_caption']=True;f['regions'][1]['kind']='reviewed_word'
  out,_=stabilize_records([f],1920,1080)
  self.assertEqual(len(out[0]['boxes']),2);self.assertEqual(out[0]['regions'][-1]['kind'],'reviewed_word');self.assertFalse(out[0]['regions'][-1].get('preserve_orange_caption',False))
 def test_review_deletes_only_requested_baseline_index(self):
  r={'frames':[frame(0,[[100,200,100,40],[300,200,100,40]])]};p={'start_frame':9000}
  patch={'frames':{'9000':{'remove_indexes':[0],'add':[{'box':[100,200,50,40],'id':'review','kind':'url'}]}}}
  out=apply_review_ops(r,p,[patch]);self.assertEqual(out['frames'][0]['boxes'],[[300,200,100,40],[100,200,50,40]]);self.assertEqual(len(r['frames'][0]['boxes']),2)
 def test_reviewed_prefix_never_expands_into_retained_suffix(self):
  fs=[frame(n,[[100+n%2,200,320,40]],'reviewed_path','review_v2')for n in range(20)]
  out,_=stabilize_records(fs,1920,1080)
  for f,o in zip(out,fs):self.assertEqual(f['boxes'],o['boxes'])

if __name__=='__main__':unittest.main()
