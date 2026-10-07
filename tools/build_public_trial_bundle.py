"""Archive the complete independent one-minute trial without Git credentials/caches."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--trial-root', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--canonical-skill-archive', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    trial = args.trial_root.resolve()
    if not (trial / 'trial-result.json').is_file():
        raise ValueError('The completed trial result is required before freezing files')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    archive = args.output_dir / 'complete-one-minute-review.zip'
    if archive.exists():
        raise ValueError('Archive destination already exists')
    excluded = {'.git', '__pycache__', '.pytest_cache', '.DS_Store'}
    files = [(p, Path('agent-trial') / p.relative_to(trial))
             for p in sorted(trial.rglob('*')) if p.is_file()
             and not excluded.intersection(p.relative_to(trial).parts)]
    files.extend([(args.source.resolve(), Path('source') / args.source.name),
                  (args.canonical_skill_archive.resolve(),
                   Path('canonical-skill') / args.canonical_skill_archive.name)])
    rows = [{'path': str(rel), 'bytes': src.stat().st_size, 'sha256': sha256(src)}
            for src, rel in files]
    catalog = {'version': 1, 'scope': 'Complete one-minute trial; not the 68.5GB historical film archive.',
               'files': rows, 'file_count': len(rows),
               'logical_bytes': sum(row['bytes'] for row in rows),
               'excluded': sorted(excluded)}
    text = json.dumps(catalog, ensure_ascii=False, indent=2) + '\n'
    (args.output_dir / 'one-minute-review-file-catalog.json').write_text(text)
    readme = ('# Complete independent one-minute trial\n\n'
              'Read agent-trial/trial-report.md and trial-result.json first. '
              'The reviewed output still contains documented missed masks; it is a trial, '
              'not a guaranteed ready-to-publish video.\n\n'
              'source/ contains the exact 60s input. agent-trial/ preserves all outputs, '
              'including the first correction attempt, review frames, patches, scripts, '
              'and the Skill snapshot actually tested. canonical-skill/ contains the '
              'published release source ZIP; its later report-label fix does not change mask geometry.\n\n'
              'No Git credential/configuration directory or interpreter cache is included. '
              'The full historical film archive remains local.\n')
    with zipfile.ZipFile(archive, 'w', allowZip64=True) as bundle:
        for src, rel in files:
            compression = zipfile.ZIP_DEFLATED if src.suffix in {'.md', '.json', '.py', '.swift', '.log', '.txt', '.yaml'} else zipfile.ZIP_STORED
            bundle.write(src, str(rel), compress_type=compression, compresslevel=6 if compression else None)
        bundle.writestr('FILE_CATALOG.json', text, compress_type=zipfile.ZIP_DEFLATED)
        bundle.writestr('README.md', readme, compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(archive) as bundle:
        bad = bundle.testzip()
        if bad:
            raise ValueError('Archive CRC failure: ' + bad)
        assert len(bundle.namelist()) == len(rows) + 2
    print(json.dumps({'archive': str(archive.resolve()), 'bytes': archive.stat().st_size,
                      'sha256': sha256(archive), 'catalog_files': len(rows), 'crc_checked': True}))


if __name__ == '__main__':
    main()
