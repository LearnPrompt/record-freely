#!/usr/bin/env python3
"""Apply reviewed global-frame rectangles to a completed chunk without OCR.

Only generated chunks named in manifest.json are writable. Video/report/complete
are staged and verified before their per-file atomic replacements; complete.json
is written last as the commit marker. Original and approved first-five-minute
videos are never write targets.
"""
from __future__ import annotations
import argparse
from bisect import bisect_right
import copy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import fcntl
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import unittest

import cv2
import numpy as np
from stream_capture import StreamCapture

BASE = Path(__file__).resolve().parent


def execute(command, log):
    with open(log, 'ab') as error:
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=error)
    if result.returncode:
        raise RuntimeError(f'{Path(command[0]).name} failed (exit {result.returncode}); staged files retained until cleanup')


def probe(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('ffprobe could not inspect generated media')
    return json.loads(result.stdout)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def normalized_box(box, width, height):
    if len(box) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in box):
        raise ValueError('Patch rectangle must contain four finite numbers')
    x, y, w, h = box
    if w <= 0 or h <= 0:
        raise ValueError('Patch rectangle must have positive dimensions')
    left, top = max(0, math.floor(x)), max(0, math.floor(y))
    right, bottom = min(width, math.ceil(x + w)), min(height, math.ceil(y + h))
    if right <= left or bottom <= top:
        raise ValueError('Patch rectangle lies outside the video')
    return [left, top, right-left, bottom-top]


def merge_report(report, part, patches, remove_ids=()):
    """Return an independent report, changed local frames, and exact delta stats."""
    merged = copy.deepcopy(report)
    frames = merged['frames']
    if len(frames) != part['frames'] or any(f.get('frame') != i for i, f in enumerate(frames)):
        raise ValueError('Chunk report does not contain every ordered local frame')
    fps = float(report['fps'])
    if fps != 30 or float(part['start_frame']) / fps != part['start_seconds']:
        raise ValueError('Repair input must use the manifest 30 fps frame timeline')
    width, height = int(report['width']), int(report['height'])
    changed = set()
    before_masked = sum(bool(f['boxes']) for f in frames)
    removed = added = skipped = 0
    remove_ids = set(remove_ids)
    for index, frame in enumerate(frames):
        boxes, origins, regions = frame['boxes'], frame['origins'], frame['regions']
        if len(boxes) != len(origins) or len(boxes) != len(regions):
            raise ValueError('Chunk boxes/origins/regions are not aligned')
        keep = [i for i, region in enumerate(regions) if region.get('id') not in remove_ids]
        if len(keep) != len(boxes):
            removed += len(boxes) - len(keep)
            frame['boxes'] = [boxes[i] for i in keep]
            frame['origins'] = [origins[i] for i in keep]
            frame['regions'] = [regions[i] for i in keep]
            changed.add(index)
    patch_evidence = []
    for name, digest, patch in patches:
        if float(patch.get('fps', fps)) != fps:
            raise ValueError('Patch frame rate differs from the chunk')
        if not isinstance(patch.get('frames'), dict):
            raise ValueError('Patch frames must be keyed by global source frame')
        prefix = f'R{digest[:12]}'
        in_chunk_frames = in_chunk_regions = 0
        for global_key, records in patch['frames'].items():
            global_frame = int(global_key)
            local_frame = global_frame - part['start_frame']
            if not 0 <= local_frame < len(frames):
                continue
            if not isinstance(records, list):
                raise ValueError('Patch frame records must be a list')
            if records:
                in_chunk_frames += 1
            frame = frames[local_frame]
            for ordinal, record in enumerate(records):
                box = normalized_box(record['box'], width, height)
                original_id = record.get('id')
                identity = f'{prefix}:{original_id}' if original_id else f'{prefix}:F{global_frame}:B{ordinal}'
                if any(region.get('id') == identity and old_box == box
                       for region, old_box in zip(frame['regions'], frame['boxes'])):
                    skipped += 1
                    continue
                region = {key: copy.deepcopy(value) for key, value in record.items() if key != 'box'}
                region.update(id=identity, repair_patch=prefix, origin=record.get('origin', 'review_patch'),
                              patch_global_frame=global_frame)
                if 'confidence' in region and 'ocr_confidence' not in region:
                    region['ocr_confidence'] = region.pop('confidence')
                frame['boxes'].append(box)
                frame['origins'].append(region['origin'])
                frame['regions'].append(region)
                added += 1
                in_chunk_regions += 1
                changed.add(local_frame)
        patch_evidence.append({'file': name, 'sha256': digest, 'id_prefix': prefix,
                               'matched_frames': in_chunk_frames, 'added_regions': in_chunk_regions})
    after_masked = sum(bool(f['boxes']) for f in frames)
    newly_masked = sum(not old['boxes'] and bool(new['boxes']) for old,new in zip(report['frames'],frames))
    newly_unmasked = sum(bool(old['boxes']) and not new['boxes'] for old,new in zip(report['frames'],frames))
    merged['masked_frames'] = after_masked
    stats = {'added_regions': added, 'removed_regions': removed, 'duplicate_regions_skipped': skipped,
             'affected_frames': len(changed), 'masked_frames_before': before_masked,
             'masked_frames_after': after_masked, 'new_masked_frames': newly_masked,
             'removed_masked_frames': newly_unmasked, 'masked_frames_delta': after_masked-before_masked,
             'remove_ids': sorted(remove_ids), 'patches': patch_evidence}
    return merged, sorted(changed), stats


