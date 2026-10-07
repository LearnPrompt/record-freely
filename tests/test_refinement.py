import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from refine_video import apply_patch, validate_report
from stabilize_masks import stabilize_records
import redact_video as r


def record(n, box):
    boxes = [] if box is None else [box]
    return dict(frame=n, time=n / 30, boxes=boxes, origins=["ocr"] * len(boxes),
                regions=[dict(id="U001", kind="domain", origin="ocr")] * len(boxes))


def baseline():
    return dict(status="complete", width=100, height=60, fps=30, processed_frames=2,
                frames=[record(0, [10, 10, 30, 10]), record(1, [11, 10, 29, 10])])


def test_stable_envelope_covers_jitter_without_hold_and_respects_scene_cuts():
    frames = [record(n, [10 + n % 2, 10, 30, 10]) for n in range(7)]
    frames.append(record(7, None))
    frames.extend(record(n, [12, 10, 30, 10]) for n in range(8, 15))
    original = copy.deepcopy(frames)
    result, _ = stabilize_records(frames, 100, 60, [10])
    assert frames == original
    assert result[7]["boxes"] == []
    assert len({tuple(f["boxes"][0]) for f in result[:7]}) == 1
    for old, new in zip(frames, result):
        for x, y, w, h in old["boxes"]:
            assert any(a <= x and b <= y and a + c >= x + w and b + d >= y + h
                       for a, b, c, d in new["boxes"])
    # Scene cut resets the envelope even if anonymous URL identity stays identical.
    frames = [record(n, [10 if n < 7 else 15, 10, 30, 10]) for n in range(14)]
    result, _ = stabilize_records(frames, 100, 60, [7])
    assert result[6]["boxes"] == [[10, 10, 30, 10]]
    assert result[7]["boxes"] == [[15, 10, 30, 10]]


def test_global_index_gaps_do_not_create_or_extend_masks():
    frames = [record(0, [10, 10, 30, 10]), record(20, [15, 10, 30, 10])]
    result, stats = stabilize_records(frames, 100, 60)
    assert [f["frame"] for f in result] == [0, 20]
    assert len(stats["segments"]) == 2


def test_moving_envelopes_cover_each_observed_rectangle():
    frames = [record(n, [5 + 3 * n, 12 + n, 20 + n % 3, 10]) for n in range(16)]
    result, _ = stabilize_records(frames, 100, 60)
    for old, new in zip(frames, result):
        x, y, w, h = old["boxes"][0]
        a, b, c, d = new["boxes"][0]
        assert a <= x and b <= y and a + c >= x + w and b + d >= y + h


def test_review_is_sha_bound_and_narrow_bounds_remain_exact():
    original = baseline()
    patch = dict(version=1, source_report_sha256="a" * 64, frames={"0": {"boxes": [[10, 10, 10, 10]]}})
    with pytest.raises(ValueError):
        apply_patch(original, patch, "b" * 64)
    result = apply_patch(original, patch, "a" * 64)
    assert original["frames"][0]["boxes"] == [[10, 10, 30, 10]]
    result["frames"] = [copy.deepcopy(f) for _ in range(4) for f in result["frames"]]
    for n, f in enumerate(result["frames"]):
        f["frame"] = n
    stable, _ = stabilize_records(result["frames"], 100, 60)
    assert stable[0]["boxes"] == [[10, 10, 10, 10]]


@pytest.mark.parametrize("boxes", [[[True, 1, 2, 3]], [[-1, 1, 2, 3]], [[99, 1, 2, 3]], [[0, 0, 0, 1]], [[0, 0, 1.5, 2]]])
def test_bad_review_rectangles_rejected(boxes):
    patch = dict(version=1, source_report_sha256="a" * 64, frames={"0": {"boxes": boxes}})
    with pytest.raises(ValueError):
        apply_patch(baseline(), patch, "a" * 64)


def test_sparse_or_duplicated_report_rejected():
    report = baseline()
    report["frames"][1]["frame"] = 0
    with pytest.raises(ValueError):
        validate_report(report)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS engine export integration")
