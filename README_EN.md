# Record Freely · 放心录

**Record the idea first. Let your Agent handle the parts that need masking.**

[中文](README.md) · [日本語](README_JA.md) · [GitHub](https://github.com/LearnPrompt/record-freely) · [Downloads and one-minute clip](https://github.com/LearnPrompt/record-freely/releases/tag/v1.0.1) · [Public review](docs/public-review.md)

[Before / after](assets/comparisons/index.html) · [Implementation](references/implementation.md) · [Cost and time](docs/cost-and-time.md) · [Online comparison sliders](https://learnprompt.github.io/record-freely/)

A URL appears in your terminal. A file path reveals your username. A zoom makes a small address fill the screen. You pause, record again, or spend the evening adjusting masks. The thing you wanted to teach gets interrupted.

Record Freely grew from an actual **35:29, 4K, 30fps** screen recording of a workflow for editing content related to Media Storm (影视飓风). Our first masks covered the addresses, but some jittered, hid Skill names, or missed a row under the cursor highlight. We revised the real frames: retain the author and Skill name, hide the personal home-directory prefix, keep static masks steady, and follow real movement.

That follows LearnPrompt’s story: see what is possible, learn how to do it, and turn it into something you can use again. A visible address should not interrupt your willingness to share.

A fresh Agent ran a real one-minute 4K clip: **4m54s** automatic, 50s stabilization, and 41s final patch rendering. Agent review/correction spanned about 33 min including waits and overlapping computation; these are not additive or human hands-on time. A 12-frame title-overlap leak remains. See the [actual trial, reports and videos](docs/one-minute-trial.md).

## Same-frame comparisons

Both sides use the same decoded source frame, crop, and display scale. BEFORE intentionally shows the original visible text so you can inspect the masking choice.

![01:02: keep the author and Skill name](assets/comparisons/01-02-comparison.jpg)

![06:39: preserve the two identifying Skill components](assets/comparisons/06-39-comparison.jpg)

![09:00: hide the personal prefix, retain directories and filenames](assets/comparisons/09-00-comparison.jpg)

[Move the comparison sliders](assets/comparisons/index.html). This is an independent creator’s technical example involving Media Storm content, not a claim of an official partnership.

## Use it

Currently **macOS only**. Requires Xcode Command Line Tools, FFmpeg, Python 3, `opencv-python`, and `numpy`. The processing engine runs locally and does not upload video frames. **No separate YOLO or OCR model weights need downloading**: recognition uses Apple Vision built into macOS, with the Swift worker compiled by Xcode command-line tools.

Get the complete source from GitHub and copy it into your Agent’s skills folder, for example:

```bash
git clone https://github.com/LearnPrompt/record-freely.git
mkdir -p ~/.codex/skills
cp -R record-freely ~/.codex/skills/
```

A compatible Skill installer may also support `npx skills add LearnPrompt/record-freely`; that installer command has not been validated in this delivery. Preserve an existing installation before replacing it.

Then ask:

> Use $record-freely on this screen recording. Mask text that looks like a link, keep instructional text readable, show a short preview, then deliver the complete video and inspection report.

Or run the automatic first pass:

```bash
python3 scripts/redact_video.py /absolute/input.mp4 \
  --output-dir /absolute/new-output --ocr-workers 3
```

OCR locates text, and offline domain rules select likely links. OpenCV template matching follows position and scale. Stabilization holds a fixed covering rectangle for static text and splits motion, zoom, cuts, and observation gaps into separate runs to reduce repeated size changes.

See [implementation notes](references/implementation.md) for reviewed rectangle edits and stabilization. Automatic detection, reviewed edits, and final inspection are distinct stages. The source remains intact; outputs go into a new directory.

## What we measured

| Item | Evidence |
| --- | --- |
| Input | 35:29.033, 3840 × 2160, 30fps, 63,871 frames |
| Automatic first pass on one 5-minute segment | 13m 56s, excluding development, manual revisions, and final acceptance |
| Engine | Apple Vision OCR, OpenCV tracking/stabilization, FFmpeg; no cloud vision model calls |
| Final technical validation | Full video/audio decoding, continuous PTS, identical original audio packet payloads, sampled AV alignment |
| Final assembly samples | 73 exact-timestamp samples matched the inspected chunks in native pixels |
| Codex allowance | Agent work consumes Codex allowance. Session token telemetry does not directly identify account allowance or project savings |

[Cost and time](docs/cost-and-time.md) links the underlying records. Zero cloud vision calls does not mean zero Codex use. Segment first-pass time is not full-film completion time. A savings claim needs a measured baseline under the same acceptance criteria.

## Scope

The Skill finds **visible text that resembles a URL**, follows movement and scale, and applies narrow solid masks. Reviewed edits can select path prefixes, words, or retained URL components. Keeping author/Skill suffixes and tuning personal paths require source-frame review; they are not universally automatic. Ordinary paths, email addresses, and `.html` filenames are not all treated as URLs by default.

This helps reduce visible-address concerns before publishing. It cannot guarantee platform approval or zero missed text. Check appearances, disappearances, zooms, cuts, and adjacent text. One older case item remains unlocated: the reported `.html` at 25:41, where the exact source frame shows a scales animation.

The current 70 code tests pass, including a regression for repeated whole-line Vision character bounds discovered in the fresh trial. The historical 144-frame real-OCR synthetic fixture passed. An independent Agent reran the code, checked all six real comparison images pixel for pixel, and recalculated the dataset hashes. The discovered source-binding flaw was fixed and retested. See the [independent review](docs/independent-review.md).

## Review from another machine

Start with the [public review guide](docs/public-review.md). Browse source, tests, three-language documentation, same-frame comparisons, and anonymized evidence without downloading the full film. For a real run, get `trial-source-00m55s-01m55s.mp4` from the [v1.0.1 Release](https://github.com/LearnPrompt/record-freely/releases/tag/v1.0.1): the original **00:55–01:55** segment, one minute, 4K, 30fps. A fresh Agent trial requires its own actual output and report; the historical case does not establish that result.

The complete historical **full-review-bundle/** remains local: original video, every work/ and outputs/ file, and the original and formal Skill snapshots, approximately **68.5 GB**. The public [file catalog](evidence/full-review-file-catalog.json) records paths, sizes, and SHA-256 hashes; it is not a download of all media. See [reviewer handoff](docs/reviewer-handoff.md) for the different scopes of lightweight public review and full local auditing.

The linked repository and Release are the delivery targets. Verify availability and downloads from the live pages and publication verification records.

By [LearnPrompt](https://learnprompt.pro). Turn one screen-recording problem into a Skill you can call next time.
