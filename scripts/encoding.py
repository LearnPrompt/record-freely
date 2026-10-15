"""Shared explicit H.264 quality and optional SDR BT.709 conversion."""
from __future__ import annotations
import math

PRESETS = ('ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow')


def crf_value(value):
    crf = float(value)
    if not math.isfinite(crf) or not 0 <= crf <= 51:
        raise ValueError('CRF must be finite and between 0 and 51')
    return crf


def add_encoding_arguments(parser):
    parser.add_argument('--crf', type=crf_value, default=18., help='libx264 quality, 0–51; default 18')
    parser.add_argument('--preset', choices=PRESETS, default='fast')
    parser.add_argument('--color-space', choices=['bt709'], help='Explicit SDR RGB to limited-range BT.709 conversion; omitted preserves the legacy encoder policy')


def encoding_config(args):
    return {'codec': 'libx264', 'crf': args.crf, 'preset': args.preset, 'pixel_format': 'yuv420p',
            'color_space': args.color_space, 'color_policy': 'explicit_sdr_bt709' if args.color_space else 'legacy_unspecified',
            'video_encoding_generations': 1, 'audio_codec': 'aac', 'audio_bitrate': '192k'}


def video_encoding_options(args):
    filters = 'pad=ceil(iw/2)*2:ceil(ih/2)*2'
    options = ['-c:v', 'libx264', '-crf', str(args.crf), '-preset', args.preset, '-pix_fmt', 'yuv420p']
    if args.color_space == 'bt709':
        filters += ',scale=in_range=full:out_range=tv:out_color_matrix=bt709,format=yuv420p,setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709'
        options += ['-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709']
    return options + ['-vf', filters]


def verify_encoding(video, args):
    actual = {key: video.get(key) for key in ('color_range', 'color_space', 'color_primaries', 'color_transfer')}
    if args.color_space == 'bt709' and actual != {'color_range': 'tv', 'color_space': 'bt709', 'color_primaries': 'bt709', 'color_transfer': 'bt709'}:
        raise RuntimeError('Export BT.709 color tags did not match requested conversion')
    return {'color_tags': actual, 'explicit_color_tags_verified': True if args.color_space else None}
