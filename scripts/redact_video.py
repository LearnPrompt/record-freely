#!/usr/bin/env python3
"""Local macOS OCR, motion tracking and minimal-area URL redaction."""
from __future__ import annotations

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

import cv2
import numpy as np

from review_candidates import (
    DOMAIN, SPACED_DOMAIN, ANY_DOMAIN, URL_PATTERN, FILE_EXTENSIONS,
    EMAIL_PATTERN, TLD_FILE, KNOWN_TLDS, url_spans, observation_candidates,
)


def clamp(box, width, height):
    x, y, w, h = box
    x1, y1 = max(0, int(math.floor(x))), max(0, int(math.floor(y)))
    x2, y2 = min(width, int(math.ceil(x + w))), min(height, int(math.ceil(y + h)))
    return [x1, y1, max(0, x2 - x1), max(0, y2 - y1)]


def union(boxes):
    x1, y1 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x2, y2 = max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes)
    return [x1, y1, x2 - x1, y2 - y1]


def overlap(a, b):
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    intersection = ix * iy
    return intersection / max(1, a[2] * a[3] + b[2] * b[3] - intersection)


def detection_boxes(observations, width, height, padding, metadata=None, identities=None,
                    privacy=False, review=None):
    boxes = []
    for candidate in observation_candidates(observations,width,height,padding,privacy):
        if review is not None:
            review.append({k:v for k,v in candidate.items() if k not in {'observation_index','span'}})
        if candidate['status'] != 'mask':
            continue
        padded = candidate['box']
        if any(overlap(padded,b)>.8 for b in boxes):
            continue
        boxes.append(padded)
        if metadata is not None:
            observation=observations[candidate['observation_index']]
            a,b=candidate['span']
            compact=re.sub(r"\s+", "", observation.get('text','')[a:b]).lower()
            if candidate['kind']=='qr_code':
                compact='qr:' + str(padded)
            identity=None
            if identities is not None:
                key=(candidate['kind'],compact)
                if key not in identities:
                    identities[key]=f"U{len(identities)+1:03}"
                identity=identities[key]
            metadata.append({'id':identity,'kind':candidate['kind'],
                             'box_method':candidate['box_method'],
                             'ocr_confidence':candidate['confidence'],
                             'decision':'mask','reason':candidate['reason']})
    return boxes


