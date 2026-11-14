#!/usr/bin/env python3
"""Snapshots of initially dirty files for the execution record (`Snapshot:` lines).

`capture` reads the bytes of regular files inside a repository and stores them under
a private directory; it never runs a Git command that writes and never touches the
index or the working files. `parse` validates `Snapshot:` lines against the stored
bytes and returns the mapping `cr-request`'s `check_whitespace` takes as `snapshots`.

Line format (path and file are bare tokens, or JSON strings when they contain anything
outside a conservative safe set):

    Snapshot: <path> sha256 <hex> file <absolute path>
    Snapshot: <path> unavailable <reason>
"""
import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

PREFIX = 'Snapshot: '
_SAFE = re.compile(r'[A-Za-z0-9._/@%+=,:~-]+')
_TOKEN = r'(?:"(?:[^"\\]|\\.)*"|[^\s"]+)'
_FILE_LINE = re.compile(r'(?P<path>' + _TOKEN + r') sha256 (?P<sha>[0-9a-f]{64}) file (?P<file>' + _TOKEN + r')')
_UNAVAILABLE_LINE = re.compile(r'(?P<path>' + _TOKEN + r') unavailable (?P<reason>[^\x00-\x1f\x7f]{1,200})')


def _enc(text):
    return text if _SAFE.fullmatch(text) else json.dumps(text, ensure_ascii=False)


def _dec(token):
    if token.startswith('"'):
        try:
            value = json.loads(token)
        except ValueError:
            raise ValueError('malformed quoted field')
        if not isinstance(value, str):
            raise ValueError('malformed quoted field')
        return value
    return token


def _inside(repo, relative):
    """Return the clean relative path, or raise ValueError when it leaves the repository."""
    if not relative or '\0' in relative or os.path.isabs(relative):
        raise ValueError('path is not relative to the repository')
    parts = Path(relative).parts
    if '..' in parts or '.' in parts or not parts:
        raise ValueError('path leaves the repository')
    if '/'.join(parts) != relative:
        raise ValueError('path is not canonical')
    return '/'.join(parts)


def _unavailable(path, reason):
    return {'path': path, 'status': 'unavailable', 'reason': reason,
            'line': PREFIX + _enc(path) + ' unavailable ' + reason}


