import cv2
import numpy as np
import pytest

from background_masks import MaskSamplingError, SurfaceFiller, geometry_mask


def region(geometry, mode='local', **fill):
    return {'id': 'surface-a', 'geometry': geometry, 'fill': {'mode': mode, **fill}}


def test_all_targets_excluded_and_pixels_outside_approved_bounds_equal():
    source = np.full((80, 120, 3), [40, 60, 80], np.uint8)
    source[30:40, 40:60] = 255
    source[30:40, 62:82] = 250
    regions = [region({'box': [40, 30, 20, 10]}, sample_box=[20, 20, 80, 30]),
               dict(region({'box': [62, 30, 20, 10]}), id='surface-b')]
    output, audit = SurfaceFiller().apply(source, regions, frame_index=0)
    expected = np.full((10, 20, 3), [40, 60, 80], np.uint8)
    assert np.array_equal(output[30:40, 40:60], expected)
    assert np.array_equal(output[30:40, 62:82], expected)
    mask = np.zeros(source.shape[:2], bool)
    mask[30:40, 40:60] = mask[30:40, 62:82] = True
    assert np.array_equal(source[~mask], output[~mask])
    assert all(r['sample_count'] >= 64 for r in audit)
    assert np.all(source[30:40, 40:60] == 255)


def test_polygon_plane_constrained_and_no_copy_of_sensitive_text():
    yy, xx = np.mgrid[:100, :140]
    source = np.stack([30+xx*.1+yy*.04, 60+xx*.1+yy*.04, 90+xx*.1+yy*.04], -1).astype(np.uint8)
    g = {'polygon': [[50, 35], [90, 38], [86, 62], [48, 60]]}
    mask, _ = geometry_mask(g, 140, 100)
    expected = source.copy()
    source[mask] = 255
    output, audit = SurfaceFiller().apply(source, [region(g, 'plane')], frame_index=0)
    assert np.max(np.abs(output[mask].astype(int)-expected[mask].astype(int))) <= 2
    assert np.array_equal(output[~mask], source[~mask])
    assert audit[0]['plane_coeff_bgr'] is not None
    assert audit[0]['plane_residual'] < 2
    assert np.max(output[mask]) < 120


def test_insufficient_sampling_fails_even_when_a_previous_colour_exists():
    filler = SurfaceFiller()
    good = np.full((60, 80, 3), 30, np.uint8)
    spec = region({'box': [20, 20, 20, 10]})
    filler.apply(good, [spec], frame_index=0)
    spec['fill']['sample_box'] = [20, 20, 20, 10]
    with pytest.raises(MaskSamplingError, match='insufficient'):
        filler.apply(good, [spec], frame_index=1)


def test_temporal_smoothing_is_reset_at_scene_cut_segment_or_gap():
    filler = SurfaceFiller()
    spec = region({'box': [20, 20, 20, 10]}, smooth_alpha=.25)
    colors = []
    for index, value, cut in [(0, 20, False), (1, 40, False), (2, 50, True), (4, 60, False)]:
        image = np.full((60, 80, 3), value, np.uint8)
        output, audit = filler.apply(image, [spec], frame_index=index, scene_cut=cut)
        colors.append(output[23, 23, 0])
    assert colors == [20, 25, 50, 60]
    spec['surface_segment'] = 'second-panel'
    output, _ = filler.apply(np.full((60, 80, 3), 70, np.uint8), [spec], frame_index=5)
    assert output[23, 23, 0] == 70


def test_bitmap_holes_are_preserved_and_fixed_core_is_opaque():
    source = np.full((60, 80, 3), 200, np.uint8)
    bitmap = np.full((10, 20), 255, np.uint8)
    bitmap[3:7, 8:12] = 0
    geometry = {'box': [20, 20, 20, 10], 'bitmap': bitmap}
    output, audit = SurfaceFiller().apply(source, [region(geometry, 'fixed', color_bgr=[10, 20, 30])], frame_index=0)
    assert np.array_equal(output[23:27, 28:32], source[23:27, 28:32])
    assert output[20, 20].tolist() == [10, 20, 30]
    assert audit[0]['opaque_pixels'] == 184


@pytest.mark.parametrize('geometry', [{'box': [-1, 0, 10, 10]}, {'polygon': [[0, 0], [20, 0], [0, 0]]},
                                      {'polygon': [[1, 1], [20, 1], [5, 5], [20, 20], [1, 20]]}])
def test_no_silent_clip_or_enlargement_of_bad_geometry(geometry):
    with pytest.raises(ValueError):
        geometry_mask(geometry, 30, 30)


def test_nonplanar_gradient_and_invalid_order_fail():
    random = np.random.default_rng(4).integers(0, 256, (80, 100, 3), dtype=np.uint8)
    with pytest.raises(MaskSamplingError):
        SurfaceFiller().apply(random, [region({'box': [30, 30, 20, 10]}, 'plane')], frame_index=0)
    filler = SurfaceFiller()
    filler.apply(np.zeros((80, 100, 3), np.uint8), [], frame_index=2)
    with pytest.raises(ValueError, match='increase'):
        filler.apply(np.zeros((80, 100, 3), np.uint8), [], frame_index=2)
