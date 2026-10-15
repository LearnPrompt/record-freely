#!/usr/bin/env python3
"""Render approved source-frame masks and SHA-bound RGBA layers from original once."""
from __future__ import annotations
import argparse
import copy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

import cv2
import numpy as np
from PIL import Image

from background_masks import SurfaceFiller, geometry_mask, validate_fill
from encoding import add_encoding_arguments, encoding_config, video_encoding_options, verify_encoding
from redact_video import file_sha256, probe, run
from refine_video import read_exact, validate_report


def _range(spec, start, end):
    a, b = spec.get('start_frame'), spec.get('end_frame')
    if type(a) is not int or type(b) is not int or not start <= a < b <= end:
        raise ValueError('Expected source-frame half-open range inside selected window')
    return a, b


def _asset(base, path, digest):
    if not isinstance(path, str) or not path or Path(path).is_absolute():
        raise ValueError('Assets require relative paths')
    source = (base/path).resolve(strict=True)
    if not source.is_relative_to(base.resolve()):
        raise ValueError('Asset escapes patch directory')
    if not isinstance(digest, str) or len(digest) != 64 or file_sha256(source) != digest:
        raise ValueError('Asset SHA256 mismatch')
    return source


def load_plan(path, source_hash, width, height):
    """Validate all geometry before render; do not coerce corrupt plans."""
    if path.stat().st_size > 64*1024*1024:
        raise ValueError('Plan exceeds 64 MiB; split selected shots')
    raw = path.read_bytes()
    plan = json.loads(raw)
    if plan.get('version') != 1 or plan.get('source_sha256') != source_hash:
        raise ValueError('Plan version/source SHA256 mismatch')
    if plan.get('review_status') != 'approved' or plan.get('pending_gaps'):
        raise ValueError('Plan requires human approval and no unresolved tracking gaps')
    start, end = plan.get('start_frame'), plan.get('end_frame')
    if type(start) is not int or type(end) is not int or not 0 <= start < end:
        raise ValueError('Invalid selected source-frame half-open window')
    if not isinstance(plan.get('regions', []), list) or not isinstance(plan.get('overlays', []), list):
        raise ValueError('regions/overlays must be arrays')
    cuts = plan.get('scene_cuts', [])
    if not isinstance(cuts, list) or any(type(v) is not int or not start <= v < end for v in cuts):
        raise ValueError('Invalid source-frame scene cuts')
    assets = {}
    asset_bytes = 0
    def convert(g):
        nonlocal asset_bytes
        if not isinstance(g, dict):
            raise ValueError('geometry must be an object')
        if set(g) == {'mask_path', 'mask_sha256', 'box'}:
            key = (g['mask_path'], g['mask_sha256'])
            if key not in assets:
                source = _asset(path.parent, *key)
                with Image.open(source) as im:
                    if im.mode != 'L' or im.format != 'PNG':
                        raise ValueError('Bitmap geometry requires a single-channel L PNG')
                    if im.width*im.height > 16_777_216:
                        raise ValueError('Bitmap asset too large')
                    asset_bytes += im.width*im.height
                    if asset_bytes > 256*1024*1024:
                        raise ValueError('Bitmap asset cache exceeds 256 MiB; split shots')
                    assets[key] = np.asarray(im).copy()
            result = {'box': g['box'], 'bitmap': assets[key]}
        else:
            result = g
        geometry_mask(result, width, height)
        return result
    regions, seen = [], set()
    for spec in plan.get('regions', []):
        a, b = _range(spec, start, end)
        ident = spec.get('id')
        if not isinstance(ident, str) or not ident or ident in seen:
            raise ValueError('Region ids must be unique strings')
        seen.add(ident)
        if ('geometry' in spec) == ('geometry_by_frame' in spec):
            raise ValueError('Require geometry or complete geometry_by_frame, exclusively')
        validate_fill(spec.get('fill', {'mode': 'local'}), width, height)
        item = copy.copy(spec)
        if 'geometry' in spec:
            item['geometry'] = convert(spec['geometry'])
        else:
            rows = spec['geometry_by_frame']
            if not isinstance(rows, dict) or set(rows) != {str(i) for i in range(a, b)}:
                raise ValueError('Tracked geometry must cover every active source frame; no extension')
            item['geometry_by_frame'] = {k: convert(v) for k, v in rows.items()}
        regions.append(item)
    overlays = []
    overlay_cache = {}
    overlay_bytes = 0
    for spec in plan.get('overlays', []):
        _range(spec, start, end)
        key = (spec.get('path'), spec.get('sha256'))
        if key not in overlay_cache:
            source = _asset(path.parent, *key)
            with Image.open(source) as image:
                if image.mode != 'RGBA' or image.format != 'PNG':
                    raise ValueError('Trusted overlays must be explicit RGBA PNGs')
                if image.width*image.height > 16_777_216:
                    raise ValueError('Overlay asset too large')
                overlay_bytes += image.width*image.height*4
                if overlay_bytes > 256*1024*1024:
                    raise ValueError('Overlay asset cache exceeds 256 MiB; split shots')
                overlay_cache[key] = np.asarray(image).copy()
        pixels = overlay_cache[key]
        x, y = spec.get('x'), spec.get('y')
        oh, ow = pixels.shape[:2]
        if type(x) is not int or type(y) is not int or not 0 <= x < x+ow <= width or not 0 <= y < y+oh <= height:
            raise ValueError('Overlay outside source frame')
        overlays.append(dict(spec, pixels=pixels))
    return plan, regions, overlays, hashlib.sha256(raw).hexdigest()