def render_mask(frame, record):
    """Match gray-112 masks with individually reviewed caption preservation."""
    result = frame.copy()
    original = frame
    for box, region in zip(record['boxes'], record['regions']):
        x, y, w, h = box
        if not (region.get('preserve_orange_caption') or region.get('preserve_white_caption')):
            result[y:y+h, x:x+w] = 112
        else:
            patch = original[y:y+h, x:x+w]
            hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
            orange = np.zeros(hsv.shape[:2],np.uint8)
            if region.get('preserve_orange_caption'):
                orange |= cv2.inRange(hsv, np.array([3,120,110],np.uint8), np.array([32,255,255],np.uint8))
            if region.get('preserve_white_caption'):
                # Only individually reviewed yellow URI regions may enable this.
                orange |= cv2.inRange(hsv, np.array([0,0,180],np.uint8), np.array([179,55,255],np.uint8))
            orange = cv2.dilate(orange, np.ones((5,5),np.uint8)) > 0
            result[y:y+h, x:x+w] = 112
            result[y:y+h, x:x+w][orange] = patch[orange]
    return result


def keyframe_boundaries(video, count, fps):
    result = subprocess.run(['ffprobe','-v','error','-skip_frame','nokey','-select_streams','v:0',
                             '-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(video)],
                            capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError('Could not find H264 keyframe boundaries')
    indexes = sorted({round(float(frame['best_effort_timestamp_time']) * fps)
                      for frame in json.loads(result.stdout)['frames']})
    if not indexes or indexes[0] != 0 or any(i < 0 or i >= count for i in indexes):
        raise RuntimeError('Unexpected generated-chunk keyframe timeline')
    return indexes


def repair_window(changed, keys, total):
    left = max(k for k in keys if k <= min(changed))
    right = min((k for k in keys if k >= max(changed)+1), default=total)
    return left, right


def repair_windows(changed, keys, total):
    """Map changed frames to closed GOP intervals, merging adjacent intervals."""
    if not changed:
        return []
    if not keys or keys[0] != 0 or keys != sorted(set(keys)) or keys[-1] >= total:
        raise ValueError('Invalid keyframe boundaries')
    intervals=[]
    for frame in sorted(set(changed)):
        if not 0 <= frame < total:
            raise ValueError('Changed frame lies outside the generated chunk')
        position=bisect_right(keys,frame)-1
        left=keys[position]
        right=keys[position+1] if position+1<len(keys) else total
        if intervals and left<=intervals[-1][1]:
            intervals[-1][1]=max(intervals[-1][1],right)
        else:
            intervals.append([left,right])
    return intervals


def verify_video(path, expected_frames, fps, expected_audio=None):
    info = probe(path)
    videos = [s for s in info['streams'] if s['codec_type'] == 'video']
    if len(videos) != 1:
        raise RuntimeError('Staged media must have exactly one video stream')
    video = videos[0]
    if int(video.get('nb_frames', -1)) != expected_frames:
        raise RuntimeError('Staged video frame count mismatch')
    if abs(float(video.get('duration', 0)) - expected_frames/fps) > .002:
        raise RuntimeError('Staged video duration mismatch')
    if abs(float(video.get('start_time', 0))) > .002:
        raise RuntimeError('Staged video has a shifted start time')
    if expected_audio is not None and sum(s['codec_type']=='audio' for s in info['streams']) != expected_audio:
        raise RuntimeError('Staged audio stream count mismatch')
    # Container nb_frames alone can hide B-frame cut gaps. Verify every packet's
    # presentation timestamp forms the exact CFR frame set, without duplicates.
    packets = subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_packets',
                              '-show_entries','packet=pts','-of','json',str(path)],capture_output=True,text=True)
    if packets.returncode:
        raise RuntimeError('Could not verify staged packet timestamps')
    base = Fraction(video['time_base'])
    indexes = []
    for packet in json.loads(packets.stdout)['packets']:
        position = int(packet['pts']) * base * Fraction(str(fps))
        if position.denominator != 1:
            raise RuntimeError('Non-frame-aligned presentation timestamp')
        indexes.append(int(position))
    if sorted(indexes) != list(range(expected_frames)):
        raise RuntimeError('Copy slicing produced gaps, duplicates, or out-of-range B-frame timestamps')
    return info


