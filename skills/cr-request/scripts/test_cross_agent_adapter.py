"""Owner policy tests; no real provider, credentials, or OS sandbox."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import cross_agent_adapter as adapter


def report(identity, finding='R2-security-specialist-F1'):
    return '\n'.join([
        'Target reviewed: ' + identity['tree'] + (' ' + identity['document']['sha256']
                                                if identity.get('document') else ''),
        'Reviewer model: fixture', 'Coverage: fixture',
        'Intent: FINDINGS - fixture', 'System: PASS - fixture', 'Craft: PASS - fixture',
        'Summary: Critical 0 | Important 1 | Minor 0',
        'Merge readiness: fixes required', 'Findings:', finding + ' [Important]',
        'Location: fixture.py:1', 'Issue: fixture', 'Impact: fixture',
        'Evidence: fixture', 'Evidence source: reviewer-observed',
        'Evidence attribution: reviewer-observed', 'Not checkable from the diff: none',
        'Set aside: none', 'Open questions: none', 'Strengths: fixture'])


class ReviewPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='owner-adapter-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.env = {'HOME': str(self.root), 'PATH': '/usr/bin:/bin',
                    'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
        self.git('init', '-q')
        (self.repo / 'code.py').write_text('fixture\n')
        (self.repo / 'record.md').write_text('record\n')
        self.git('add', '.')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
                 'commit', '-qm', 'Fixture')

    def git(self, *args):
        return subprocess.check_output(['/usr/bin/git', '-C', str(self.repo), *args],
                                       env=self.env).decode().strip()

    def identity(self):
        return adapter.capture_identity(self.repo, record_host='record.md')

    def test_fingerprint_uses_committed_tree_excluding_record_host(self):
        identity = self.identity()
        self.assertNotEqual(identity['tree'], self.git('rev-parse', 'HEAD^{tree}'))
        self.assertRegex(identity['tree'], r'^[0-9a-f]{40}$')
        (self.repo / 'record.md').write_text('new record\n')
        self.assertEqual(adapter.check_identity(identity), identity)

    def test_committed_excluded_record_host_keeps_content_review_valid(self):
        identity = self.identity()
        (self.repo / 'record.md').write_text('committed review record\n')
        self.git('add', 'record.md')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
                 'commit', '-qm', 'Record review')
        current = self.identity()
        self.assertEqual(current['tree'], identity['tree'])
        self.assertNotEqual(current['head'], identity['head'])
        try:
            checked = adapter.check_identity(identity)
        except ValueError as exc:
            self.fail('excluded-host-only commit invalidated content review: ' + str(exc))
        self.assertEqual(checked['tree'], identity['tree'])

    def test_implementation_drift_and_document_drift_rejected(self):
        identity = self.identity()
        (self.repo / 'code.py').write_text('drift\n')
        with self.assertRaisesRegex(ValueError, 'dirty|stale'):
            adapter.check_identity(identity)
        (self.repo / 'code.py').write_text('fixture\n')
        doc = adapter.capture_identity(self.repo, document='record.md', record_host='record.md')
        (self.repo / 'record.md').write_text('changed doc\n')
        with self.assertRaisesRegex(ValueError, 'stale'):
            adapter.check_identity(doc)

    def test_qualified_ids_counts_and_duplicate_rejection(self):
        identity = self.identity()
        for finding in ('R1-F1', 'R2-codex-F2', 'R3-security-specialist-F1'):
            checked = adapter.validate_review(report(identity, finding), identity)
            self.assertEqual(checked['finding_ids'], [finding])
            self.assertEqual(checked['counts']['Important'], 1)
        with self.assertRaisesRegex(ValueError, 'disagree'):
            adapter.validate_review(report(identity).replace('Important 1', 'Important 0'), identity)
        duplicate = report(identity) + '\nR2-security-specialist-F1 [Important]\n'
        with self.assertRaises(ValueError):
            adapter.validate_review(duplicate, identity)

    def test_partial_review_and_wrong_target_rejected(self):
        identity = self.identity()
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            adapter.validate_review('Intent: PASS - partial', identity)
        with self.assertRaisesRegex(ValueError, 'identity'):
            adapter.validate_review(report(identity).replace(identity['tree'], 'wrong'), identity)

    def test_ambiguous_and_stale_intake_rejected(self):
        identity = self.identity()
        run = self.root / 'run'; run.mkdir()
        path = run / 'review.md'; path.write_text(report(identity))
        import json
        (run / 'identity.json').write_text(json.dumps(identity))
        entry = {'task_id': 'task1', 'role': 'review', 'status': 'COMPLETED',
                 'review_path': str(path), 'identity': identity}
        self.assertEqual(adapter.select_review_intake([entry], 'task1'), entry)
        with self.assertRaisesRegex(ValueError, 'clarify'):
            adapter.select_review_intake([entry, dict(entry)], 'task1')
        with self.assertRaises(ValueError):
            adapter.select_review_intake([entry], 'another-task')
        (self.repo / 'code.py').write_text('changed\n')
        with self.assertRaisesRegex(ValueError, 'stale|dirty'):
            adapter.select_review_intake([entry], 'task1')
        legacy = dict(entry, identity={'schema_version': 0, 'unknown': 'preserve'})
        saved = json.dumps(legacy['identity'])
        (run / 'identity.json').write_text(saved)
        with self.assertRaises(ValueError):
            adapter.select_review_intake([legacy], 'task1')
        self.assertEqual((run / 'identity.json').read_text(), saved)

    def request(self, stage='prepare', role='review', context=None, result=None):
        value = dict(schema_version=1, protocol_version=1, owner_id=adapter.OWNER_ID,
            adapter_id=adapter.ADAPTER_ID, contract_version=1, stage=stage,
            role=role, operation=role, profile='read-only' if role == 'review' else 'execution',
            task_kind='skill', host={'repo': str(self.repo), 'conversation_id': 'fixture'},
            target_identity=self.identity(), owner_context=context or {}, task_selection={})
        value['payload'] = ({'assignment': 'cr-request' if role == 'review' else 'cr-received'}
                            if stage == 'prepare' else {'result': result})
        if stage != 'prepare' and role == 'execution':
            value.update(task_id=(context or {}).get('active_task_id'),
                         session_id='receiver-session', run_id='receiver-run', provider_id='fixture-provider')
        return value

    def execution_fixture(self, *, document=False):
        import json
        identity = (adapter.capture_identity(self.repo, document='record.md', record_host='record.md')
                    if document else self.identity())
        artifact_root = self.root / 'execution-artifacts'; artifact_root.mkdir()
        review_run = artifact_root / 'prior-review'; review_run.mkdir()
        path = review_run / 'review.md'; path.write_text(report(identity))
        (review_run / 'identity.json').write_text(json.dumps(identity))
        entry = {'task_id': 'task1', 'role': 'review', 'status': 'COMPLETED',
                 'review_path': str(path), 'identity': identity}
        context = {'active_task_id': 'task1', 'review_records': [entry],
                   'artifact_root': str(artifact_root), 'intake_binding_id': 'fixture-invocation'}
        prepare = self.request(role='execution', context=context)
        prepare['target_identity'] = identity
        self.assertTrue(adapter.handle(prepare, 'prepare')['payload']['accepted'])
        output = 'R2-security-specialist-F1 ACCEPT - applied fix\n' + '\n'.join(
            label + ': ' + ('verify' if label == 'Route' else 'code.py' if label == 'Changed paths'
                           else 'stale' if label == 'Previous verification' else 'none')
            for label in ('Changed paths', 'Previous verification', 'Checks to rerun',
                'Re-review', 'Blocking', 'Deferred', 'Rulings for the execution record',
                'Durable rulings', 'Route'))
        result = {'status': 'COMPLETED', 'target_identity': identity, 'output': output}
        validate = self.request('validate', role='execution', context=context, result=result)
        validate['target_identity'] = identity
        return identity, path, validate

    def test_receiver_fix_commit_preserves_original_and_captures_post_identity(self):
        identity, path, request = self.execution_fixture()
        original = path.read_bytes()
        (self.repo / 'code.py').write_text('accepted fix\n')
        self.git('add', 'code.py')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
                 'commit', '-qm', 'Address findings')
        try:
            validated = adapter.handle(request, 'validate')['payload']
            request['stage'] = 'intake'
            received = adapter.handle(request, 'intake')['payload']
        except ValueError as exc:
            self.fail('legitimate fix commit rejected at finalization: ' + str(exc))
        self.assertTrue(validated['accepted'])
        self.assertEqual(received['original_identity'], identity)
        self.assertNotEqual(received['post_identity']['tree'], identity['tree'])
        self.assertEqual(received['post_identity']['head'], self.git('rev-parse', 'HEAD'))
        self.assertEqual(path.read_bytes(), original)

    def test_receiver_document_edit_has_separate_post_document_hash(self):
        identity, path, request = self.execution_fixture(document=True)
        original = path.read_bytes()
        (self.repo / 'record.md').write_text('accepted spec revision\n')
        try:
            adapter.handle(request, 'validate')
            request['stage'] = 'intake'
            received = adapter.handle(request, 'intake')['payload']
        except ValueError as exc:
            self.fail('legitimate document edit rejected at finalization: ' + str(exc))
        self.assertEqual(received['original_identity'], identity)
        self.assertNotEqual(received['post_identity']['document']['sha256'],
                            identity['document']['sha256'])
        self.assertEqual(path.read_bytes(), original)

    def test_prepared_review_content_mutation_is_rejected(self):
        identity, path, request = self.execution_fixture()
        path.write_text(report(identity).replace('Issue: fixture', 'Issue: mutated evidence'))
        with self.assertRaisesRegex(ValueError, 'changed|mutat|binding'):
            adapter.handle(request, 'validate')

    def test_validated_execution_cannot_rebind_an_old_result_to_new_content(self):
        identity, path, request = self.execution_fixture()
        adapter.handle(request, 'validate')
        (self.repo / 'code.py').write_text('later unrelated content\n')
        with self.assertRaisesRegex(ValueError, 'post-fix content changed'):
            adapter.handle(request, 'validate')

    def test_prepare_uses_installed_contract_and_rejects_unknown_envelope(self):
        request = self.request()
        prepared = adapter.handle(request, 'prepare')['payload']
        self.assertTrue(prepared['accepted'])
        self.assertIn('Evidence source:', prepared['context'])
        self.assertIn(request['target_identity']['tree'], prepared['context'])
        with self.assertRaises(ValueError):
            adapter.handle(dict(request, callback='/must/not/execute'), 'prepare')
        with self.assertRaises(ValueError):
            adapter.handle(dict(request, contract_version=True), 'prepare')
        stale = dict(request)
        (self.repo / 'code.py').write_text('drift\n')
        self.assertEqual(adapter.handle(stale, 'prepare')['payload']['status'], 'BLOCKED')

    def test_short_intake_needs_current_task_and_does_not_select_random_review(self):
        request = self.request(role='execution')
        stopped = adapter.handle(request, 'prepare')['payload']
        self.assertFalse(stopped['accepted'])
        self.assertEqual(stopped['status'], 'USER_INPUT_REQUIRED')
        self.assertIn('current task', stopped['reason'])

    def test_stale_target_named_elsewhere_does_not_satisfy_review_identity(self):
        identity = self.identity()
        text = report(identity).replace('Target reviewed: ' + identity['tree'], 'Target reviewed: stale')
        with self.assertRaisesRegex(ValueError, 'identity'):
            adapter.validate_review(text + '\nEvidence: ' + identity['tree'], identity)

    def test_receiver_requires_original_qualified_disposition_and_return_block(self):
        identity = self.identity()
        run = self.root / 'prior-review'; run.mkdir()
        path = run / 'review.md'; path.write_text(report(identity))
        import json
        (run / 'identity.json').write_text(json.dumps(identity))
        entry = {'task_id': 'task1', 'role': 'review', 'status': 'COMPLETED',
                 'review_path': str(path), 'identity': identity}
        artifact_root = self.root / 'receiver-artifacts'; artifact_root.mkdir()
        context = {'active_task_id': 'task1', 'review_records': [entry],
                   'artifact_root': str(artifact_root), 'intake_binding_id': 'fixture-receiver'}
        self.assertTrue(adapter.handle(self.request(role='execution', context=context),
                                       'prepare')['payload']['accepted'])
        result = {'status': 'COMPLETED', 'target_identity': identity, 'output': 'done'}
        request = self.request('validate', role='execution', context=context, result=result)
        with self.assertRaisesRegex(ValueError, 'incomplete review resolution'):
            adapter.handle(request, 'validate')
        block = '\n'.join(label + ': ' + ('verify' if label == 'Route' else 'none') for label in (
            'Changed paths', 'Previous verification', 'Checks to rerun', 'Re-review',
            'Blocking', 'Deferred', 'Rulings for the execution record', 'Durable rulings', 'Route'))
        result['output'] = 'R2-security-specialist-F1 ACCEPT - fixture\n' + block
        self.assertEqual(adapter.handle(request, 'validate')['payload']['finding_ids'],
                         ['R2-security-specialist-F1'])
        result['output'] = result['output'].replace('R2-security-specialist-F1', 'R1-F1')
        with self.assertRaisesRegex(ValueError, 'missing disposition'):
            adapter.handle(request, 'validate')

    def test_actual_core_pair_and_resume_after_owner_relocation(self):
        source = os.environ.get('CROSS_AGENT_TEST_SOURCE')
        if not source:
            self.skipTest('explicit standalone source required for paired test')
        import importlib.util
        import json
        import shutil
        import sys
        scripts = Path(source).resolve() / 'skills/cross-agent/scripts'
        sys.path.insert(0, str(scripts))
        self.addCleanup(lambda: sys.path.remove(str(scripts)))
        from cross_agent import HostContext, dispatch
        from cross_agent_request import load_config, parse_request
        from cross_agent_state import TaskContext
        from dataclasses import replace
        fake_bin = self.root / 'bin'; fake_bin.mkdir()
        (fake_bin / 'python3').symlink_to(sys.executable)
        for name in ('codex', 'claude', 'agy'):
            self.assertIsNone(shutil.which(name, path=str(fake_bin)))
        output = report(self.identity())
        fixture = '''#!/usr/bin/env python3
import sys,json,uuid
from pathlib import Path
sys.stdin.read()
args=sys.argv[1:]
sid=args[-2] if 'resume' in args else str(uuid.uuid4())
print(json.dumps({'type':'thread.started','thread_id':sid}))
print(json.dumps({'type':'session_meta','payload':{'model':'gpt-6.1-sol','reasoning_effort':'low'}}))
Path(args[args.index('-o')+1]).write_text(json.dumps({'schema_version':1,'status':'COMPLETED','output':OUTPUT}))
'''.replace('OUTPUT', repr(output))
        (fake_bin / 'codex').write_text(fixture)
        (fake_bin / 'codex').chmod(0o700)
        policy = {'schema_version': 1, 'agents': {'codex': {
            'models': {'gpt-6.1-sol': ['low']}, 'default_model': 'gpt-6.1-sol',
            'default_effort': 'low', 'profiles': ['read-only'],
            'capabilities': {'read-only': 'supported'}}}}
        artifact_root = self.root / 'artifacts'
        binding = {'owner_id': adapter.OWNER_ID, 'adapter_id': adapter.ADAPTER_ID,
                   'protocol_version': 1, 'contract_version': 1,
                   'capabilities': list(adapter.CAPABILITIES),
                   'installed_root': str(Path(adapter.__file__).resolve().parents[1]),
                   'entrypoint': str(Path(adapter.__file__).resolve()), 'interpreter': sys.executable}
        skill = Path(adapter.__file__).resolve().parents[1]
        host = HostContext(load_config(host_config=policy, role='review', profile='read-only'),
            TaskContext(str(self.root / 'registry'), str(self.repo), 'fixture'),
            'claude', str(self.repo), str(artifact_root), self.identity(),
            assignment_kind='skill', installed_skills={'cr-request': {
                'origin': 'fixture-agentflow', 'base': str(skill), 'integration_required': True}},
            integration=binding, owner_context={'artifact_root': str(artifact_root)},
            environment={'HOME': str(self.root), 'PATH': str(fake_bin)}, timeout_seconds=5)
        first = dispatch(parse_request('codex [cr-request]'), host).results[0]
        self.assertEqual(first['status'], 'COMPLETED', first.get('reason'))
        self.assertEqual(first['domain_result']['finding_ids'], ['R2-security-specialist-F1'])
        self.assertTrue(Path(first['domain_intake']['review_path']).is_file())
        relocated = self.root / 'relocated-owner'
        shutil.copytree(skill, relocated)
        moved_binding = dict(binding, installed_root=str(relocated),
                             entrypoint=str(relocated / 'scripts/cross_agent_adapter.py'))
        second = dispatch(parse_request('codex [cr-request]'), replace(host,
            integration=moved_binding, installed_skills={'cr-request': {
                'origin': 'fixture-agentflow', 'base': str(relocated), 'integration_required': True}})).results[0]
        self.assertEqual(second['status'], 'COMPLETED', second.get('reason'))
        self.assertEqual(first['task_id'], second['task_id'])
        self.assertEqual(first['session_id'], second['session_id'])
        self.assertEqual(first['cli_session_id'], second['cli_session_id'])
        resolution = 'R2-security-specialist-F1 ACCEPT - fixture\n' + '\n'.join(
            label + ': ' + ('verify' if label == 'Route' else 'none') for label in ('Changed paths', 'Previous verification',
            'Checks to rerun', 'Re-review', 'Blocking', 'Deferred',
            'Rulings for the execution record', 'Durable rulings', 'Route'))
        self.assertEqual(fixture.count(repr(output)), 1)
        (fake_bin / 'codex').write_text(fixture.replace(repr(output), repr(resolution)))
        execution = json.loads(json.dumps(policy))
        execution['agents']['codex']['profiles'].append('execution')
        execution['agents']['codex']['capabilities']['execution'] = 'supported'
        from cli_transport import VerifiedProfilePolicy
        scoped = VerifiedProfilePolicy('codex', str(self.repo), 'fixture-only-fresh',
            'fixture-only-resume', ('read', 'write-workspace'), True, True)
        receiver = replace(host,
            config=load_config(host_config=execution, role='execution', profile='execution'),
            installed_skills={'cr-received': {'origin': 'fixture-agentflow',
                'base': str(skill.parent / 'cr-received'), 'integration_required': True}},
            owner_context={'artifact_root': str(artifact_root), 'intake_binding_id': 'fixture-core-receiver',
                'active_task_id': first['task_id'], 'review_records': [{
                    'task_id': first['task_id'], 'role': 'review', 'status': 'COMPLETED',
                    'review_path': first['domain_intake']['review_path'],
                    'identity': host.target_identity}]}, policy=scoped)
        received = dispatch(parse_request('codex [cr-received]'), receiver).results[0]
        self.assertEqual(received['status'], 'COMPLETED', received.get('reason'))
        self.assertEqual(received['domain_result']['finding_ids'], ['R2-security-specialist-F1'])


if __name__ == '__main__':
    unittest.main()
