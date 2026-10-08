import importlib.util
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'masked_collection', Path(__file__).parents[1] / 'tools/build_masked_collection.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MaskedCollectionTests(unittest.TestCase):
    def test_runs_include_first_last_and_single_frame(self):
        self.assertEqual(module.runs([True, False, True, True, False, True]),
                         [[0, 1], [2, 4], [5, 6]])

    def test_empty_selection(self):
        self.assertEqual(module.runs([False] * 5), [])

    def test_gap_includes_exact_threshold_but_not_larger(self):
        self.assertEqual(module.merge_runs([[0, 2], [32, 34], [65, 66]], 30),
                         [[0, 34], [65, 66]])

    def test_merge_does_not_mutate_raw_intervals(self):
        raw = [[0, 2], [3, 4]]
        module.merge_runs(raw, 1)
        self.assertEqual(raw, [[0, 2], [3, 4]])

    def test_all_masked_frames_preserved_and_gap_labelled_context(self):
        flags = [True, False, True, True, False, False, False, True]
        merged = module.merge_runs(module.runs(flags), 1)
        entries = module.make_catalog(flags, merged, 30)
        self.assertEqual(sum(e['masked_frames'] for e in entries), sum(flags))
        self.assertEqual(sum(e['context_frames'] for e in entries), 1)
        self.assertEqual(entries[-1]['collection_start_frame'], 4)
        selected = {f for a, b in merged for f in range(a, b) if flags[f]}
        self.assertEqual(selected, {0, 2, 3, 7})

    def test_overlapping_intervals_rejected(self):
        with self.assertRaises(ValueError):
            module.merge_runs([[0, 4], [3, 5]], 30)

    def test_existing_clips_without_source_binding_are_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / 'source.mp4'
            source.write_bytes(b'fixture')
            output = root / 'output'
            clips = output / 'clips'
            clips.mkdir(parents=True)
            (clips / 'unknown.mp4').write_bytes(b'other movie')
            argv = ['build', '--source', str(source), '--manifest', str(root / 'manifest.json'),
                    '--chunks', str(root / 'chunks'), '--output', str(output)]
            with patch('sys.argv', argv), patch.object(module, 'load_timeline', return_value=(
                    {'fps': 30, 'source_frames': 2}, [True, False], [])), \
                    patch.object(module, 'digest', return_value='fixture-sha'), \
                    patch.object(module, 'probe', return_value={'streams': [
                        {'codec_type': 'video', 'nb_frames': '2', 'avg_frame_rate': '30/1'}]}):
                with self.assertRaisesRegex(ValueError, 'no completed provenance catalog'):
                    module.main()

    def test_actual_encoder_command_keeps_frame_counter_across_color_property_changes(self):
        class StopAfterCommandCapture(Exception):
            pass

        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / 'source.mp4'
            source.write_bytes(b'fixture')
            argv = ['build', '--source', str(source), '--manifest', str(root / 'manifest.json'),
                    '--chunks', str(root / 'chunks'), '--output', str(root / 'output')]
            with patch('sys.argv', argv), patch.object(module, 'load_timeline', return_value=(
                    {'fps': 30, 'source_frames': 2}, [True, False], [])), \
                    patch.object(module, 'digest', return_value='fixture-sha'), \
                    patch.object(module, 'probe', return_value={'streams': [
                        {'codec_type': 'video', 'nb_frames': '2', 'avg_frame_rate': '30/1'}]}), \
                    patch.object(module, 'run', side_effect=StopAfterCommandCapture) as run:
                with self.assertRaises(StopAfterCommandCapture):
                    module.main()
                command = run.call_args.args[0]
                option = command.index('-reinit_filter')
                self.assertEqual(command[option + 1], '0')
                self.assertLess(option, command.index('-i'))
                self.assertIn('trim=start_frame=0:end_frame=1', command[command.index('-vf') + 1])

    def test_actual_concat_command_does_not_shift_video_by_aac_priming(self):
        class StopAfterConcatCapture(Exception):
            pass

        def capture(command, *args):
            if '-f' in command and command[command.index('-f') + 1] == 'concat':
                raise StopAfterConcatCapture

        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / 'source.mp4'
            source.write_bytes(b'fixture')
            argv = ['build', '--source', str(source), '--manifest', str(root / 'manifest.json'),
                    '--chunks', str(root / 'chunks'), '--output', str(root / 'output')]
            with patch('sys.argv', argv), patch.object(module, 'load_timeline', return_value=(
                    {'fps': 30, 'source_frames': 2}, [True, False], [])), \
                    patch.object(module, 'digest', return_value='fixture-sha'), \
                    patch.object(module, 'probe', return_value={'streams': [
                        {'codec_type': 'video', 'nb_frames': '2', 'avg_frame_rate': '30/1'}]}), \
                    patch.object(module, 'verify_media', return_value={'bytes': 1, 'sha256': 'clip-sha'}), \
                    patch.object(module, 'run', side_effect=capture) as run:
                with self.assertRaises(StopAfterConcatCapture):
                    module.main()
                command = run.call_args.args[0]
                self.assertLess(command.index('-copyts'), command.index('-i'))
                self.assertEqual(command[command.index('-avoid_negative_ts') + 1], 'disabled')


if __name__ == '__main__':
    unittest.main()
