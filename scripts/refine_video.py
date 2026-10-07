#!/usr/bin/env python3
"""Re-render a source video from anonymous rectangles; optional stabilization/review."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

import numpy as np
from redact_video import cover, file_sha256, probe, run
from stabilize_masks import stabilize_records


def validate_box(box, width, height):
    if not isinstance(box, list) or len(box) != 4 or any(type(x) is not int for x in box):
        raise ValueError("Rectangle must contain four integer pixel coordinates")
    x, y, w, h = box
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
        raise ValueError("Rectangle outside source frame")
    return list(box)


def validate_report(report):
    if report.get("status") != "complete":
        raise ValueError("Expected a completed automatic report")
    width, height, fps = report["width"], report["height"], report["fps"]
    if type(width) is not int or type(height) is not int or min(width, height) <= 0:
        raise ValueError("Invalid frame dimensions")
    if not isinstance(fps, (int, float)) or not math.isfinite(fps) or not 1 <= fps <= 120:
        raise ValueError("Invalid frame rate")
    records = report["frames"]
    if not records or len(records) != report["processed_frames"]:
        raise ValueError("Report frame count is incomplete")
    for i, f in enumerate(records):
        if type(f.get("frame")) is not int or f["frame"] != i:
            raise ValueError("Expected dense, zero-based frame indexes within selected clip")
        if len(f["boxes"]) != len(f["regions"]) or len(f["boxes"]) != len(f["origins"]):
            raise ValueError("Inconsistent region metadata")
        for b in f["boxes"]:
            validate_box(b, width, height)
    return width, height, fps


def apply_patch(report, patch, report_hash):
    """Explicit complete replacement per local frame, bound to reviewed baseline."""
    if patch.get("version") != 1 or patch.get("source_report_sha256") != report_hash:
        raise ValueError("Review patch must match this exact report SHA256 and version 1")
    if not isinstance(patch.get("frames"), dict):
        raise ValueError("Patch frames must be an object")
    result = copy.deepcopy(report)
    for key, op in patch["frames"].items():
        if not isinstance(key, str) or not key.isdecimal() or str(int(key)) != key:
            raise ValueError("Patch frame keys must be canonical nonnegative integers")
        index = int(key)
        if not 0 <= index < len(result["frames"]):
            raise ValueError("Review frame outside selected clip")
        if set(op) != {"boxes"} or not isinstance(op["boxes"], list):
            raise ValueError("Only explicit boxes replacements are supported")
        boxes = [validate_box(b, report["width"], report["height"]) for b in op["boxes"]]
        frame = result["frames"][index]
        frame["boxes"] = boxes
        frame["origins"] = ["human_review"] * len(boxes)
        frame["regions"] = [dict(id=f"R{index:07}-{n}", kind="reviewed_rectangle",
                                  origin="human_review", preserve_review_bounds=True)
                            for n in range(len(boxes))]
    return result


def read_exact(pipe, size):
    chunks, received = [], 0
    while received < size:
        chunk = pipe.read(size - received)
        if not chunk:
            break
        chunks.append(chunk)
        received += len(chunk)
    if received != size:
        raise RuntimeError("Source decoder ended before all reviewed frames")
    return b"".join(chunks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Original source used by the automatic report")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="Must not already exist")
    parser.add_argument("--stabilize", action="store_true", help="Coverage-safe envelopes within observed scene runs")
    parser.add_argument("--patch", type=Path, help="SHA-bound reviewed per-frame rectangle replacements")
    args = parser.parse_args()
    started = time.monotonic()
    source = args.input.resolve(strict=True)
    if args.output_dir.exists():
        raise ValueError("Output directory already exists")
    raw = args.report.read_bytes()
    baseline_hash = hashlib.sha256(raw).hexdigest()
    report = json.loads(raw)
    width, height, fps = validate_report(report)
    signature = {"size": source.stat().st_size, "mtime_ns": source.stat().st_mtime_ns}
    expected_hash = report.get("source_sha256")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64 or any(c not in "0123456789abcdef" for c in expected_hash):
        raise ValueError("Report lacks a valid source SHA256; rerun the packaged automatic engine")
    if file_sha256(source) != expected_hash:
        raise ValueError("Source SHA256 does not match automatic report; refusing unrelated media")
    report["refinement_original_source_signature"] = report.get("source_signature")
    report["source_signature"] = signature
    start = report.get("start", 0)
    if not isinstance(start, (int, float)) or not math.isfinite(start) or start < 0:
        raise ValueError("Invalid selected clip start")
    # Stabilize before applying reviewed bounds, so reviewed suffixes never expand again.
    if args.stabilize:
        report["frames"], stats = stabilize_records(report["frames"], width, height, report.get("scene_cuts", []))
        report["stability_statistics"] = stats
    if args.patch:
        report = apply_patch(report, json.loads(args.patch.read_bytes()), baseline_hash)
        report["review_patch_sha256"] = hashlib.sha256(args.patch.read_bytes()).hexdigest()
    validate_report(report)
    source_info = probe(source)
    source_audio_count = sum(s["codec_type"] == "audio" for s in source_info["streams"])
    frame_count = len(report["frames"])
    duration = frame_count / fps
    args.output_dir.mkdir(parents=True)
    decoder = encoder = None
    report.update(status="processing", refinement_baseline_sha256=baseline_hash,
                  refinement_style="solid", publication_review_required=True)
    try:
        with tempfile.TemporaryDirectory(prefix="record-freely-refine-") as temp:
            scratch = Path(temp)
            decode = ["ffmpeg", "-v", "error", "-nostdin", "-ss", str(start), "-reinit_filter", "0", "-i", str(source),
                      "-map", f"0:{report['source_video_stream']}", "-an", "-vf", f"fps={fps:.10f}",
                      "-frames:v", str(frame_count), "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1"]
            decoder = subprocess.Popen(decode, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            silent = scratch / "masked.mp4"
            encoder = subprocess.Popen(["ffmpeg", "-v", "error", "-nostdin", "-n", "-f", "rawvideo", "-pix_fmt", "bgr24",
                                        "-s", f"{width}x{height}", "-r", f"{fps:.10f}", "-i", "pipe:0", "-an",
                                        "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p",
                                        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-map_metadata", "-1", str(silent)],
                                       stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            for record in report["frames"]:
                frame = np.frombuffer(read_exact(decoder.stdout, width * height * 3), np.uint8).reshape(height, width, 3)
                encoder.stdin.write(cover(frame, record["boxes"], "solid").tobytes())
            decoder.stdout.close()
            encoder.stdin.close()
            if decoder.wait() or encoder.wait():
                raise RuntimeError("Decode or encoding failed")
            staged = scratch / "redacted.mp4"
            mux = ["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(silent), "-ss", str(start), "-i", str(source),
                   "-map", "0:v:0", "-map", "1:a?", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]
            if source_audio_count:
                mux += ["-af", f"aresample=48000:async=1:first_pts=0,apad=whole_dur={duration:.10f}"]
            mux += ["-t", str(duration), "-map_metadata", "-1", "-map_chapters", "-1", "-movflags", "+faststart", str(staged)]
            run(mux)
            info = probe(staged)
            video = next(s for s in info["streams"] if s["codec_type"] == "video")
            if int(video.get("nb_frames", -1)) != frame_count or abs(float(video.get("duration", 0)) - duration) > 1 / fps + .005:
                raise RuntimeError("Export frame count/duration did not match report")
            if sum(s["codec_type"] == "audio" for s in info["streams"]) != source_audio_count:
                raise RuntimeError("Export audio stream count changed")
            run(["ffmpeg", "-v", "error", "-xerror", "-nostdin", "-i", str(staged), "-f", "null", "-"])
            if signature != {"size": source.stat().st_size, "mtime_ns": source.stat().st_mtime_ns}:
                raise RuntimeError("Source changed during rendering")
            shutil.copy2(staged, args.output_dir / "redacted.mp4")
            report.update(status="complete", masked_frames=sum(bool(f["boxes"]) for f in report["frames"]),
                          refinement_elapsed_seconds=round(time.monotonic() - started, 2),
                          refinement_verification={"frame_count": True, "duration": True, "audio_stream_count": True,
                                                   "full_codec_decode": True, "source_signature_unchanged": True,
                                                   "source_sha256_bound_before_render": True})
    except BaseException:
        report["status"] = "failed"
        raise
    finally:
        for process in (decoder, encoder):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
        (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "processed_frames", "masked_frames", "refinement_elapsed_seconds")}))


if __name__ == "__main__":
    main()