def capture(repo, paths, store):
    """Store the current bytes of each path; return one result dict per path.

    Each result has `path`, `status` (`file` or `unavailable`) and `line`. A symlink, a
    non-regular file, a path outside the repository and an unreadable file are
    `unavailable`; nothing is stored for them and `HEAD` is never substituted.
    """
    repo = Path(os.path.realpath(repo))
    store = Path(store)
    store.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(store, 0o700)
    results = []
    for given in paths:
        text = os.fspath(given)
        if os.path.isabs(text) and Path(text).is_relative_to(repo):
            text = str(Path(text).relative_to(repo))
        try:
            relative = _inside(repo, text)
        except ValueError:
            results.append(_unavailable(text.replace('\n', ' ') or 'empty', 'outside repository'))
            continue
        full = repo / relative
        try:
            info = os.lstat(full)
        except OSError:
            results.append(_unavailable(relative, 'unreadable'))
            continue
        if stat.S_ISLNK(info.st_mode):
            results.append(_unavailable(relative, 'symlink'))
            continue
        if not stat.S_ISREG(info.st_mode):
            results.append(_unavailable(relative, 'not a regular file'))
            continue
        # A parent component that is a symlink would let the path leave the repository.
        if Path(os.path.realpath(full.parent)) != Path(os.path.realpath(repo / Path(relative).parent)) \
                or not Path(os.path.realpath(full)).is_relative_to(repo):
            results.append(_unavailable(relative, 'outside repository'))
            continue
        try:
            fd = os.open(full, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
            with os.fdopen(fd, 'rb') as handle:
                data = handle.read()
        except OSError:
            results.append(_unavailable(relative, 'unreadable'))
            continue
        digest = hashlib.sha256(data).hexdigest()
        target = store / digest
        if not (target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == digest):
            with tempfile.NamedTemporaryFile(dir=store, prefix='.tmp-', delete=False) as temp:
                temp.write(data)
            os.chmod(temp.name, 0o400)
            os.replace(temp.name, target)
        results.append({'path': relative, 'status': 'file', 'sha256': digest, 'file': str(target),
                        'line': PREFIX + _enc(relative) + ' sha256 ' + digest + ' file ' + _enc(str(target))})
    return results


def parse(line, repo):
    """Validate one `Snapshot:` line; return a dict or raise ValueError."""
    if not line.startswith(PREFIX):
        raise ValueError('not a Snapshot line')
    body = line[len(PREFIX):].rstrip('\n')
    match = _FILE_LINE.fullmatch(body)
    other = None if match else _UNAVAILABLE_LINE.fullmatch(body)
    if not match and not other:
        raise ValueError('malformed Snapshot line (wrong or extra fields)')
    found = match or other
    path = _inside(repo, _dec(found.group('path')))
    if other:
        return {'path': path, 'status': 'unavailable', 'reason': other.group('reason')}
    file = _dec(match.group('file'))
    if not os.path.isabs(file):
        raise ValueError('snapshot file path is not absolute')
    try:
        data = Path(file).read_bytes()
    except OSError:
        raise ValueError('snapshot file is unreadable')
    if hashlib.sha256(data).hexdigest() != match.group('sha'):
        raise ValueError('snapshot hash does not match the stored bytes')
    return {'path': path, 'status': 'file', 'sha256': match.group('sha'), 'file': file}


def parse_lines(lines, repo):
    """Read every `Snapshot:` line; return {'snapshots', 'unavailable', 'rejected'}.

    `snapshots` is the mapping for `check_whitespace`. A rejected line contributes nothing,
    so its path stays without a before-snapshot (`unverified`).
    """
    result = {'snapshots': {}, 'unavailable': {}, 'rejected': []}
    for line in lines:
        if not line.startswith(PREFIX):
            continue
        try:
            item = parse(line, repo)
        except ValueError as error:
            result['rejected'].append({'line': line.rstrip('\n'), 'reason': str(error)})
            continue
        if item['status'] == 'file':
            result['snapshots'][item['path']] = {'sha256': item['sha256'], 'file': item['file']}
            result['unavailable'].pop(item['path'], None)
        else:
            result['unavailable'][item['path']] = item['reason']
            result['snapshots'].pop(item['path'], None)
    return result


def _slug(path):
    resolved = str(Path(path).resolve())
    digest = hashlib.sha256(os.fsencode(resolved)).hexdigest()[:12]
    return re.sub(r'[^A-Za-z0-9._-]', '_', Path(resolved).name or 'root')[:64] + '-' + digest


def default_store(repo, home=None):
    """`~/.sentimony/agentflow/implement/<project>/<branch>/snapshots`."""
    home = home or os.environ.get('HOME', '')
    if not home or not os.path.isabs(home):
        raise ValueError('HOME is not usable')

    def run(*args):
        done = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True)
        if done.returncode:
            raise ValueError('git failed: ' + done.stderr.strip())
        return done.stdout.rstrip('\n')
    common = Path(os.path.realpath(run('rev-parse', '--path-format=absolute', '--git-common-dir')))
    key = common.parent if common.name == '.git' else common
    branch = run('rev-parse', '--abbrev-ref', 'HEAD')
    branch = 'detached' if branch == 'HEAD' else branch
    safe = re.sub(r'[^A-Za-z0-9._-]', '_', branch)[:64] + '-' + hashlib.sha256(branch.encode()).hexdigest()[:8]
    return Path(home) / '.sentimony' / 'agentflow' / 'implement' / _slug(key) / safe / 'snapshots'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    cap = sub.add_parser('capture', help='store paths and print Snapshot lines')
    cap.add_argument('--repo', default=os.getcwd())
    cap.add_argument('--store')
    cap.add_argument('--home')
    cap.add_argument('paths', nargs='*')
    par = sub.add_parser('parse', help='validate Snapshot lines read from a file or stdin')
    par.add_argument('--repo', default=os.getcwd())
    par.add_argument('file', nargs='?', default='-')
    args = parser.parse_args(argv)
    try:
        if args.command == 'capture':
            store = args.store or default_store(args.repo, args.home)
            for item in capture(args.repo, args.paths, store):
                print(item['line'])
            return 0
        text = sys.stdin.read() if args.file == '-' else Path(args.file).read_text(encoding='utf-8')
        result = parse_lines(text.splitlines(), args.repo)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result['rejected'] else 0
    except (ValueError, OSError) as error:
        print('snapshot_record: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