def encode_window(source, part, report, left, right, output, log):
    width, height, fps = report['width'], report['height'], report['fps']
    capture = StreamCapture(source, (part['start_frame']+left)/fps, right-left,
                            width=width,height=height,fps=fps,log=str(log)+'.decode')
    command = ['ffmpeg','-v','error','-nostdin','-y','-threads','4','-f','rawvideo','-pix_fmt','bgr24',
               '-s',f'{width}x{height}','-r',str(fps),'-i','pipe:0','-an','-c:v','libx264',
               '-crf','18','-preset','fast','-threads','4','-pix_fmt','yuv420p',
               '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709',
               '-map_metadata','-1',str(output)]
    error = open(log,'ab')
    encoder = subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=error)
    try:
        for index in range(left,right):
            ok,frame = capture.read()
            if not ok:
                raise RuntimeError('Source RGB stream ended before the repair window')
            encoder.stdin.write(render_mask(frame,report['frames'][index]).tobytes())
            if (index-left+1) % 60 == 0:
                print(json.dumps({'stage':'rendering_repair','local_frames':index-left+1,'total':right-left}),flush=True)
        encoder.stdin.close()
        if encoder.wait() != 0:
            raise RuntimeError('Repair encoding failed')
    finally:
        capture.release()
        if encoder.poll() is None:
            encoder.kill();encoder.wait()
        error.close()
    verify_video(output,right-left,fps,0)


def copy_video_segment(source,left,count,fps,output,log):
    execute(['ffmpeg','-v','error','-nostdin','-y','-ss',f'{left/fps:.10f}','-i',str(source),
             '-map','0:v:0','-an','-c:v','copy','-frames:v',str(count),'-map_metadata','-1',str(output)],log)
    verify_video(output,count,fps,0)


