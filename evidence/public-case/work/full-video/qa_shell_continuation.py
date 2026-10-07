#!/usr/bin/env python3
"""Targeted URL continuation review. Never persist recognized address text."""
import argparse
import json
import math
import re
import subprocess
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

ASSETS = Path('/Users/carl/.codex/skills/video-link-redactor/scripts')
HTTP = re.compile(r'https?\s*[:：]\s*[/／]{2}', re.I)
TAIL = re.compile(r'[A-Za-z0-9._~%+/-]{4,}')
QUOTES = str.maketrans({'‘': "'", '’': "'", '“': '"', '”': '"'})


def group_rows(observations):
    rows = []
    for observation in sorted(observations, key=lambda o: (o['box'][1] + o['box'][3] / 2, o['box'][0])):
        x, y, w, h = observation['box']
        cy = y + h / 2
        match = next((row for row in reversed(rows[-3:])
                      if abs(cy - row['center_y']) <= .38 * max(h, row['height'])), None)
        if match is None:
            match = {'observations': [], 'center_y': cy, 'height': h}
            rows.append(match)
        match['observations'].append(observation)
        match['height'] = max(match['height'], h)
        match['center_y'] = sum(o['box'][1] + o['box'][3] / 2 for o in match['observations']) / len(match['observations'])
    result = []
    for row in rows:
        observations = sorted(row['observations'], key=lambda o: o['box'][0])
        text, pieces, offset = '', [], 0
        for observation in observations:
            if text:
                text += ' '
                offset += 1
            value = observation['text'].translate(QUOTES)
            pieces.append((offset, offset + len(value), observation))
            text += value
            offset += len(value)
        row.update(text=text, pieces=pieces,
                   left=min(o['box'][0] for o in observations),
                   right=max(o['box'][0] + o['box'][2] for o in observations))
        result.append(row)
    return sorted(result, key=lambda row: row['center_y'])


def unterminated_quoted_url(row):
    matches = list(HTTP.finditer(row['text']))
    if not matches:
        return None
    last = matches[-1]
    before = row['text'][:last.start()].rstrip()
    if not before or before[-1] not in "'\"":
        return None
    quote = before[-1]
    suffix = row['text'][last.start():]
    if quote in suffix:
        return None
    return quote


def prefix_geometry(row, end):
    parts, methods = [], []
    for start, stop, observation in row['pieces']:
        a, b = max(0, -start), min(end - start, stop - start)
        if b <= a:
            continue
        chars = [c for c in observation.get('chars', []) if c['start'] < b and c['end'] > a]
        if chars and all(any(c['start'] <= i < c['end'] for c in chars) for i in range(a, b)):
            parts.extend(c['box'] for c in chars)
            methods.append('reviewed_continuation_characters')
        else:
            # This exception is constrained to confirmed ASCII terminal rows.
            # Geometry for rows without a dot is omitted by the native worker.
            x, y, w, h = observation['box']
            length = max(1, stop - start)
            parts.append([x + w*a/length, y, w*(b-a)/length, h])
            methods.append('reviewed_continuation_monospace')
    if not parts:
        return None, None
    x = min(b[0] for b in parts)
    y = min(b[1] for b in parts)
    right = max(b[0] + b[2] for b in parts)
    bottom = max(b[1] + b[3] for b in parts)
    return [x, y, right-x, bottom-y], ('reviewed_continuation_characters' if all(m.endswith('characters') for m in methods)
                                      else 'reviewed_continuation_monospace')


def trim_white_line(image, box):
    height, width = image.shape[:2]
    x, y, w, h = box
    x, y = max(0, round(x)), max(0, round(y))
    right, bottom = min(width, math.ceil(x+w)), min(height, math.ceil(y+h))
    patch = image[y:bottom, x:right]
    if patch.size == 0:
        return None
    channels = patch.astype(np.int16)
    white = (channels.min(axis=2) >= 155) & ((channels.max(axis=2)-channels.min(axis=2)) <= 80)
    counts = white.sum(axis=1)
    threshold = max(3, (right-x)*.012)
    runs, first = [], None
    for i, count in enumerate(counts):
        if count >= threshold and first is None:
            first = i
        if count < threshold and first is not None:
            if i-first >= 4:
                runs.append((first, i))
            first = None
    if first is not None and len(counts)-first >= 4:
        runs.append((first, len(counts)))
    if not runs:
        return None
    # Choose the local glyph band nearest the OCR row center, never merge rows.
    top, low = min(runs, key=lambda r: abs((r[0]+r[1])/2 - len(counts)/2))
    if low-top < max(6, .2*len(counts)):
        return None
    padding = 4
    return [max(0, x-padding), max(0, y+top-padding),
            min(width, right+padding)-max(0, x-padding),
            min(height, y+low+padding)-max(0, y+top-padding)]


def candidates(observations, source_image):
    height, width = source_image.shape[:2]
    rows = group_rows(observations)
    found = []
    for previous, current in zip(rows, rows[1:]):
        quote = unterminated_quoted_url(previous)
        if not quote or previous['right'] < .985 or current['left'] > .12:
            continue
        gap = current['center_y'] - previous['center_y']
        max_height = max(previous['height'], current['height'])
        if not .55 * max_height <= gap <= 1.35 * max_height:
            continue
        if min(previous['height'], current['height']) < .65 * max_height:
            continue
        text = current['text']
        if text != text.lstrip() or not TAIL.match(text):
            continue
        closing = text.find(quote)
        # A quoted URI tail must close on this row. Do not absorb later code.
        if closing < 4 or not re.fullmatch(r'[A-Za-z0-9._~%+/-]+', text[:closing]):
            continue
        if min(o.get('confidence', 0) for _, _, o in current['pieces']) < .65:
            continue
        box, method = prefix_geometry(current, closing)
        if box is None:
            continue
        pixels = [box[0]*width, box[1]*height, box[2]*width, box[3]*height]
        cropped = trim_white_line(source_image, pixels)
        if cropped is None:
            continue
        # Identity strings remain transient and are never logged or serialized.
        identity = previous['text'][list(HTTP.finditer(previous['text']))[-1].start():] + text[:closing]
        found.append({'box': cropped, 'box_method': method,
                      'confidence': min(o.get('confidence', 0) for _, _, o in current['pieces']),
                      '_identity': identity})
    return found


