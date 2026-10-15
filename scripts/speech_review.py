#!/usr/bin/env python3
"""Local, transient ASR and subtitle checks; only anonymous findings survive."""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from array import array
from pathlib import Path

from review_candidates import text_candidates


# whisper.cpp language IDs; keep CLI choices and the library entry point aligned.
# https://github.com/ggml-org/whisper.cpp/blob/master/src/whisper.cpp (g_lang)
ASR_LANGUAGES = tuple(('auto en zh de es ru ko fr ja pt tr pl ca nl ar sv it id hi fi vi he uk el '
                       'ms cs ro da hu ta no th ur hr bg lt la mi ml cy sk te fa lv bn sr az sl kn '
                       'et mk br eu is hy ne mn bs kk sq sw gl mr pa si km sn yo so af oc ka be '
                       'tg sd gu am yi lo uz fo ht ps tk nn mt sa lb my bo tl mg as tt haw ln ha '
                       'ba jw su yue').split())
PCM_CHUNK_FRAMES = 32768


def _pcm_summary(decoded):
    """Inspect the ASR input PCM; this downmixed format cannot establish source silence."""
    if decoded.getnchannels() != 1 or decoded.getsampwidth() != 2 or decoded.getcomptype() != 'NONE':
        raise RuntimeError('invalid_pcm_format')
    sample_count = peak = 0
    while block := decoded.readframes(PCM_CHUNK_FRAMES):
        samples = array('h')
        samples.frombytes(block)
        if sys.byteorder != 'little':
            samples.byteswap()
        sample_count += len(samples)
        peak = max(peak, max(map(abs, samples), default=0))
    if not sample_count or sample_count != decoded.getnframes():
        raise RuntimeError('audio_pcm_incomplete')
    return {'pcm_samples_checked': sample_count, 'pcm_peak_absolute': peak,
            'pcm_sample_rate': decoded.getframerate(), 'pcm_sample_width_bits': 16}


def _native_audio_format(source, stream):
    metadata = stream
    if not stream.get('channels') or not stream.get('sample_rate'):
        result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', str(stream['index']),
                                 '-show_entries', 'stream=sample_rate,channels', '-of', 'json', str(source)],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if result.returncode:
            raise RuntimeError('audio_metadata_failed')
        rows = json.loads(result.stdout).get('streams', [])
        if len(rows) != 1:
            raise RuntimeError('audio_metadata_failed')
        metadata = rows[0]
    channels, sample_rate = int(metadata['channels']), int(metadata['sample_rate'])
    if channels <= 0 or sample_rate <= 0:
        raise RuntimeError('audio_metadata_failed')
    return channels, sample_rate


def _native_pcm_summary(path, *, channels, sample_rate, duration):
    """Check all channels at native rate in float64 before any ASR downmix or quantization."""
    sample_count, peak = 0, 0.
    with Path(path).open('rb') as decoded:
        while block := decoded.read(PCM_CHUNK_FRAMES * 8):
            samples = array('d')
            samples.frombytes(block)
            if sys.byteorder != 'little':
                samples.byteswap()
            for sample in samples:
                if not math.isfinite(sample):
                    raise RuntimeError('audio_nonfinite_pcm')
                peak = max(peak, abs(sample))
            sample_count += len(samples)
    if not sample_count or sample_count % channels:
        raise RuntimeError('audio_pcm_incomplete')
    frames = sample_count // channels
    decoded_duration = frames / sample_rate
    if abs(decoded_duration - duration) > .05:
        raise RuntimeError('audio_window_incomplete')
    return {'source_pcm_samples_checked': sample_count, 'source_pcm_frames_checked': frames,
            'source_pcm_peak_absolute': peak, 'source_pcm_sample_rate': sample_rate,
            'source_pcm_channels': channels, 'source_pcm_sample_width_bits': 64,
            'source_pcm_decoded_duration': decoded_duration,
            'silence_basis': 'all_channels_native_rate_float64_full_window'}


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


def review_audio(source, streams, *, video_origin, start, duration, model=None, privacy=False, whisper_cli='whisper-cli', scratch_parent=None, language='auto'):
    if language not in ASR_LANGUAGES:
        raise ValueError('invalid_asr_language')
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
                audio, native_audio, prefix = scratch / 'audio.wav', scratch / 'source.f64le', scratch / 'speech'
                relative_origin = float(stream.get('start_time') or 0.) - video_origin
                filters = ['asetpts=PTS-STARTPTS']
                if relative_origin > 0:
                    filters.append(f'adelay={relative_origin * 1000:.6f}:all=1')
                elif relative_origin < 0:
                    filters += [f'atrim=start={-relative_origin:.9f}', 'asetpts=PTS-STARTPTS']
                filters += [f'apad=whole_dur={start + duration:.9f}',
                            f'atrim=start={start:.9f}:end={start + duration:.9f}', 'asetpts=PTS-STARTPTS']
                channels, sample_rate = _native_audio_format(source, stream)
                _run(['ffmpeg', '-v', 'error', '-nostdin', '-reinit_filter', '0', '-i', str(source),
                      '-map', f'0:{index}', '-vn', '-af', ','.join(filters),
                      '-c:a', 'pcm_f64le', '-f', 'f64le', str(native_audio)])
                native_pcm = _native_pcm_summary(native_audio, channels=channels, sample_rate=sample_rate, duration=duration)
                _run(['ffmpeg', '-v', 'error', '-nostdin', '-reinit_filter', '0', '-i', str(source),
                      '-map', f'0:{index}', '-vn', '-af', ','.join(filters), '-ac', '1', '-ar', '16000',
                      '-c:a', 'pcm_s16le', str(audio)])
                with wave.open(str(audio), 'rb') as decoded:
                    audio_duration = decoded.getnframes() / decoded.getframerate()
                    pcm = _pcm_summary(decoded)
                if abs(audio_duration - duration) > .05:
                    raise RuntimeError('audio_window_incomplete')
                row.update(window_start=start, window_duration=duration, decoded_duration=audio_duration,
                           timeline='source_normalized_seconds', asr_language=language, **pcm, **native_pcm)
                if native_pcm['source_pcm_peak_absolute'] == 0:
                    row.update(status='checked', result='digital_silence', segments=0,
                               asr_skipped=True, reason='all_source_window_pcm_samples_zero')
                    continue
                _run([whisper_cli, '-m', str(model), '-f', str(audio), '-l', language, '-osrt', '-of', str(prefix)])
                segments = subtitle_segments(prefix.with_suffix('.srt').read_text(encoding='utf-8-sig'))
                findings = anonymous_findings(segments, privacy=privacy, offset=start, start=start,
                                              end=start + duration, channel='audio', track=index)
                row.update(status='checked', result='hits' if findings else 'no_hits',
                           segments=len(segments), window_start=start, window_duration=duration,
                           decoded_duration=audio_duration,
                           timeline='source_normalized_seconds', findings=findings)
        except (OSError, RuntimeError, ValueError, KeyError, UnicodeError, wave.Error):
            row.update(status='failed', result='failed', failure_code='local_asr_failed')
    failures = sum(track['status'] == 'failed' for track in tracks)
    checked = sum(track['status'] == 'checked' for track in tracks)
    return {'status': 'failed' if failures else 'checked' if checked else 'not_checked' if tracks else 'not_applicable',
            'streams_total': len(tracks), 'streams_checked': checked, 'streams_failed': failures,
            'tracks': tracks, 'transcripts_retained': False}
