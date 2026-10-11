"""Independent encoded-frame coverage; no inference from upstream mask reports."""
import hashlib
import json
import shutil
import subprocess
import sys

import numpy as np
import cv2
import pytest

import review_video as v


class EmptyOCR:
    def __init__(self, scratch, privacy=False):
        pass
    def read(self, frame):
        return {'observations': [], 'barcodes': []}
    def close(self):
        pass


def test_qr_box_has_no_payload_and_is_privacy_opt_in():
    recognized = {'observations': [], 'barcodes': [{'box': [.1, .2, .3, .4], 'confidence': .8,
                                                   'payload': 'https://secret.example.com'}]}
    assert not v.frame_findings(recognized, 100, 100)
    findings = v.frame_findings(recognized, 100, 100, privacy=True)
    assert findings[0]['box'] == [6, 16, 38, 48]
    assert findings[0]['status'] == 'needs_review'
    assert 'secret' not in json.dumps(findings)


@pytest.mark.parametrize('args', [['--detect-every', '0'], ['--start', 'nan'], ['--duration', 'inf'], ['--duration', '-1']])
def test_bad_window_and_sample_interval_rejected(args):
    with pytest.raises(SystemExit):
        v.parse_args(['input.mp4', '--output-dir', 'new', *args])


def test_new_output_required_and_source_preserved(tmp_path):
    source = tmp_path / 'source.mp4'
    source.write_bytes(b'original')
    output = tmp_path / 'existing'
    output.mkdir()
    (output / 'keep').write_text('other work')
    args = v.parse_args([str(source), '--output-dir', str(output)])
    with pytest.raises(RuntimeError, match='already exists'):
        v.review(args)
    assert source.read_bytes() == b'original'
    assert (output / 'keep').read_text() == 'other work'


def test_probe_failure_is_recorded_without_metadata(tmp_path, monkeypatch):
    source = tmp_path / 'source.mp4'
    source.write_bytes(b'invalid')
    monkeypatch.setattr(v, 'probe', lambda _: (_ for _ in ()).throw(RuntimeError('private@email.example')))
    report = v.review(v.parse_args([str(source), '--output-dir', str(tmp_path / 'new')]))
    assert report['status'] == 'failed'
    assert report['visual']['status'] == 'not_checked'
    assert report['source']['unchanged']
    assert 'private@' not in json.dumps(report)


HAS_FFMPEG = shutil.which('ffmpeg') and shutil.which('ffprobe')


def make_video(path):
    # One-frame flash on normalized frame 5 at .5 sec; every-second-frame misses it.
    pixels = np.zeros((20, 48, 64, 3), np.uint8)
    pixels[5] = 255
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', '64x48',
                    '-r', '10', '-i', 'pipe:0', '-c:v', 'ffv1', str(path)], input=pixels.tobytes(), check=True)


@pytest.mark.skipif(not HAS_FFMPEG, reason='FFmpeg integration')
def test_short_flash_sampling_and_window_times(tmp_path):
    source = tmp_path / 'flash.mkv'
    make_video(source)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    class FlashOCR(EmptyOCR):
        def read(self, frame):
            if frame.mean() > 200:
                return {'observations': [{'text': 'https://secret.example.com', 'box': [.1, .1, .8, .2], 'confidence': .99}]}
            return super().read(frame)
    spec = v.video_spec(v.probe(source), 0.)
    full = v.scan_visual(source, spec, tmp_path, ocr_factory=FlashOCR)
    assert full['status'] == 'checked' and full['decoded_frames'] == full['checked_frames'] == 20
    assert full['findings'][0]['time'] == .5
    assert full['findings'][0]['frame'] == 5
    assert 'secret' not in json.dumps(full)
    sampled = v.scan_visual(source, spec, tmp_path, detect_every=2, ocr_factory=FlashOCR)
    assert sampled['result'] == 'no_hits' and sampled['mode'] == 'sampled'
    assert sampled['checked_frames'] == sampled['skipped_frames'] == 10
    assert sampled['nominal_sample_interval_seconds'] == .2
    clip = v.scan_visual(source, v.video_spec(v.probe(source), .4, .4), tmp_path, ocr_factory=FlashOCR)
    assert clip['decoded_frames'] == 4 and clip['findings'][0]['time'] == .5
    assert clip['first_checked_time'] == .4 and clip['last_checked_time'] == pytest.approx(.7)
    offset = v.scan_visual(source, v.video_spec(v.probe(source), .45, .4), tmp_path, ocr_factory=FlashOCR)
    assert offset['checked_frames'] == 4 and offset['findings'][0]['time'] == .5
    assert offset['findings'][0]['source_normalized_frame'] == 5
    assert offset['first_checked_time'] == .5 and offset['last_checked_time'] == .8
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    command = v.decoder_command(source, spec)
    assert command[command.index('-reinit_filter') + 1] == '0'


