"""Opaque reviewed geometry with adjacent-surface sampling; BGR throughout.

No inpainting, texture reconstruction, detection or implicit fallback is used.
"""
from __future__ import annotations

import cv2
import numpy as np


class MaskSamplingError(ValueError):
    """No safe observed surface sample; requires a human patch."""


def geometry_mask(geometry, width, height):
    mask = np.zeros((height, width), np.uint8)
    if set(geometry) == {'box'}:
        box = geometry['box']
        if not isinstance(box, list) or len(box) != 4 or any(type(v) is not int for v in box):
            raise ValueError('box requires four integer pixels')
        x, y, w, h = box
        if not (0 <= x < x+w <= width and 0 <= y < y+h <= height):
            raise ValueError('box outside frame')
        mask[y:y+h, x:x+w] = 1
    elif set(geometry) == {'bitmap', 'box'}:
        base, (x, y, w, h) = geometry_mask({'box': geometry['box']}, width, height)
        pixels = geometry['bitmap']
        if not isinstance(pixels, np.ndarray) or pixels.dtype != np.uint8 or pixels.shape != (h, w) or not np.all((pixels == 0) | (pixels == 255)) or not np.any(pixels):
            raise ValueError('bitmap requires nonempty exact 0/255 uint8 box dimensions')
        base[y:y+h, x:x+w] = pixels != 0
        return base, (x, y, w, h)
    elif set(geometry) == {'polygon'}:
        points = geometry['polygon']
        if not isinstance(points, list) or len(points) < 3 or any(not isinstance(p, list) or len(p) != 2 or any(type(v) is not int for v in p) for p in points):
            raise ValueError('polygon requires at least three integer pixel points')
        poly = np.asarray(points, np.int32)
        if np.any(poly < 0) or np.any(poly[:, 0] >= width) or np.any(poly[:, 1] >= height) or not cv2.isContourConvex(poly) or cv2.contourArea(poly) < 1:
            raise ValueError('polygon must be convex, nonempty and inside frame')
        cv2.fillPoly(mask, [poly], 1)
        x, y, w, h = cv2.boundingRect(poly)
    else:
        raise ValueError('geometry requires exactly box or polygon')
    return mask.astype(bool), (x, y, w, h)


def _color(value):
    if not isinstance(value, list) or len(value) != 3 or any(type(v) is not int or not 0 <= v <= 255 for v in value):
        raise ValueError('color_bgr requires three integer channels in 0..255')
    return np.asarray(value, float)


def validate_fill(spec, width, height):
    if not isinstance(spec, dict) or set(spec)-{'mode', 'color_bgr', 'radius', 'min_samples', 'max_local_edge', 'sample_box', 'sample_bgr_min', 'sample_bgr_max', 'max_gradient', 'smooth_alpha'}:
        raise ValueError('Unknown or malformed fill parameters')
    mode = spec.get('mode', 'local')
    if mode not in ('fixed', 'local', 'plane'):
        raise ValueError('Unknown fill mode')
    if mode == 'fixed':
        _color(spec.get('color_bgr'))
    radius, minimum = spec.get('radius', 20), spec.get('min_samples', 64)
    if type(radius) is not int or not 1 <= radius <= 512 or type(minimum) is not int or minimum < 8:
        raise ValueError('Invalid sampling radius/min_samples')
    for key, default, lower, upper in [('smooth_alpha', .3, 0, 1), ('max_gradient', 25, -1, 64), ('max_local_edge', 16, -1, 255)]:
        value = spec.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or not (0 < value <= upper if key == 'smooth_alpha' else 0 <= value <= upper):
            raise ValueError(f'Invalid {key}')
    if 'sample_box' in spec:
        geometry_mask({'box': spec['sample_box']}, width, height)
    for key in ('sample_bgr_min', 'sample_bgr_max'):
        if key in spec:
            _color(spec[key])
    if 'sample_bgr_min' in spec and 'sample_bgr_max' in spec and np.any(_color(spec['sample_bgr_min']) > _color(spec['sample_bgr_max'])):
        raise ValueError('Inverted sample colour limits')


