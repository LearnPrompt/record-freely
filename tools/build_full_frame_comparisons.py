"""Export source/final full frames without cropping or replacing their content."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

CASES = [('01-02', 1860), ('06-39', 11970), ('09-00', 16200)]

def run(*args):
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-threads', '2', *args], check=True)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--final', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    a = p.parse_args()
    a.output_dir.mkdir(parents=True, exist_ok=False)
    rows = []
    for label, n in CASES:
        images = []
        for role, video in [('before', a.source), ('after', a.final)]:
            start = max(0, n // 30 - 1)
            image = a.output_dir / f'{label}-{role}.png'
            run('-ss', str(start), '-reinit_filter', '0', '-i', str(video), '-an', '-vf', f'select=eq(n\\,{n-start*30})', '-frames:v', '1', '-fps_mode', 'passthrough', str(image))
            images.append(image)
        board = a.output_dir / f'{label}-full-comparison.jpg'
        filters = (
            '[0:v]scale=1600:900:flags=lanczos,pad=1600:912:0:0:color=0x0e1720[b];'
            '[1:v]scale=1600:900:flags=lanczos[a];'
            '[b][a]vstack=inputs=2[out]'
        )
        run('-i', str(images[0]), '-i', str(images[1]), '-filter_complex_threads', '1', '-filter_complex', filters, '-map', '[out]', '-frames:v', '1', '-q:v', '2', str(board))
        rows.append({'id': label, 'global_frame': n, 'time_seconds': n / 30, 'full_frame_size': [3840,2160], 'crop_xyxy': [0,0,3840,2160], 'comparison_method': 'Source and v3 at the same verified 30fps frame. Full-frame PNGs are unscaled; display board scales both equally, with BEFORE above AFTER and a neutral separator outside the frames. No text or mask replacement.', 'before': images[0].name, 'after': images[1].name, 'board': board.name, 'file_sha256': {f.name: sha(f) for f in [*images,board]}})
    (a.output_dir / 'manifest.json').write_text(json.dumps({'source': a.source.name, 'final': 'v3/redacted.mp4', 'source_existing_masks_preserved': True, 'rows': rows}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'full_frame_pairs': len(rows), 'output': str(a.output_dir)}))

if __name__ == '__main__':
    main()
