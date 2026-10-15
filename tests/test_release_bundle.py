import importlib.util
import subprocess
import tempfile
from pathlib import Path
import zipfile

import pytest

spec = importlib.util.spec_from_file_location('release_bundle', Path(__file__).parents[1] / 'tools/build_release_bundle.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def repo_fixture(root):
    root.mkdir()
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    (root / 'VERSION').write_text('1.1.0\n')
    (root / 'SKILL.md').write_text('synthetic fixture\n')
    subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                    '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture'], check=True)


def test_complete_committed_source_roundtrip_and_no_git_credentials():
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        repo = root / 'repo'
        repo_fixture(repo)
        result = module.package(repo, root / 'assets', '1.1.0')
        assert result['file_count'] == 2
        assert result['all_archive_files_match_git_tree']
        with zipfile.ZipFile(root / 'assets' / result['archive']['name']) as archive:
            assert sorted(archive.namelist()) == ['record-freely/', 'record-freely/SKILL.md', 'record-freely/VERSION']
        with pytest.raises(FileExistsError):
            module.package(repo, root / 'assets', '1.1.0')


def test_refuses_dirty_source_and_version_mismatch_without_output():
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        repo = root / 'repo'
        repo_fixture(repo)
        with pytest.raises(ValueError, match='VERSION differs'):
            module.package(repo, root / 'assets', '1.2.0')
        (repo / 'private-raw.txt').write_text('untracked private evidence')
        with pytest.raises(ValueError, match='Commit intended files'):
            module.package(repo, root / 'assets', '1.1.0')
        assert not (root / 'assets').exists()


def test_source_remains_pinned_when_head_advances_after_capture(monkeypatch):
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        repo = root / 'repo'
        repo_fixture(repo)
        captured = module.git(repo, 'rev-parse', 'HEAD').decode().strip()
        real_git = module.git

        def advance_after_capture(location, *args):
            result = real_git(location, *args)
            if args == ('rev-parse', 'HEAD'):
                (repo / 'VERSION').write_text('1.2.0\n')
                (repo / 'SKILL.md').write_text('later committed source\n')
                subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
                subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Fixture',
                                '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false',
                                'commit', '-qm', 'concurrent update'], check=True)
            return result

        monkeypatch.setattr(module, 'git', advance_after_capture)
        result = module.package(repo, root / 'assets', '1.1.0')
        assert real_git(repo, 'rev-parse', 'HEAD').decode().strip() != captured
        assert result['commit'] == captured
        assert result['all_archive_files_match_git_tree']
        with zipfile.ZipFile(root / 'assets' / result['archive']['name']) as archive:
            assert archive.read('record-freely/VERSION') == b'1.1.0\n'
            assert archive.read('record-freely/SKILL.md') == b'synthetic fixture\n'


def test_refuses_archive_that_export_ignore_silently_omits_source():
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        repo = root / 'repo'
        repo_fixture(repo)
        (repo / '.gitattributes').write_text('SKILL.md export-ignore\n')
        subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Fixture',
                        '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false',
                        'commit', '-qm', 'export rule'], check=True)
        with pytest.raises(ValueError, match='Archive file set differs'):
            module.package(repo, root / 'assets', '1.1.0')
        assert not (root / 'assets' / 'SOURCE-CATALOG.json').exists()
