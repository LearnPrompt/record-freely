# Encoded-frame review coverage

`scripts/review_video.py` reviews a half-open window on an FFmpeg-normalized
timeline. It runs `fps=...` before the frame-number trim; timestamps in findings
refer to that normalized source timeline, including when a window starts between
two frames.

## A duration is not a verified frame count

A 30 fps MP4 containing 5,990 frames can report a duration of `199.666667`
seconds. Multiplying this rounded duration by 30 gives `5990.00001`; an
unqualified `ceil` invents frame 5,991 and incorrectly reports an incomplete
decode.

For a boundary derived from the source's reported endpoint, the reviewer snaps
to the nearest integer only within half a microsecond of timestamp rounding,
converted to frames and capped at `0.0001` frame. Explicit user window boundaries
only receive a floating-point arithmetic tolerance. A genuine fractional frame
still uses `ceil`: `1.016667` seconds at 30 fps includes normalized frame 30.

The expected count comes from these normalized time bounds. `nb_frames` is not
used to override the result: it can be missing, inaccurate, or incompatible with
the normalized rate of a variable-frame-rate source.

## What a successful decode proves

The visual report records:

| Field | Meaning |
| --- | --- |
| `expected_count_basis` | `normalized_time_bounds`, rather than an unverified source count |
| `expected_normalized_frames` | End-exclusive normalized frame index minus first frame index |
| `endpoint_precision_seconds` | Probe endpoint rounding tolerance; zero for an explicit interior window |
| `decoder_reached_eof` | The raw-video pipe reached EOF without a partial final frame |
| `decoder_exit_code` | FFmpeg's actual exit code |
| `decoded_frames` / `checked_frames` / `failed_frames` / `skipped_frames` | Decoded frames, successful OCR frames, OCR failures, and sampling omissions |
| `source_rate_hint` | Rate metadata is unequal/variable, apparently constant but unverified, or unknown |
| `source_frame_coverage` | `not_verified`: normalized scanning does not verify the original source frame sequence |

Visual status becomes `checked` only when FFmpeg succeeds, complete decoded
frames exactly match the expected normalized count, and every requested OCR
operation succeeds. A clean EOF with 19 decoded frames against an expectation of
20 remains `decoded_coverage_incomplete`. A partial raw frame or nonzero decoder
exit remains a failure.

Equal `avg_frame_rate` and `r_frame_rate` are only a metadata hint. They do not
prove constant frame timing. The `fps` filter may duplicate or drop source VFR
frames, so even `mode=every_frame` means every frame of this normalized review
window. Verifying every original source frame would require independent frame
timestamps and a decoding path that preserves those frames. That verification
is not implemented here.

OCR success is not complete visual understanding or zero-leak proof. Sampled
mode can miss a one-frame disclosure. Final-media SHA binding, native-size
first/last-frame checks around each mask, and explicit review coverage remain
necessary.

## Regression evidence

The test suite generates a local 16×16, 30 fps, 5,990-frame MP4 with FFmpeg;
ffprobe reports `199.666667`, and the reviewer checks all 5,990 decoded frames
through clean EOF. Additional tests preserve non-aligned windows and real
fractional endpoints, ignore arbitrary `nb_frames`, keep unknown/VFR metadata
distinct from original-frame coverage, and reject a real one-frame omission.
This synthetic test uses an empty OCR worker to isolate decode coverage; it is
not an OCR recall or platform-approval test.
