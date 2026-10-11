"""Anonymous ASR/subtitle coverage and transient data regressions."""
import json
from pathlib import Path
import wave
import hashlib
import shutil
import subprocess
import struct

import numpy as np

import pytest

import speech_review as s


SRT = '1\n00:00:01,000 --> 00:00:02,500\nContact hidden@example.com or https://example.com/private\n\n2\n00:00:06,000 --> 00:00:07,000\nordinary words\n'


def test_subtitle_anonymous_with_source_window(tmp_path):
    source = tmp_path / 'private-name.srt'
    source.write_text(SRT)
    report = s.review_subtitle(source, start=1.5, duration=2., privacy=True)
    serialized = json.dumps(report)
    assert report['status'] == 'checked'
    assert report['result'] == 'hits'
    assert report['findings']
    assert all(row['start'] == 1.5 and row['end'] == 2.5 for row in report['findings'])
    assert all(row['status'] == 'needs_review' for row in report['findings'])
    assert not any(word in serialized for word in ['hidden', 'example.com', 'private-name', 'ordinary words'])
    assert source.read_text() == SRT
    assert s.review_subtitle(source, start=4., duration=1., privacy=True)['result'] == 'no_hits'


@pytest.mark.parametrize('text', ['not a subtitle', '1\n00:00:02,000 --> 00:00:01,000\ntext',
                                  '1\n00:99:00,000 --> 00:99:01,000\ntext'])
def test_malformed_subtitle_never_becomes_no_hits(tmp_path, text):
    path = tmp_path / 'bad.srt'
    path.write_text(text)
    result = s.review_subtitle(path, start=0., duration=4.)
    assert result['status'] == result['result'] == 'failed'


def test_each_audio_track_explicitly_not_checked():
    result = s.review_audio('unused.mp4', [{'index': 1}, {'index': 3}], video_origin=0., start=0., duration=4.)
    assert result['streams_total'] == 2
    assert result['streams_checked'] == 0
    assert [row['audio_stream_index'] for row in result['tracks']] == [1, 3]
    assert all(row['result'] == 'not_checked' for row in result['tracks'])
    assert s.review_audio('none', [], video_origin=0., start=0., duration=1.)['status'] == 'not_applicable'


def test_ordinary_file_extension_does_not_become_audio_warning():
    assert s.anonymous_findings([(0., 1., 'open video.mp4 or demo.html')], channel='audio') == []


def test_missing_model_is_failed_per_track(tmp_path):
    result = s.review_audio('unused.mp4', [{'index': 1}, {'index': 2}], video_origin=0., start=0., duration=4., model=tmp_path / 'missing')
    assert result['streams_failed'] == 2
    assert result['status'] == 'failed'


def test_asr_per_track_window_cleanup_and_partial_failure(tmp_path, monkeypatch):
    model = tmp_path / 'model.bin'
    model.write_bytes(b'model')
    source = tmp_path / 'source.bin'
    source.write_bytes(b'untouched')
    commands = []
    def fake_run(command):
        commands.append(command)
        if command[0] == 'ffmpeg':
            if command[command.index('-map') + 1] == '0:3':
                raise RuntimeError('may contain private data; must never persist')
            if command[-1].endswith('.f64le'):
                Path(command[-1]).write_bytes(struct.pack('<d', 1 / 32768) * 16000 * 4)
                return
            with wave.open(command[-1], 'wb') as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(b'\1\0' * 16000 * 4)
        else:
            prefix = Path(command[command.index('-of') + 1])
            prefix.with_suffix('.srt').write_text(SRT)
    monkeypatch.setattr(s, '_run', fake_run)
    monkeypatch.setattr(s.shutil, 'which', lambda _: '/bin/local-whisper')
    result = s.review_audio(source, [{'index': 1, 'start_time': '1.25', 'channels': 1, 'sample_rate': '16000'},
                                   {'index': 3, 'channels': 1, 'sample_rate': '16000'}],
                            video_origin=.25, start=10., duration=4., model=model, privacy=True, scratch_parent=tmp_path)
    assert result['streams_checked'] == 1 and result['streams_failed'] == 1
    assert result['status'] == 'failed'
    assert result['tracks'][0]['findings'][0]['start'] == 11.
    assert all(row['status'] == 'needs_review' for row in result['tracks'][0]['findings'])
    assert 'adelay=1000.000000:all=1' in commands[0][commands[0].index('-af') + 1]
    assert not list(tmp_path.glob('speech-review-*'))
    assert source.read_bytes() == b'untouched'
    assert not any(word in json.dumps(result) for word in ['hidden', 'example.com', 'private data'])


