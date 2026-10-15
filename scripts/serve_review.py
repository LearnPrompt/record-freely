#!/usr/bin/env python3
"""Serve a SHA-bound video and actual-mask timeline on 127.0.0.1 only."""
import argparse
from fractions import Fraction
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from build_review_timeline import build, digest, integer

ASSETS = Path(__file__).resolve().parent.parent / 'assets' / 'review-viewer'
CATEGORY = re.compile(r'[a-z][a-z0-9_-]{0,48}\Z')


def prepare(video, timeline_path, manifest_path=None):
    """Validate supplied files; expose numeric, anonymized selection data only."""
    video = Path(video).resolve(strict=True)
    if not video.is_file():
        raise ValueError('Video must be a regular file')
    timeline = json.loads(Path(timeline_path).read_text(encoding='utf-8'))
    if timeline.get('schema_version') != 1:
        raise ValueError('Unsupported timeline schema')
    sha = timeline.get('encoded_sha256', '')
    if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
        raise ValueError('Timeline requires an encoded SHA256')
    if digest(video) != sha:
        raise ValueError('Video SHA256 differs from reviewed timeline')
    fps = Fraction(str(timeline['fps']))
    frames = integer(timeline['output_frames'])
    if not 0 < fps <= 120 or frames <= 0:
        raise ValueError('Invalid CFR rate or frame count')
    rows = []
    last = 0
    for r in timeline['intervals']:
        a, b = integer(r['start_frame']), integer(r['end_frame'])
        sa, sb = integer(r['source_start_frame']), integer(r['source_end_frame'])
        if not last <= a < b <= frames or sa < a or sb - sa != b - a:
            raise ValueError('Invalid interval or source mapping')
        rows.append({'start_frame': a, 'end_frame': b,
                     'source_start_frame': sa, 'source_end_frame': sb})
        last = b
    events, cuts, checkpoints = [], None, []
    if manifest_path:
        manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
        rebuilt = build(manifest)
        if (rebuilt['encoded_sha256'] != sha or rebuilt['fps'] != str(fps)
                or rebuilt['output_frames'] != frames):
            raise ValueError('Manifest does not match timeline version')
        rebuilt_rows = [{k: r[k] for k in rows[0]} for r in rebuilt['intervals']] if rows else []
        if len(rebuilt['intervals']) != len(rows) or rebuilt_rows != rows:
            raise ValueError('Manifest intervals do not match reviewed timeline')
        cuts = manifest.get('source_cuts', [])
        for e in manifest['events']:
            if e['role'] != 'local_redaction':
                continue
            category = e.get('category', e.get('kind', 'local'))
            if not isinstance(category, str) or not CATEGORY.fullmatch(category):
                category = 'local'
            events.append({'start_frame': e['start_frame'], 'end_frame': e['end_frame'],
                           'category': category})
        for f in manifest.get('checkpoints', []):
            f = integer(f)
            if not 0 <= f < frames:
                raise ValueError('Checkpoint lies outside encoded video')
            checkpoints.append(f)
    data = {'schema_version': 1, 'encoded_sha256': sha, 'fps': str(fps),
            'output_frames': frames, 'intervals': rows, 'events': events,
            'source_cuts': cuts, 'checkpoints': sorted(set(checkpoints)),
            'video_sha_verified': True,
            'scope': 'Reviewed local redactions; not proof that all private content was detected'}
    return video, data


def byte_range(header, size):
    """Single RFC byte range. Unsupported/malformed ranges fail with 416."""
    if header is None:
        return 0, size - 1, 200
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', header)
    if not match or not any(match.groups()) or size <= 0:
        raise ValueError('Unsatisfiable range')
    left, right = match.groups()
    if left:
        start = int(left)
        end = min(int(right), size - 1) if right else size - 1
    else:
        length = int(right)
        if length <= 0:
            raise ValueError('Unsatisfiable range')
        start, end = max(0, size - length), size - 1
    if start >= size or end < start:
        raise ValueError('Unsatisfiable range')
    return start, end, 206


def make_server(video, data, port=8767):
    """Only these fixed resources are available; never serve task directories."""
    video = Path(video).resolve(strict=True)
    initial = video.stat()
    signature = (initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns, initial.st_ctime_ns)
    static = {'/': ('text/html; charset=utf-8', (ASSETS / 'index.html').read_bytes()),
              '/index.html': ('text/html; charset=utf-8', (ASSETS / 'index.html').read_bytes()),
              '/viewer.js': ('text/javascript; charset=utf-8', (ASSETS / 'viewer.js').read_bytes()),
              '/viewer.css': ('text/css; charset=utf-8', (ASSETS / 'viewer.css').read_bytes()),
              '/timeline.json': ('application/json; charset=utf-8', json.dumps(data).encode()),
              '/health': ('application/json', b'{"ready":true,"video_sha_verified":true}')}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.serve(True)

        def do_HEAD(self):
            self.serve(False)

        def fail(self, status, body):
            payload = body.encode()
            self.send_response(status)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(payload)

        def serve(self, body):
            allowed_hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            if self.headers.get('Host') not in allowed_hosts:
                self.fail(403, 'Only localhost requests are allowed')
                return
            route = unquote(urlsplit(self.path).path)
            if route in static:
                content_type, payload = static[route]
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(payload)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; media-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
                self.end_headers()
                if body:
                    self.wfile.write(payload)
                return
            if route != '/video':
                self.fail(404, 'Not found')
                return
            try:
                # Open once, then verify this exact handle to avoid path-swap races.
                with video.open('rb') as stream:
                    import os
                    current = os.fstat(stream.fileno())
                    now = (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns)
                    if now != signature:
                        self.fail(409, 'Video changed; restart to verify its SHA256')
                        return
                    size = current.st_size
                    try:
                        start, end, status = byte_range(self.headers.get('Range'), size)
                    except (ValueError, OverflowError):
                        self.send_response(416)
                        self.send_header('Content-Range', f'bytes */{size}')
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                    self.send_response(status)
                    self.send_header('Content-Type', mimetypes.guess_type(video.name)[0] or 'application/octet-stream')
                    self.send_header('Accept-Ranges', 'bytes')
                    self.send_header('Content-Length', str(end - start + 1))
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    if status == 206:
                        self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                    self.end_headers()
                    if body:
                        stream.seek(start)
                        remaining = end - start + 1
                        while remaining:
                            chunk = stream.read(min(256 * 1024, remaining))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
            except FileNotFoundError:
                self.fail(409, 'Video missing; restart after selecting the reviewed file')
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_):
            pass

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--timeline-json', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, help='Original anonymized reviewed manifest for categories and complete cut mapping')
    parser.add_argument('--port', type=int, default=8767)
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error('Port must be 0..65535 (0 chooses a free port)')
    video, data = prepare(args.video, args.timeline_json, args.manifest)
    with make_server(video, data, args.port) as server:
        print(f'http://127.0.0.1:{server.server_port}/', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