def concat_video(segments,fps,scratch,log):
    playlist=scratch/'concat.txt'
    # Temporary path names are controlled here; no user-provided playlist data.
    playlist.write_text(''.join(f"file '{path.resolve()}'\nduration {count/fps:.10f}\n" for path,count in segments))
    output=scratch/'joined-video.mp4'
    execute(['ffmpeg','-v','error','-nostdin','-y','-f','concat','-safe','0','-i',str(playlist),
             '-map','0:v:0','-an','-c:v','copy','-map_metadata','-1',str(output)],log)
    verify_video(output,sum(count for _,count in segments),fps,0)
    return output


def apply(part_name,patch_files,remove_ids=(),base=BASE):
    # Independent calendar/shell/visual-QA runners may reach the same finished
    # chunk. Serialize the entire read/merge/render/commit transaction so a
    # later repair always includes all already committed anonymous regions.
    if not re.fullmatch(r'part-\d{2}',part_name):
        raise ValueError('Part must identify a generated chunk')
    directory=Path(base)/'chunks'/part_name
    if not directory.is_dir():
        raise ValueError('Repair requires an existing completed chunk')
    with open(directory/'repair.lock','a') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        try:
            return _apply_locked(part_name,patch_files,remove_ids,Path(base))
        finally:
            fcntl.flock(lock.fileno(),fcntl.LOCK_UN)


