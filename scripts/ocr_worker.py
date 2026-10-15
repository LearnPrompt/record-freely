"""Deadline-bound JSON-line IPC for one owned local OCR subprocess."""
from __future__ import annotations
import json
import math
import os
import selectors
import subprocess
import threading
import time


class OCRWorkerError(RuntimeError):
    """Fatal IPC failure: the worker cannot be reused after this exception."""


def positive_timeout(value):
    timeout = float(value)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('OCR timeout must be finite and positive')
    return timeout


def valid_ocr_response(result, auxiliary):
    """Validate IPC structure without rejecting extra observation metadata."""
    def rectangle(value, *, allow_empty=False):
        return (isinstance(value, list) and len(value) == 4
                and all(type(v) in (int, float) and math.isfinite(v) for v in value)
                and (min(value[2:]) >= 0 if allow_empty else min(value[2:]) > 0))

    def observation(value):
        if not isinstance(value, dict) or not isinstance(value.get('text'), str) or not rectangle(value.get('box')):
            return False
        if 'confidence' in value and (type(value['confidence']) not in (int, float) or not math.isfinite(value['confidence'])):
            return False
        if 'chars' in value:
            chars = value['chars']
            if not isinstance(chars, list):
                return False
            for char in chars:
                if (not isinstance(char, dict) or type(char.get('start')) is not int
                        or type(char.get('end')) is not int or not rectangle(char.get('box'), allow_empty=True)):
                    return False
        return True

    if not isinstance(result, dict) or not isinstance(result.get('observations'), list):
        return False
    if not all(observation(value) for value in result['observations']):
        return False
    for key in ('codes', 'barcodes'):
        if key in result and (not isinstance(result[key], list) or not all(
                isinstance(value, dict) and rectangle(value.get('box')) for value in result[key])):
            return False
    return True


class JSONLineWorker:
    def __init__(self, process, timeout=60.):
        self.process = process
        self.timeout = positive_timeout(timeout)
        self.failed = False
        self._lock = threading.Lock()
        for stream in (process.stdin, process.stdout):
            os.set_blocking(stream.fileno(), False)

    def abort(self):
        # Only this Popen child is terminated; never process-name/global kills.
        self.failed = True
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1.)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1.)

    def request(self, payload):
        with self._lock:
            if self.failed:
                raise OCRWorkerError('ocr_worker_unavailable')
            deadline = time.monotonic() + positive_timeout(self.timeout)
            data = (json.dumps(payload) + '\n').encode('utf-8')
            sent = 0
            response = bytearray()
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(self.process.stdin, selectors.EVENT_WRITE)
                    selector.register(self.process.stdout, selectors.EVENT_READ)
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise OCRWorkerError('ocr_timeout')
                        events = selector.select(remaining)
                        if not events:
                            raise OCRWorkerError('ocr_timeout')
                        for key, _ in events:
                            if key.fileobj is self.process.stdin:
                                try:
                                    sent += os.write(key.fd, data[sent:sent + 4096])
                                except BlockingIOError:
                                    continue
                                if sent == len(data):
                                    selector.unregister(self.process.stdin)
                            else:
                                try:
                                    chunk = os.read(key.fd, 65536)
                                except BlockingIOError:
                                    continue
                                if not chunk:
                                    raise OCRWorkerError('ocr_worker_exited')
                                response.extend(chunk)
                                if len(response) > 16 * 1024 * 1024:
                                    raise OCRWorkerError('ocr_response_too_large')
                                if b'\n' in response:
                                    result = json.loads(response.split(b'\n', 1)[0])
                                    if not isinstance(result, dict):
                                        raise OCRWorkerError('ocr_invalid_response')
                                    if 'error' in result:
                                        raise OCRWorkerError('ocr_frame_failed')
                                    return result
            except (OSError, ValueError, OCRWorkerError) as error:
                self.abort()
                if isinstance(error, OCRWorkerError):
                    raise
                raise OCRWorkerError('ocr_ipc_failed') from None

    def close(self):
        self.abort()
        for stream in (self.process.stdin, self.process.stdout):
            if stream and not stream.closed:
                stream.close()
