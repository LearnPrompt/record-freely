"""Export every v3 report-masked frame, with explicitly mapped gap context.

Input is an already rendered CFR film, not the original recording. Reports are
used only as an exhaustive selection index; this tool adds no new redaction.
Frame intervals are zero-based and half-open. No sampling or speed change.
"""
import argparse
import csv
import hashlib
import json
import math
import shutil
import subprocess
import time
import zipfile
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def runs(flags):
    result = []
    start = None
    for index, flag in enumerate(list(flags) + [False]):
        if flag and start is None:
            start = index
        if not flag and start is not None:
            result.append([start, index])
            start = None
    return result


def merge_runs(intervals, max_gap):
    if max_gap < 0:
        raise ValueError('Gap must be nonnegative')
    merged = []
    for start, end in intervals:
        if start >= end or (merged and start < merged[-1][1]):
            raise ValueError('Intervals must be sorted, nonempty and disjoint')
        if merged and start - merged[-1][1] <= max_gap:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return merged


def load_timeline(manifest, chunks):
    meta = json.loads(Path(manifest).read_text())
    flags, provenance = [], []
    fps = meta['fps']
    for part in meta['parts']:
        if part['start_frame'] != len(flags):
            raise ValueError('Chunk boundaries contain gaps or overlaps')
        path = Path(chunks) / part['name'] / 'report.json'
        report = json.loads(path.read_text())
        if report['status'] != 'complete' or report['fps'] != fps:
            raise ValueError('Incomplete report or differing frame rate')
        frames = report['frames']
        if len(frames) != part['frames']:
            raise ValueError('Report frame count disagrees with manifest')
        for i, frame in enumerate(frames):
            if frame['frame'] != i:
                raise ValueError('Frame indices are missing or out of order')
            if len(frame['boxes']) != len(frame['regions']):
                raise ValueError('Box/region alignment differs')
            flags.append(bool(frame['boxes']))
        provenance.append({'part': part['name'], 'start_frame': part['start_frame'],
                           'frames': part['frames'], 'report_sha256': digest(path),
                           'masked_frames': sum(bool(f['boxes']) for f in frames)})
    if len(flags) != meta['source_frames']:
        raise ValueError('Global frame count differs from manifest')
    return meta, flags, provenance


def make_catalog(flags, segments, fps):
    entries, offset = [], 0
    for number, (start, end) in enumerate(segments, 1):
        entries.append({'segment': number, 'source_start_frame': start,
                        'source_end_frame_exclusive': end, 'frames': end - start,
                        'source_start_seconds': start / fps,
                        'source_end_seconds_exclusive': end / fps,
                        'collection_start_frame': offset,
                        'collection_end_frame_exclusive': offset + end - start,
                        'masked_frames': sum(flags[start:end]),
                        'context_frames': end - start - sum(flags[start:end])})
        offset += end - start
    return entries


def timestamp(frame, fps):
    total = round(frame / fps * 1000)
    seconds, ms = divmod(total, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours:02d}h{minutes:02d}m{seconds:02d}s{ms:03d}'


def probe(path):
    return json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def run(command, log, commands):
    started = time.monotonic()
    with log.open('w') as f:
        result = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT)
    commands.append({'argv': command, 'log': str(log.name), 'log_sha256': digest(log),
                     'exit_code': result.returncode,
                     'elapsed_seconds': round(time.monotonic() - started, 3)})
    if result.returncode:
        raise RuntimeError(f'Command failed; see {log}')


