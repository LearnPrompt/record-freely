import copy
import json
import tempfile
from pathlib import Path

import pytest
from build_review_timeline import build, digest, main


def manifest():
    return {'fps': '30/1', 'output_frames': 120, 'source_frames': 126,
            'source_cuts': [[60, 66]], 'encoded_sha256': 'a' * 64,
            'events': [
                {'role': 'global_protection', 'start_frame': 0, 'end_frame': 120},
                {'role': 'ai_label', 'start_frame': 0, 'end_frame': 120},
                {'role': 'trusted_restoration', 'start_frame': 0, 'end_frame': 120},
                {'role': 'local_redaction', 'start_frame': 10, 'end_frame': 20},
                {'role': 'local_redaction', 'start_frame': 19, 'end_frame': 25},
                {'role': 'local_redaction', 'start_frame': 26, 'end_frame': 27},
                {'role': 'local_redaction', 'start_frame': 59, 'end_frame': 62} ]}


def test_actual_masks_only_no_unmasked_gap_and_no_cut_bridge():
    data = build(manifest())
    assert [(r['start_frame'], r['end_frame']) for r in data['intervals']] == [
        (10, 25), (26, 27), (59, 60), (60, 62)]
    assert data['masked_frames'] == 19
    assert data['local_event_count'] == 4
    assert sum(data['excluded_event_counts'].values()) == 3
    before, after = data['intervals'][-2:]
    assert before['source_end_frame'] == 60
    assert after['source_start_frame'] == 66
    assert after['source_end_frame'] == 68


def test_every_displayed_frame_has_actual_mask_and_all_masks_are_indexed():
    original = manifest()
    expected = {f for e in original['events'] if e['role'] == 'local_redaction'
                for f in range(e['start_frame'], e['end_frame'])}
    actual = {f for r in build(original)['intervals'] for f in range(r['start_frame'], r['end_frame'])}
    assert actual == expected


def test_touching_intervals_merge_and_input_is_unchanged():
    original = manifest()
    original['events'][-1] = {'role': 'local_redaction', 'start_frame': 25, 'end_frame': 26}
    old = copy.deepcopy(original)
    assert len(build(original)['intervals']) == 1
    assert original == old


def test_multiple_cuts_including_prefix_and_suffix_keep_source_mapping():
    value = {'fps': 30, 'output_frames': 20, 'source_frames': 31,
             'source_cuts': [[0, 2], [7, 10], [17, 20], [28, 31]],
             'encoded_sha256': 'a' * 64,
             'events': [{'role': 'local_redaction', 'start_frame': 0, 'end_frame': 20,
                         'color': 'background', 'raw_text': 'private-sentinel'},
                        {'role': 'local_redaction', 'start_frame': 4, 'end_frame': 15}]}
    data = build(value)
    assert [(r['start_frame'], r['end_frame']) for r in data['intervals']] == [(0, 5), (5, 12), (12, 20)]
    assert [(r['source_start_frame'], r['source_end_frame']) for r in data['intervals']] == [(2, 7), (10, 17), (20, 28)]
    assert 'private-sentinel' not in json.dumps(data)


def test_unknown_roles_and_broken_mapping_rejected():
    value = manifest()
    value['events'][0]['role'] = 'background_color'
    with pytest.raises(ValueError, match='Unknown role'):
        build(value)
    value = manifest()
    value['source_frames'] = 123
    with pytest.raises(ValueError, match='disagree'):
        build(value)


def test_rational_fps_empty_masks_and_private_labels_are_not_exported():
    value = manifest()
    value['fps'] = '30000/1001'
    value['events'] = value['events'][:3]
    value['events'][0]['raw_text'] = 'private-address'
    data = build(value)
    assert not data['intervals']
    assert 'private-address' not in json.dumps(data)
    assert data['fps'] == '30000/1001'


def test_cli_hash_binding_and_existing_destination_protection():
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        movie = root / 'synthetic.bin'
        movie.write_bytes(b'synthetic test, no video')
        source = root / 'manifest.json'
        value = manifest()
        source.write_text(json.dumps(value))
        args = [str(source), '--video', str(movie), '--output-dir', str(root / 'out')]
        with pytest.raises(ValueError, match='SHA256 differs'):
            main(args)
        assert not (root / 'out').exists()
        value['encoded_sha256'] = digest(movie)
        source.write_text(json.dumps(value))
        main(args)
        assert json.loads((root / 'out/timeline.json').read_text())['video_sha_verified']
        assert (root / 'out/timeline.csv').is_file()
        with pytest.raises(FileExistsError):
            main(args)
