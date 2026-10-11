"""Real subprocess regressions for alive-but-unresponsive OCR workers."""
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from ocr_worker import JSONLineWorker, OCRWorkerError, positive_timeout
from redact_video import VisionOCR


def worker(code, timeout=.2):
    process = subprocess.Popen([sys.executable, '-u', '-c', code], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
    return JSONLineWorker(process, timeout)


@pytest.mark.parametrize('value', ['nan', 'inf', '-inf', '0', '-1'])
def test_invalid_deadline_rejected(value):
    with pytest.raises(ValueError):
        positive_timeout(value)


@pytest.mark.parametrize('code,payload,reason', [
    ('import sys,time; sys.stdin.readline(); time.sleep(20)', {'path': 'frame.png'}, 'ocr_timeout'),
    ('import sys,time; sys.stdin.readline(); sys.stdout.write("{\\\"observations\\\": ["); sys.stdout.flush(); time.sleep(20)', {}, 'ocr_timeout'),
    ('import time; time.sleep(20)', {'path': 'x' * 2_000_000}, 'ocr_timeout'),
    ('import sys; sys.stdin.readline(); sys.exit(0)', {}, 'ocr_worker_exited'),
    ('import sys; sys.stdin.readline(); print("not-json")', {}, 'ocr_ipc_failed'),
])
def test_deadline_covers_write_partial_line_and_read_and_never_reuses_worker(code, payload, reason):
    ipc = worker(code)
    started = time.monotonic()
    try:
        with pytest.raises(OCRWorkerError, match=reason):
            ipc.request(payload)
        assert time.monotonic() - started < 2.
        assert ipc.process.poll() is not None
        again = time.monotonic()
        with pytest.raises(OCRWorkerError, match='ocr_worker_unavailable'):
            ipc.request(payload)
        assert time.monotonic() - again < .1
    finally:
        ipc.close()


def test_fragmented_success_and_owned_abort_preserve_other_process():
    ipc = worker('import sys,time; sys.stdin.readline(); sys.stdout.write("{\\\"observations\\\":"); sys.stdout.flush(); time.sleep(.02); print("[]}")')
    unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'])
    try:
        assert ipc.request({}) == {'observations': []}
        ipc.close()
        assert unrelated.poll() is None
    finally:
        ipc.close()
        unrelated.terminate()
        unrelated.wait(timeout=2)


@pytest.mark.parametrize('class_name', ['VisionOCR', 'ReviewOCR'])
def test_both_ocr_adapters_have_bounded_alive_worker_read(tmp_path, class_name):
    if class_name == 'ReviewOCR':
        from review_video import ReviewOCR
        cls = ReviewOCR
    else:
        cls = VisionOCR
    adapter = cls.__new__(cls)
    adapter.ipc = worker('import sys,time; sys.stdin.readline(); time.sleep(20)')
    adapter.process = adapter.ipc.process
    adapter.timeout = .2
    adapter.privacy = True
    adapter.image = tmp_path / 'frame.png'
    try:
        with pytest.raises(OCRWorkerError, match='ocr_timeout'):
            adapter.read(np.zeros((12, 12, 3), np.uint8))
        assert adapter.process.poll() is not None
    finally:
        adapter.close()


@pytest.mark.parametrize('class_name,auxiliary', [('VisionOCR', 'codes'), ('ReviewOCR', 'barcodes')])
@pytest.mark.parametrize('response', [
    {}, {'wrong': []}, {'observations': None}, {'observations': {}},
    {'observations': ['not-an-observation']}, {'observations': [{}]},
    {'observations': [{'text': 'README.md', 'box': [.1, .1, 'wide', .1]}]},
    {'observations': [{'text': 'README.md', 'box': [.1, .1, .8, .1], 'chars': {}}]},
    {'observations': [], 'auxiliary': None}, {'observations': [], 'auxiliary': {}},
    {'observations': [], 'auxiliary': [{}]},
    {'observations': [], 'codes': None}, {'observations': [], 'barcodes': None},
])
def test_adapters_reject_invalid_response_schema_and_abort(tmp_path, class_name, auxiliary, response):
    from review_video import ReviewOCR
    cls = VisionOCR if class_name == 'VisionOCR' else ReviewOCR
    response = dict(response)
    if 'auxiliary' in response:
        response[auxiliary] = response.pop('auxiliary')
    adapter = cls.__new__(cls)
    code = 'import sys,json,time;sys.stdin.readline();print(' + repr(json.dumps(response)) + ');time.sleep(20)'
    adapter.ipc = worker(code, timeout=1)
    adapter.process = adapter.ipc.process
    adapter.timeout = 1.
    adapter.privacy = True
    adapter.image = tmp_path / 'frame.png'
    try:
        with pytest.raises(OCRWorkerError, match='ocr_invalid_response'):
            adapter.read(np.zeros((12, 12, 3), np.uint8))
        assert adapter.process.poll() is not None
        with pytest.raises(OCRWorkerError, match='ocr_worker_unavailable'):
            adapter.read(np.zeros((12, 12, 3), np.uint8))
    finally:
        adapter.close()


@pytest.mark.parametrize('class_name,auxiliary', [('VisionOCR', 'codes'), ('ReviewOCR', 'barcodes')])
@pytest.mark.parametrize('observations', [[], [{
    'text': 'README.md', 'box': [.1, .1, .8, .1], 'confidence': .99,
    'geometry_engine': 'vision_fast', 'geometry_only': True,
    'chars': [{'start': 0, 'end': 1, 'box': [0, 0, 0, 0]}], 'extra_field': 'future-metadata',
}]])
def test_adapters_accept_empty_and_extended_observation_schema(tmp_path, class_name, auxiliary, observations):
    from review_video import ReviewOCR
    cls = VisionOCR if class_name == 'VisionOCR' else ReviewOCR
    response = {'observations': observations, auxiliary: []}
    adapter = cls.__new__(cls)
    code = 'import sys;sys.stdin.readline();print(' + repr(json.dumps(response)) + ')'
    adapter.ipc = worker(code, timeout=1)
    adapter.process = adapter.ipc.process
    adapter.timeout = 1.
    adapter.privacy = True
    adapter.image = tmp_path / 'frame.png'
    try:
        result = adapter.read(np.zeros((12, 12, 3), np.uint8))
        assert result == (observations if class_name == 'VisionOCR' else response)
    finally:
        adapter.close()