def _apply_locked(part_name,patch_files,remove_ids=(),base=BASE):
    begin=time.monotonic()
    manifest=json.loads((base/'manifest.json').read_text())
    part=next((p for p in manifest['parts'] if p['name']==part_name),None)
    if part is None or not re.fullmatch(r'part-\d{2}',part_name):
        raise ValueError('Part must identify a generated chunk from the manifest')
    if part['start_frame'] < manifest['approved_first_frames']:
        raise ValueError('Approved first-five-minute material is not a writable chunk')
    dest=base/'chunks'/part_name
    video,report_path,complete_path=dest/'redacted.mp4',dest/'report.json',dest/'complete.json'
    if not all(path.is_file() for path in (video,report_path,complete_path)):
        raise ValueError('Repair requires a finished chunk')
    source=Path(manifest['source'])
    source_state=(source.stat().st_size,source.stat().st_mtime_ns)
    if source_state != (manifest['source_size'],manifest['source_mtime_ns']):
        raise ValueError('Original source changed since the manifest was recorded')
    report=json.loads(report_path.read_text())
    if report.get('status')!='complete' or report.get('processed_frames')!=part['frames']:
        raise ValueError('Chunk report is not complete')
    patches=[]
    for path in patch_files:
        data=Path(path).read_bytes()
        patches.append((Path(path).name,hashlib.sha256(data).hexdigest(),json.loads(data)))
    merged,changed,stats=merge_report(report,part,patches,remove_ids)
    if not changed:
        result={'part':part_name,'status':'unchanged',**stats}
        print(json.dumps(result,ensure_ascii=False),flush=True)
        return result
    fps=float(report['fps']);total=part['frames']
    original_info=verify_video(video,total,fps)
    audio_count=sum(s['codec_type']=='audio' for s in original_info['streams'])
    keys=keyframe_boundaries(video,total,fps)
    windows=repair_windows(changed,keys,total)
    left,right=windows[0][0],windows[-1][1]
    backup=base/'patch-backups'/part_name/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'))
    backup.mkdir(parents=True)
    for path in (video,report_path,complete_path):shutil.copy2(path,backup/path.name)
    log=backup/'repair.log'
    print(json.dumps({'part':part_name,'stage':'staging','local_window':[left,right],
                      'global_window':[part['start_frame']+left,part['start_frame']+right],
                      'local_windows':windows,'rendered_frames':sum(z-a for a,z in windows),**stats}),flush=True)
    with tempfile.TemporaryDirectory(prefix='repair-stage-',dir=base) as td:
        scratch=Path(td)
        mode='keyframe_windows'
        rendered=[]
        for ordinal,(window_left,window_right) in enumerate(windows):
            middle=scratch/f'window-{ordinal:03}.mp4'
            encode_window(source,part,merged,window_left,window_right,middle,log)
            rendered.append((window_left,window_right,middle))
        segments=[]
        try:
            cursor=0
            for ordinal,(window_left,window_right,middle) in enumerate(rendered):
                if cursor<window_left:
                    gap=scratch/f'copy-{ordinal:03}.mp4'
                    copy_video_segment(video,cursor,window_left-cursor,fps,gap,log)
                    segments.append((gap,window_left-cursor))
                segments.append((middle,window_right-window_left))
                cursor=window_right
            if cursor<total:
                suffix=scratch/'suffix.mp4'
                copy_video_segment(video,cursor,total-cursor,fps,suffix,log)
                segments.append((suffix,total-cursor))
            joined=concat_video(segments,fps,scratch,log)
        except RuntimeError:
            # Preserve correctness if this file's B-frame copy boundaries cannot
            # represent the exact presentation frame set. Never repeat OCR.
            mode='whole_chunk_fallback'
            left,right=0,total
            windows=[[0,total]]
            joined=scratch/'whole-video.mp4'
            encode_window(source,part,merged,left,right,joined,log)
        staged_video=scratch/'redacted.mp4'
        execute(['ffmpeg','-v','error','-nostdin','-y','-i',str(joined),'-i',str(video),
                 '-map','0:v:0','-map','1:a?','-c','copy','-map_metadata','-1','-map_chapters','-1',
                 '-movflags','+faststart',str(staged_video)],log)
        verified=verify_video(staged_video,total,fps,audio_count)
        if any(s['codec_name']!='aac' for s in verified['streams'] if s['codec_type']=='audio'):
            raise RuntimeError('Original chunk audio is not AAC')
        audio_before=subprocess.check_output(['ffmpeg','-v','error','-i',str(video),'-map','0:a?',
                                             '-c','copy','-f','streamhash','-hash','sha256','pipe:1'])
        audio_after=subprocess.check_output(['ffmpeg','-v','error','-i',str(staged_video),'-map','0:a?',
                                            '-c','copy','-f','streamhash','-hash','sha256','pipe:1'])
        if audio_before!=audio_after:raise RuntimeError('AAC packet content changed while copying original audio')
        if abs(float(verified['format']['duration'])-total/fps)>.002:
            raise RuntimeError('Final container duration differs from the chunk timeline')
        if (source.stat().st_size,source.stat().st_mtime_ns)!=source_state:
            raise RuntimeError('Source changed during repair')
        evidence={**stats,'mode':mode,'local_render_window':[left,right],
                  'global_render_window':[part['start_frame']+left,part['start_frame']+right],
                  'local_render_windows':windows,
                  'global_render_windows':[[part['start_frame']+a,part['start_frame']+z]for a,z in windows],
                  'rendered_frames':sum(z-a for a,z in windows),'backup':str(backup),
                  'verification':{'frames':total,'duration':total/fps,'packet_pts':'passed','aac_packet_hash':'passed'},
                  'elapsed_seconds':round(time.monotonic()-begin,2)}
        merged.setdefault('review_repairs',[]).append(evidence)
        complete=json.loads(complete_path.read_text())
        complete.update(masked_frames=merged['masked_frames'],review_repairs=len(merged['review_repairs']))
        staged_report,staged_complete=scratch/'report.json',scratch/'complete.json'
        write_json(staged_report,merged);write_json(staged_complete,complete)
        # Remove the completion marker only for the brief commit interval. A
        # interrupted commit is recoverable from the verified baseline backup.
        qa_marker=dest/'qa-complete.json'
        if qa_marker.exists():
            shutil.copy2(qa_marker,backup/qa_marker.name)
        complete_path.unlink()
        qa_marker.unlink(missing_ok=True)
        try:
            os.replace(staged_video,video)
            os.replace(staged_report,report_path)
            os.replace(staged_complete,complete_path)
        except BaseException:
            for path in (video,report_path,complete_path):shutil.copy2(backup/path.name,path)
            if (backup/qa_marker.name).exists():shutil.copy2(backup/qa_marker.name,qa_marker)
            raise
        write_json(backup/'repair-result.json',evidence)
        result={'part':part_name,'status':'patched',**evidence}
        print(json.dumps(result,ensure_ascii=False),flush=True)
        return result


