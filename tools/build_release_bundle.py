#!/usr/bin/env python3
"""Freeze the clean committed public repository, never the private working folder."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def sha(data):
    return hashlib.sha256(data).hexdigest()


def package(root, destination, version):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Expected a semantic release version without a v prefix')
    if git(root, 'status', '--porcelain').strip():
        raise ValueError('Commit intended files and preserve other edits before packaging')
    if destination == root or root in destination.parents:
        raise ValueError('Release assets must be outside the repository')
    commit = git(root, 'rev-parse', 'HEAD').decode().strip()
    expected_paths = set(git(root, 'ls-tree', '-r', '--name-only', '-z', commit).decode().split('\0')) - {''}
    if git(root, 'show', f'{commit}:VERSION').decode().strip() != version:
        raise ValueError('Committed VERSION differs from requested release')
    destination.mkdir(parents=True, exist_ok=False)
    archive = destination / f'record-freely-v{version}.zip'
    subprocess.run(['git', '-C', str(root), 'archive', '--format=zip', '--prefix=record-freely/',
                    '--output', str(archive), commit], check=True)
    rows = []
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise ValueError('ZIP CRC check failed')
        for item in bundle.infolist():
            if item.is_dir():
                continue
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Do not bundle symlink targets or paths')
            relative = Path(item.filename)
            if relative.is_absolute() or '..' in relative.parts or '.git' in relative.parts:
                raise ValueError('Unsafe archive entry')
            content = bundle.read(item)
            repo_relative = str(relative.relative_to('record-freely'))
            # Read back every byte against the frozen Git tree, not a moving checkout.
            if content != git(root, 'show', f'{commit}:{repo_relative}'):
                raise ValueError('Archive differs from committed source')
            rows.append({'path': item.filename, 'bytes': len(content), 'sha256': sha(content)})
    if {str(Path(row['path']).relative_to('record-freely')) for row in rows} != expected_paths:
        raise ValueError('Archive file set differs from committed tree; do not omit public source')
    receipt = {'version': version, 'commit': commit, 'scope': 'Complete committed public source; '
               'new private case videos/transcripts and local historical review packs are excluded.',
               'archive': {'name': archive.name, 'bytes': archive.stat().st_size,
                           'sha256': sha(archive.read_bytes())},
               'file_count': len(rows), 'files': rows, 'crc_checked': True,
               'all_archive_files_match_git_tree': True, 'all_git_tree_files_included': True}
    (destination / 'SOURCE-CATALOG.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    receipt = package(args.repo, args.output_dir, args.version)
    print(json.dumps({key: receipt[key] for key in ['version', 'commit', 'file_count', 'archive']}))


if __name__ == '__main__':
    main()
