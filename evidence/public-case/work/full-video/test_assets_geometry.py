"""Source-specific reviewed URI geometry checks; no OCR strings required."""
import ast
import json
from pathlib import Path
import pytest

P = Path(__file__).resolve().parent
# Extract the pure helper without decoding the source video during unit tests.
tree = ast.parse((P / 'qa_part05_assets_geometry.py').read_text())
helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'subtract_portrait')
namespace = {}
exec(compile(ast.Module(body=[helper], type_ignores=[]), '<portrait-helper>', 'exec'), namespace)
subtract = namespace['subtract_portrait']


def area(box):
    return box[2] * box[3]


@pytest.mark.parametrize('box', [[100, 100, 3700, 40], [2800, 1510, 1040, 80], [0, 2040, 3840, 80], [2990, 1600, 700, 40]])
def test_portrait_subtraction_preserves_every_visible_rectangle_pixel(box):
    x, y, w, h = box
    ix = max(0, min(x+w, 3780)-max(x, 2980))
    iy = max(0, min(y+h, 2064)-max(y, 1528))
    result = subtract(box)
    assert sum(map(area, result)) == area(box)-ix*iy
    for a, b, c, d in result:
        assert x <= a < a+c <= x+w and y <= b < b+d <= y+h
        assert not (a < 3780 and a+c > 2980 and b < 2064 and b+d > 1528)


def test_right_edge_uri_remains_masked_beside_opaque_portrait():
    assert subtract([137, 1600, 3703, 52]) == [[137, 1600, 2843, 52], [3780, 1600, 60, 52]]


def test_frozen_patch_covers_only_reviewed_runs_with_bounded_individual_rows():
    patch = json.loads((P / 'qa_part05_assets_geometry.json').read_text())
    frames = patch['frames']
    assert patch['review_status'] == 'source_geometry_reviewed_frozen'
    assert not patch['unconfirmed_frames']
    assert set(map(int, frames)) == set(range(45636, 45714)) | set(range(45811, 46149))
    for n, rows in frames.items():
        for r in rows:
            x, y, w, h = r['box']
            assert 0 <= x < x+w <= 3840 and 0 <= y < y+h <= 2160 and h <= 65
            assert subtract(r['box']) == [r['box']]
            assert r['preserve_orange_caption']
            assert r['preserve_white_caption'] == (int(n) <= 45661)


def test_confirmed_argument_boundaries_and_wrapped_five_row_layout():
    frames = json.loads((P / 'qa_part05_assets_geometry.json').read_text())['frames']
    seed = frames['46122']
    assert seed[0]['box'][0] > 1160  # Keep attachments and adjacent Chinese.
    assert max(r['box'][0]+r['box'][2] for r in seed if r['box'][1] > 1150) < 2230
    wrapped = frames['45690']
    assert len({r['box'][1] for r in wrapped}) == 5
    assert wrapped[0]['box'][0] > 3500
    assert wrapped[-1]['box'][0]+wrapped[-1]['box'][2] < 1330  # Keep prefer-models/include-tools.


def test_exit_patch_stops_at_true_last_visible_tail_and_keeps_flags():
    patch = json.loads((P / 'qa_part05_assets_exit.json').read_text())
    assert set(map(int, patch['frames'])) == set(range(45714, 45721))
    assert patch['last_visible_frame'] == 45720 and patch['first_absent_frame'] == 45721
    for rows in patch['frames'].values():
        assert len(rows) == 1
        row = rows[0]
        x, y, w, h = row['box']
        assert x == 729 and x+w < 1334 and 130 < y < y+h < 220
        assert h < 45 and row['anchor_score'] > .9
        assert not row.get('preserve_white_caption')


@pytest.mark.parametrize('name,start,end', [('qa_part02_shell_exit.json',18119,18128),('qa_part02_shell_variant.json',18128,18151)])
def test_shell_exit_uses_individual_bounded_uri_fields_and_exact_source_exit(name,start,end):
    patch=json.loads((P/name).read_text())
    assert set(map(int,patch['frames']))==set(range(start,end))
    assert patch['last_visible_frame']==end-1 and patch['first_absent_frame']==end
    for rows in patch['frames'].values():
        assert len(rows)>=4
        for row in rows:
            x,y,w,h=row['box']
            assert 0<=x<x+w<=3840 and 0<=y<y+h<=2160 and 0<h<=49
            assert row['anchor_score']>.9 and row['preserve_orange_caption']
            assert not row.get('preserve_white_caption')
            assert not (x<3840 and x+w>1080 and y<120)
