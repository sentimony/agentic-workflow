"""Whitespace check of a review target through a private index; the real index is never touched."""
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path


def _git(repo, *args, index=None, data=None):
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent',
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
    if index is not None:
        env['GIT_INDEX_FILE'] = str(index)
    return subprocess.run(['/usr/bin/git', '--no-optional-locks', '-C', str(repo), *args],
                          env=env, input=data, capture_output=True, check=False)


def _ok(process, what):
    if process.returncode:
        raise ValueError(what + ' failed: ' + process.stderr.decode(errors='replace'))
    return process.stdout


def inventory(repo):
    """Changed tracked paths against HEAD plus untracked, non-ignored paths, sorted."""
    changed = _ok(_git(repo, 'diff', '--name-only', '-z', '--no-renames', 'HEAD', '--'), 'diff')
    untracked = _ok(_git(repo, 'ls-files', '--others', '--exclude-standard', '-z'), 'ls-files')
    names = {os.fsdecode(item) for item in (changed + untracked).split(b'\0') if item}
    return sorted(names)


def check_whitespace(repo, *, initial_dirty=(), snapshots=None):
    """Return {'status', 'output', 'foreign', 'unverified'}.

    `initial_dirty` lists paths that were already dirty before the change. A path there
    needs a snapshot {'sha256': hex, 'file': path}; the delta is then snapshot -> current.
    Without a usable snapshot the path is `unverified`: HEAD is not assumed to be its before.
    """
    snapshots = snapshots or {}
    # A snapshot path counts even when the file was restored to HEAD and left the inventory.
    # A dirty path restored to HEAD without a snapshot adds nothing to check: its state is HEAD.
    paths = sorted(set(inventory(repo)) | set(snapshots))
    unverified, foreign, before = [], [], {}
    own = []
    for path in paths:
        if path in snapshots:
            try:
                data = Path(snapshots[path]['file']).read_bytes()
            except OSError:
                unverified.append((path, 'snapshot unreadable'))
                continue
            if hashlib.sha256(data).hexdigest() != snapshots[path]['sha256']:
                unverified.append((path, 'snapshot hash mismatch'))
                continue
            before[path] = data
            foreign.append(path)
        elif path in set(initial_dirty):
            unverified.append((path, 'no before-snapshot; HEAD is not assumed'))
            continue
        own.append(path)
    result = {'status': 'clean', 'output': '', 'foreign': foreign, 'unverified': unverified}
    if own:
        with tempfile.TemporaryDirectory(prefix='whitespace-index-') as temp:
            index_a, index_b = Path(temp) / 'a', Path(temp) / 'b'
            for index in (index_a, index_b):
                _ok(_git(repo, 'read-tree', 'HEAD', index=index), 'read-tree')
            for path, data in before.items():
                blob = _ok(_git(repo, 'hash-object', '-w', '--stdin', data=data), 'hash-object').strip()
                tracked = _git(repo, 'ls-files', '-s', '-z', '--', ':(literal)' + path).stdout.split(b' ')
                mode = tracked[0].decode() if len(tracked) > 1 else '100644'
                _ok(_git(repo, 'update-index', '--add', '--cacheinfo',
                         mode + ',' + blob.decode() + ',' + path, index=index_a), 'update-index')
            # A path gone from the tree and absent from HEAD (an untracked file removed after
            # its snapshot) has nothing to add; index_b then lacks it and the diff is a deletion.
            present = [path for path in own if (Path(repo) / path).is_symlink() or
                       (Path(repo) / path).exists() or
                       _ok(_git(repo, 'ls-tree', '-z', 'HEAD', '--', ':(literal)' + path), 'ls-tree')]
            if present:
                spec = b'\0'.join(b':(literal)' + os.fsencode(path) for path in present) + b'\0'
                _ok(_git(repo, 'add', '-A', '--pathspec-from-file=-', '--pathspec-file-nul',
                         index=index_b, data=spec), 'add')
            # Paths without a snapshot start from HEAD, so only snapshot paths differ in index_a.
            tree_a = _ok(_git(repo, 'write-tree', index=index_a), 'write-tree').strip().decode()
            tree_b = _ok(_git(repo, 'write-tree', index=index_b), 'write-tree').strip().decode()
            check = _git(repo, 'diff', '--check', '--no-ext-diff', '--no-textconv', tree_a, tree_b)
            if check.returncode not in (0, 2):
                raise ValueError('diff --check failed: ' + check.stderr.decode(errors='replace'))
            if check.returncode == 2:
                result['status'] = 'findings'
                result['output'] = check.stdout.decode(errors='replace')
    if result['status'] == 'clean' and unverified:
        result['status'] = 'unverified'
    return result
