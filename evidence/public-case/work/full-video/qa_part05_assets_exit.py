"""Confirmed resource URI tail at the existing run's exit; public anchor only."""
import cv2
import json
from pathlib import Path
import qa_part05_assets_geometry as g

P = Path(__file__).resolve().parent
capture = g.StreamCapture(g.SOURCE, 45714/30, 8)
frames = {}
proof = []
for n in range(45714, 45722):
    ok, source = capture.read()
    assert ok
    score, anchor = g.locate(cv2.cvtColor(source, cv2.COLOR_BGR2GRAY), g.PREFER, [.76, .775, .79], [500, 0, 2400, 950])
    if n == 45721:
        assert score < .6  # Source scroll removes the confirmed tail here.
        continue
    assert score > .85
    px, py, _, _, scale = anchor
    x = 729
    y = int(py + 8*scale - 6)
    right = int(px - 15*scale + 6)
    height = int(36*scale + 12)
    box = [x, y, right-x, height]
    assert right < px and 0 < y < y+height < 300
    frames[str(n)] = [{'box': box, 'id': 'QA5E001', 'kind': 'url_continuation', 'origin': 'review_resource_exit_tail',
        'box_method': 'reviewed_uri_tail_public_flag_anchor', 'anchor_score': round(float(score), 4),
        'review_basis': 'Confirmed final URI tail remains after head scrolls out; stop before prefer-models and before source removes row',
        'preserve_orange_caption': True}]
    if n in [45714, 45720]:
        image = source[:360].copy()
        cv2.rectangle(image, (x, y), (right, y+height), (0, 0, 255), 3)
        proof.append(image)
capture.release()
result = {'frames': frames, 'review_status': 'source_geometry_reviewed_frozen', 'last_visible_frame': 45720,
          'first_absent_frame': 45721, 'remove_ids': [], 'private_text_persisted': False}
(P/'qa_part05_assets_exit.json').write_text(json.dumps(result, indent=2))
cv2.imwrite(str(P/'qa_part05_assets_exit_proof.jpg'), cv2.vconcat(proof))
print(json.dumps({'frames': len(frames), 'last_visible_frame': 45720, 'first_absent_frame': 45721}))