class MergeTests(unittest.TestCase):
    def baseline(self):
        report={'fps':30,'width':100,'height':50,'frames':[
            {'frame':0,'boxes':[[1,1,4,4]],'origins':['ocr'],'regions':[{'id':'U001'}]},
            {'frame':1,'boxes':[],'origins':[],'regions':[]},
            {'frame':2,'boxes':[],'origins':[],'regions':[]}], 'masked_frames':1}
        part={'start_frame':9000,'start_seconds':300,'frames':3}
        return report,part
    def test_global_to_local_namespaces_deltas_and_no_source_mutation(self):
        original,part=self.baseline();before=copy.deepcopy(original)
        patch={'frames':{'8999':[{'id':'U001','box':[2,2,2,2]}],
                         '9001':[{'id':'U001','box':[10,10,6,6],'origin':'review','confidence':.9}],
                         '9003':[{'id':'U001','box':[2,2,2,2]}]}}
        merged,changed,stats=merge_report(original,part,[('qa.json','a'*64,patch)])
        self.assertEqual(original,before);self.assertEqual(changed,[1])
        self.assertEqual(stats['new_masked_frames'],1);self.assertEqual(merged['masked_frames'],2)
        self.assertEqual(merged['frames'][1]['regions'][0]['id'],'R'+('a'*12)+':U001')
        self.assertNotIn('box',merged['frames'][1]['regions'][0])
        self.assertEqual(merged['frames'][1]['regions'][0]['ocr_confidence'],.9)
    def test_removal_keeps_parallel_arrays_aligned_and_extends_window(self):
        report,part=self.baseline();report['frames'][0]['boxes'].append([10,10,4,4])
        report['frames'][0]['origins'].append('tracked');report['frames'][0]['regions'].append({'id':'U002'})
        merged,changed,stats=merge_report(report,part,[],['U001'])
        self.assertEqual(merged['frames'][0]['boxes'],[[10,10,4,4]])
        self.assertEqual(merged['frames'][0]['origins'],['tracked'])
        self.assertEqual(merged['frames'][0]['regions'],[{'id':'U002'}])
        self.assertEqual(changed,[0]);self.assertEqual(stats['removed_regions'],1)
    def test_removed_masked_frame_is_not_a_negative_added_count(self):
        report,part=self.baseline()
        _,_,stats=merge_report(report,part,[],['U001'])
        self.assertEqual(stats['new_masked_frames'],0)
        self.assertEqual(stats['removed_masked_frames'],1)
        self.assertEqual(stats['masked_frames_delta'],-1)
    def test_duplicate_application_is_idempotent(self):
        report,part=self.baseline();patch={'frames':{'9001':[{'id':'C001','box':[10,10,6,6]}]}}
        patches=[('qa.json','b'*64,patch)]
        first,_,_=merge_report(report,part,patches)
        second,changed,stats=merge_report(first,part,patches)
        self.assertEqual(changed,[]);self.assertEqual(stats['added_regions'],0)
        self.assertEqual(stats['duplicate_regions_skipped'],1);self.assertEqual(second,first)
    def test_multiple_patch_namespaces_do_not_collide(self):
        report,part=self.baseline();patch={'frames':{'9001':[{'id':'C001','box':[10,10,6,6]}]}}
        merged,_,stats=merge_report(report,part,[('qa1.json','a'*64,patch),('qa2.json','b'*64,patch)])
        self.assertEqual(stats['added_regions'],2)
        self.assertEqual(len({r['id'] for r in merged['frames'][1]['regions']}),2)
    def test_invalid_alignment_rejected(self):
        report,part=self.baseline();report['frames'][0]['regions']=[]
        with self.assertRaises(ValueError):merge_report(report,part,[])
    def test_keyframe_window_covers_removals_additions_and_eof(self):
        self.assertEqual(repair_window([7,8],[0,5,10],12),(5,10))
        self.assertEqual(repair_window([1,11],[0,5,10],12),(0,12))
    def test_multiple_keyframe_windows_keep_untouched_gap_copyable(self):
        self.assertEqual(repair_windows([1,2,3,21,22],[0,5,10,15,20,25],30),[[0,5],[20,25]])
    def test_adjacent_keyframe_windows_merge_but_do_not_fill_distant_gaps(self):
        self.assertEqual(repair_windows([6,11,26],[0,5,10,15,20,25],30),[[5,15],[25,30]])
    def test_frame_on_boundary_selects_next_gop_and_eof_is_covered(self):
        self.assertEqual(repair_windows([10,29],[0,5,10,15,20,25],30),[[10,15],[25,30]])
        self.assertEqual(repair_windows([], [0,5,10],15),[])
        with self.assertRaises(ValueError):repair_windows([30],[0,5,10],30)
    def test_two_repair_runners_cannot_overwrite_each_others_committed_state(self):
        from concurrent.futures import ThreadPoolExecutor
        original=globals()['_apply_locked']
        with tempfile.TemporaryDirectory(prefix='repair-lock-test-',dir=BASE) as td:
            base=Path(td)
            (base/'chunks/part-01').mkdir(parents=True)
            state=base/'state.json';write_json(state,[])
            def transaction(part_name,patch_files,remove_ids,base):
                committed=json.loads(state.read_text())
                time.sleep(.02)
                committed.append(patch_files[0])
                write_json(state,committed)
            globals()['_apply_locked']=transaction
            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results=[pool.submit(apply,'part-01',[name],base=base) for name in ['shell','calendar']]
                    for result in results:result.result()
                self.assertEqual(sorted(json.loads(state.read_text())),['calendar','shell'])
            finally:
                globals()['_apply_locked']=original
    def test_reviewed_white_caption_restored_without_exposing_yellow_uri(self):
        hsv=np.full((30,30,3),(25,200,230),np.uint8)
        hsv[10:15,10:15]=(0,0,240)
        frame=cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR);before=frame.copy()
        out=render_mask(frame,{'boxes':[[0,0,30,30]],'regions':[{'preserve_white_caption':True}]})
        self.assertTrue(np.array_equal(out[10:15,10:15],frame[10:15,10:15]))
        self.assertTrue(np.all(out[:5,:5]==112))
        self.assertTrue(np.array_equal(frame,before))
        default=render_mask(frame,{'boxes':[[0,0,30,30]],'regions':[{}]})
        self.assertTrue(np.all(default==112))

    def test_orange_caption_preservation_does_not_modify_source(self):
        hsv=np.full((8,8,3),(15,220,220),np.uint8)
        frame=cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR);before=frame.copy()
        result=render_mask(frame,{'boxes':[[0,0,8,8]],'regions':[{'preserve_orange_caption':True}]})
        self.assertTrue(np.array_equal(frame,before));self.assertTrue(np.array_equal(result,frame))
        gray=render_mask(frame,{'boxes':[[0,0,8,8]],'regions':[{}]})
        self.assertTrue(np.all(gray==112))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('part',nargs='?')
    parser.add_argument('patches',nargs='*',type=Path)
    parser.add_argument('--remove-id',action='append',default=[])
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if args.self_test:
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(MergeTests))
        if not result.wasSuccessful():raise SystemExit(1)
        return
    if not args.part or not args.patches:parser.error('part and one or more patch JSON files are required')
    apply(args.part,args.patches,args.remove_id)


if __name__=='__main__':main()