def verify_media(path, expected, fps, logs, commands):
    meta = probe(path)
    video = next(s for s in meta['streams'] if s['codec_type'] == 'video')
    audio = [s for s in meta['streams'] if s['codec_type'] == 'audio']
    checks = {'frame_count': int(video['nb_frames']) == expected,
              'video_starts_at_zero': abs(float(video['start_time'])) < .00001,
              'video_duration': abs(float(video['duration']) - expected / fps) < .002,
              'dimensions': (video['width'], video['height']) == (1920, 1080),
              'frame_rate': video['avg_frame_rate'] == f'{fps}/1',
              'audio_present': len(audio) == 1,
              'audio_starts_at_zero': len(audio) == 1 and
              abs(float(audio[0]['start_time'])) < .00001,
              'audio_duration': len(audio) == 1 and
              abs(float(audio[0]['duration']) - expected / fps) < .055,
              'asset_below_2GiB': path.stat().st_size < 2 * 1024 ** 3}
    run(['ffmpeg', '-v', 'error', '-nostdin', '-xerror', '-threads', '2',
         '-i', str(path), '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', '-'],
        logs / (path.stem + '-decode.log'), commands)
    checks['full_decode'] = True
    if not all(checks.values()):
        raise RuntimeError(f'Media validation failed: {path.name}: {checks}')
    return {'file': str(path.name), 'frames': expected,
            'bytes': path.stat().st_size, 'sha256': digest(path), 'checks': checks,
            'video_duration': float(video['duration']),
            'audio_duration': float(audio[0]['duration'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--chunks', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-gap-seconds', type=float, default=1)
    parser.add_argument('--plan-only', action='store_true')
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    meta, flags, reports = load_timeline(args.manifest, args.chunks)
    fps = meta['fps']
    raw = runs(flags)
    segments = merge_runs(raw, math.floor(args.max_gap_seconds * fps))
    entries = make_catalog(flags, segments, fps)
    catalog = {'schema_version': 1, 'fps': fps, 'source_frames': len(flags),
               'scope': 'Every frame with nonempty boxes in final v3 chunk reports. '
               'Existing masks embedded in the original recording are not indexed. '
               'Caption restoration and static navigation restoration are part of the '
               'already rendered input film; no masks are added by this tool.',
               'frame_interval_basis': 'zero-based, half-open',
               'raw_masked_runs': raw, 'raw_run_count': len(raw),
               'max_gap_seconds': args.max_gap_seconds, 'segments': entries,
               'masked_frames': sum(flags),
               'collection_frames': sum(e['frames'] for e in entries),
               'context_frames': sum(e['context_frames'] for e in entries),
               'manifest_sha256': digest(args.manifest), 'reports': reports}
    for e in entries:
        e['file'] = (f"segment-{e['segment']:03d}_"
                     f"{timestamp(e['source_start_frame'], fps)}-"
                     f"{timestamp(e['source_end_frame_exclusive'], fps)}_"
                     f"f{e['source_start_frame']}-{e['source_end_frame_exclusive']}.mp4")
    (output / 'selection-plan.json').write_text(json.dumps(catalog, indent=2))
    print(json.dumps({k: catalog[k] for k in ['raw_run_count', 'masked_frames',
                                             'collection_frames', 'context_frames']}) +
          f' segments={len(entries)}', flush=True)
    if args.plan_only:
        return
    if not entries:
        raise ValueError('No report-masked frames exist; no video collection can be exported')
    before_stat = (source.stat().st_size, source.stat().st_mtime_ns)
    source_hash = digest(source)
    source_probe = probe(source)
    video = next(s for s in source_probe['streams'] if s['codec_type'] == 'video')
    if int(video['nb_frames']) != len(flags) or video['avg_frame_rate'] != f'{fps}/1':
        raise ValueError('Input rendered film does not match indexed CFR timeline')
    catalog['input'] = {'path': str(source), 'bytes': before_stat[0], 'sha256': source_hash}
    clips, logs = output / 'clips', output / 'logs'
    reusable = {}
    if clips.exists() and any(clips.glob('*.mp4')):
        previous_path = output / 'catalog.json'
        if not previous_path.exists():
            raise ValueError('Existing clips have no completed provenance catalog; use a new output directory')
        previous = json.loads(previous_path.read_text())
        if (previous.get('input', {}).get('sha256') != source_hash or
                previous.get('manifest_sha256') != catalog['manifest_sha256'] or
                previous.get('reports') != reports or
                previous.get('max_gap_seconds') != args.max_gap_seconds):
            raise ValueError('Existing output belongs to different input, reports or gap settings')
        reusable = {e['file']: e['sha256'] for e in previous['segments']}
    clips.mkdir(exist_ok=True)
    logs.mkdir(exist_ok=True)
    commands, validation = [], []
    for e in entries:
        path = clips / e['file']
        seek = e['source_start_frame'] // fps
        relative = e['source_start_frame'] - seek * fps
        count = e['frames']
        if path.exists() and (path.name not in reusable or digest(path) != reusable[path.name]):
            raise ValueError('Existing clip does not match the completed provenance catalog')
        if not path.exists():
            run(['ffmpeg', '-v', 'warning', '-nostdin', '-n', '-threads', '2',
                 '-ss', str(seek), '-reinit_filter', '0', '-i', str(source),
                 '-map', '0:v:0', '-map', '0:a:0',
                 '-vf', f'trim=start_frame={relative}:end_frame={relative + count},'
                 'setpts=PTS-STARTPTS,scale=1920:1080:flags=lanczos',
                 '-af', f'atrim=start={relative / fps:.9f}:duration={count / fps:.9f},'
                 'asetpts=PTS-STARTPTS', '-t', f'{count / fps:.9f}',
                 '-c:v', 'libx264', '-preset', 'fast', '-crf', '22', '-threads', '2',
                 '-filter_threads', '1', '-pix_fmt', 'yuv420p', '-r', str(fps),
                 '-fps_mode', 'cfr', '-c:a', 'aac', '-b:a', '128k',
                 '-movflags', '+faststart', str(path)],
                logs / (path.stem + '-encode.log'), commands)
        checked = verify_media(path, count, fps, logs, commands)
        validation.append(checked)
        e.update(bytes=checked['bytes'], sha256=checked['sha256'])
        print(f"verified {e['segment']}/{len(entries)} frames={count}", flush=True)
    concat = output / 'concat.txt'
    concat.write_text(''.join(f"file 'clips/{e['file']}'\nduration {e['frames'] / fps:.9f}\n"
                              for e in entries))
    collection = output / 'all-masked-segments.mp4'
    if not collection.exists():
        run(['ffmpeg', '-v', 'warning', '-nostdin', '-n', '-copyts', '-threads', '2',
             '-f', 'concat', '-safe', '0', '-i', str(concat), '-map', '0:v:0',
             '-map', '0:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k',
             '-af', 'aresample=async=1:first_pts=0',
             '-t', f"{catalog['collection_frames'] / fps:.9f}",
             '-avoid_negative_ts', 'disabled', '-movflags', '+faststart', str(collection)],
            logs / 'collection-encode.log', commands)
    collection_validation = verify_media(collection, catalog['collection_frames'], fps, logs, commands)
    # Explicitly map every output frame; distinguish selected mask from gap context.
    mapped = []
    for e in entries:
        for local, original in enumerate(range(e['source_start_frame'], e['source_end_frame_exclusive'])):
            mapped.append({'collection_frame': e['collection_start_frame'] + local,
                           'segment': e['segment'], 'segment_frame': local,
                           'source_frame': original, 'source_seconds': original / fps,
                           'report_has_mask': flags[original]})
    expected = {i for i, flag in enumerate(flags) if flag}
    selected = {m['source_frame'] for m in mapped if m['report_has_mask']}
    coverage = expected == selected
    unchanged = (before_stat == (source.stat().st_size, source.stat().st_mtime_ns)
                 and source_hash == digest(source))
    if not coverage or not unchanged:
        raise RuntimeError('Coverage or immutable input check failed')
    catalog['frame_mapping'] = mapped
    (output / 'catalog.json').write_text(json.dumps(catalog, indent=2))
    with (output / 'frame-mapping.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(mapped[0]))
        writer.writeheader()
        writer.writerows(mapped)
    shutil.copy2(__file__, output / 'build_masked_collection.py')
    (output / 'commands.json').write_text(json.dumps(commands, indent=2))
    result = {'passed': True, 'all_report_mask_frames_covered': coverage,
              'input_unchanged_sha256_and_stat': unchanged,
              'clips': validation, 'collection': collection_validation,
              'masked_frames': sum(flags), 'context_frames': catalog['context_frames'],
              'collection_frames': len(mapped), 'visual_limit':
              'Selection coverage and technical media integrity do not establish '
              'that every suspicious link was detected or correctly masked.'}
    (output / 'validation.json').write_text(json.dumps(result, indent=2))
    input_dir = output / 'inputs/revision-v3'
    input_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.manifest, input_dir / 'manifest.json')
    for part in meta['parts']:
        target = input_dir / 'chunks' / part['name'] / 'report.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.chunks / part['name'] / 'report.json', target)
    archive = output / 'masked-segment-clips.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_STORED) as z:
        for path in sorted(clips.glob('*.mp4')):
            z.write(path, 'clips/' + path.name)
        for name in ['catalog.json', 'frame-mapping.csv', 'validation.json',
                     'selection-plan.json', 'commands.json', 'build_masked_collection.py']:
            z.write(output / name, name)
        for path in sorted(logs.glob('*.log')):
            z.write(path, 'logs/' + path.name)
        for path in sorted(input_dir.rglob('*.json')):
            z.write(path, str(path.relative_to(output)), compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise RuntimeError('ZIP CRC validation failed')
    if archive.stat().st_size >= 2 * 1024 ** 3:
        raise RuntimeError('ZIP exceeds release asset limit')
    result['clips_archive'] = {'file': archive.name, 'bytes': archive.stat().st_size,
                             'sha256': digest(archive), 'crc_passed': True}
    # Archive contains the pre-archive validation, avoiding recursive hash binding.
    (output / 'validation.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({'passed': True, 'segments': len(entries),
                      'collection': collection_validation, 'zip': result['clips_archive']}), flush=True)


if __name__ == '__main__':
    main()