@pytest.mark.parametrize('language', ['auto', 'zh', 'en', 'ja', 'yue'])
@pytest.mark.parametrize('last_sample', [0, 1, -1, -32768])
def test_full_pcm_silence_blocks_hallucination_but_quiet_signal_runs_asr(tmp_path, monkeypatch, language, last_sample):
    model = tmp_path / 'model.bin'
    model.write_bytes(b'local model')
    # The only signal is beyond the first chunk; a spot-check would miss it.
    samples_total = s.PCM_CHUNK_FRAMES * 2 + 17
    duration = samples_total / 16000
    commands = []
    def hallucinating_run(command):
        commands.append(command)
        if command[0] == 'ffmpeg':
            if command[-1].endswith('.f64le'):
                Path(command[-1]).write_bytes(b'\0' * (samples_total - 1) * 8 + struct.pack('<d', last_sample / 32768))
                return
            with wave.open(command[-1], 'wb') as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(b'\0\0' * (samples_total - 1) + struct.pack('<h', last_sample))
        else:
            # A transcriber that invents link speech even when supplied silence.
            Path(command[command.index('-of') + 1]).with_suffix('.srt').write_text(SRT)
    monkeypatch.setattr(s, '_run', hallucinating_run)
    monkeypatch.setattr(s.shutil, 'which', lambda _: '/bin/local-whisper')
    report = s.review_audio('source.mp4', [{'index': 2, 'channels': 1, 'sample_rate': '16000'}], video_origin=0., start=10., duration=duration,
                            model=model, language=language, scratch_parent=tmp_path)
    row = report['tracks'][0]
    assert report['status'] == 'checked' and report['streams_checked'] == 1
    assert row['pcm_samples_checked'] == samples_total
    assert row['pcm_peak_absolute'] == abs(last_sample)
    assert row['pcm_sample_rate'] == 16000 and row['pcm_sample_width_bits'] == 16
    assert row['source_pcm_samples_checked'] == samples_total
    assert row['source_pcm_peak_absolute'] == abs(last_sample) / 32768
    assert row['source_pcm_channels'] == 1 and row['source_pcm_sample_rate'] == 16000
    assert row['silence_basis'] == 'all_channels_native_rate_float64_full_window'
    assert row['asr_language'] == language
    assert row['window_start'] == 10. and row['window_duration'] == duration
    if last_sample == 0:
        assert row['result'] == 'digital_silence'
        assert row['asr_skipped'] and row['reason'] == 'all_source_window_pcm_samples_zero'
        assert row['findings'] == [] and row['segments'] == 0
        assert len(commands) == 2
    else:
        assert row['result'] == 'hits' and len(commands) == 3
        assert commands[-1][commands[-1].index('-l') + 1] == language
        assert row['findings'][0]['start'] == 11.
        assert row['findings'][0]['end'] == 12.5
    assert not list(tmp_path.glob('speech-review-*'))
    assert not any(word in json.dumps(report) for word in ['hidden', 'example.com', 'ordinary words'])


def test_pcm_reads_are_bounded_and_truncated_audio_never_counts_as_silence():
    class TruncatedPCM:
        getnchannels = lambda self: 1
        getsampwidth = lambda self: 2
        getcomptype = lambda self: 'NONE'
        getnframes = lambda self: s.PCM_CHUNK_FRAMES + 10
        getframerate = lambda self: 16000
        def __init__(self):
            self.reads = 0
        def readframes(self, count):
            assert count == s.PCM_CHUNK_FRAMES
            self.reads += 1
            return b'\0\0' * count if self.reads == 1 else b''
    with pytest.raises(RuntimeError, match='audio_pcm_incomplete'):
        s._pcm_summary(TruncatedPCM())


def test_invalid_language_rejected_and_unrequested_asr_does_not_extract(monkeypatch):
    monkeypatch.setattr(s, '_run', lambda _: pytest.fail('unrequested ASR must not extract or invoke tools'))
    with pytest.raises(ValueError, match='invalid_asr_language'):
        s.review_audio('unused', [{'index': 1}], video_origin=0., start=0., duration=4., language='unsupported')
    report = s.review_audio('unused', [{'index': 1}], video_origin=0., start=0., duration=4., language='zh')
    assert report['tracks'][0]['reason'] == 'local_asr_not_requested'
    assert report['tracks'][0]['result'] == 'not_checked'


