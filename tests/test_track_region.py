import cv2
import numpy as np

from track_region import track_frames, track_step


def texture():
    return cv2.GaussianBlur(np.random.default_rng(40).integers(0, 256, (180, 240), dtype=np.uint8), (3, 3), 0)


def test_bidirectional_optical_flow_recovers_translation_and_perspective():
    source = texture()
    polygon = np.array([[75, 65], [145, 65], [145, 100], [75, 100]], np.float32)
    matrix = np.array([[1.005, .01, 3.], [-.004, 1., 2.], [.00003, -.00004, 1.]])
    target = cv2.warpPerspective(source, matrix, (240, 180))
    found, evidence = track_step(source, target, polygon)
    expected = cv2.perspectiveTransform(polygon.reshape(1, -1, 2), matrix)[0]
    assert found is not None
    assert np.linalg.norm(found-expected, axis=1).max() < 1.
    assert evidence['inlier_ratio'] >= .6 and evidence['inliers'] >= 8
    assert evidence['fb_max'] <= 1.5


def test_failed_chain_does_not_hold_last_polygon_or_extend_into_cut():
    source = texture()
    blank = np.zeros_like(source)
    polygon = [[75, 65], [145, 65], [145, 100], [75, 100]]
    shapes, evidence, failures, gaps = track_frames([source, source.copy(), blank, blank], {10: polygon}, start_frame=10)
    assert set(shapes) == {10, 11} and gaps == [12, 13]
    assert failures and 12 not in evidence
    shapes, _, failures, gaps = track_frames([source, source.copy(), source.copy()], {10: polygon}, start_frame=10, scene_cuts=[11])
    assert set(shapes) == {10} and gaps == [11, 12]
    assert failures[0]['reason'] == 'scene_cut'


def test_manual_anchor_after_failure_recovers_only_supported_frames():
    source = texture()
    blank = np.zeros_like(source)
    polygon = [[75, 65], [145, 65], [145, 100], [75, 100]]
    shapes, evidence, _, gaps = track_frames([source, source.copy(), blank, source.copy(), source.copy()],
                                            {0: polygon, 4: polygon}, scene_cuts=[3])
    assert set(shapes) == {0, 1, 3, 4} and gaps == [2]
    assert evidence[0]['reason'] == evidence[4]['reason'] == 'human_anchor'
