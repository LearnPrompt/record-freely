"""Anonymous ASR/subtitle coverage and transient data regressions."""
import json
from pathlib import Path
import wave
import hashlib
import shutil
import subprocess

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
            with wave.open(command[-1], 'wb') as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(b'\0' * 16000 * 2 * 4)
        else:
            prefix = Path(command[command.index('-of') + 1])
            prefix.with_suffix('.srt').write_text(SRT)
    monkeypatch.setattr(s, '_run', fake_run)
    monkeypatch.setattr(s.shutil, 'which', lambda _: '/bin/local-whisper')
    result = s.review_audio(source, [{'index': 1, 'start_time': '1.25'}, {'index': 3}],
                            video_origin=.25, start=10., duration=4., model=model, privacy=True, scratch_parent=tmp_path)
    assert result['streams_checked'] == 1 and result['streams_failed'] == 1
    assert result['status'] == 'failed'
    assert result['tracks'][0]['findings'][0]['start'] == 11.
    assert all(row['status'] == 'needs_review' for row in result['tracks'][0]['findings'])
    assert 'adelay=1000.000000:all=1' in commands[0][commands[0].index('-af') + 1]
    assert not list(tmp_path.glob('speech-review-*'))
    assert source.read_bytes() == b'untouched'
    assert not any(word in json.dumps(result) for word in ['hidden', 'example.com', 'private data'])


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