class Vision:
    def __init__(self, scratch):
        self.image = Path(scratch)/'frame.png'
        binary = Path(scratch)/'vision'
        result = subprocess.run(['xcrun','swiftc','-O',str(ASSETS/'vision_ocr.swift'),'-o',str(binary)],capture_output=True)
        if result.returncode:
            raise RuntimeError('Could not compile native OCR worker')
        self.worker = subprocess.Popen([str(binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL,text=True)

    def read(self, image, maximum_width=1920):
        height, width = image.shape[:2]
        if width > maximum_width:
            image = cv2.resize(image,(maximum_width,round(height*maximum_width/width)))
        cv2.imwrite(str(self.image),image)
        self.worker.stdin.write(json.dumps({'path':str(self.image)})+'\n')
        self.worker.stdin.flush()
        data = json.loads(self.worker.stdout.readline())
        if 'error' in data:
            raise RuntimeError('Native OCR failed')
        return data['observations']

    def close(self):
        self.worker.stdin.close()
        self.worker.wait(timeout=20)
        self.worker.stdout.close()


def build(source, output, start=570, end=645, scout_step=150, expand_frames=150, scan_all=False):
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError('Could not open source video')
    fps = capture.get(cv2.CAP_PROP_FPS)
    first, last = round(start*fps), round(end*fps)
    identities, frame_records, scout, intervals = {}, {}, [], []
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='qa-shell-') as scratch:
        ocr = Vision(scratch)
        try:
            # The whole approved window is only sampled to establish where the
            # exact paired-line pattern exists. Other scenes are never patched.
            for number in sorted(set(range(first,last,scout_step)) | {18000}):
                if not first <= number < last:
                    continue
                capture.set(cv2.CAP_PROP_POS_FRAMES,number)
                ok,image = capture.read()
                if not ok:
                    raise RuntimeError('Could not read scout frame')
                found = candidates(ocr.read(image),image)
                scout.append({'frame':number,'time':number/fps,'continuation_count':len(found),
                              'boxes':[f['box'] for f in found]})
                if found:
                    intervals.append((max(first,number-expand_frames),min(last,number+expand_frames+1)))
                print(json.dumps({'stage':'scout','frame':number,'boxes':len(found)}),flush=True)
            if scan_all:
                intervals = [(first,last)]
            windows = []
            for a,b in sorted(intervals):
                if windows and a <= windows[-1][1]:
                    windows[-1][1] = max(windows[-1][1],b)
                else:
                    windows.append([a,b])
            for a,b in windows:
                capture.set(cv2.CAP_PROP_POS_FRAMES,a)
                for number in range(a,b):
                    ok,image = capture.read()
                    if not ok:
                        raise RuntimeError('Could not read continuation frame')
                    found = candidates(ocr.read(image),image)
                    for patch in found:
                        identity = patch.pop('_identity')
                        if identity not in identities:
                            identities[identity] = f'C{len(identities)+1:03}'
                        patch.update(id=identities[identity],kind='url_continuation',origin='review_url_continuation',
                                     review_basis='Manually confirmed terminal URL-list window; preceding row has quoted unclosed HTTP URL at right viewport edge; adjacent row URI prefix ends at the first matching quote; white glyph row plus 4px padding')
                        frame_records.setdefault(str(number),[]).append(patch)
                    if number % 30 == 0:
                        print(json.dumps({'stage':'review','frame':number,'frames_with_patches':len(frame_records)}),flush=True)
        finally:
            ocr.close()
            capture.release()
    data = {'schema_version':1,'fps':fps,'source_time_reference':'Original video global frame',
            'reviewed_window_seconds':[start,end],'scout_frames':scout,'scanned_frame_windows':windows,
            'method':'Targeted paired-line native OCR plus white-glyph row trim; only URI continuation before closing quote',
            'scope':'Manual review supplement; not generic file/path redaction; unsampled or unmatched continuation cases can remain',
            'elapsed_seconds':round(time.monotonic()-started,2),'frames':frame_records,
            'patched_frame_count':len(frame_records),'patch_count':sum(map(len,frame_records.values()))}
    Path(output).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'patched_frames':data['patched_frame_count'],'patches':data['patch_count'],
                      'scanned_windows':windows}),flush=True)
    return data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path('/Users/carl/Downloads/带封面.mp4'))
    parser.add_argument('--output',type=Path,default=Path(__file__).with_name('qa_shell_boxes.json'))
    parser.add_argument('--start',type=float,default=570)
    parser.add_argument('--end',type=float,default=645)
    parser.add_argument('--scout-step',type=int,default=150)
    parser.add_argument('--expand-frames',type=int,default=150)
    parser.add_argument('--scan-all',action='store_true')
    args=parser.parse_args()
    build(args.source,args.output,args.start,args.end,args.scout_step,args.expand_frames,args.scan_all)


if __name__=='__main__':
    main()