@pytest.mark.skipif(not HAS_FFMPEG, reason='FFmpeg integration')
def test_ocr_failure_cannot_report_no_hits(tmp_path):
    source = tmp_path / 'flash.mkv'
    make_video(source)
    class FailingOCR(EmptyOCR):
        def read(self, frame):
            if frame.mean() > 200:
                raise RuntimeError('secret data')
            return super().read(frame)
    report = v.scan_visual(source, v.video_spec(v.probe(source), 0.), tmp_path, ocr_factory=FailingOCR)
    assert report['status'] == report['result'] == 'failed'
    assert report['checked_frames'] == 19 and report['failed_frames'] == 1
    assert report['failure_frames'] == [{'frame': 5, 'source_normalized_frame': 5, 'time': .5, 'reason': 'ocr_frame_failed'}]
    assert 'secret data' not in json.dumps(report)


@pytest.mark.skipif(not HAS_FFMPEG, reason='FFmpeg integration')
def test_end_to_end_report_source_binding_and_skipped_audio(tmp_path, monkeypatch):
    source = tmp_path / 'private-source.mkv'
    make_video(source)
    # Hook the scan worker without changing what orchestration reports.
    original_scan = v.scan_visual
    monkeypatch.setattr(v, 'scan_visual', lambda *a, **kw: original_scan(*a, **kw, ocr_factory=EmptyOCR))
    output = tmp_path / 'new'
    report = v.review(v.parse_args([str(source), '--output-dir', str(output), '--detect-every', '2']))
    assert report['status'] == 'complete'
    assert report['source']['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert report['source']['unchanged']
    assert report['subtitle']['result'] == 'not_checked'
    assert report['audio']['status'] == 'not_applicable'
    assert report['visual']['mode'] == 'sampled'
    assert report['coverage_status'] == 'partial' and report['acceptance'] == 'not_verified'
    assert not report['media_modified'] and not report['uploaded']
    assert list(output.iterdir()) == [output / 'review.json']
    assert 'private-source' not in (output / 'review.json').read_text()


@pytest.mark.skipif(not HAS_FFMPEG, reason='FFmpeg integration')
def test_independent_subtitle_sources_and_failure_stay_visible(tmp_path, monkeypatch):
    source = tmp_path / 'video.mkv'
    make_video(source)
    subtitle = tmp_path / 'a.srt'
    subtitle.write_text('1\n00:00:00,200 --> 00:00:00,400\nhttps://secret.example.com\n')
    malformed = tmp_path / 'b.srt'
    malformed.write_text('not an SRT')
    original_scan = v.scan_visual
    monkeypatch.setattr(v, 'scan_visual', lambda *a, **kw: original_scan(*a, **kw, ocr_factory=EmptyOCR))
    args = v.parse_args([str(source), '--output-dir', str(tmp_path / 'new'),
                         '--subtitle', str(subtitle), '--subtitle', str(malformed)])
    assert args.subtitle == [subtitle, malformed]
    report = v.review(args)
    assert report['status'] == 'partial'
    assert report['subtitle']['sources_total'] == 2
    assert report['subtitle']['sources_checked'] == report['subtitle']['sources_failed'] == 1
    assert [row['status'] for row in report['subtitle']['sources']] == ['checked', 'failed']
    assert report['pending_review'][0]['subtitle_source_id'] == 'S0001'
    assert report['acceptance'] == 'needs_review'
    assert 'secret.example' not in json.dumps(report)


@pytest.mark.skipif(sys.platform != 'darwin' or not HAS_FFMPEG or not shutil.which('xcrun'), reason='Local macOS Vision integration')
def test_native_vision_finds_encoded_single_frame_email_and_qr(tmp_path):
    payload = 'https://private.example.com/never-open-this'
    qr = cv2.QRCodeEncoder_create().encode(payload)
    qr = cv2.resize(qr, (240, 240), interpolation=cv2.INTER_NEAREST)
    pixels = np.full((8, 480, 720, 3), 255, np.uint8)
    cv2.putText(pixels[3], 'hidden@example.com', (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 0, 0), 2, cv2.LINE_AA)
    pixels[3, 180:420, 240:480] = cv2.cvtColor(qr, cv2.COLOR_GRAY2BGR)
    source = tmp_path / 'encoded.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', '720x480',
                    '-r', '10', '-i', 'pipe:0', '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', str(source)],
                   input=pixels.tobytes(), check=True)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    report = v.scan_visual(source, v.video_spec(v.probe(source), 0.), tmp_path, privacy=True)
    assert report['status'] == 'checked' and report['checked_frames'] == 8
    email = next(row for row in report['findings'] if row['kind'] == 'email')
    code = next(row for row in report['findings'] if row['kind'] == 'qr_code')
    assert email['frame'] == code['frame'] == 3
    assert email['time'] == code['time'] == pytest.approx(.3)
    assert 'hidden' not in json.dumps(report) and 'private.example' not in json.dumps(report)
    assert report['qr_status'] == 'checked'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before