def paint_frame(original, source_frame, regions, overlays, filler, *, scene_cut=False):
    active = []
    for spec in regions:
        if spec['start_frame'] <= source_frame < spec['end_frame']:
            geometry = spec.get('geometry')
            if geometry is None:
                geometry = spec['geometry_by_frame'][str(source_frame)]
            active.append(dict(id=spec['id'], geometry=geometry, fill=spec.get('fill', {'mode': 'local'}),
                               surface_segment=spec.get('surface_segment', 'default')))
    active_overlays = [spec for spec in overlays if spec['start_frame'] <= source_frame < spec['end_frame']]
    # An approved layer may erase sensitive source text. Its entire native canvas
    # is excluded, even at alpha-zero holes: do not borrow its underlying source
    # as supposedly safe surface colour for a nearby local/plane mask.
    overlay_exclusions = [{'box': [spec['x'], spec['y'], spec['pixels'].shape[1], spec['pixels'].shape[0]]}
                          for spec in active_overlays]
    output, audit = filler.apply(original, active, frame_index=source_frame, scene_cut=scene_cut,
                                 exclude_geometries=overlay_exclusions)
    height, width = original.shape[:2]
    allowed = np.zeros((height, width), bool)
    boxes, metadata = [], []
    for spec in active:
        mask, bounds = geometry_mask(spec['geometry'], width, height)
        allowed |= mask
        boxes.append(list(bounds))
        meta = {'id': spec['id'], 'kind': 'reviewed_surface', 'origin': 'human_review', 'preserve_review_bounds': True}
        if 'polygon' in spec['geometry']:
            meta['polygon'] = spec['geometry']['polygon']
        elif 'bitmap' in spec['geometry']:
            meta['geometry_kind'] = 'exact_bitmap_with_holes'
        metadata.append(meta)
    applied_overlays = []
    for spec in overlays:
        if spec['start_frame'] <= source_frame < spec['end_frame']:
            rgba, x, y = spec['pixels'], spec['x'], spec['y']
            h, w = rgba.shape[:2]
            alpha = rgba[:, :, 3:4].astype(float)/255
            roi = output[y:y+h, x:x+w]
            roi[:] = np.rint(rgba[:, :, :3][:, :, ::-1]*alpha+roi*(1-alpha)).clip(0, 255).astype(np.uint8)
            allowed[y:y+h, x:x+w] |= alpha[:, :, 0] > 0
            applied_overlays.append(spec['sha256'])
    unapproved = int(np.count_nonzero(np.any(output != original, axis=2) & ~allowed))
    if unapproved:
        raise RuntimeError('Pixels outside approved geometry/layers changed before encoding')
    return output, dict(boxes=boxes, regions=metadata, origins=['human_review']*len(boxes),
                        surface_audit=audit, overlay_sha256=applied_overlays, outside_changed_pixels=unapproved)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path, help='Original source, never an earlier encoded/redacted output')
    p.add_argument('--patch', type=Path, required=True, help='Approved SHA-bound source-frame plan v1')
    p.add_argument('--report', type=Path, help='Optional original automatic report: reviewed plan adds to its rectangles')
    p.add_argument('--output-dir', type=Path, required=True, help='New directory; existing versions remain intact')
    add_encoding_arguments(p)
    args = p.parse_args()
    started = time.monotonic()
    source = args.input.resolve(strict=True)
    if args.output_dir.exists():
        raise ValueError('Output directory exists')
    source_hash = file_sha256(source)
    signature = (source.stat().st_size, source.stat().st_mtime_ns)
    info = probe(source)
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    width, height = video['width'], video['height']
    fps_ratio = Fraction(video['avg_frame_rate'])
    if fps_ratio <= 0 or Fraction(video['r_frame_rate']) != fps_ratio:
        raise ValueError('Reviewed source-frame renderer requires CFR media; explicitly normalize VFR first')
    fps = float(fps_ratio)
    plan, regions, overlays, plan_hash = load_plan(args.patch, source_hash, width, height)
    start, end = plan['start_frame'], plan['end_frame']
    frame_count, duration = end-start, (end-start)/fps
    baseline_hash = None
    baseline = None
    if args.report:
        raw = args.report.read_bytes()
        baseline_hash = hashlib.sha256(raw).hexdigest()
        baseline = json.loads(raw)
        rw, rh, rfps = validate_report(baseline)
        if (rw, rh) != (width, height) or abs(rfps-fps) > 1e-7 or baseline.get('source_sha256') != source_hash:
            raise ValueError('Baseline report source geometry/SHA256 mismatch')
        base_start = round(baseline.get('start', 0)*fps)
        if abs(base_start-baseline.get('start', 0)*fps) > 1e-5 or start < base_start or end > base_start+len(baseline['frames']):
            raise ValueError('Selected window not covered by original baseline report')
        if plan.get('source_report_sha256') != baseline_hash:
            raise ValueError('Plan must bind source_report_sha256 when using baseline rectangles')
        validate_fill(plan.get('baseline_fill', {'mode': 'fixed', 'color_bgr': [110, 110, 110]}), width, height)
        for sf in range(start, end):
            for n, box in enumerate(baseline['frames'][sf-base_start]['boxes']):
                regions.append(dict(id=f'baseline-{sf}-{n}', start_frame=sf, end_frame=sf+1,
                                    geometry={'box': box}, fill=plan.get('baseline_fill', {'mode': 'fixed', 'color_bgr': [110, 110, 110]})))
    active_regions = {i: [] for i in range(start, end)}
    active_overlays = {i: [] for i in range(start, end)}
    for collection, index in ((regions, active_regions), (overlays, active_overlays)):
        for spec in collection:
            for sf in range(spec['start_frame'], spec['end_frame']):
                index[sf].append(spec)
    audio_count = sum(s['codec_type'] == 'audio' for s in info['streams'])
    report = dict(version=1, status='processing', source_sha256=source_hash,
                  source_video_stream=video['index'], width=width, height=height, fps=fps,
                  start=start/fps, start_frame=start, end_frame=end, processed_frames=frame_count,
                  reviewed_plan_sha256=plan_hash, refinement_baseline_sha256=baseline_hash,
                  source_signature={'size': signature[0], 'mtime_ns': signature[1]},
                  encoding=encoding_config(args), frames=[], scene_cuts=[v-start for v in plan.get('scene_cuts', [])],
                  acceptance='not_verified', publication_review_required=True)
    args.output_dir.mkdir(parents=True)
    decoder = encoder = None
    try:
        with tempfile.TemporaryDirectory(prefix='record-freely-reviewed-') as temp:
            scratch = Path(temp)
            decoder = subprocess.Popen(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(source), '-map', f"0:{video['index']}",
                                        '-an', '-vf', f'trim=start_frame={start}:end_frame={end}', '-frames:v', str(frame_count), '-vsync', '0',
                                        '-f', 'rawvideo', '-pix_fmt', 'bgr24', 'pipe:1'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            silent = scratch/'masked.mp4'
            encoder = subprocess.Popen(['ffmpeg', '-v', 'error', '-nostdin', '-n', '-f', 'rawvideo', '-pix_fmt', 'bgr24',
                                        '-s', f'{width}x{height}', '-r', str(fps_ratio), '-i', 'pipe:0', '-an',
                                        *video_encoding_options(args), '-map_metadata', '-1', str(silent)],
                                       stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            filler = SurfaceFiller()
            for sf in range(start, end):
                original = np.frombuffer(read_exact(decoder.stdout, width*height*3), np.uint8).reshape(height, width, 3)
                output, meta = paint_frame(original, sf, active_regions[sf], active_overlays[sf], filler, scene_cut=sf in plan.get('scene_cuts', []))
                report['frames'].append(dict(frame=sf-start, source_frame=sf, **meta))
                encoder.stdin.write(output.tobytes())
            decoder.stdout.close()
            encoder.stdin.close()
            if decoder.wait(timeout=30) or encoder.wait(timeout=120):
                raise RuntimeError('Decode/encode failed')
            final = scratch/'redacted.mp4'
            mux = ['ffmpeg', '-v', 'error', '-nostdin', '-n', '-i', str(silent), '-ss', str(start/fps), '-i', str(source),
                   '-map', '0:v:0', '-map', '1:a?', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k']
            if audio_count:
                mux += ['-af', f'aresample=48000:async=1:first_pts=0,apad=whole_dur={duration:.10f}']
            mux += ['-t', str(duration), '-map_metadata', '-1', '-map_chapters', '-1', '-movflags', '+faststart', str(final)]
            run(mux)
            exported = probe(final)
            out_video = next(s for s in exported['streams'] if s['codec_type'] == 'video')
            report['encoding_verification'] = verify_encoding(out_video, args)
            if (int(out_video.get('nb_frames', -1)) != frame_count or
                abs(float(out_video.get('duration', 0))-duration) > 1/fps+.005 or
                sum(s['codec_type'] == 'audio' for s in exported['streams']) != audio_count):
                raise RuntimeError('Export frame count/duration/audio streams mismatch')
            run(['ffmpeg', '-v', 'error', '-xerror', '-nostdin', '-i', str(final), '-f', 'null', '-'])
            if signature != (source.stat().st_size, source.stat().st_mtime_ns):
                raise RuntimeError('Source changed during rendering')
            shutil.copy2(final, args.output_dir/'redacted.mp4')
            report.update(status='complete', output_sha256=file_sha256(args.output_dir/'redacted.mp4'),
                          masked_frames=sum(bool(r['boxes']) for r in report['frames']),
                          elapsed_seconds=round(time.monotonic()-started, 3),
                          refinement_verification={'frame_count': True, 'duration': True, 'audio_stream_count': True,
                                                   'full_codec_decode': True, 'source_signature_unchanged': True,
                                                   'source_sha256_bound_before_render': True,
                                                   'outside_pixels_equal_before_encode': True})
    except BaseException as exc:
        report.update(status='failed', failure_type=type(exc).__name__)
        raise
    finally:
        for proc in (decoder, encoder):
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait()
        (args.output_dir/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: report[k] for k in ('status', 'processed_frames', 'masked_frames', 'elapsed_seconds')}))


if __name__ == '__main__':
    main()