@pytest.mark.parametrize('samples', [[float('nan')], [float('inf')], [0.]])
def test_invalid_native_pcm_cannot_be_reported_as_digital_silence(tmp_path, samples):
    raw = tmp_path / 'native.f64le'
    raw.write_bytes(b''.join(struct.pack('<d', sample) for sample in samples))
    # Non-finite PCM and an incomplete duration both fail closed.
    with pytest.raises(RuntimeError):
        s._native_pcm_summary(raw, channels=1, sample_rate=48000, duration=1.)


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='Local FFmpeg native PCM integration')
@pytest.mark.parametrize('expression,channels,source_nonzero', [
    ('0.1*sin(2*PI*600*t)|-0.1*sin(2*PI*600*t)', 2, True),
    ('1e-12', 1, True),
    ('0|0', 2, False),
])
def test_native_channels_and_float_signal_survive_silence_decision(tmp_path, monkeypatch, expression, channels, source_nonzero):
    source = tmp_path / 'native.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                    f'aevalsrc={expression}:s=48000:d=0.4', '-c:a', 'pcm_f64le', str(source)], check=True)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    model = tmp_path / 'local.bin'
    model.write_bytes(b'test stub')
    real_run = s._run
    asr_calls = []
    def fake_asr(command):
        if command[0] == 'ffmpeg':
            return real_run(command)
        asr_calls.append(command)
        Path(command[command.index('-of') + 1]).with_suffix('.srt').write_text(
            '1\n00:00:00,010 --> 00:00:00,030\nhttps://example.com/private\n')
    monkeypatch.setattr(s, '_run', fake_asr)
    monkeypatch.setattr(s.shutil, 'which', lambda _: '/bin/stub-local-whisper')
    # Deliberately omit format metadata to exercise numeric ffprobe fallback.
    result = s.review_audio(source, [{'index': 0}], video_origin=0., start=.05, duration=.2,
                            model=model, scratch_parent=tmp_path, language='zh')
    row = result['tracks'][0]
    assert row['status'] == 'checked'
    assert row['pcm_peak_absolute'] == 0  # ASR downmix/quantization lost the signal.
    assert row['source_pcm_channels'] == channels and row['source_pcm_sample_rate'] == 48000
    assert row['source_pcm_frames_checked'] == 9600
    assert row['source_pcm_samples_checked'] == 9600 * channels
    if source_nonzero:
        assert row['source_pcm_peak_absolute'] > 0
        assert row['result'] == 'hits' and len(asr_calls) == 1
        assert row['findings'][0]['start'] == pytest.approx(.06)
    else:
        assert row['source_pcm_peak_absolute'] == 0
        assert row['result'] == 'digital_silence' and not asr_calls
    assert not list(tmp_path.glob('speech-review-*'))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='Local FFmpeg audio integration')
def test_audio_extraction_checks_all_tracks_and_preserves_relative_origin(tmp_path, monkeypatch):
    source = tmp_path / 'tracks.mkv'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=size=64x48:rate=10:duration=1',
                    '-f', 'lavfi', '-i', 'sine=frequency=600:duration=1',
                    '-itsoffset', '0.3', '-f', 'lavfi', '-i', 'sine=frequency=800:duration=0.7',
                    '-map', '0:v', '-map', '1:a', '-map', '2:a', '-c:v', 'ffv1', '-c:a', 'pcm_s16le', str(source)], check=True)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    model = tmp_path / 'model.bin'
    model.write_bytes(b'test stub')
    from redact_video import probe
    metadata = probe(source)
    streams = [row for row in metadata['streams'] if row['codec_type'] == 'audio']
    real_run = s._run
    def fake_transcriber(command):
        if command[0] == 'ffmpeg':
            return real_run(command)
        audio = Path(command[command.index('-f') + 1])
        with wave.open(str(audio), 'rb') as decoded:
            samples = np.frombuffer(decoded.readframes(decoded.getnframes()), dtype=np.int16)
            active = np.flatnonzero(np.abs(samples) > 20)
            first_ms = round(active[0] / decoded.getframerate() * 1000)
        prefix = Path(command[command.index('-of') + 1])
        prefix.with_suffix('.srt').write_text(f'1\n00:00:00,{first_ms:03} --> 00:00:00,{first_ms + 50:03}\nhttps://example.com/private\n')
    monkeypatch.setattr(s, '_run', fake_transcriber)
    monkeypatch.setattr(s.shutil, 'which', lambda _: '/bin/stub-local-whisper')
    result = s.review_audio(source, streams, video_origin=0., start=.1, duration=.5, model=model, scratch_parent=tmp_path)
    assert result['status'] == 'checked' and result['streams_checked'] == result['streams_total'] == 2
    assert result['tracks'][0]['findings'][0]['start'] == pytest.approx(.1, abs=.003)
    assert result['tracks'][1]['findings'][0]['start'] == pytest.approx(.3, abs=.003)
    assert all(track['decoded_duration'] == .5 for track in result['tracks'])
    assert not list(tmp_path.glob('speech-review-*'))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
