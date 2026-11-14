"""Tests for snapshot_record; temporary repositories, HOME and snapshot stores only."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import snapshot_record as sr

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'cr-request' / 'scripts'))
try:
    import target_whitespace as tw
except ImportError:  # pragma: no cover
    tw = None

ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'GIT_CONFIG_NOSYSTEM': '1',
       'GIT_CONFIG_GLOBAL': '/dev/null'}


def git(repo, *args):
    return subprocess.check_output(['/usr/bin/git', '-C', str(repo), *args], env=ENV)


class SnapshotRecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='snapshot-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / 'home'
        self.home.mkdir()
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        git(self.repo, 'init', '-q', '-b', 'main')
        git(self.repo, 'config', 'user.email', 't@example.invalid')
        git(self.repo, 'config', 'user.name', 't')
        (self.repo / 'a.txt').write_bytes(b'one\n')
        (self.repo / 'run.sh').write_bytes(b'#!/bin/sh\n')
        os.chmod(self.repo / 'run.sh', 0o755)
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'init')
        self.store = self.root / 'store'

    def state(self):
        files = {}
        for path in sorted(self.repo.rglob('*')):
            if '.git' in path.parts or path.is_dir():
                continue
            files[str(path.relative_to(self.repo))] = (path.read_bytes() if not path.is_symlink() else None,
                                                       path.lstat().st_mode)
        return git(self.repo, 'status', '--porcelain=v2', '--untracked-files=all'), files

    def test_capture_leaves_index_bytes_and_modes_unchanged(self):
        (self.repo / 'a.txt').write_bytes(b'one\ntwo \n')
        (self.repo / 'run.sh').write_bytes(b'#!/bin/sh\necho\n')
        (self.repo / 'new.txt').write_bytes(b'new\n')
        git(self.repo, 'add', 'a.txt')
        before = self.state()
        index_before = (self.repo / '.git' / 'index').read_bytes()
        results = sr.capture(self.repo, ['a.txt', 'run.sh', 'new.txt'], self.store)
        self.assertEqual(before, self.state())
        self.assertEqual(index_before, (self.repo / '.git' / 'index').read_bytes())
        self.assertEqual(['file'] * 3, [item['status'] for item in results])

    def test_store_is_private_and_content_addressed(self):
        data = (self.repo / 'a.txt').read_bytes()
        item = sr.capture(self.repo, ['a.txt'], self.store)[0]
        digest = hashlib.sha256(data).hexdigest()
        self.assertEqual(digest, item['sha256'])
        self.assertEqual(self.store / digest, Path(item['file']))
        self.assertEqual(0o700, self.store.stat().st_mode & 0o777)
        self.assertEqual(0o400, Path(item['file']).stat().st_mode & 0o777)
        self.assertEqual(data, Path(item['file']).read_bytes())
        again = sr.capture(self.repo, ['a.txt'], self.store)[0]
        self.assertEqual(item['line'], again['line'])

    def test_file_changed_after_snapshot_is_unverified(self):
        (self.repo / 'a.txt').write_bytes(b'one\ntwo \n')
        item = sr.capture(self.repo, ['a.txt'], self.store)[0]
        # Someone rewrites the stored bytes: the hash no longer matches.
        os.chmod(item['file'], 0o600)
        Path(item['file']).write_bytes(b'tampered\n')
        parsed = sr.parse_lines([item['line']], self.repo)
        self.assertEqual({}, parsed['snapshots'])
        self.assertIn('hash does not match', parsed['rejected'][0]['reason'])
        if tw:
            (self.repo / 'a.txt').write_bytes(b'one\ntwo \nthree \n')
            result = tw.check_whitespace(self.repo, initial_dirty=['a.txt'], snapshots=parsed['snapshots'])
            self.assertEqual('unverified', result['status'])

    def test_snapshot_feeds_check_whitespace_as_own_delta(self):
        if not tw:
            self.skipTest('target_whitespace unavailable')
        (self.repo / 'a.txt').write_bytes(b'one\nforeign \n')
        item = sr.capture(self.repo, ['a.txt'], self.store)[0]
        (self.repo / 'a.txt').write_bytes(b'one\nforeign \nclean\n')
        snapshots = sr.parse_lines([item['line']], self.repo)['snapshots']
        result = tw.check_whitespace(self.repo, initial_dirty=['a.txt'], snapshots=snapshots)
        self.assertEqual('clean', result['status'])
        self.assertEqual(['a.txt'], result['foreign'])

    def test_symlink_is_unavailable(self):
        (self.repo / 'link').symlink_to('a.txt')
        item = sr.capture(self.repo, ['link'], self.store)[0]
        self.assertEqual('unavailable', item['status'])
        self.assertEqual('Snapshot: link unavailable symlink', item['line'])
        self.assertEqual([], list(self.store.iterdir()))
        parsed = sr.parse_lines([item['line']], self.repo)
        self.assertEqual({}, parsed['snapshots'])
        self.assertEqual({'link': 'symlink'}, parsed['unavailable'])

    def test_unavailable_cases_store_nothing(self):
        (self.repo / 'dir').mkdir()
        (self.root / 'outside.txt').write_bytes(b'x')
        (self.repo / 'via').symlink_to(self.root)
        (self.repo / 'dir' / 'f.txt').write_bytes(b'x')
        cases = {'dir': 'not a regular file', 'missing.txt': 'unreadable',
                 '../outside.txt': 'outside repository', str(self.root / 'outside.txt'): 'outside repository',
                 'via/outside.txt': 'outside repository'}
        for path, reason in cases.items():
            item = sr.capture(self.repo, [path], self.store)[0]
            self.assertEqual(('unavailable', reason), (item['status'], item['reason']), path)
        self.assertEqual([], list(self.store.iterdir()))

    def test_unreadable_file_is_unavailable(self):
        if os.geteuid() == 0:
            self.skipTest('root reads everything')
        (self.repo / 'secret.txt').write_bytes(b'x')
        os.chmod(self.repo / 'secret.txt', 0)
        self.addCleanup(os.chmod, self.repo / 'secret.txt', 0o600)
        item = sr.capture(self.repo, ['secret.txt'], self.store)[0]
        self.assertEqual('unavailable', item['status'])

    def test_spaces_and_unicode_paths_round_trip(self):
        names = ['with space.txt', 'ґанок/тест файл.md', 'quote"name.txt', 'back\\slash.txt', 'new\nline.txt']
        for name in names:
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode() + b'\n')
        results = sr.capture(self.repo, names, self.store)
        for name, item in zip(names, results):
            self.assertEqual('file', item['status'], name)
            self.assertEqual('\n' not in item['line'], True)
        parsed = sr.parse_lines([item['line'] for item in results], self.repo)
        self.assertEqual([], parsed['rejected'])
        self.assertEqual(sorted(names), sorted(parsed['snapshots']))
        for name in names:
            self.assertEqual(name.encode() + b'\n', Path(parsed['snapshots'][name]['file']).read_bytes())
        self.assertTrue(results[0]['line'].startswith('Snapshot: "with space.txt" sha256 '))

    def test_parser_rejects_foreign_hash(self):
        item = sr.capture(self.repo, ['a.txt'], self.store)[0]
        other = sr.capture(self.repo, ['run.sh'], self.store)[0]
        forged = item['line'].replace('sha256 ' + item['sha256'], 'sha256 ' + other['sha256'])
        with self.assertRaisesRegex(ValueError, 'hash'):
            sr.parse(forged, self.repo)
        # The file name must be the hash it claims even when the bytes match some other hash.
        bad = 'Snapshot: a.txt sha256 ' + '0' * 64 + ' file ' + item['file']
        with self.assertRaises(ValueError):
            sr.parse(bad, self.repo)

    def test_parser_does_not_read_a_fifo_named_by_a_line(self):
        fifo = self.root / 'pipe'
        os.mkfifo(fifo)
        empty = hashlib.sha256(b'').hexdigest()
        line = 'Snapshot: a.txt sha256 ' + empty + ' file ' + str(fifo)
        with self.assertRaisesRegex(ValueError, 'regular file'):
            sr.parse(line, self.repo)

    def test_parser_rejects_path_outside_repo(self):
        item = sr.capture(self.repo, ['a.txt'], self.store)[0]
        for path in ('../a.txt', '/etc/passwd', 'x/../../a.txt', './a.txt', ''):
            line = 'Snapshot: ' + json.dumps(path) + ' sha256 ' + item['sha256'] + ' file ' + item['file']
            with self.assertRaises(ValueError, msg=path):
                sr.parse(line, self.repo)
            with self.assertRaises(ValueError, msg=path):
                sr.parse('Snapshot: ' + json.dumps(path) + ' unavailable symlink', self.repo)

    def test_parser_rejects_extra_or_missing_fields(self):
        item = sr.capture(self.repo, ['a.txt'], self.store)[0]
        line = item['line']
        for bad in (line + ' extra', line.replace(' file ', ' mode 644 file '),
                    line.replace('sha256 ' + item['sha256'], 'sha256 ' + item['sha256'][:-1]),
                    'Snapshot: a.txt', 'Snapshot: a.txt unavailable', 'Snapshot: a.txt sha256 ' + item['sha256'],
                    line.replace(' file ' + item['file'], ' file relative/path'),
                    'Snapshot: two words sha256 ' + item['sha256'] + ' file ' + item['file'],
                    'Snapshot:  a.txt unavailable symlink', 'Verify: PASS'):
            with self.assertRaises(ValueError, msg=bad):
                sr.parse(bad, self.repo)

    def test_rejected_line_leaves_path_without_snapshot(self):
        item = sr.capture(self.repo, ['a.txt'], self.store)[0]
        parsed = sr.parse_lines(['Task 1: done', item['line'] + ' extra'], self.repo)
        self.assertEqual({}, parsed['snapshots'])
        self.assertEqual(1, len(parsed['rejected']))

    def test_default_store_layout(self):
        git(self.repo, 'checkout', '-q', '-b', 'feature/x')
        store = sr.default_store(self.repo, self.home)
        relative = store.relative_to(self.home)
        self.assertEqual(('.sentimony', 'agentflow', 'implement'), relative.parts[:3])
        self.assertEqual('snapshots', relative.parts[-1])
        self.assertTrue(relative.parts[3].startswith('repo-'))
        self.assertTrue(relative.parts[4].startswith('feature_x-'))

    def test_cli_capture_and_parse(self):
        (self.repo / 'a.txt').write_bytes(b'dirty \n')
        run = subprocess.run([sys.executable, str(HERE / 'snapshot_record.py'), 'capture', '--repo', str(self.repo),
                              '--home', str(self.home), 'a.txt', 'nothere'], capture_output=True, text=True)
        self.assertEqual(0, run.returncode, run.stderr)
        lines = run.stdout.splitlines()
        self.assertEqual('Snapshot: nothere unavailable unreadable', lines[1])
        self.assertTrue(str(self.home) in lines[0])
        parse = subprocess.run([sys.executable, str(HERE / 'snapshot_record.py'), 'parse', '--repo', str(self.repo)],
                               input=run.stdout, capture_output=True, text=True)
        self.assertEqual(0, parse.returncode, parse.stderr)
        self.assertEqual(['a.txt'], list(json.loads(parse.stdout)['snapshots']))
        bad = subprocess.run([sys.executable, str(HERE / 'snapshot_record.py'), 'parse', '--repo', str(self.repo)],
                             input='Snapshot: a.txt bogus\n', capture_output=True, text=True)
        self.assertEqual(1, bad.returncode)
        self.assertFalse((Path.home() / '.sentimony' / 'agentflow' / 'implement' / ('repo-' + 'x')).exists())


if __name__ == '__main__':
    unittest.main()