@pytest.mark.parametrize("use_copy", [False, True])
def test_refine_cli_preserves_input_and_review_bounds_with_audio(tmp_path, monkeypatch, use_copy):
    source = tmp_path / "source.mkv"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=30:duration=0.4",
                    "-f", "lavfi", "-i", "sine=frequency=800:duration=0.4", "-c:v", "ffv1", "-c:a", "pcm_s16le", str(source)], check=True)
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    class FakeOCR:
        def __init__(self, scratch): pass
        def read(self, frame): return []
        def close(self): pass
    monkeypatch.setattr(r, "VisionOCR", FakeOCR)
    automatic = tmp_path / "auto"
    monkeypatch.setattr(sys, "argv", ["redact_video.py", str(source), "--output-dir", str(automatic)])
    r.main()
    raw = (automatic / "report.json").read_bytes()
    patch = tmp_path / "patch.json"
    patch.write_text(json.dumps(dict(version=1, source_report_sha256=hashlib.sha256(raw).hexdigest(),
                                    frames={"0": {"boxes": [[4, 4, 12, 8]]}, "1": {"boxes": []}})))
    refine_source = source
    if use_copy:
        import os
        refine_source = tmp_path / "copied-identical.mkv"
        refine_source.write_bytes(source.read_bytes())
        os.utime(refine_source, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns - 1000000))
        assert refine_source.stat().st_mtime_ns != source.stat().st_mtime_ns
    refined = tmp_path / "refined"
    script = Path(__file__).resolve().parents[1] / "scripts" / "refine_video.py"
    subprocess.run([sys.executable, str(script), str(refine_source), "--report", str(automatic / "report.json"),
                    "--stabilize", "--patch", str(patch), "--output-dir", str(refined)], check=True)
    report = json.loads((refined / "report.json").read_text())
    assert report["status"] == "complete"
    assert all(report["refinement_verification"].values())
    assert report["source_sha256"] == checksum
    assert report["source_signature"]["mtime_ns"] == refine_source.stat().st_mtime_ns
    if use_copy:
        assert report["refinement_original_source_signature"]["mtime_ns"] != report["source_signature"]["mtime_ns"]
    assert report["frames"][0]["boxes"] == [[4, 4, 12, 8]]
    assert report["frames"][1]["boxes"] == []
    assert hashlib.sha256(source.read_bytes()).hexdigest() == checksum
    assert sum(s["codec_type"] == "audio" for s in r.probe(refined / "redacted.mp4")["streams"]) == 1


@pytest.mark.parametrize("missing_hash", [False, True])
def test_same_size_mtime_unrelated_source_rejected_before_probe_or_output(tmp_path, monkeypatch, missing_hash):
    import os
    import refine_video
    original = tmp_path / "original.mp4"
    unrelated = tmp_path / "unrelated.mp4"
    original.write_bytes(b"original-media-bytes")
    unrelated.write_bytes(b"different-video-data")
    assert original.stat().st_size == unrelated.stat().st_size
    os.utime(unrelated, ns=(original.stat().st_atime_ns, original.stat().st_mtime_ns))
    assert original.stat().st_mtime_ns == unrelated.stat().st_mtime_ns
    report = baseline()
    report["source_signature"] = {"size": original.stat().st_size, "mtime_ns": original.stat().st_mtime_ns}
    if not missing_hash:
        report["source_sha256"] = hashlib.sha256(original.read_bytes()).hexdigest()
    report_file = tmp_path / "report.json"
    report_file.write_text(json.dumps(report))
    output = tmp_path / "out"
    def forbidden_probe(*args):
        raise AssertionError("Unrelated input reached codec probe")
    monkeypatch.setattr(refine_video, "probe", forbidden_probe)
    monkeypatch.setattr(sys, "argv", ["refine_video.py", str(unrelated), "--report", str(report_file),
                                     "--output-dir", str(output)])
    with pytest.raises(ValueError, match="SHA256"):
        refine_video.main()
    assert not output.exists()
    assert original.read_bytes() == b"original-media-bytes"
    assert unrelated.read_bytes() == b"different-video-data"
