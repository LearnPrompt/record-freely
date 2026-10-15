# Reviewed local masks and motion proposals

The portable tools contain the reusable principles from local editing work, not customer paths, coordinates, frames, fonts or video. They run offline with the existing NumPy, OpenCV, Pillow and FFmpeg dependencies. No YOLO, model download, generative inpainting or network request is needed.

## Approved source-frame plan

`scripts/render_reviewed.py` takes a SHA256-bound original and JSON plan. Every interval uses original source-frame indices: `start_frame` is inclusive; `end_frame` is exclusive. Output frame zero maps to the selected `start_frame`. These are not local OCR-report frame indices. The reviewed renderer currently accepts CFR input only; VFR must first be explicitly normalized and become a new SHA-bound source.

```json
{
  "version": 1,
  "source_sha256": "<SHA256 of original input>",
  "review_status": "approved",
  "start_frame": 1800,
  "end_frame": 3600,
  "scene_cuts": [2400],
  "pending_gaps": [],
  "regions": [
    {
      "id": "same-reviewed-ui-surface",
      "start_frame": 1800,
      "end_frame": 2400,
      "geometry": {"box": [40, 60, 240, 24]},
      "surface_segment": "dark-panel-a",
      "fill": {"mode": "local", "sample_box": [20, 50, 290, 48], "radius": 20, "min_samples": 64, "smooth_alpha": 0.3}
    }
  ],
  "overlays": []
}
```

Coordinates are integer native pixels. A box is `[x,y,width,height]`; its right and bottom bounds are exclusive. A polygon is `{"polygon":[[x,y],...]}`: at least three convex points inside the source frame, including boundary pixels. Invalid/offscreen geometry is rejected rather than clipped or enlarged. Polygon masks leave pixels outside the polygon untouched.

For frame-varying motion, replace `geometry` with `geometry_by_frame`, mapping every active source frame as a canonical decimal string to its explicitly observed geometry. Missing entries are an error, even if the prior polygon looks plausible. A region must use exactly one of these geometry formats. IDs identify the same reviewed physical surface, never unrelated targets. Give each person's badge a distinct ID. A new panel/background inside a shot gets a different `surface_segment`.

Exact reviewed shapes with filename/suffix holes use a single-channel `L` PNG containing only 0/255:

```json
{"mask_path":"assets/mask.png","mask_sha256":"<PNG SHA256>","box":[40,60,240,24]}
```

PNG dimensions must exactly match the box. Pixels of 255 are opaque coverage; 0 remains original, including approved holes. Asset paths are relative to the plan's directory and may not escape it. Raster mask assets and overlay assets are bound to their own SHA256 hashes before rendering.

## Surface colour and opacity

Supported fills:

- `fixed`: requires `color_bgr:[B,G,R]`, each integer 0–255; exactly opaque. Choose this for already accepted colours, when nearby sampling is ambiguous, or when deliberately preserving an old approved appearance.
- `local`: excludes all sensitive interiors plus a three-pixel boundary guard, chooses a dominant low-edge adjacent colour cluster, and uses its median. Optional `sample_box` limits sampling to a human-confirmed surface; `sample_bgr_min`/`sample_bgr_max` further restrict channels. Samples from every target on the frame and every active RGBA overlay’s entire native canvas are excluded before any mask is painted, so drawing order does not affect colour. Overlay canvases may contain private source text under a clean subtitle or privacy cover; their underlying source is excluded even at transparent holes. This conservative exclusion can make sampling insufficient and require a reviewed fixed colour. `radius` defaults to 20 and `min_samples` to 64.
- `plane`: fits a robust first-order colour plane to the same excluded adjacent samples. It requires spatially independent support, at least 70% inliers, and low post-constraint residual. Normalized x/y slopes are bounded by `max_gradient` (default 25, permitted 0–64). This reduces visible seams on gently shaded posters; it does not reconstruct background texture or original text.

All modes write opaque colour only inside the explicit reviewed geometry. There is no feathered privacy core or mask size smoothing that could expose text. The same ID/segment can smooth observed colour over consecutive frames (`smooth_alpha`, default 0.3). Scene cuts, gaps, segment changes and unsupported large colour changes reset the blend. A missing surface sample raises `MaskSamplingError`; cached colour or a gray replacement is never silently substituted. Correct the sampling area or explicitly approve a fixed colour instead.

Masks do not detect which text requires covering. Review both badges, translucent logos and subtitle overlap, and use whole-frame re-review to discover misses outside the approved geometry. Colour blending alone cannot establish privacy acceptance or platform approval.

## Trusted RGBA overlays