class VisionOCR:
    def __init__(self, scratch):
        source = Path(__file__).with_name("vision_ocr.swift")
        binary = scratch / "vision-ocr"
        run(["xcrun", "swiftc", "-O", str(source), "-o", str(binary)])
        self.process = subprocess.Popen([str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.image = scratch / "ocr.png"
        self.privacy = False

    def read(self, frame):
        if not cv2.imwrite(str(self.image), frame):
            raise RuntimeError("Could not write OCR frame")
        self.process.stdin.write(json.dumps({"path": str(self.image), "privacy": self.privacy}) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("Vision OCR worker exited unexpectedly")
        result = json.loads(line)
        if "error" in result:
            raise RuntimeError("Vision OCR failed: " + result["error"])
        return result["observations"] + result.get("codes", [])

    def close(self):
        try:
            self.process.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        finally:
            self.process.stdout.close()


def run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        # FFmpeg stderr may contain input metadata. Avoid printing arbitrary metadata.
        raise RuntimeError(f"{Path(command[0]).name} failed (exit {result.returncode}); no finished output produced")
    return result.stdout


def file_sha256(path):
    """Hash original bytes in bounded chunks without persisting media contents."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe(path):
    return json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]))


def scene_changed(before, after):
    if before is None:
        return False
    difference = cv2.absdiff(cv2.resize(before, (96, 54)), cv2.resize(after, (96, 54)))
    # Also detect a changed content panel with persistent browser chrome.
    return bool(np.mean(difference) > 38 or (np.mean(difference > 12) > .18 and np.mean(difference) > 5))


@dataclass
class Track:
    box: list
    template: np.ndarray
    age: int = 0
    details: dict = field(default_factory=dict)
    score: float = 0
    scale: float = 1


def make_track(gray, box, details=None):
    x, y, w, h = box
    return Track(list(box), gray[y:y + h, x:x + w].copy(), details=dict(details or {}))


def move_track(track, gray, radius=70):
    """Require current-frame visual evidence; never blindly retain an old box."""
    height, width = gray.shape
    x, y, w, h = track.box
    sx, sy, sw, sh = clamp([x - radius, y - radius, w + radius * 2, h + radius * 2], width, height)
    search = gray[sy:sy + sh, sx:sx + sw]
    best = None
    if track.template.size == 0 or float(track.template.std()) < 3:
        return None
    for scale in (1.0, .94, 1.06):
        tw, th = round(track.template.shape[1] * scale), round(track.template.shape[0] * scale)
        if min(tw, th) < 4 or tw > sw or th > sh:
            continue
        template = cv2.resize(track.template, (tw, th))
        response = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(response)
        if score >= .87 and (best is None or score > best[0]):
            best = (score, [sx + location[0], sy + location[1], tw, th], scale)
    if best is None:
        return None
    moved = make_track(gray, best[1], track.details)
    moved.age = track.age + 1
    moved.score, moved.scale = best[0], best[2]
    return moved


def cover(frame, boxes, style):
    result = frame.copy()
    for x, y, w, h in boxes:
        patch = result[y:y + h, x:x + w]
        if not patch.size:
            continue
        if style == "solid":
            patch[:] = (112, 112, 112)
        else:
            # Very coarse blocks; solid is preferred when text must be unreadable.
            tiny = cv2.resize(patch, (max(1, w // max(12, h)), 1), interpolation=cv2.INTER_AREA)
            patch[:] = cv2.resize(tiny, (w, h), interpolation=cv2.INTER_NEAREST)
    return result


def contact_sheet(samples, width):
    thumb_width = min(640, width)
    tiles = []
    for index, frame, boxes, fps in samples:
        annotated = frame.copy()
        for x, y, w, h in boxes:
            cv2.rectangle(annotated, (x, y), (x + w - 1, y + h - 1), (60, 180, 50), 1)
        thumb_height = round(frame.shape[0] * thumb_width / width)
        tile = cv2.resize(annotated, (thumb_width, thumb_height))
        cv2.putText(tile, f"{index / fps:.2f}s  {len(boxes)} region(s)", (8, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, .55, (40, 160, 50), 1, cv2.LINE_AA)
        tiles.append(tile)
    if len(tiles) % 2:
        tiles.append(np.full_like(tiles[0], 240))
    return np.vstack([np.hstack(tiles[i:i + 2]) for i in range(0, len(tiles), 2)])


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True, help="Must be a new directory")
    parser.add_argument("--privacy", action="store_true", help="Also mask emails, contact numbers, QR codes and identity path prefixes; unresolved candidates remain for review")
    parser.add_argument("--padding", type=int, default=4, help="Extra pixels around text; default 4")
    parser.add_argument("--detect-every", type=int, default=1, help="1 scans every frame; higher values can miss flashes")
    parser.add_argument("--ocr-workers", type=int, choices=[1, 2, 3], default=1,
                        help="Parallel local Vision workers; every frame still gets scanned")
    parser.add_argument("--hold-seconds", type=float, default=.35, help="Maximum visual tracking across OCR dropouts")
    parser.add_argument("--style", choices=["solid", "pixelate"], default="solid")
    parser.add_argument("--start", type=float, default=0, help="Preview start in seconds")
    parser.add_argument("--duration", type=float, help="Process only this many seconds")
    args = parser.parse_args()
    if not all(math.isfinite(x) for x in (args.hold_seconds, args.start)) or \
            (args.duration is not None and not math.isfinite(args.duration)):
        parser.error("time parameters must be finite numbers")
    if args.padding < 0 or args.detect_every < 1 or args.hold_seconds < 0 or args.start < 0:
        parser.error("padding, hold-seconds, start must be nonnegative; detect-every must be >= 1")
    if args.duration is not None and args.duration <= 0:
        parser.error("duration must be positive")
    return args


def main():
    args = parse_args()
    if sys.platform != "darwin":
        raise RuntimeError("This first version uses macOS Vision; macOS is required")
    for binary in ("ffmpeg", "ffprobe", "xcrun"):
        if not shutil.which(binary):
            raise RuntimeError(f"Missing required command: {binary}")
    source = args.input.resolve(strict=True)
    if args.output_dir.exists():
        raise RuntimeError("Output directory already exists; choose a new directory to preserve previous work")
    info = probe(source)
    video = next((s for s in info["streams"] if s["codec_type"] == "video"
                  and not s.get("disposition", {}).get("attached_pic")), None)
    if video is None:
        raise RuntimeError("Input has no video stream")
    numerator, denominator = map(int, video.get("avg_frame_rate", "0/1").split("/"))
    fps = numerator / denominator if denominator else 0
    if not 1 <= fps <= 120:
        raise RuntimeError("Unsupported or unavailable frame rate (expected 1–120 fps)")
    if video.get("color_transfer") in ("smpte2084", "arib-std-b67"):
        raise RuntimeError("HDR input needs an explicit SDR tone-mapping workflow; this first version accepts SDR only")
    source_stat = source.stat()
    started = time.monotonic()
    args.output_dir.mkdir(parents=True)
    report = {"status": "processing", "engine": "macOS Vision + OpenCV", "fps": fps,
              "style": args.style, "padding": args.padding, "detect_every": args.detect_every,
              "frames": [], "scene_cuts": [], "warnings": [],
              "privacy_mode": args.privacy, "review_candidates": [],
              "coverage": {"visual": {"state": "processing", "scanned_frames": 0},
                  "audio": "not_checked", "embedded_subtitles": "not_checked", "platform_rules": "not_checked"},
              "privacy": "Local only. OCR text and URL contents are not saved in the report."}
    report.update(start=args.start, selected_duration=args.duration,
                  source_sha256=file_sha256(source),
                  source_signature={"size": source_stat.st_size, "mtime_ns": source_stat.st_mtime_ns},
                  audio_policy="AAC re-encode; stream count verified, packet identity not promised")
    report["ocr_workers"] = args.ocr_workers if args.detect_every == 1 else 1
    report_path = args.output_dir / "report.json"
    progress_path = args.output_dir / "progress.json"
    progress_path.write_text(json.dumps({"stage": "normalizing", "processed_frames": 0}), encoding="utf-8")
    warnings = report["warnings"]
    warnings.append("OCR and tracking are heuristic. Inspect the preview before publication; missed links remain possible.")
    if args.detect_every > 1:
        warnings.append("Sampled OCR is enabled: links visible between detection frames may be missed.")
    if args.style == "pixelate":
        warnings.append("Pixelation is a visual effect; use solid masking for stronger text concealment.")
    warnings.append("Output uses constant frame rate and original metadata is removed.")
    capture = None
    ocr = None
    encoder = None
    ocr_pool = None
    extra_ocr = []
    scanned_frames = 0
    try:
        with tempfile.TemporaryDirectory(prefix="link-redactor-") as temp:
            scratch = Path(temp)
            # FFmpeg handles rotation, VFR and codec decoding consistently. The same
            # clipped time window is used for audio. Intermediate frames stay temporary.
            normalized = scratch / "normalized.mkv"
            decode_command = ["ffmpeg", "-v", "error", "-nostdin", "-n", "-ss", str(args.start), "-reinit_filter", "0", "-i", str(source)]
            if args.duration is not None:
                decode_command += ["-t", str(args.duration)]
            decode_command += ["-map", f"0:{video['index']}", "-an", "-vf", f"fps={fps:.10f}",
                               "-c:v", "ffv1", "-pix_fmt", "bgr0", "-map_metadata", "-1", str(normalized)]
            run(decode_command)
            capture = cv2.VideoCapture(str(normalized))
            if not capture.isOpened():
                raise RuntimeError("Could not decode normalized video")
            width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            expected = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            report.update(width=width, height=height, source_video_stream=video["index"])
            ocr = VisionOCR(scratch)
            ocr.privacy = args.privacy
            if args.detect_every == 1 and args.ocr_workers > 1:
                for worker_index in range(1, args.ocr_workers):
                    worker_dir = scratch / f"ocr-worker-{worker_index}"
                    worker_dir.mkdir()
                    extra_ocr.append(VisionOCR(worker_dir))
                    extra_ocr[-1].privacy = args.privacy
                ocr_pool = ThreadPoolExecutor(max_workers=args.ocr_workers)
            silent = scratch / "masked.mp4"
            encoder = subprocess.Popen(["ffmpeg", "-v", "error", "-nostdin", "-n", "-f", "rawvideo", "-pix_fmt", "bgr24",
                                        "-s", f"{width}x{height}", "-r", f"{fps:.10f}", "-i", "pipe:0", "-an",
                                        "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p",
                                        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-map_metadata", "-1", str(silent)],
                                       stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            tracks, previous, pending, samples = [], None, deque(), []
            identities = {}
            max_gap = max(0, round(args.hold_seconds * fps))
            lookback_frames = min(max_gap, max(0, (96 * 1024 * 1024) // (width * height * 3)))
            report.update(hold_seconds=args.hold_seconds, lookback_frames=lookback_frames,
                          tld_snapshot=TLD_FILE.read_text().splitlines()[0])
            if lookback_frames < max_gap:
                warnings.append("Look-back buffer is capped at 96 MiB; fewer earlier frames can be revisited at this resolution.")
            sample_interval = max(1, round(expected / 10))
            sample_shape = (min(640, width), round(height * min(640, width) / width))
            number = 0
            scanned_frames = 0
            future_frames = deque()
            next_frame = 0

            def prefetch():
                nonlocal next_frame
                if ocr_pool is None:
                    return
                while len(future_frames) < args.ocr_workers:
                    ok, queued_frame = capture.read()
                    if not ok:
                        break
                    worker = ([ocr] + extra_ocr)[next_frame % args.ocr_workers]
                    future_frames.append((queued_frame, ocr_pool.submit(worker.read, queued_frame)))
                    next_frame += 1

            prefetch()

            def emit(item):
                index, frame, boxes, origins, regions = item
                redacted = cover(frame, boxes, args.style)
                encoder.stdin.write(redacted.tobytes())
                report["frames"].append({"frame": index, "time": round(index / fps, 6),
                                         "boxes": boxes, "origins": origins, "regions": regions})
                if index % sample_interval == 0 and len(samples) < 12:
                    # Keep preview memory bounded even for 4K input.
                    small = cv2.resize(redacted, sample_shape)
                    ratio = sample_shape[0] / width
                    small_boxes = [clamp([v * ratio for v in b], *sample_shape) for b in boxes]
                    samples.append((index, small, small_boxes, fps))

            while True:
                if ocr_pool is not None:
                    if not future_frames:
                        break
                    frame, future = future_frames.popleft()
                    observations = future.result()
                    prefetch()
                else:
                    ok, frame = capture.read()
                    if not ok:
                        break
                    observations = None
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                cut = scene_changed(previous, gray)
                if cut:
                    report["scene_cuts"].append(number)
                    tracks = []
                    while pending:
                        emit(pending.popleft())
                details, candidates = [], []
                should_scan = number % args.detect_every == 0 or cut
                detected = detection_boxes(observations if observations is not None else ocr.read(frame),
                                           width, height, args.padding, details, identities,
                                           privacy=args.privacy, review=candidates) if should_scan else []
                for candidate in candidates:
                    report['review_candidates'].append(dict(candidate, frame=number,
                        time=round(number/fps,6), normalized_source_time=round(args.start+number/fps,6),
                        action='masked' if candidate['status']=='mask' else
                               'preserved' if candidate['status']=='keep' else 'pending'))
                scanned_frames += int(should_scan)
                current, boxes, origins = [], list(detected), ["ocr"] * len(detected)
                regions = [dict(d, origin="ocr") for d in details]
                for track in tracks:
                    if track.age >= max_gap:
                        continue
                    moved = move_track(track, gray)
                    if moved is not None and not any(overlap(moved.box, b) > .35 for b in boxes):
                        current.append(moved)
                        boxes.append(moved.box)
                        origins.append("tracked")
                        regions.append(dict(moved.details, origin="tracked", tracking_score=moved.score,
                                            relative_scale=moved.scale))
                current.extend(make_track(gray, b, d) for b, d in zip(detected, details))

                # Offline look-back covers brief OCR misses before the first
                # detection. Require a matching patch in each earlier frame.
                for box, detail in zip(detected, details):
                    backtrack = make_track(gray, box, detail)
                    for item in reversed(pending):
                        _, earlier, earlier_boxes, earlier_origins, earlier_regions = item
                        moved = move_track(backtrack, cv2.cvtColor(earlier, cv2.COLOR_BGR2GRAY))
                        if moved is None:
                            break
                        if not any(overlap(moved.box, b) > .35 for b in earlier_boxes):
                            earlier_boxes.append(moved.box)
                            earlier_origins.append("backfilled")
                            earlier_regions.append(dict(moved.details, origin="backfilled", tracking_score=moved.score,
                                                        relative_scale=moved.scale))
                        backtrack = moved
                pending.append((number, frame, boxes, origins, regions))
                if len(pending) > lookback_frames:
                    emit(pending.popleft())
                tracks, previous = current, gray
                number += 1
                if number % max(1, round(fps * 2)) == 0:
                    print(f"Processed {number}/{expected or '?'} frames", flush=True)
                    progress_path.write_text(json.dumps({"stage": "ocr_and_masking", "processed_frames": number,
                                                        "total_frames": expected, "video_seconds": number / fps,
                                                        "elapsed_seconds": round(time.monotonic() - started, 1)}), encoding="utf-8")
            while pending:
                emit(pending.popleft())
            if not number:
                raise RuntimeError("Selected time range contains no video frames")
            if expected and number != expected:
                raise RuntimeError(f"Decode incomplete: expected {expected} frames, read {number}")
            encoder.stdin.close()
            if encoder.wait() != 0:
                raise RuntimeError("Video encoding failed")
            ocr.close()
            ocr = None
            for worker in extra_ocr:
                worker.close()
            extra_ocr = []
            if ocr_pool is not None:
                ocr_pool.shutdown(wait=True)
                ocr_pool = None
            capture.release()
            capture = None
            clip_duration = number / fps
            staged_output = scratch / "redacted.mp4"
            mux = ["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(silent),
                   "-ss", str(args.start), "-i", str(source), "-map", "0:v:0", "-map", "1:a?",
                   "-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]
            source_audio_count = sum(s["codec_type"] == "audio" for s in info["streams"])
            if source_audio_count:
                # Keep delayed audio in sync and preserve tracks even when a
                # preview is entirely before/after their actual sound packets.
                mux += ["-af", f"aresample=48000:async=1:first_pts=0,apad=whole_dur={clip_duration:.10f}"]
            mux += ["-t", str(clip_duration), "-map_metadata", "-1", "-map_chapters", "-1",
                    "-movflags", "+faststart", str(staged_output)]
            run(mux)
            checked = probe(staged_output)
            out_video = next(s for s in checked["streams"] if s["codec_type"] == "video")
            if int(out_video.get("nb_frames", -1)) != number:
                raise RuntimeError("Exported video frame count did not match processed frames")
            if abs(float(out_video.get("duration", 0)) - clip_duration) > 1 / fps + .005:
                raise RuntimeError("Exported video duration did not match the processed time window")
            audio_count = sum(s["codec_type"] == "audio" for s in checked["streams"])
            if audio_count != source_audio_count:
                raise RuntimeError("Exported audio stream count did not match input")
            preview = contact_sheet(samples, samples[0][1].shape[1])
            if not cv2.imwrite(str(args.output_dir / "preview.jpg"), preview):
                raise RuntimeError("Could not save inspection preview")
            shutil.copy2(staged_output, args.output_dir / "redacted.mp4")
            if (source.stat().st_size, source.stat().st_mtime_ns) != (source_stat.st_size, source_stat.st_mtime_ns):
                raise RuntimeError("Input changed during processing")
            report.update(status="complete", processed_frames=number, duration=clip_duration,
                          masked_frames=sum(bool(f["boxes"]) for f in report["frames"]),
                          output_sha256=file_sha256(args.output_dir / 'redacted.mp4'),
                          audio_streams=audio_count, elapsed_seconds=round(time.monotonic() - started, 2),
                          verification={"frame_count": "passed", "duration": "passed", "audio_stream_count": "passed"},
                          coverage={"visual": {"state": "complete", "mode": "every_normalized_frame" if args.detect_every==1 else "sampled_plus_scene_cuts",
                              "scanned_frames": scanned_frames, "total_frames": number,
                              "timeline": "CFR normalized window; normalized_source_time = selected start + frame/fps; not original VFR PTS"},
                              "audio": "not_checked", "embedded_subtitles": "not_checked", "platform_rules": "not_checked"})
            report['review_summary']={state:sum(c['status']==state for c in report['review_candidates'])
                                      for state in ('mask','needs_review','keep')}
            report['acceptance']='needs_review' if report['review_summary']['needs_review'] else 'not_verified'
            report['warnings'].append("Export completion is not visual acceptance. Independently rescan the encoded output with review_video.py.")
    except BaseException:
        report["status"] = "failed"
        report['coverage']['visual'].update(state='failed',scanned_frames=scanned_frames)
        report['acceptance']='not_verified'
        raise
    finally:
        cleanup_errors = []
        if ocr_pool is not None:
            try:
                ocr_pool.shutdown(wait=True)
            except Exception as error:
                cleanup_errors.append("OCR pool: " + type(error).__name__)
        if capture is not None:
            try:
                capture.release()
            except Exception as error:
                cleanup_errors.append("Decoder: " + type(error).__name__)
        for worker in [ocr] + extra_ocr:
            if worker is not None:
                try:
                    worker.close()
                except Exception as error:
                    cleanup_errors.append("OCR worker: " + type(error).__name__)
        if encoder is not None and encoder.poll() is None:
            try:
                encoder.kill()
                encoder.wait()
            except Exception as error:
                cleanup_errors.append("Encoder: " + type(error).__name__)
        if cleanup_errors:
            warnings.append("Cleanup issue(s): " + "; ".join(cleanup_errors))
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        progress_path.write_text(json.dumps({"stage": report["status"], "processed_frames": len(report["frames"]),
                                            "elapsed_seconds": round(time.monotonic() - started, 1)}), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "processed_frames", "masked_frames", "elapsed_seconds")},
                     ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, FileNotFoundError, BrokenPipeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
