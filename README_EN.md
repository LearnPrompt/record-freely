[中文](README.md) · [English](README_EN.md) · [日本語](README_JA.md)

# Record Freely · 放心录

**Record the idea first. Let your Agent handle the parts that need masking.**

[GitHub](https://github.com/LearnPrompt/record-freely) · [Download v1.1.0](https://github.com/LearnPrompt/record-freely/releases/tag/v1.1.0) · [Public review](docs/public-review.md)

[Before / after](https://learnprompt.github.io/record-freely/) · [Implementation](references/implementation.md) · [Cost and time](docs/cost-and-time.md) · [Online comparison sliders](https://learnprompt.github.io/record-freely/)

A URL appears in your terminal. A file path reveals your username. A zoom makes a small address fill the screen. You pause, record again, or spend the evening adjusting masks. The thing you wanted to teach gets interrupted.

Record Freely grew from an actual **35:29, 4K, 30fps** screen recording of a workflow for editing content related to Media Storm (影视飓风). Our first masks covered the addresses, but some jittered, hid Skill names, or missed a row under the cursor highlight. We revised the real frames: retain the author and Skill name, hide the personal home-directory prefix, keep static masks steady, and follow real movement.

That follows LearnPrompt’s story: see what is possible, learn how to do it, and turn it into something you can use again. A visible address should not interrupt your willingness to share.

In the historical v1.0.1 trial, a fresh Agent ran a real one-minute 4K clip: **4m54s** automatic, 50s stabilization, and 41s final patch rendering. Agent review/correction spanned about 33 min including waits and overlapping computation; these are not additive or human hands-on time. A 12-frame title-overlap leak remains. See the [actual trial, reports and videos](docs/one-minute-trial.md).

## Independent-audit fixes (unreleased)

The public v1.1.0 package matched all 343 tag-source files and passed 138 tests, but its independent one-minute output retained sensitive fragments and overmasked content: **visual privacy acceptance failed**. These fixes add per-request `--ocr-timeout` (60s default), explicit `--crf 16 --preset medium --color-space bt709` (defaults remain 18/fast), and `--asr-language` (auto default) with digital-silence signal checks. In privacy mode, `--path-policy parent` retains only the final filename of identity paths; `--github-policy host` hides GitHub scheme/host while retaining the owner/repository. Defaults remain identity-prefix/full URL. Retention requires reliable character geometry; pending candidates are not concealed findings. Follow the [Skill entry](SKILL.md), [audit-fix boundaries](docs/independent-audit-fixes.md), [PCM, language and private diagnostics](docs/audio-review-examples.md), and [actual-mask timeline](docs/actual-mask-timeline.md). These options neither restore trusted captions automatically nor guarantee platform approval; review residual text and preserved teaching content.

## v1.1.0: turn real feedback into the next workflow

This release brings together the long-video revisions and four distinct videos reviewed with Record Freely and Huangbai’s guoshen: a long screen-recorded tutorial, a silent mobile recording, a multilingual AI drama tutorial, and a mini-program tutorial. The lesson is how to preserve the explanation, locate what actually needs attention, and verify the edited frames. Each case keeps precheck, editing and publication states separate. **No actual platform approval has been established.**

- **Mask narrowly and preserve viewing.** A candidate is not authorization to rewrite the scene. Cover confirmed addresses, identity prefixes or explicitly requested terms; retain filenames, Skill names, people, subtitles and original animation. Masking publishing-platform names is a preference for that material, not a blacklist of every tool brand. A whole-page replacement damaged an animation and was rejected; the correction restored local masks, and the failure remains part of the lessons.
- **Review the full display lifetime.** Keep static masks steady; handle motion, zoom, cuts and detection gaps separately. Inspect first and last frames, wrapped tails, clipped characters and later reappearance in reduced panels. Intermittent whole-frame OCR hits do not establish the mask interval. Background-colored local masks still need native-frame acceptance.
- **Check evidence before explaining moderation.** Exclude repeated ASR hallucinations on silent audio; supplement mixed-language segments while retaining source-time offsets. Verify AI demonstrations, factual sources, feature permissions and actual publishing states separately. Generic “unsuitable for sharing” feedback does not establish a reason, and masking a 403 cannot prove that a feature works.
- **Combine edits on the original before export.** The v6 long-video workflow applied accepted masks and trusted caption layers to the original, then encoded with `libx264 / CRF 16 / preset medium / BT.709`, preserving 4K30 without scaling, denoising or sharpening. A one-minute preview was accepted before rebuilding the full film. This is a tested Agent recipe for that material, **not an automatic change to the default CLI encoding mode**. Task retries and the encoding generations of the delivered pixels are counted separately.
- **Jump to real masking.** Build contiguous local-mask intervals from reviewed events; exclude global background processing, AI labels and ordinary text restoration. Do not bridge unmasked gaps. Map times after cuts to the delivered video, and verify that the browser actually displays the sought frame as well as reporting the right time.

Use `python3 scripts/build_review_timeline.py --help` to export existing event records as actual-mask intervals in JSON, CSV and Markdown for viewer navigation. It **does not detect video content or decide platform violations**, and does not generate a general-purpose web player. See [actual-mask timeline](docs/actual-mask-timeline.md). See the [sanitized case lessons](docs/case-lessons-v1.1.md) and [review and minimal-edit boundaries](references/review-lessons.md). Quality, speech, timeline and privacy checks retain their own coverage; sampling, an older version’s full-frame OCR, or successful decoding must not become a claim of zero misses in the latest file.

The v3 comparisons, independent one-minute trial and collection below are **historical v1.0.1 assets**, retained for reproduction. They are not new v6 quality comparisons or acceptance of every v1.1.0 capability.

## Full-frame before and after

Each board shows the **entire frame**: the input above and the v3 output below, at the same instant. The presenter, subtitles, and terminal remain visible. Existing masks in the input are preserved; this pass adds the solid masks visible in the lower frame.

### 01:02: hide the URL prefix, retain its author and Skill name

![01:02 full-frame comparison; input above, v3 below](assets/full-frame-comparisons/01-02-full-comparison.jpg)

### 06:39: mask enlarged addresses while preserving how to find the Skill

![06:39 full-frame comparison; input above, v3 below](assets/full-frame-comparisons/06-39-full-comparison.jpg)

### 09:00: hide personal path prefixes in a Media Storm editing tutorial

The recording shows a workflow that selects shots with three or more people from Media Storm material. The full frame retains the presenter, subtitles, detection results, and useful filenames. Personal prefixes were selected through reviewed edits.

![09:00 full-frame comparison with the editing workflow intact](assets/full-frame-comparisons/09-00-full-comparison.jpg)

[Full-frame sliders](https://learnprompt.github.io/record-freely/) · [Original-size 4K frame files](assets/full-frame-comparisons/) · [Exact frame IDs and hashes](assets/full-frame-comparisons/manifest.json)

<details>
<summary>Inspect the cropped masking boundaries</summary>

Retained author/Skill components were verified from the source text, not inferred automatically.

![01:02 masking detail](assets/comparisons/01-02-comparison.jpg)

![06:39 masking detail](assets/comparisons/06-39-comparison.jpg)

![09:00 masking detail](assets/comparisons/09-00-comparison.jpg)

</details>

This creator's recording documents learning and applying a workflow using Media Storm material. The name describes the case background, not an official partnership.

## Historical v1.0.1 masked-segment collection

[Watch/download the collection](https://github.com/LearnPrompt/record-freely/releases/download/v1.0.1/all-masked-segments.mp4) · [55 individual clips and reproduction files](https://github.com/LearnPrompt/record-freely/releases/download/v1.0.1/masked-segment-clips.zip) · [Original and collection timeline index](docs/masked-segment-collection.md)

The final v3 frame reports identify 106 contiguous masked runs, totaling 13,407 masked frames. Joining gaps of at most one second produces **55 clips and a 7m40.9s collection**, including 14 seconds explicitly marked as context. Every reported masked frame is retained at original speed, with full framing and matching audio, exported at 1080p30. This is not a selection of successful examples. Masks already present in the recording are outside the scope of these added-mask reports.

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
  --output-dir /absolute/new-output --ocr-workers 1
```

OCR locates text, and offline domain rules select likely links. OpenCV template matching follows position and scale. Stabilization holds a fixed covering rectangle for static text and splits motion, zoom, cuts, and observation gaps into separate runs to reduce repeated size changes.

See [implementation notes](references/implementation.md) for reviewed rectangle edits and stabilization. Automatic detection, reviewed edits, and final inspection are distinct stages. The source remains intact; outputs go into a new directory.

## Optional privacy checks and independent output review

The default still masks likely URLs only. Add `--privacy` to check email addresses, mainland Chinese mobile numbers, labeled phone numbers, personal path prefixes, and QR codes as well, while retaining useful path components where possible. Candidates without reliable recognition or bounds stay in a review queue. Each is marked `mask`, `needs_review`, or `keep`; reports omit the recognized addresses and contact details.

```bash
# Make a short privacy-mode first pass
python3 scripts/redact_video.py /absolute/input.mp4 \
  --output-dir /absolute/privacy-preview --privacy --start 60 --duration 20

# Independently scan the encoded output
python3 scripts/review_video.py /absolute/final.mp4 \
  --output-dir /absolute/new-review --privacy --detect-every 1 \
  --redaction-report /absolute/final/report.json

# Optionally inspect local speech and existing SRT subtitles
python3 scripts/review_video.py /absolute/final.mp4 \
  --output-dir /absolute/new-review-with-speech --privacy \
  --redaction-report /absolute/final/report.json \
  --asr-model /absolute/local-whisper-model.bin \
  --subtitle /absolute/captions.srt
```

Speech inspection requires an installed `whisper-cli` and an existing local model. It neither downloads a model automatically nor uploads media. Without `--asr-model`, audio is explicitly recorded as unchecked, separately from absent audio or transcription failure. Temporary transcripts are cleaned up; anonymous reports omit ASR text. Existing subtitles are independent sources, and `--subtitle` may be repeated. Speech and subtitle candidates are reminders; the scripts do not mute speech, edit subtitles, or rewrite content.

Review writes `review.json` and checks audio tracks separately. SRT timestamps must start at the original video’s zero point, not the selected clip’s zero point. Output review defaults to OCR on every normalized CFR frame. `--detect-every N` enables sampling and records coverage and failures. `--start` and `--duration` limit the inspected window; content outside it remains unchecked. Normalizing variable frame rates to CFR may duplicate or omit source frames. Even every-frame OCR can fail or miss text. Inspect flashes, scrolling, transitions, first appearances, clipped edges, and subtitle overlaps. Review leaves the input intact.

Platform review is a separate Agent workflow using audiovisual context and sourced policies. Keep source dates, applicable scenarios, user preferences, observed feedback, and inferred causes separate. Tool names and unverified feedback do not become platform keyword bans. See the [prepublication workflow](docs/prepublication-review.md) and [blank record template](references/platform-review-template.json). Approval is not guaranteed.

The workflow draws on [guoshen](https://github.com/huangbai-AI/guoshen)'s evidence, candidate review, and feedback separation, implemented around Record Freely's own engine without importing its full code or policy library. Historical 4K and one-minute results describe their original versions, not validation of these new modules.

The earlier privacy upgrade passed **121 tests**, including real Vision single-frame flash/QR rescans, audio-track offsets, independent subtitle sources and rejection of mismatched output hashes. Separate local runs verified concealment in a 36-frame synthetic video and checked two synthesized speech tracks with an existing Whisper model. See [validation scope](docs/privacy-review-validation.md). This does not establish zero missed content in long videos or platform approval.

Use `--redaction-report /absolute/final/report.json` to bind a rescan to the final output hash; use the newest report after refinement. Identity prefixes with unreliable character geometry remain pending. Spatially adjacent address fragments produce review hints, never automatic enlarged masks.

## How the algorithm works

This diagram follows the current source. The default run produces an automatic first pass; the Agent reviews it and optionally stabilizes or patches it. HDR input is rejected and needs a separate SDR conversion workflow first.

```mermaid
flowchart TD
  A["Input: probe SDR and frame rate / calculate full source SHA-256"]
  B["FFmpeg decode / FFV1 constant-frame-rate intermediate"]
  C["Detect cuts per frame / clear old tracks and look-back cache at cuts"]
  D["Apple Vision OCR / text and character bounds"]
  E["Offline HTTP(S), www and IANA domain rules"]
  F["Mask bounds: character boxes / missing bounds fall back to line; repeated bounds marked degraded"]
  G["OpenCV multi-scale template tracking and visual backfill / stop on mismatch or timeout"]
  H["Automatic video + per-frame report.json"]
  I["refine: verify source SHA-256 again"]
  J["Optional stabilization: fixed static envelopes / split motion and zoom / break at cuts and missing frames"]
  K["Agent reviews source frames / optional manual patch bound to report SHA-256"]
  L["FFmpeg re-render H.264 + AAC / check frame count, duration, audio streams and full decoding"]
  A --> B --> C
  C --> D --> E --> F
  C -->|"Existing tracks can match even without current OCR boxes"| G
  F -->|"New detections seed tracks / visual backfill"| G
  G --> H --> I --> J --> K --> L
```

The diagram shows logical stages, not a strict per-frame sequence. OCR workers may prefetch concurrently. Existing tracks can continue through visual matching without current OCR boxes, and later detections may visually backfill earlier frames.

Degraded character bounds can overmask; stabilization and tracking can still miss text. Inspect the actual frames: technical checks are not visual acceptance. See [implementation notes](references/implementation.md).

## Historical v1.0.1 measurements

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

The previously published version passed 70 core code tests and 9 collection-tool tests, including a regression for repeated whole-line Vision character bounds discovered in the fresh trial. The historical 144-frame real-OCR synthetic fixture passed. An independent Agent reran the code, checked all six real comparison images pixel for pixel, and recalculated the dataset hashes. The discovered source-binding flaw was fixed and retested. See the [independent review](docs/independent-review.md).

## Review from another machine

Start with the [public review guide](docs/public-review.md). Browse source, tests, three-language documentation, same-frame comparisons, and anonymized evidence without downloading the full film. For a real run, get `trial-source-00m55s-01m55s.mp4` from the [v1.0.1 Release](https://github.com/LearnPrompt/record-freely/releases/tag/v1.0.1): the original **00:55–01:55** segment, one minute, 4K, 30fps. A fresh Agent trial requires its own actual output and report; the historical case does not establish that result.

The complete historical **full-review-bundle/** remains local: original video, every work/ and outputs/ file, and the original and formal Skill snapshots, approximately **68.5 GB**. The public [file catalog](evidence/full-review-file-catalog.json) records paths, sizes, and SHA-256 hashes; it is not a download of all media. See [reviewer handoff](docs/reviewer-handoff.md) for the different scopes of lightweight public review and full local auditing.

The linked repository and Release are the delivery targets. Verify availability and downloads from the live pages and publication verification records.

By [LearnPrompt](https://learnprompt.pro). Turn one screen-recording problem into a Skill you can call next time.