Each overlay specifies `path`, `sha256`, `x`, `y`, `start_frame`, `end_frame`. Files must be actual RGBA PNGs with native dimensions, no implicit conversion or resize. The renderer paints overlays in array order **after** all masks; alpha-zero pixels preserve source exactly. Only reviewed subtitle/AI labels belong here. An overlay containing original sensitive text can reintroduce it; asset integrity is not semantic approval.

When rebuilding an older recipe, inspect each restoration layer and remove or replace contaminated ones before rendering. A later clean glyph layer does not erase earlier private pixels through its transparent holes. Adding a smaller rectangle also does not remove an earlier oversized rectangle: correct the complete plan rather than stacking a repair over it. Check every affected row and the full subtitle-overlap lifecycle, including neighboring native frames and the first filename character.

```json
{"path":"assets/ai-label.png","sha256":"<RGBA PNG SHA256>","x":40,"y":40,"start_frame":1800,"end_frame":3600}
```

## Render original once

```bash
python3 scripts/render_reviewed.py original.mp4 \
  --patch approved-plan.json --output-dir new-reviewed-output \
  --crf 16 --preset medium --color-space bt709
```

It reads original frames, paints all geometry and trusted layers, and encodes video once through the shared H.264 quality helper. Final audio comes from the matching source interval and is AAC 192 kbps; the intermediate encoded video is copied during audio mux, not encoded again. Audio stream count is checked, but this alone is not a perceptual sync check. Output directories must be new; old versions and original input remain intact.

Optional `--report automatic/report.json` imports all automatic rectangular masks for the selected window and adds the plan geometry. The report must be complete and match original SHA256, dimensions and frame rate. The plan must contain the exact `source_report_sha256`; rectangle fills default to fixed gray or explicit plan `baseline_fill`. It adds rectangles, not replacements: when correcting overmask, supply the complete corrected geometry in the plan and omit `--report`. This avoids accidentally retaining the old oversized rectangle beneath a smaller patch.

Each output has `report.json`, original/plan/output hashes, source-frame mapping, exact region kind, per-frame sampled colours/plane coefficients and overlay hashes. Runtime validation checks that every pixel outside actual mask/overlay support matches the original **before encoding**, counts/duration/audio streams and full decode. Reports retain the standard rectangle bounding-box fields for timeline navigation, but bitmap holes and polygons remain precise during execution. Their bounding box in a viewer is a navigation aid, not the raster mask itself. Technical completion leaves `acceptance:not_verified`: final-frame OCR and visual acceptance are still required.

## Motion and perspective: propose, then review

```bash
python3 scripts/track_region.py original.mp4 \
  --anchors anchors.json --output proposed-plan.json --context 40
```

`anchors.json` contains source SHA256, `start_frame`, `end_frame`, optional source-frame `scene_cuts`, `id`, `fill`, and `anchors:{"SOURCE_FRAME":[[x,y],...]}`. Use short bounded shots: the CLI deliberately rejects windows exceeding 18,000 frames or two billion grayscale pixels in memory. Full resolution is used without implicit resize.

Tracking selects local feature points around the reviewed anchor, runs forward and backward Lucas–Kanade optical flow, rejects tracks exceeding 1.5-pixel round-trip error, and fits a RANSAC homography. It requires at least eight consistent points/inliers and 60% inliers. Implausible jumps/scale changes, offscreen shapes, scene cuts and unavailable evidence stop that direction. A later manual anchor can independently restart an observed chain. Nearer supported anchor proposals win; no interpolation, frozen-last-polygon extension, or scene-cut bridging is used.

Output includes `tracking_evidence`, `tracking_failures`, `pending_gaps`, full observed `geometry_by_frame`, and `review_status:pending`. RANSAC confidence is a proposal, not proof the features belonged to the correct object. Human review must check coverage throughout the shot, correct/add source-frame anchors, resolve every gap, and then explicitly set approved status before rendering. The renderer rejects pending plans and absent geometry. Failures may still occur within a plausible observed chain; final re-OCR and visual inspection remain mandatory.

## Verification scope

The tests exercise simultaneous-target sample exclusion, exact bitmap holes, outside-region pixel equality, constrained gradient fitting, temporal cut/gap resets, explicit sample failure, perspective/translation recovery, stop-on-failure/cut behavior, asset/hash refusal, native RGBA alpha, and a real source-once FFmpeg render with audio, frame mapping and BT.709 tags. These synthetic checks establish the mechanics, not complete coverage of a creator's real video. The one-minute native acceptance record must separately bind the final output hash and list any unresolved privacy/visual findings.
