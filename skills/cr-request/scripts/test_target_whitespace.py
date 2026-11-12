"""Whitespace helper tests; temporary Git repositories only."""
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

import target_whitespace as tw

ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'GIT_CONFIG_NOSYSTEM': '1',
       'GIT_CONFIG_GLOBAL': '/dev/null'}


def git(repo, *args):
    return subprocess.check_output(['/usr/bin/git', '-C', str(repo), *args], env=ENV)


def snapshot(root, name, data):
    path = Path(root) / name
    path.write_bytes(data)
    return {'sha256': hashlib.sha256(data).hexdigest(), 'file': str(path)}


class TargetWhitespaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='whitespace-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        git(self.repo, 'init', '-q')
        (self.repo / 'a.txt').write_text('one\ntwo\n')
        (self.repo / 'with space.txt').write_text('x\n')
        git(self.repo, 'add', '.')
        git(self.repo, '-c', 'user.name=F', '-c', 'user.email=f@example.invalid',
            '-c', 'commit.gpgsign=false', 'commit', '-qm', 'base')

    def state(self):
        return (git(self.repo, 'status', '--porcelain=v2', '--untracked-files=all'),
                git(self.repo, 'diff', '--cached', '--binary'),
                git(self.repo, 'diff', '--binary'),
                {p.name: (p.read_bytes(), p.stat().st_mode) for p in self.repo.iterdir()
                 if p.is_file()})

    def test_new_untracked_file_with_trailing_whitespace_is_found(self):
        (self.repo / 'new.txt').write_text('bad \n')
        plain = subprocess.run(['/usr/bin/git', '-C', str(self.repo), 'diff', '--check'], env=ENV)
        self.assertEqual(plain.returncode, 0)  # plain diff --check misses untracked files
        before = self.state()
        result = tw.check_whitespace(self.repo)
        self.assertEqual(result['status'], 'findings')
        self.assertIn('new.txt:1: trailing whitespace', result['output'])
        self.assertEqual(self.state(), before)

    def test_path_with_spaces_is_checked(self):
        (self.repo / 'with space.txt').write_text('x\ny \n')
        result = tw.check_whitespace(self.repo)
        self.assertEqual(result['status'], 'findings')
        self.assertIn('with space.txt:2: trailing whitespace', result['output'])

    def test_foreign_staged_hunk_is_context_not_own_delta(self):
        (self.repo / 'a.txt').write_text('one\ntwo\nforeign \n')
        git(self.repo, 'add', 'a.txt')
        snap = snapshot(self.root, 'a.snap', (self.repo / 'a.txt').read_bytes())
        (self.repo / 'a.txt').write_text('one\ntwo\nforeign \nown\n')
        before = self.state()
        result = tw.check_whitespace(self.repo, initial_dirty=['a.txt'], snapshots={'a.txt': snap})
        self.assertEqual(result['status'], 'clean')
        self.assertEqual(result['foreign'], ['a.txt'])
        self.assertEqual(self.state(), before)

    def test_foreign_unstaged_hunk_is_context_and_own_whitespace_is_found(self):
        (self.repo / 'a.txt').write_text('one\ntwo\nforeign \n')
        snap = snapshot(self.root, 'a.snap', (self.repo / 'a.txt').read_bytes())
        (self.repo / 'a.txt').write_text('one\ntwo\nforeign \nown \n')
        result = tw.check_whitespace(self.repo, initial_dirty=['a.txt'], snapshots={'a.txt': snap})
        self.assertEqual(result['status'], 'findings')
        self.assertIn('a.txt:4: trailing whitespace', result['output'])
        self.assertNotIn('a.txt:3', result['output'])

    def test_dirty_file_restored_to_head_is_still_accounted_for(self):
        (self.repo / 'a.txt').write_text('one\ntwo\nforeign \n')
        snap = snapshot(self.root, 'a.snap', (self.repo / 'a.txt').read_bytes())
        (self.repo / 'a.txt').write_text('one\ntwo\n')
        self.assertEqual(tw.inventory(self.repo), [])
        result = tw.check_whitespace(self.repo, initial_dirty=['a.txt'], snapshots={'a.txt': snap})
        self.assertEqual(result['status'], 'clean')
        self.assertEqual(result['foreign'], ['a.txt'])

    def test_dirty_file_without_snapshot_is_unverified_not_checked_against_head(self):
        (self.repo / 'a.txt').write_text('one\ntwo\nforeign \n')
        result = tw.check_whitespace(self.repo, initial_dirty=['a.txt'])
        self.assertEqual(result['status'], 'unverified')
        self.assertEqual(result['unverified'][0][0], 'a.txt')

    def test_snapshot_hash_mismatch_is_unverified(self):
        (self.repo / 'a.txt').write_text('one\ntwo\nforeign \n')
        snap = snapshot(self.root, 'a.snap', b'one\ntwo\nforeign \n')
        Path(snap['file']).write_bytes(b'tampered\n')
        result = tw.check_whitespace(self.repo, initial_dirty=['a.txt'], snapshots={'a.txt': snap})
        self.assertEqual(result['status'], 'unverified')
        self.assertEqual(result['unverified'], [('a.txt', 'snapshot hash mismatch')])

    def test_missing_snapshot_file_is_unverified_not_an_error(self):
        (self.repo / 'a.txt').write_text('one\ntwo\nforeign \n')
        snap = snapshot(self.root, 'a.snap', (self.repo / 'a.txt').read_bytes())
        Path(snap['file']).unlink()
        result = tw.check_whitespace(self.repo, initial_dirty=['a.txt'], snapshots={'a.txt': snap})
        self.assertEqual(result['status'], 'unverified')
        self.assertEqual(result['unverified'], [('a.txt', 'snapshot unreadable')])

    def test_untracked_file_deleted_after_its_snapshot_is_checked_without_error(self):
        (self.repo / 'scratch.txt').write_text('draft \n')
        snap = snapshot(self.root, 'scratch.snap', (self.repo / 'scratch.txt').read_bytes())
        (self.repo / 'scratch.txt').unlink()
        (self.repo / 'a.txt').write_text('one\ntwo\nthree \n')
        result = tw.check_whitespace(self.repo, initial_dirty=['scratch.txt'],
                                     snapshots={'scratch.txt': snap})
        self.assertEqual(result['status'], 'findings')
        self.assertIn('a.txt:3: trailing whitespace', result['output'])
        self.assertEqual(result['foreign'], ['scratch.txt'])

    def test_clean_change_is_clean(self):
        (self.repo / 'a.txt').write_text('one\ntwo\nthree\n')
        self.assertEqual(tw.check_whitespace(self.repo)['status'], 'clean')


if __name__ == '__main__':
    unittest.main()
