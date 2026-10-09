#!/usr/bin/env python3
"""Local, transient ASR and subtitle checks; only anonymous findings survive."""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

from review_candidates import text_candidates


def _timestamp(value):
    hours, minutes, seconds = value.replace(',', '.').split(':')
    if not 0 <= int(minutes) < 60 or not 0 <= float(seconds) < 60:
        raise ValueError('invalid_subtitle_timestamp')
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def subtitle_segments(text):
    """Read SRT blocks, rejecting malformed nonempty input instead of passing it."""
    result = []
    for block in re.split(r'\n\s*\n', text.replace('\r\n', '\n').strip()):
        if not block.strip():
            continue
        lines = block.splitlines()
        time_index = 1 if lines[0].strip().isdigit() else 0
        if len(lines) <= time_index + 1:
            raise ValueError('invalid_subtitle')
        match = re.fullmatch(r'(\d+:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d+:\d{2}:\d{2}[,.]\d{3})', lines[time_index].strip())
        if not match:
            raise ValueError('invalid_subtitle')
        start, end = map(_timestamp, match.groups())
        if end < start:
            raise ValueError('invalid_subtitle')
        result.append((start, end, '\n'.join(lines[time_index + 1:])))
    return result


def anonymous_findings(segments, *, privacy=False, offset=0., start=0., end=float('inf'), channel='subtitle', track=None):
    result = []
    for first, last, text in segments:
        first, last = first + offset, last + offset
        if last <= start or first >= end:
            continue
        for candidate in text_candidates(text, privacy=privacy, channel=channel):
            if candidate['status'] == 'keep':
                continue
            # No offsets, words or user-chosen filenames are persisted.
            row = {'start': max(start, first), 'end': min(end, last), 'channel': channel,
                   'kind': candidate['kind'], 'status': 'needs_review', 'reason': candidate['reason']}
            if track is not None:
                row['audio_stream_index'] = track
            result.append(row)
    return result


def review_subtitle(path, *, start, duration, privacy=False):
    try:
        segments = subtitle_segments(Path(path).read_text(encoding='utf-8-sig'))
        findings = anonymous_findings(segments, start=start, end=start + duration, privacy=privacy)
        return {'status': 'checked', 'result': 'hits' if findings else 'no_hits',
                'segments_in_file': len(segments), 'timeline': 'source_normalized_seconds',
                'window_start': start, 'window_duration': duration, 'findings': findings}
    except (OSError, ValueError, UnicodeError):
        return {'status': 'failed', 'result': 'failed', 'failure_code': 'subtitle_read_or_parse_failed', 'findings': []}


def _run(command):
    # Metadata and recognized speech can contain sensitive text; never echo it.
    result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode:
        raise RuntimeError('local_tool_failed')


def review_audio(source, streams, *, video_origin, start, duration, model=None, privacy=False, whisper_cli='whisper-cli', scratch_parent=None):
    tracks = []
    for stream in streams:
        index = int(stream['index'])
        row = {'audio_stream_index': index, 'status': 'not_checked', 'result': 'not_checked', 'findings': []}
        tracks.append(row)
        if model is None:
            row['reason'] = 'local_asr_not_requested'
            continue
        if not Path(model).is_file() or not shutil.which(whisper_cli):
            row.update(status='failed', result='failed', failure_code='local_asr_dependency_unavailable')
            continue
        try:
            with tempfile.TemporaryDirectory(prefix='speech-review-', dir=scratch_parent) as temporary:
                scratch = Path(temporary)
                audio, prefix = scratch / 'audio.wav', scratch / 'speech'
                relative_origin = float(stream.get('start_time') or 0.) - video_origin
                filters = ['asetpts=PTS-STARTPTS']
                if relative_origin > 0:
                    filters.append(f'adelay={relative_origin * 1000:.6f}:all=1')
                elif relative_origin < 0:
                    filters += [f'atrim=start={-relative_origin:.9f}', 'asetpts=PTS-STARTPTS']
                filters += [f'apad=whole_dur={start + duration:.9f}',
                            f'atrim=start={start:.9f}:end={start + duration:.9f}', 'asetpts=PTS-STARTPTS']
                _run(['ffmpeg', '-v', 'error', '-nostdin', '-reinit_filter', '0', '-i', str(source),
                      '-map', f'0:{index}', '-vn', '-af', ','.join(filters), '-ac', '1', '-ar', '16000', str(audio)])
                with wave.open(str(audio), 'rb') as decoded:
                    audio_duration = decoded.getnframes() / decoded.getframerate()
                if abs(audio_duration - duration) > .05:
                    raise RuntimeError('audio_window_incomplete')
                _run([whisper_cli, '-m', str(model), '-f', str(audio), '-l', 'auto', '-osrt', '-of', str(prefix)])
                segments = subtitle_segments(prefix.with_suffix('.srt').read_text(encoding='utf-8-sig'))
                findings = anonymous_findings(segments, privacy=privacy, offset=start, start=start,
                                              end=start + duration, channel='audio', track=index)
                row.update(status='checked', result='hits' if findings else 'no_hits',
                           segments=len(segments), window_start=start, window_duration=duration,
                           decoded_duration=audio_duration,
                           timeline='source_normalized_seconds', findings=findings)
        except (OSError, RuntimeError, ValueError, UnicodeError, wave.Error):
            row.update(status='failed', result='failed', failure_code='local_asr_failed')
    failures = sum(track['status'] == 'failed' for track in tracks)
    checked = sum(track['status'] == 'checked' for track in tracks)
    return {'status': 'failed' if failures else 'checked' if checked else 'not_checked' if tracks else 'not_applicable',
            'streams_total': len(tracks), 'streams_checked': checked, 'streams_failed': failures,
            'tracks': tracks, 'transcripts_retained': False}
