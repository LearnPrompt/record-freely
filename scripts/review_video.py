#!/usr/bin/env python3
"""Independent local rescan of an encoded video; never alter or upload media."""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import subprocess
import tempfile

import cv2
import numpy as np

from redact_video import clamp, file_sha256, probe
from review_candidates import observation_candidates
from speech_review import review_audio, review_subtitle


class ReviewOCR:
    def __init__(self, scratch, privacy=False):
        self.privacy = privacy
        binary = Path(scratch) / 'review-ocr'
        result = subprocess.run(['xcrun', 'swiftc', '-O', str(Path(__file__).with_name('review_ocr.swift')),
                                 '-o', str(binary)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode:
            raise RuntimeError('vision_compile_failed')
        self.process = subprocess.Popen([str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.image = Path(scratch) / 'frame.png'

    def read(self, frame):
        if not cv2.imwrite(str(self.image), frame):
            raise RuntimeError('frame_write_failed')
        self.process.stdin.write(json.dumps({'path': str(self.image), 'privacy': self.privacy}) + '\n')
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError('vision_worker_exited')
        result = json.loads(line)
        if 'error' in result:
            raise RuntimeError('vision_frame_failed')
        return result

    def close(self):
        try:
            self.process.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process.stdout.close()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--redaction-report', type=Path, help='Optional report whose output SHA256 must match this encoded video')
    parser.add_argument('--privacy', action='store_true', help='Also check email, telephone, QR and identity paths')
    parser.add_argument('--detect-every', type=int, default=1, metavar='N', help='OCR every N normalized frames; default every frame')
    parser.add_argument('--start', type=float, default=0.)
    parser.add_argument('--duration', type=float)
    parser.add_argument('--asr-model', type=Path, help='Existing local whisper.cpp model; never downloaded')
    parser.add_argument('--subtitle', type=Path, action='append', default=[],
                        help='Local SRT on the source normalized timeline; repeat for independent sources')
    args = parser.parse_args(argv)
    if args.detect_every < 1:
        parser.error('--detect-every must be positive')
    if not math.isfinite(args.start) or args.start < 0:
        parser.error('--start must be finite and nonnegative')
    if args.duration is not None and (not math.isfinite(args.duration) or args.duration <= 0):
        parser.error('--duration must be finite and positive')
    return args


def video_spec(metadata, start, duration=None):
    video = next((s for s in metadata['streams'] if s.get('codec_type') == 'video' and not s.get('disposition',{}).get('attached_pic')), None)
    if not video:
        raise ValueError('video_stream_missing')
    fps = 0.
    for value in (video.get('avg_frame_rate'), video.get('r_frame_rate')):
        try:
            candidate = float(Fraction(value or '0/1'))
        except (ValueError, ZeroDivisionError):
            continue
        if math.isfinite(candidate) and candidate > 0:
            fps = candidate
            break
    if fps <= 0:
        raise ValueError('invalid_video_rate')
    total = float(video.get('duration') or metadata.get('format', {}).get('duration') or 0.)
    if not math.isfinite(total) or total <= start:
        raise ValueError('window_outside_video')
    window = min(total - start, duration) if duration is not None else total - start
    first = math.ceil(start * fps - 1e-8)
    last = math.ceil((start + window) * fps - 1e-8)
    return {'width': int(video['width']), 'height': int(video['height']), 'fps': fps,
            'stream_index': int(video['index']), 'origin': float(video.get('start_time') or 0.),
            'source_duration': total, 'start': start, 'duration': window,
            'first_source_frame': first, 'end_source_frame_exclusive': last}


def decoder_command(source, spec):
    # Normalize FIRST, then select normalized source frame numbers. Resetting PTS
    # after a time trim otherwise shifts non-frame-aligned start timestamps.
    filters = (f"setpts=PTS-STARTPTS,fps={spec['fps']:.12f},"
               f"trim=start_frame={spec['first_source_frame']}:end_frame={spec['end_source_frame_exclusive']},"
               'setpts=PTS-STARTPTS')
    return ['ffmpeg', '-v', 'error', '-nostdin', '-reinit_filter', '0', '-i', str(source),
            '-map', f"0:{spec['stream_index']}", '-an', '-sn', '-vf', filters,
            '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'bgr24', 'pipe:1']


def read_frame(pipe, size):
    parts, remaining = [], size
    while remaining:
        chunk = pipe.read(remaining)
        if not chunk:
            break
        parts.append(chunk)
        remaining -= len(chunk)
    return b''.join(parts)


def frame_findings(result, width, height, privacy=False):
    candidates = observation_candidates(result.get('observations', []), width, height, padding=4, privacy=privacy)
    findings = [{key: candidate[key] for key in ('kind', 'status', 'reason', 'box', 'confidence', 'box_method') if key in candidate}
                for candidate in candidates]
    if privacy:
        for code in result.get('barcodes', []):
            x, y, w, h = code['box']
            box = clamp([x * width - 4, y * height - 4, w * width + 8, h * height + 8], width, height)
            if box[2] > 0 and box[3] > 0:
                findings.append({'kind': 'qr_code', 'status': 'needs_review', 'reason': 'qr_payload_not_retained',
                                 'box': box, 'confidence': float(code.get('confidence', 0.))})
    return findings


def scan_visual(source, spec, scratch, *, detect_every=1, privacy=False, ocr_factory=ReviewOCR):
    coverage = {'status': 'failed', 'result': 'failed', 'mode': 'every_frame' if detect_every == 1 else 'sampled',
                'timeline': 'CFR_source_normalized_seconds', 'normalized_fps': spec['fps'],
                'window_start': spec['start'], 'window_duration': spec['duration'],
                'first_source_frame': spec['first_source_frame'],
                'end_source_frame_exclusive': spec['end_source_frame_exclusive'],
                'detect_every': detect_every, 'nominal_sample_interval_seconds': detect_every / spec['fps'],
                'decoded_frames': 0, 'checked_frames': 0, 'failed_frames': 0, 'skipped_frames': 0,
                'failure_frames': [], 'first_checked_time': None, 'last_checked_time': None,
                'findings': [], 'qr_status': 'requested' if privacy else 'not_checked'}
    worker = decoder = None
    try:
        worker = ocr_factory(scratch, privacy=privacy)
        decoder = subprocess.Popen(decoder_command(source, spec), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        size = spec['width'] * spec['height'] * 3
        while True:
            data = read_frame(decoder.stdout, size)
            if not data:
                break
            if len(data) != size:
                coverage['failure_code'] = 'truncated_decoded_frame'
                break
            index = coverage['decoded_frames']
            coverage['decoded_frames'] += 1
            if index % detect_every:
                coverage['skipped_frames'] += 1
                continue
            source_index = spec['first_source_frame'] + index
            timestamp = source_index / spec['fps']
            frame = np.frombuffer(data, dtype=np.uint8).reshape(spec['height'], spec['width'], 3)
            try:
                findings = frame_findings(worker.read(frame), spec['width'], spec['height'], privacy=privacy)
                coverage['checked_frames'] += 1
                if coverage['first_checked_time'] is None:
                    coverage['first_checked_time'] = timestamp
                coverage['last_checked_time'] = timestamp
                for finding in findings:
                    coverage['findings'].append(dict(finding, frame=index, source_normalized_frame=source_index,
                                                     time=timestamp, channel='visual'))
            except (RuntimeError, OSError, ValueError, KeyError, TypeError):
                coverage['failed_frames'] += 1
                coverage['failure_frames'].append({'frame': index, 'source_normalized_frame': source_index,
                                                    'time': timestamp, 'reason': 'ocr_frame_failed'})
        if decoder.wait() != 0:
            coverage['failure_code'] = 'video_decode_failed'
        expected = spec['end_source_frame_exclusive'] - spec['first_source_frame']
        coverage['expected_normalized_frames'] = expected
        if not coverage['decoded_frames'] or coverage['decoded_frames'] != expected:
            coverage.setdefault('failure_code', 'decoded_coverage_incomplete')
        if coverage['failed_frames']:
            coverage.setdefault('failure_code', 'ocr_coverage_incomplete')
        if 'failure_code' not in coverage:
            coverage['status'] = 'checked'
            coverage['result'] = 'hits' if coverage['findings'] else 'no_hits'
            if privacy:
                coverage['qr_status'] = 'checked'
        elif privacy:
            coverage['qr_status'] = 'incomplete'
    except (RuntimeError, OSError, ValueError, KeyError, TypeError):
        coverage['failure_code'] = 'visual_review_failed'
        if privacy:
            coverage['qr_status'] = 'failed'
    finally:
        if decoder is not None:
            decoder.stdout.close()
            if decoder.poll() is None:
                decoder.terminate()
                decoder.wait()
        if worker is not None:
            worker.close()
    return coverage


def review(args):
    source = args.input.resolve()
    output = args.output_dir.resolve()
    if not source.is_file():
        raise RuntimeError('Input must be an existing local file')
    if output.exists():
        raise RuntimeError('Output directory already exists; use a new directory')
    if output == source or source in output.parents:
        raise RuntimeError('Output must not overwrite input')
    source_hash = file_sha256(source)
    binding = None
    if getattr(args,'redaction_report',None) is not None:
        try:
            binding_bytes = args.redaction_report.read_bytes()
            binding_report = json.loads(binding_bytes)
            expected_hash = binding_report.get('output_sha256')
            if binding_report.get('status') != 'complete' or expected_hash != source_hash:
                raise ValueError('output_hash_mismatch')
        except (OSError,ValueError,TypeError,AttributeError):
            raise RuntimeError('Redaction report does not bind this encoded video; use its matching final report') from None
        import hashlib
        binding = {'redaction_report_sha256':hashlib.sha256(binding_bytes).hexdigest(),
                   'encoded_output_sha256_match': True}
    output.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'record-freely-review/v1', 'status': 'failed',
              'source': {'sha256': source_hash, 'size_bytes': source.stat().st_size},
              'privacy_requested': args.privacy, 'media_modified': False, 'uploaded': False,
              'redaction_binding': binding,
              'limitations': ['OCR and ASR can miss or misrecognize content',
                              'No zero-leak guarantee or platform approval prediction',
                              'Sampling can miss short flashes; CFR duplicates/drops source VFR frames'],
              'visual': {'status': 'not_checked', 'result': 'not_checked', 'findings': []},
              'audio': {'status': 'not_checked', 'streams_total': None, 'tracks': []},
              'subtitle': {'status': 'not_checked', 'result': 'not_checked', 'findings': []}}
    try:
        metadata = probe(source)
        spec = video_spec(metadata, args.start, args.duration)
        report['video'] = {key: spec[key] for key in ('width', 'height', 'fps', 'source_duration')}
        with tempfile.TemporaryDirectory(prefix='local-review-') as temporary:
            report['visual'] = scan_visual(source, spec, Path(temporary), detect_every=args.detect_every, privacy=args.privacy)
            audio_streams = [s for s in metadata['streams'] if s.get('codec_type') == 'audio']
            report['audio'] = review_audio(source, audio_streams, video_origin=spec['origin'], start=spec['start'],
                                          duration=spec['duration'], model=args.asr_model, privacy=args.privacy,
                                          scratch_parent=temporary)
            if args.subtitle:
                sources = []
                for index, path in enumerate(args.subtitle, 1):
                    row = review_subtitle(path, start=spec['start'], duration=spec['duration'], privacy=args.privacy)
                    row['source_id'] = f'S{index:04d}'
                    for finding in row['findings']:
                        finding['subtitle_source_id'] = row['source_id']
                    sources.append(row)
                subtitle_findings = [finding for row in sources for finding in row['findings']]
                failed = sum(row['status'] == 'failed' for row in sources)
                report['subtitle'] = {'status': 'failed' if failed else 'checked',
                                      'result': 'failed' if failed else 'hits' if subtitle_findings else 'no_hits',
                                      'sources_total': len(sources), 'sources_checked': len(sources) - failed,
                                      'sources_failed': failed, 'sources': sources, 'findings': subtitle_findings}
        failures = any(report[channel]['status'] == 'failed' for channel in ('visual', 'audio', 'subtitle'))
        report['status'] = 'partial' if failures else 'complete'
    except (RuntimeError, OSError, ValueError, KeyError, StopIteration):
        report['failure_code'] = 'review_setup_failed'
    report['source']['unchanged'] = file_sha256(source) == source_hash
    if not report['source']['unchanged']:
        report['status'] = 'failed'
        report['failure_code'] = 'source_changed_during_review'
    findings = list(report['visual'].get('findings', [])) + list(report['subtitle'].get('findings', []))
    for track in report['audio'].get('tracks', []):
        findings.extend(track.get('findings', []))
    pending = [row for row in findings if row['status'] != 'keep']
    report['pending_review'] = [dict(row, id=f'R{index:06d}') for index, row in enumerate(pending, 1)]
    uninspected = any(report[channel]['status'] in ('not_checked', 'failed') for channel in ('visual', 'audio', 'subtitle'))
    report['coverage_status'] = 'partial' if uninspected or args.detect_every > 1 else 'checked'
    report['acceptance'] = 'needs_review' if pending else 'not_verified'
    (output / 'review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    report = review(parse_args())
    print(f"Local review: {report['status']}; {len(report['pending_review'])} anonymous candidates")
    return 0 if report['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
