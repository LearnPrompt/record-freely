#!/usr/bin/env python3
"""Export actual local-mask jumps from a reviewed, anonymized CFR event manifest.

This is a selection index, not a detector or an independent privacy rescan.
All frame intervals are zero-based and half-open on the encoded output timeline.
"""
import argparse
import csv
from fractions import Fraction
import hashlib
import json
from pathlib import Path

ROLES = {'local_redaction', 'global_protection', 'ai_label', 'trusted_restoration', 'keep'}


def integer(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError('Frame positions must be integers')
    return value


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def build(manifest):
    fps = Fraction(str(manifest['fps']))
    n = integer(manifest['output_frames'])
    if not 0 < fps <= 120 or n <= 0:
        raise ValueError('Invalid CFR rate or frame count')
    sha = manifest['encoded_sha256']
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
        raise ValueError('An encoded-file SHA256 is required')
    cuts, removed, last = [], 0, 0
    for pair in manifest.get('source_cuts', []):
        a, b = map(integer, pair)
        if a < last or a < 0 or b <= a:
            raise ValueError('Source cuts must be sorted, disjoint, nonempty')
        boundary = a - removed
        if boundary > n:
            raise ValueError('Cut lies outside the source/output mapping')
        cuts.append((boundary, b - a))
        removed += b - a
        last = b
    if 'source_frames' in manifest and integer(manifest['source_frames']) != n + removed:
        raise ValueError('Source/output frame counts disagree with cuts')

    def source(frame):
        return frame + sum(length for boundary, length in cuts if boundary <= frame)

    selected, excluded = [], {role: 0 for role in sorted(ROLES - {'local_redaction'})}
    boundaries = {a for a, _ in cuts}
    local_count = 0
    for index, event in enumerate(manifest['events']):
        role = event['role']
        if role not in ROLES:
            raise ValueError('Unknown role; assign every event after reviewing it')
        a, b = integer(event['start_frame']), integer(event['end_frame'])
        if not 0 <= a < b <= n:
            raise ValueError('Event lies outside encoded output')
        if role != 'local_redaction':
            excluded[role] += 1
            continue
        local_count += 1
        # A source cut is a discontinuity even when both output frames touch.
        edges = [a] + sorted(c for c in boundaries if a < c < b) + [b]
        selected.extend((x, y, index) for x, y in zip(edges, edges[1:]))
    merged = []
    for a, b, index in sorted(selected):
        if merged and a <= merged[-1]['end_frame'] and not (a in boundaries and a == merged[-1]['end_frame']):
            merged[-1]['end_frame'] = max(b, merged[-1]['end_frame'])
            merged[-1]['event_indices'].add(index)
        else:
            merged.append({'start_frame': a, 'end_frame': b, 'event_indices': {index}})
    for ordinal, row in enumerate(merged, 1):
        a, b = row['start_frame'], row['end_frame']
        row.update(ordinal=ordinal, start_seconds=float(a / fps), end_seconds=float(b / fps),
                   source_start_frame=source(a), source_end_frame=source(b - 1) + 1,
                   source_start_seconds=float(source(a) / fps),
                   source_end_seconds=float((source(b - 1) + 1) / fps))
        row['event_indices'] = sorted(row['event_indices'])
    return {'schema_version': 1, 'fps': str(fps), 'output_frames': n, 'encoded_sha256': sha,
            'frame_basis': 'encoded CFR, zero-based half-open; source cuts separately mapped',
            'scope': 'Reviewed local redactions only; not proof of all private content being detected',
            'local_event_count': local_count, 'excluded_event_counts': excluded,
            'masked_frames': sum(r['end_frame'] - r['start_frame'] for r in merged),
            'intervals': merged}


def timestamp(seconds):
    milliseconds = round(seconds * 1000)
    return f'{milliseconds // 60000:02d}:{milliseconds // 1000 % 60:02d}.{milliseconds % 1000:03d}'


def export(data, destination):
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'timeline.json').write_text(json.dumps(data, indent=2) + '\n')
    with (destination / 'timeline.csv').open('w', newline='', encoding='utf-8-sig') as f:
        fields = ['ordinal', 'start_seconds', 'end_seconds', 'source_start_seconds',
                  'source_end_seconds', 'start_frame', 'end_frame', 'source_start_frame', 'source_end_frame']
        writer = csv.DictWriter(f, fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(data['intervals'])
    lines = ['# Actual local redaction intervals', '', data['scope'], '',
             '| # | Encoded video | Source |', '| --- | --- | --- |']
    lines += [f"| {r['ordinal']} | {timestamp(r['start_seconds'])}–{timestamp(r['end_seconds'])} | "
              f"{timestamp(r['source_start_seconds'])}–{timestamp(r['source_end_seconds'])} |"
              for r in data['intervals']]
    (destination / 'timeline.md').write_text('\n'.join(lines) + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--video', type=Path, help='Verify the actual encoded file SHA before exporting')
    args = parser.parse_args(argv)
    data = build(json.loads(args.manifest.read_text()))
    data['manifest_sha256'] = digest(args.manifest)
    data['video_sha_verified'] = False
    if args.video:
        if digest(args.video) != data['encoded_sha256']:
            raise ValueError('Encoded video SHA256 differs; select the reviewed version')
        data['video_sha_verified'] = True
    export(data, args.output_dir)
    print(json.dumps({'interval_count': len(data['intervals']), 'masked_frames': data['masked_frames'],
                      'video_sha_verified': data['video_sha_verified']}))


if __name__ == '__main__':
    main()
