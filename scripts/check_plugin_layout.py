"""Validate the three-manifest package; optionally prove a byte-preserving migration."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

AGY_SCHEMA = 'https://antigravity.google/schemas/v1/plugin.json'
BASE = {'name', 'version', 'description', 'author', 'homepage', 'repository',
        'license', 'keywords'}
ALLOWED = {
    '.claude-plugin/plugin.json': BASE,
    '.codex-plugin/plugin.json': BASE | {'skills', 'interface'},
    '.antigravity-plugin/plugin.json': BASE | {'$schema', 'displayName',
                                               'suggestedPrompts', 'category'},
}
HIDDEN_PATHS = tuple(ALLOWED)


def load_manifest(root, relative, errors):
    try:
        data = json.loads((root / relative).read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('manifest must be an object')
        return data
    except (OSError, ValueError) as exc:
        errors.append(f'{relative}: {exc}')
        return None


def check_layout(root):
    """Check current metadata and discovery without freezing skill contents."""
    root = Path(root)
    errors = []
    skill_files = sorted(root.glob('skills/*/SKILL.md'))
    names = [p.parent.name for p in skill_files]
    if not names:
        errors.append('no skills/*/SKILL.md found')
    declared = []
    for path in skill_files:
        match = re.search(r'^name:\s*(\S+)\s*$', path.read_text(encoding='utf-8'), re.M)
        name = match.group(1) if match else None
        if name != path.parent.name:
            errors.append(f'{path}: frontmatter name differs from directory')
        if name in declared:
            errors.append(f'{path}: duplicate skill name {name}')
        declared.append(name)
    for path in root.rglob('SKILL.md'):
        if path not in skill_files:
            errors.append(f'{path.relative_to(root)}: skill outside root skills/<name>/')
    for directory in (root / 'skills').iterdir() if (root / 'skills').is_dir() else []:
        if directory.is_dir() and not (directory / 'SKILL.md').is_file():
            errors.append(f'{directory}: missing SKILL.md')
    if (root / 'plugin.json').exists():
        errors.append('root plugin.json returned; the three hidden manifests are the only manifests')
    manifests = {}
    for relative in HIDDEN_PATHS:
        data = load_manifest(root, relative, errors)
        if data is not None:
            manifests[relative] = data
    claude = manifests.get('.claude-plugin/plugin.json', {})
    identity = (claude.get('name'), claude.get('version'))
    if identity[0] != 'agentflow' or not isinstance(identity[1], str) or not re.fullmatch(r'\d+\.\d+\.\d+', identity[1]):
        errors.append('.claude-plugin/plugin.json: identity must be agentflow with a semver version')
    for relative, data in manifests.items():
        if (data.get('name'), data.get('version')) != identity:
            errors.append(f'{relative}: identity name/version differs from .claude-plugin/plugin.json')
        unsupported = set(data) - ALLOWED[relative]
        if unsupported:
            errors.append(f'{relative}: unsupported metadata fields {sorted(unsupported)}')
        if relative == '.codex-plugin/plugin.json':
            if data.get('skills') != './skills/':
                errors.append(f'{relative}: skills path must be ./skills/')
            if not isinstance(data.get('interface'), dict) or not data['interface']:
                errors.append(f'{relative}: interface must be a non-empty object')
        elif 'skills' in data:
            errors.append(f'{relative}: explicit skills can duplicate default discovery')
        if relative == '.antigravity-plugin/plugin.json' and data.get('$schema') != AGY_SCHEMA:
            errors.append(f'{relative}: incorrect schema')
    try:
        release = re.search(r'^## \[(\d+\.\d+\.\d+)\]', (root / 'CHANGELOG.md').read_text(encoding='utf-8'), re.M)
        if not release or release.group(1) != identity[1]:
            errors.append('manifest version differs from newest CHANGELOG release')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f'catalog/release: {exc}')
    return errors


def compare_entries(before, after):
    """Compare relative paths, Git modes/types, and exact bytes."""
    errors = []
    for path in sorted(before.keys() | after.keys()):
        if path not in before or path not in after:
            errors.append(f'{path}: migration file added or removed')
        elif before[path] != after[path]:
            errors.append(f'{path}: migration bytes/type/mode changed')
    return errors


def migration_entries(root, baseline):
    """Read an immutable full commit and the actual destination, including modes."""
    if not re.fullmatch(r'[0-9a-f]{40}', baseline):
        raise ValueError('--baseline requires a full 40-character commit SHA')
    prefix = 'plugins/aw/skills/'
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args])
    before = {}
    for record in git('ls-tree', '-rz', baseline, '--', prefix).split(b'\0'):
        if not record:
            continue
        metadata, path = record.split(b'\t', 1)
        mode, kind, oid = metadata.decode().split()
        relative = path.decode().removeprefix(prefix)
        before[relative] = (mode, kind, git('cat-file', 'blob', oid))
    if not before:
        raise ValueError('baseline has no legacy skills')
    after = {}
    for path in (root / 'skills').rglob('*'):
        if '__pycache__' in path.parts:
            continue
        info = path.lstat()
        relative = path.relative_to(root / 'skills').as_posix()
        if stat.S_ISLNK(info.st_mode):
            after[relative] = ('120000', 'blob', os.readlink(path).encode())
        elif stat.S_ISREG(info.st_mode):
            mode = '100755' if info.st_mode & 0o111 else '100644'
            after[relative] = (mode, 'blob', path.read_bytes())
        elif not stat.S_ISDIR(info.st_mode):
            after[relative] = ('unsupported', 'unsupported', b'')
    return before, after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', help='full immutable pre-move commit SHA; optional one-time proof')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        import unittest
        suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern='test_plugin_layout.py')
        return 0 if unittest.TextTestRunner().run(suite).wasSuccessful() else 1
    root = Path(__file__).resolve().parents[1]
    errors = check_layout(root)
    if args.baseline:
        try:
            before, after = migration_entries(root, args.baseline)
            errors.extend(compare_entries(before, after))
            if not errors:
                print(f'Migration PASS: {len(before)} files, exact bytes/type/mode')
        except (ValueError, OSError, subprocess.CalledProcessError) as exc:
            errors.append(str(exc))
    for error in errors:
        print(f'::error::{error}')
    if not errors:
        print('Plugin layout PASS')
    return int(bool(errors))


if __name__ == '__main__':
    sys.exit(main())