@pytest.mark.parametrize('binding',[
    {'status':'complete','output_sha256':'0'*64},
    {'status':'failed','output_sha256':None},
    {'status':'complete'},
])
def test_wrong_or_legacy_output_binding_rejected_before_output_creation(tmp_path,binding):
    source=tmp_path/'encoded.mp4';source.write_bytes(b'encoded fixture')
    report=tmp_path/'report.json';report.write_text(json.dumps(binding))
    output=tmp_path/'review'
    args=v.parse_args([str(source),'--output-dir',str(output),'--redaction-report',str(report)])
    with pytest.raises(RuntimeError,match='does not bind'):
        v.review(args)
    assert not output.exists() and source.read_bytes()==b'encoded fixture'


def test_attached_picture_does_not_replace_playable_video_stream():
    info={'streams':[{'index':0,'codec_type':'video','width':400,'height':400,'avg_frame_rate':'0/0','disposition':{'attached_pic':1}},
        {'index':1,'codec_type':'video','width':640,'height':360,'avg_frame_rate':'30/1','duration':'1'}]}
    spec=v.video_spec(info,0)
    assert spec['stream_index']==1 and spec['width']==640 and spec['fps']==30


def metadata_video(**overrides):
    video = {'index': 0, 'codec_type': 'video', 'width': 16, 'height': 16,
             'avg_frame_rate': '30/1', 'r_frame_rate': '30/1',
             'duration': '199.666667', 'nb_frames': '5990'}
    video.update(overrides)
    return {'streams': [video]}


def test_rounded_duration_does_not_invent_5991st_frame():
    spec = v.video_spec(metadata_video(), 0.)
    assert spec['end_source_frame_exclusive'] == 5990
    assert spec['expected_count_basis'] == 'normalized_time_bounds'
    assert spec['endpoint_precision_seconds'] == 0.0000005
    # Neither a plausible count nor an arbitrary wrong one overrides timing.
    for count in ('1', '5991', 'N/A', None):
        assert v.video_spec(metadata_video(nb_frames=count), 0.)['end_source_frame_exclusive'] == 5990


def test_non_aligned_windows_and_real_fractional_endpoint_are_not_rounded_away():
    info = metadata_video(duration='2.000000', nb_frames='60')
    spec = v.video_spec(info, .015, .04)
    assert (spec['first_source_frame'], spec['end_source_frame_exclusive']) == (1, 2)
    # Explicit windows are precise user input, not rounded probe timestamps.
    assert v.video_spec(info, 0., 1.0000001)['end_source_frame_exclusive'] == 31
    assert v.video_spec(metadata_video(duration='1.016667'), 0.)['end_source_frame_exclusive'] == 31
    # Binary floating point noise around an exact boundary is still harmless.
    assert v.frame_boundary(.1 + .2, 10) == 3
    assert v.frame_boundary(.45, 10) == 5


@pytest.mark.parametrize('overrides, hint', [
    ({'avg_frame_rate': '24/1', 'r_frame_rate': '30/1', 'nb_frames': '5990'}, 'variable_or_mixed'),
    ({'frame_rate_mode': 'VFR', 'nb_frames': '5990'}, 'variable_or_mixed'),
    ({'r_frame_rate': '0/0', 'nb_frames': '5990'}, 'unknown'),
    ({}, 'constant_rate_metadata_unverified'),
])
def test_frame_rate_metadata_never_proves_original_source_frame_coverage(overrides, hint):
    spec = v.video_spec(metadata_video(**overrides), 0.)
    assert spec['source_rate_hint'] == hint
    assert spec['source_frame_coverage'] == 'not_verified'
    assert spec['expected_count_basis'] == 'normalized_time_bounds'
    if overrides.get('avg_frame_rate') == '24/1':
        assert spec['end_source_frame_exclusive'] != 5990


