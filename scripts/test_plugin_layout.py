"""Exercise discovery, manifest agreement, and optional migration evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from check_plugin_layout import HIDDEN_PATHS, check_layout, compare_entries


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('first', 'second'):
            p = self.root / 'skills' / name / 'SKILL.md'
            p.parent.mkdir(parents=True)
            p.write_text(f'---\nname: {name}\ndescription: Fixture\n---\n')
        self.interface = {'displayName': 'Fixture'}
        for path in HIDDEN_PATHS:
            self.manifest(path)
        (self.root / 'CHANGELOG.md').write_text('## [1.2.3] - 2026-10-31\n')

    def manifest(self, path):
        data = {'name': 'agentflow', 'version': '1.2.3', 'description': 'Fixture'}
        if path == '.codex-plugin/plugin.json':
            data.update(skills='./skills/', interface=dict(self.interface))
        if path == '.antigravity-plugin/plugin.json':
            data['$schema'] = 'https://antigravity.google/schemas/v1/plugin.json'
        self.write(path, data)
        return data

    def write(self, path, data):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data))

    def fails(self, text):
        errors = check_layout(self.root)
        self.assertTrue(any(text in error for error in errors), errors)

    def test_three_manifest_layout_passes(self):
        self.assertEqual(check_layout(self.root), [])

    def test_root_manifest_rejected(self):
        self.write('plugin.json', {'name': 'agentflow', 'version': '1.2.3'})
        self.fails('root plugin.json returned')

    def test_missing_manifest_rejected(self):
        for path in HIDDEN_PATHS:
            with self.subTest(path=path):
                (self.root / path).unlink()
                self.fails(path)
                self.manifest(path)

    def test_identity_mismatch_rejected(self):
        for path in HIDDEN_PATHS:
            with self.subTest(path=path):
                data = self.manifest(path)
                data['version'] = '1.2.2'
                self.write(path, data)
                self.fails('identity')
                self.manifest(path)

    def test_codex_skills_path_and_interface_required(self):
        path = '.codex-plugin/plugin.json'
        data = self.manifest(path)
        data['skills'] = './plugins/aw/skills/'
        self.write(path, data)
        self.fails('skills path')
        data = self.manifest(path)
        del data['interface']
        self.write(path, data)
        self.fails('interface')

    def test_claude_and_antigravity_skills_field_rejected(self):
        for path in ('.claude-plugin/plugin.json', '.antigravity-plugin/plugin.json'):
            with self.subTest(path=path):
                data = self.manifest(path)
                data['skills'] = './skills/'
                self.write(path, data)
                self.fails('duplicate')
                self.manifest(path)

    def test_antigravity_schema_required(self):
        path = '.antigravity-plugin/plugin.json'
        data = self.manifest(path)
        data['$schema'] = 'https://example.invalid/schema.json'
        self.write(path, data)
        self.fails('incorrect schema')

    def test_previous_plugin_identity_rejected(self):
        for path in ('.codex-plugin/plugin.json', '.claude-plugin/plugin.json'):
            with self.subTest(path=path):
                data = self.manifest(path)
                data['name'] = 'aw'
                self.write(path, data)
                self.fails(f'{path}: identity')
                self.manifest(path)

    def test_empty_discovery_rejected(self):
        for p in self.root.glob('skills/*/SKILL.md'):
            p.unlink()
        self.fails('no skills')

    def test_legacy_path_rejected(self):
        p = self.root / 'plugins/aw/skills/third/SKILL.md'
        p.parent.mkdir(parents=True)
        p.write_text('---\nname: third\n---\n')
        self.fails('outside root')

    def test_release_mismatch_rejected(self):
        (self.root / 'CHANGELOG.md').write_text('## [1.2.4]\n')
        self.fails('release')

    def test_duplicate_frontmatter_name_rejected(self):
        (self.root / 'skills/second/SKILL.md').write_text('---\nname: first\n---\n')
        self.fails('duplicate skill name')

    def test_nonportable_fields_rejected(self):
        for path, key in (('.codex-plugin/plugin.json', 'extensions'),
                          ('.claude-plugin/plugin.json', 'interface')):
            with self.subTest(path=path):
                data = self.manifest(path)
                data[key] = {}
                self.write(path, data)
                self.fails('unsupported')
                self.manifest(path)

    def test_malformed_manifest_rejected(self):
        (self.root / '.codex-plugin/plugin.json').write_text('{')
        self.fails('.codex-plugin/plugin.json')

    def test_migration_detects_blob_type_and_mode_changes(self):
        original = {'first/SKILL.md': ('100644', 'blob', b'original')}
        self.assertEqual(compare_entries(original, copy.deepcopy(original)), [])
        for entry in [('100644', 'blob', b'changed'), ('120000', 'blob', b'original'),
                      ('100755', 'blob', b'original'), ('100644', 'commit', b'original')]:
            with self.subTest(entry=entry):
                self.assertTrue(compare_entries(original, {'first/SKILL.md': entry}))

    def test_migration_detects_missing_and_added_files(self):
        original = {'a': ('100644', 'blob', b'a')}
        self.assertTrue(compare_entries(original, {}))
        self.assertTrue(compare_entries(original, {**original, 'b': ('100644', 'blob', b'b')}))


class GitMigrationTests(unittest.TestCase):
    def test_real_git_baseline_detects_content_mode_and_type(self):
        import os
        import shutil
        import subprocess
        from check_plugin_layout import migration_entries
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args],
                                               stderr=subprocess.DEVNULL)
            git('init', '-q')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            source = root / 'plugins/aw/skills/first/SKILL.md'
            source.parent.mkdir(parents=True)
            source.write_bytes(b'original')
            git('add', '.')
            git('commit', '-qm', 'Fixture baseline')
            baseline = git('rev-parse', 'HEAD').decode().strip()
            shutil.move(str(root / 'plugins/aw/skills'), str(root / 'skills'))
            target = root / 'skills/first/SKILL.md'
            self.assertEqual(compare_entries(*migration_entries(root, baseline)), [])
            target.write_bytes(b'changed')
            self.assertTrue(compare_entries(*migration_entries(root, baseline)))
            target.write_bytes(b'original')
            target.chmod(0o755)
            self.assertTrue(compare_entries(*migration_entries(root, baseline)))
            target.unlink()
            os.symlink('original', target)
            self.assertTrue(compare_entries(*migration_entries(root, baseline)))
            with self.assertRaisesRegex(ValueError, 'full 40'):
                migration_entries(root, baseline[:7])


if __name__ == '__main__':
    unittest.main()
