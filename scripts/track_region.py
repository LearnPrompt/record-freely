#!/usr/bin/env python3
"""Source-bound bidirectional LK/RANSAC polygon proposals; never bridge failure gaps."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np

from background_masks import geometry_mask
from redact_video import file_sha256, probe
from refine_video import read_exact


def track_step(previous, current, polygon, *, context=40, max_fb_error=1.5):
    """Return (polygon or None, evidence), rejecting unsupported movement."""
    h, w = previous.shape
    region, (x, y, bw, bh) = geometry_mask({'polygon': np.rint(polygon).astype(int).tolist()}, w, h)
    support = np.zeros((h, w), np.uint8)
    support[max(0, y-context):min(h, y+bh+context), max(0, x-context):min(w, x+bw+context)] = 255
    points = cv2.goodFeaturesToTrack(previous, maxCorners=240, qualityLevel=.01, minDistance=3, mask=support)
    if points is None or len(points) < 8:
        return None, {'reason': 'few_features'}
    forward, status, _ = cv2.calcOpticalFlowPyrLK(previous, current, points, None, winSize=(21, 21), maxLevel=3)
    if forward is None:
        return None, {'reason': 'no_forward_flow'}
    backward, back_status, _ = cv2.calcOpticalFlowPyrLK(current, previous, forward, None, winSize=(21, 21), maxLevel=3)
    if backward is None:
        return None, {'reason': 'no_backward_flow'}
    fb = np.linalg.norm(points[:, 0]-backward[:, 0], axis=1)
    valid = (status[:, 0] > 0) & (back_status[:, 0] > 0) & np.isfinite(fb) & (fb <= max_fb_error)
    if valid.sum() < 8:
        return None, {'reason': 'few_consistent_tracks', 'consistent_tracks': int(valid.sum())}
    matrix, inliers = cv2.findHomography(points[valid], forward[valid], cv2.RANSAC, 2.)
    if matrix is None or inliers is None or inliers.sum() < 8 or inliers.mean() < .6:
        return None, {'reason': 'no_supported_homography'}
    # Homography is needed for oblique handheld surfaces; no rectangle enlargement.
    result = cv2.perspectiveTransform(np.asarray(polygon, np.float32).reshape(1, -1, 2), matrix)[0]
    if not np.isfinite(result).all():
        return None, {'reason': 'nonfinite_transform'}
    area_ratio = abs(cv2.contourArea(result))/max(1., abs(cv2.contourArea(np.asarray(polygon, np.float32))))
    max_move = float(np.linalg.norm(result-np.asarray(polygon), axis=1).max())
    if not .5 <= area_ratio <= 2 or max_move > max(32., min(w, h)*.15):
        return None, {'reason': 'implausible_step', 'area_ratio': area_ratio, 'max_move': max_move}
    try:
        geometry_mask({'polygon': np.rint(result).astype(int).tolist()}, w, h)
    except ValueError:
        return None, {'reason': 'outside_or_degenerate_geometry'}
    return result, {'reason': 'observed_flow', 'consistent_tracks': int(valid.sum()), 'inliers': int(inliers.sum()),
                    'inlier_ratio': float(inliers.mean()), 'fb_max': float(fb[valid].max()), 'area_ratio': area_ratio}


def track_frames(frames, anchors, *, start_frame=0, scene_cuts=(), context=40):
    """Nearest anchored proposals in each direction; failed chains stop immediately."""
    end_frame = start_frame+len(frames)
    if type(start_frame) is not int or start_frame < 0 or type(context) is not int or not 0 <= context <= 512:
        raise ValueError('Invalid source frame/context')
    if any(type(c) is not int or not start_frame <= c < end_frame for c in scene_cuts):
        raise ValueError('Scene cuts must be source-frame indices in the selected range')
    cuts = set(scene_cuts)
    if not frames or not anchors:
        raise ValueError('Frames and explicit manual anchors are required')
    h, w = frames[0].shape
    accepted, evidence, failures, distances = {}, {}, [], {}
    for frame, polygon in sorted(anchors.items()):
        if type(frame) is not int or not start_frame <= frame < end_frame:
            raise ValueError('Anchor outside selected half-open source range')
        geometry_mask({'polygon': polygon}, w, h)
        accepted[frame], evidence[frame], distances[frame] = polygon, {'reason': 'human_anchor'}, 0
    for anchor, points in sorted(anchors.items()):
        for direction in (-1, 1):
            polygon = np.asarray(points, np.float32)
            previous = anchor
            for frame in range(anchor+direction, end_frame if direction == 1 else start_frame-1, direction):
                if max(frame, previous) in cuts:
                    failures.append({'frame': frame, 'anchor': anchor, 'reason': 'scene_cut'})
                    break
                if frame in anchors:
                    break
                result, meta = track_step(frames[previous-start_frame], frames[frame-start_frame], polygon, context=context)
                if result is None:
                    failures.append(dict(frame=frame, anchor=anchor, **meta))
                    break
                distance = abs(frame-anchor)
                if distance < distances.get(frame, float('inf')):
                    accepted[frame] = np.rint(result).astype(int).tolist()
                    evidence[frame], distances[frame] = dict(anchor=anchor, **meta), distance
                polygon, previous = result, frame
    gaps = [i for i in range(start_frame, end_frame) if i not in accepted]
    return accepted, evidence, failures, gaps


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('--anchors', type=Path, required=True, help='JSON source_sha256,start_frame,end_frame,anchors map,scene_cuts')
    p.add_argument('--output', type=Path, required=True, help='New reviewed-plan proposal JSON; human review is mandatory')
    p.add_argument('--context', type=int, default=40)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError('Output exists')
    spec = json.loads(args.anchors.read_text())
    source_hash = file_sha256(args.input)
    if spec.get('source_sha256') != source_hash:
        raise ValueError('Anchor source SHA256 mismatch')
    start, end = spec['start_frame'], spec['end_frame']
    if type(start) is not int or type(end) is not int or not 0 <= start < end or not 0 <= args.context <= 512:
        raise ValueError('Invalid frame range/context')
    video = next(s for s in probe(args.input)['streams'] if s['codec_type'] == 'video')
    w, h = video['width'], video['height']
    if end-start > 18000 or (end-start)*w*h > 2_000_000_000:
        raise ValueError('Tracking window too large; split into bounded reviewed shots')
    command = ['ffmpeg', '-v', 'error', '-nostdin', '-i', str(args.input), '-map', f"0:{video['index']}", '-an',
               '-vf', f'trim=start_frame={start}:end_frame={end}', '-frames:v', str(end-start), '-vsync', '0', '-f', 'rawvideo', '-pix_fmt', 'gray', 'pipe:1']
    decoder = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    frames = []
    try:
        for _ in range(end-start):
            frames.append(np.frombuffer(read_exact(decoder.stdout, w*h), np.uint8).reshape(h, w).copy())
        decoder.stdout.close()
        if decoder.wait(timeout=10):
            raise RuntimeError('Tracking decoder failed')
    finally:
        if decoder.poll() is None:
            decoder.kill()
            decoder.wait()
    if not isinstance(spec.get('anchors'), dict) or any(not isinstance(k, str) or not k.isdecimal() or str(int(k)) != k for k in spec['anchors']):
        raise ValueError('Anchor keys must be canonical decimal source-frame strings')
    anchors = {int(k): v for k, v in spec['anchors'].items()}
    geometries, evidence, failures, gaps = track_frames(frames, anchors, start_frame=start,
                                                       scene_cuts=spec.get('scene_cuts', []), context=args.context)
    output = dict(version=1, source_sha256=source_hash, start_frame=start, end_frame=end,
                  scene_cuts=spec.get('scene_cuts', []), publication_review_required=True,
                  review_status='pending', pending_gaps=gaps, tracking_failures=failures,
                  tracking_evidence={str(k): v for k, v in evidence.items()},
                  regions=[dict(id=spec.get('id', 'reviewed-track'), start_frame=start, end_frame=end,
                                geometry_by_frame={str(k): {'polygon': v} for k, v in sorted(geometries.items())},
                                fill=spec.get('fill', {'mode': 'local'}))], overlays=[])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(json.dumps({'observed_frames': len(geometries), 'pending_frames': len(gaps), 'review_status': 'pending'}))


if __name__ == '__main__':
    main()