@pytest.mark.skipif(not HAS_FFMPEG, reason='FFmpeg integration')
def test_actual_5990_frame_mp4_rescan_reaches_verified_normalized_eof(tmp_path):
    source = tmp_path / 'rounded-duration.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=size=16x16:rate=30',
                    '-frames:v', '5990', '-c:v', 'libx264', '-preset', 'ultrafast',
                    '-pix_fmt', 'yuv420p', str(source)], check=True)
    info = v.probe(source)
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    assert video['nb_frames'] == '5990'
    assert video['duration'] == '199.666667'
    report = v.scan_visual(source, v.video_spec(info, 0.), tmp_path, ocr_factory=EmptyOCR)
    assert report['status'] == 'checked'
    assert report['decoded_frames'] == report['checked_frames'] == report['expected_normalized_frames'] == 5990
    assert report['decoder_reached_eof'] and report['decoder_exit_code'] == 0
    assert report['source_frame_coverage'] == 'not_verified'


@pytest.mark.skipif(not HAS_FFMPEG, reason='FFmpeg integration')
def test_real_missing_frame_still_fails_despite_clean_eof(tmp_path, monkeypatch):
    source = tmp_path / 'flash.mkv'
    make_video(source)
    spec = v.video_spec(v.probe(source), 0.)
    original_command = v.decoder_command
    # A clean decoder exit alone must not accept only 19 of 20 required frames.
    def incomplete_command(source, requested):
        command = original_command(source, requested)
        index = command.index('-vf') + 1
        command[index] = command[index].replace('end_frame=20', 'end_frame=19')
        return command
    monkeypatch.setattr(v, 'decoder_command', incomplete_command)
    report = v.scan_visual(source, spec, tmp_path, ocr_factory=EmptyOCR)
    assert report['decoder_reached_eof'] and report['decoder_exit_code'] == 0
    assert report['decoded_frames'] == 19 and report['expected_normalized_frames'] == 20
    assert report['status'] == report['result'] == 'failed'
    assert report['failure_code'] == 'decoded_coverage_incomplete'


@pytest.mark.skipif(not HAS_FFMPEG, reason='FFmpeg integration')
def test_fatal_timeout_stops_scan_and_records_coverage_gap(tmp_path):
    from ocr_worker import JSONLineWorker
    source = tmp_path / 'flash.mkv'
    make_video(source)
    class TimedOCR(v.ReviewOCR):
        calls = 0
        def __init__(self, scratch, privacy=False):
            self.privacy = privacy
            self.image = tmp_path / 'ocr.png'
            self.process = subprocess.Popen([sys.executable, '-u', '-c',
                'import sys,time;sys.stdin.readline();time.sleep(20)'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
            self.ipc = JSONLineWorker(self.process)
        def read(self, frame):
            type(self).calls += 1
            return super().read(frame)
    result = v.scan_visual(source, v.video_spec(v.probe(source), 0), tmp_path,
                           ocr_factory=TimedOCR, ocr_timeout=.1)
    assert TimedOCR.calls == 1
    assert result['status'] == result['result'] == 'failed'
    assert result['failure_code'] == 'ocr_timeout'
    assert result['checked_frames'] == 0 and result['failed_frames'] == 1
    assert result['decoded_frames'] == 1 and not result['decoder_reached_eof']
    assert result['failure_frames'][0]['reason'] == 'ocr_timeout'


def test_language_and_timeout_cli_validation():
    parsed = v.parse_args(['input.mp4', '--output-dir', 'new', '--asr-language', 'zh', '--ocr-timeout', '.25'])
    assert parsed.asr_language == 'zh' and parsed.ocr_timeout == .25
    for switches in (['--ocr-timeout', 'nan'], ['--ocr-timeout', '0'], ['--asr-language', 'invalid']):
        with pytest.raises(SystemExit):
            v.parse_args(['input.mp4', '--output-dir', 'new', *switches])


@pytest.mark.skipif(not HAS_FFMPEG, reason='FFmpeg integration')
def test_review_passes_selected_language_to_audio(tmp_path, monkeypatch):
    source = tmp_path / 'flash.mkv'
    make_video(source)
    original_scan = v.scan_visual
    monkeypatch.setattr(v, 'scan_visual', lambda *a, **kw: original_scan(*a, **kw, ocr_factory=EmptyOCR))
    selected = []
    def audio(source, streams, **kwargs):
        selected.append(kwargs['language'])
        return {'status': 'not_applicable', 'tracks': []}
    monkeypatch.setattr(v, 'review_audio', audio)
    report = v.review(v.parse_args([str(source), '--output-dir', str(tmp_path / 'new'), '--asr-language', 'zh']))
    assert report['status'] == 'complete' and selected == ['zh']
