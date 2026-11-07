"""Exercise root discovery, manifest agreement, and optional migration evidence."""
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
        self.root_manifest = {
            '$schema': 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json',
            'name': 'agentflow', 'version': '1.2.3', 'description': 'Fixture',
            'skills': './skills/',
            'extensions': {'com.openai': {'interface': dict(self.interface)}},
        }
        self.write('plugin.json', self.root_manifest)
        (self.root / 'CHANGELOG.md').write_text('## [1.2.3] - 2026-10-31\n')

    def hidden(self, path):
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

    def fails(self, text, kept=()):
        errors = check_layout(self.root, kept)
        self.assertTrue(any(text in error for error in errors), errors)

    def test_root_only_layout_passes(self):
        self.assertEqual(check_layout(self.root, ()), [])

    def test_returned_hidden_manifest_rejected(self):
        for path in HIDDEN_PATHS:
            with self.subTest(path=path):
                self.hidden(path)
                self.fails('hidden manifest returned')
                (self.root / path).unlink()

    def test_kept_hidden_manifests_pass(self):
        for path in HIDDEN_PATHS:
            self.hidden(path)
        self.assertEqual(check_layout(self.root, HIDDEN_PATHS), [])

    def test_kept_manifest_missing_rejected(self):
        self.fails('.codex-plugin/plugin.json', kept=('.codex-plugin/plugin.json',))

    def test_kept_manifest_empty_rejected(self):
        for path in HIDDEN_PATHS:
            with self.subTest(path=path):
                self.write(path, {})
                self.fails(f'{path}: identity', kept=(path,))

    def test_kept_codex_interface_must_match_root(self):
        data = self.hidden('.codex-plugin/plugin.json')
        data['interface'] = {'displayName': 'Other'}
        self.write('.codex-plugin/plugin.json', data)
        self.fails('interface', kept=('.codex-plugin/plugin.json',))

    def test_kept_identity_mismatch_rejected(self):
        data = self.hidden('.claude-plugin/plugin.json')
        data['version'] = '1.2.2'
        self.write('.claude-plugin/plugin.json', data)
        self.fails('identity', kept=('.claude-plugin/plugin.json',))

    def test_kept_claude_skills_field_rejected(self):
        data = self.hidden('.claude-plugin/plugin.json')
        data['skills'] = ['./skills/first']
        self.write('.claude-plugin/plugin.json', data)
        self.fails('duplicate', kept=('.claude-plugin/plugin.json',))

    def test_root_skills_path_required(self):
        self.root_manifest['skills'] = './plugins/aw/skills/'
        self.write('plugin.json', self.root_manifest)
        self.fails('skills path')

    def test_root_openai_interface_required(self):
        self.root_manifest['extensions'] = {}
        self.write('plugin.json', self.root_manifest)
        self.fails('interface')

    def test_previous_plugin_identity_rejected(self):
        self.root_manifest['name'] = 'aw'
        self.write('plugin.json', self.root_manifest)
        self.fails('root identity')

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
        self.root_manifest['interface'] = {}
        self.write('plugin.json', self.root_manifest)
        self.fails('unsupported')

    def test_malformed_manifest_rejected(self):
        (self.root / 'plugin.json').write_text('{')
        self.fails('plugin.json')

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