class SurfaceFiller:
    """One instance per increasing stream; cache identity is explicitly reviewed."""
    def __init__(self):
        self.previous = {}
        self.last_frame = None

    def apply(self, frame, regions, *, frame_index, scene_cut=False, exclude_geometries=()):
        if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError('Expected uint8 HxWx3 BGR')
        if self.last_frame is not None and frame_index <= self.last_frame:
            raise ValueError('Source frames must increase')
        if scene_cut:
            self.previous.clear()
        h, w = frame.shape[:2]
        masks = [geometry_mask(r['geometry'], w, h) for r in regions]
        excluded = np.zeros((h, w), bool)
        for m, _ in masks:
            excluded |= m
        for g in exclude_geometries:
            excluded |= geometry_mask(g, w, h)[0]
        # Exclude antialiasing at *all* sensitive interiors before any sampling.
        excluded = cv2.dilate(excluded.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
        out = frame.copy()
        audit, new_cache = [], {}
        identities = set()
        for region, (mask, bounds) in zip(regions, masks):
            ident = region['id']
            if not isinstance(ident, str) or not ident or ident in identities:
                raise ValueError('Region ids must be unique nonempty strings per frame')
            identities.add(ident)
            spec = region.get('fill', {'mode': 'local'})
            validate_fill(spec, w, h)
            mode = spec.get('mode', 'local')
            if mode not in ('fixed', 'local', 'plane'):
                raise ValueError('Unknown fill mode')
            x, y, bw, bh = bounds
            count = 0
            residual = None
            coeff = None
            if mode == 'fixed':
                color = _color(spec.get('color_bgr'))
            else:
                radius = spec.get('radius', 20)
                minimum = spec.get('min_samples', 64)
                if type(radius) is not int or not 1 <= radius <= 512 or type(minimum) is not int or minimum < 8:
                    raise ValueError('Invalid sampling radius/min_samples')
                left, top = max(0, x-radius), max(0, y-radius)
                right, bottom = min(w, x+bw+radius), min(h, y+bh+radius)
                roi = frame[top:bottom, left:right]
                valid = ~excluded[top:bottom, left:right]
                # Do not borrow inside a target even when exclusion was replaced.
                valid &= ~mask[top:bottom, left:right]
                maximum = cv2.dilate(roi, np.ones((3, 3), np.uint8))
                minimum_pixels = cv2.erode(roi, np.ones((3, 3), np.uint8))
                valid &= (maximum.astype(np.int16)-minimum_pixels).max(axis=2) <= spec.get('max_local_edge', 16)
                if 'sample_box' in spec:
                    valid &= geometry_mask({'box': spec['sample_box']}, w, h)[0][top:bottom, left:right]
                if 'sample_bgr_min' in spec:
                    valid &= np.all(roi >= _color(spec['sample_bgr_min']), axis=2)
                if 'sample_bgr_max' in spec:
                    valid &= np.all(roi <= _color(spec['sample_bgr_max']), axis=2)
                yy, xx = np.where(valid)
                # Deterministic bounded sample volume, preserving spatial positions.
                stride = max(1, len(xx)//20000)
                xx, yy = xx[::stride], yy[::stride]
                pixels = roi[yy, xx].astype(float)
                if len(pixels) < minimum:
                    raise MaskSamplingError(f'{ident}: insufficient unmasked adjacent surface samples')
                if mode == 'local':
                    q = pixels.astype(np.int32)//16
                    codes = q[:, 0]*256 + q[:, 1]*16 + q[:, 2]
                    values, counts = np.unique(codes, return_counts=True)
                    chosen = pixels[codes == values[counts.argmax()]]
                    if len(chosen) < minimum or len(chosen)/len(pixels) < .25:
                        raise MaskSamplingError(f'{ident}: no dominant adjacent surface')
                    color = np.median(chosen, axis=0)
                    count = len(chosen)
                else:
                    design = np.column_stack(((xx+left-x-bw/2)/bw, (yy+top-y-bh/2)/bh, np.ones(len(xx))))
                    if np.linalg.matrix_rank(design) != 3:
                        raise MaskSamplingError(f'{ident}: plane samples lack spatial support')
                    coeff = np.linalg.lstsq(design, pixels, rcond=None)[0]
                    if not np.isfinite(coeff).all():
                        raise MaskSamplingError(f'{ident}: nonfinite fitted plane')
                    keep = np.linalg.norm(np.einsum('ij,jk->ik', design, coeff)-pixels, axis=1) <= 18
                    if keep.sum() < minimum or keep.mean() < .7 or np.linalg.matrix_rank(design[keep]) != 3:
                        raise MaskSamplingError(f'{ident}: surface is not a supported low-order plane')
                    coeff = np.linalg.lstsq(design[keep], pixels[keep], rcond=None)[0]
                    if not np.isfinite(coeff).all():
                        raise MaskSamplingError(f'{ident}: nonfinite robust plane')
                    limit = float(spec.get('max_gradient', 25))
                    if not np.isfinite(limit) or not 0 <= limit <= 64:
                        raise ValueError('max_gradient must be finite in 0..64')
                    coeff[:2] = np.clip(coeff[:2], -limit, limit)
                    residual = float(np.mean(np.linalg.norm(np.einsum('ij,jk->ik', design[keep], coeff)-pixels[keep], axis=1)))
                    if not np.isfinite(residual) or residual > 12:
                        raise MaskSamplingError(f'{ident}: constrained gradient residual too high')
                    color, count = coeff[2], int(keep.sum())
            alpha = float(spec.get('smooth_alpha', .3))
            if not np.isfinite(alpha) or not 0 < alpha <= 1:
                raise ValueError('smooth_alpha must be in (0,1]')
            old = self.previous.get((ident, region.get('surface_segment', 'default')))
            smoothed = False
            if old is not None and old['frame'] == frame_index-1 and old['mode'] == mode and mode != 'fixed':
                if np.linalg.norm(color-old['color']) <= 40:
                    color = old['color']*(1-alpha)+color*alpha
                    smoothed = True
                    if coeff is not None and old['coeff'] is not None:
                        coeff = old['coeff']*(1-alpha)+coeff*alpha
                        coeff[2] = color
            if coeff is None:
                out[mask] = np.rint(color).clip(0, 255).astype(np.uint8)
            else:
                yy, xx = np.where(mask)
                design = np.column_stack(((xx-x-bw/2)/bw, (yy-y-bh/2)/bh, np.ones(len(xx))))
                out[yy, xx] = np.rint(np.einsum('ij,jk->ik', design, coeff)).clip(0, 255).astype(np.uint8)
            new_cache[(ident, region.get('surface_segment', 'default'))] = dict(frame=frame_index, color=color, coeff=coeff, mode=mode)
            audit.append(dict(id=ident, mode=mode, color_bgr=np.rint(color).clip(0, 255).astype(int).tolist(), sample_count=count,
                              plane_coeff_bgr=None if coeff is None else coeff.tolist(), plane_residual=residual,
                              temporal_smoothed=smoothed, opaque_pixels=int(mask.sum())))
        self.previous, self.last_frame = new_cache, frame_index
        return out, audit
