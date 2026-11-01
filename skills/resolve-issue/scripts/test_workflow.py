"""Synthetic pre-delivery workflow contracts; no services or agent CLIs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import os
import sys
import contextlib
import io
import subprocess
from dataclasses import replace
from unittest.mock import patch

import workflow as w


HEAD = 'a' * 40
TREE = 'b' * 40


def fixture():
    return w.intake('https://github.com/fixture/project/issues/33',
        {'repository': 'fixture/project', 'number': 33, 'available': True,
         'scope': ['approved change'], 'requirements_clear': True},
        {'repository': 'fixture/project', 'base': 'main', 'head': HEAD,
         'tree': TREE, 'workspace': '/scratch/task-33', 'task_id': 'task-33',
         'workspace_task_id': 'task-33', 'workspace_dirty': False,
         'consultants': ['codex', 'claude-code', 'antigravity'],
         'production_contract': 'unknown'}, auto=False)


class Primitives(unittest.TestCase):
    def cli_fixture(self, root, state, *, project_changes=None, issue_changes=None):
        project = {'repository': state['repository'], 'base': state['base'],
            **state['identity'], 'workspace': state['workspace'], 'task_id': state['task_id'],
            'workspace_task_id': state['task_id'], 'workspace_dirty': False,
            'consultants': state['consultants'], 'production_contract': state['production_contract']}
        issue = {'repository': state['repository'], 'number': state['number'], 'available': True,
                 'scope': state['scope'], 'requirements_clear': state['requirements_clear']}
        project.update(project_changes or {})
        issue.update(issue_changes or {})
        (root / 'project.json').write_text(json.dumps(project))
        (root / 'issue.json').write_text(json.dumps(issue))
        return ['intake', state['issue_url'], '--issue-snapshot', str(root / 'issue.json'),
                '--project-snapshot', str(root / 'project.json'), '--state', str(root / 'state.json')]

    def test_cli_resume_retargets_changed_identity_and_invalidates_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = w.store(root / 'state.json', w.record(fixture(), 'passed', evidence=['proof']))
            args = self.cli_fixture(root, state, project_changes={'head': 'c' * 40, 'tree': 'd' * 40})
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(w.main(args), 0)
            resumed = w.load(root / 'state.json')
            self.assertEqual(resumed['identity'], {'head': 'c' * 40, 'tree': 'd' * 40})
            self.assertFalse(resumed['records'][0]['valid'])
            self.assertGreater(resumed['revision'], state['revision'])

    def test_cli_resume_rejects_changed_contract_without_overwriting_state(self):
        for project_change, issue_change in [({'base': 'other'}, {}),
                ({}, {'scope': ['different product scope']}), ({}, {'requirements_clear': False})]:
            with self.subTest(project=project_change, issue=issue_change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                state = w.store(root / 'state.json', fixture())
                before = (root / 'state.json').read_bytes()
                args = self.cli_fixture(root, state, project_changes=project_change, issue_changes=issue_change)
                with self.assertRaises(ValueError), contextlib.redirect_stdout(io.StringIO()):
                    w.main(args)
                self.assertEqual((root / 'state.json').read_bytes(), before)

    def test_cli_resume_refreshes_current_consultants_without_old_auto_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = fixture(); original['consultants'] = ['codex']; original['history_mode'] = 'auto'
            state = w.store(root / 'state.json', original)
            args = self.cli_fixture(root, state, project_changes={'consultants': ['codex', 'agy']})
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(w.main(args), 0)
            resumed = w.load(root / 'state.json')
            self.assertEqual(resumed['consultants'], ['antigravity', 'codex'])
            self.assertEqual(json.loads(output.getvalue())['mode'], 'manual')

    def test_url_and_short_issue_are_same_identity(self):
        state = fixture()
        other = w.parse_issue('#33', 'fixture/project')
        self.assertEqual(state['issue_id'], other['issue_id'])
        with self.assertRaises(ValueError):
            w.parse_issue('#33')
        with self.assertRaises(ValueError):
            w.parse_issue('https://example.invalid/fixture/project/issues/33')

    def test_unavailable_unknown_base_and_foreign_workspace_are_rejected(self):
        for key, value in [('base', None), ('head', 'short'),
                           ('workspace_task_id', 'other'), ('workspace_dirty', True)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                data = {'repository': 'fixture/project', 'base': 'main', 'head': HEAD,
                        'tree': TREE, 'workspace': '/scratch/task-33', 'task_id': 'task-33',
                        'workspace_task_id': 'task-33', 'workspace_dirty': False}
                data[key] = value
                w.intake('#33', {'repository': 'fixture/project', 'number': 33,
                    'available': True, 'scope': ['approved'], 'requirements_clear': True}, data)

    def test_full_handoff_required_and_skips_have_evidence(self):
        state = fixture()
        handoff = w.handoff(state, w.Invocation())
        for key in ('task_id', 'issue_id', 'mode', 'current_stage', 'next_stage',
                    'workspace', 'identity', 'artifacts', 'scope', 'blockers', 'consultations'):
            incomplete = dict(handoff)
            del incomplete[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                w.validate_handoff(incomplete)
        with self.assertRaises(ValueError):
            w.record(state, 'skipped', evidence=['proof'])

    def test_atomic_write_retains_last_confirmed_state(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'state.json'
            state = w.store(path, fixture())
            before = path.read_bytes()
            changed = copy.deepcopy(state)
            changed['blockers'] = ['new blocker']
            with patch.object(w.os, 'replace', side_effect=OSError('interrupted')):
                with self.assertRaises(OSError):
                    w.store(path, changed)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(w.load(path), state)
            stale = copy.deepcopy(state)
            newer = w.store(path, changed)
            self.assertGreater(newer['revision'], state['revision'])
            with self.assertRaises(ValueError):
                w.store(path, stale)

    def test_state_schema_and_delivery_resume_fail_closed(self):
        state = fixture()
        state['current_stage'] = 'deploy'
        with self.assertRaises(ValueError):
            w.validate_state(state)
        state = fixture()
        state['identity']['head'] = 'unknown'
        with self.assertRaises(ValueError):
            w.validate_state(state)


class Transitions(unittest.TestCase):
    def test_ambiguous_specification_needs_fresh_explicit_product_approval(self):
        state = fixture()
        state['requirements_clear'] = False
        calls = []
        def execute(stage, state, args):
            calls.append(stage)
            return {'status': 'passed', 'evidence': ['local proof']}
        state = w.run_loop(state, w.Invocation(auto=True), execute, measure_identity=lambda stage,state:dict(state['identity']))
        self.assertEqual(calls, ['intake', 'specify'])
        self.assertEqual(state['status'], 'awaiting-user')
        state = w.answer_question(state, 'Approved by owner')
        state = w.run_loop(state, w.Invocation(auto=True, requirements_approved=True), execute, measure_identity=lambda stage,state:dict(state['identity']))
        self.assertEqual(state['current_stage'], 'delivery')
        self.assertEqual(state['status'], 'blocked')

    def test_interrupted_loop_preserves_confirmed_progress_and_requires_reconciliation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'state.json'
            initial = w.store(path, fixture())
            def execute(stage, state, args):
                if stage == 'plan-craft':
                    raise OSError('host interrupted')
                return {'status': 'passed', 'evidence': ['intake proof']}
            with self.assertRaises(OSError):
                w.run_loop(initial, w.Invocation(auto=True), execute,
                           checkpoint=lambda state: w.store(path, state), measure_identity=lambda stage,state:dict(state['identity']))
            state = w.load(path)
            self.assertEqual(state['current_stage'], 'plan-craft')
            self.assertEqual(state['status'], 'running')
            self.assertTrue(any(r['stage'] == 'intake' and r['status'] == 'passed'
                                for r in state['records']))
            callback = unittest.mock.Mock()
            result = w.run_loop(state, w.Invocation(auto=True), callback)
            callback.assert_not_called()
            self.assertEqual(result['status'], 'blocked')

    def test_manual_stops_and_one_approval_does_not_enable_auto(self):
        calls = []
        def execute(stage, state, args):
            calls.append((stage, args))
            return {'status': 'passed', 'evidence': ['local proof']}
        state = w.run_loop(fixture(), w.Invocation(), execute)
        self.assertEqual([x[0] for x in calls], ['intake'])
        self.assertEqual(state['current_stage'], 'plan-craft')
        self.assertEqual(state['status'], 'awaiting-user')
        self.assertEqual(w.handoff(state, w.Invocation())['next_stage'], 'plan-craft')
        state = w.run_loop(state, w.Invocation(), execute)
        self.assertEqual(len(calls), 1)
        state = w.run_loop(state, w.Invocation(approve_stage='plan-craft'), execute, measure_identity=lambda stage,state:dict(state['identity']))
        self.assertEqual([x[0] for x in calls], ['intake', 'plan-craft'])
        self.assertEqual(state['status'], 'awaiting-user')

    def test_auto_propagates_but_stops_at_missing_delivery_contract(self):
        calls = []
        def execute(stage, state, args):
            calls.append((stage, args))
            return {'status': 'passed', 'evidence': ['local proof']}
        state = w.run_loop(fixture(), w.Invocation(auto=True), execute, measure_identity=lambda stage,state:dict(state['identity']))
        self.assertEqual(state['status'], 'blocked')
        self.assertEqual(state['current_stage'], 'delivery')
        self.assertTrue(all('--auto' in args for _, args in calls))
        self.assertTrue(any('G3' in reason for reason in state['blockers']))
        self.assertNotIn('delivery', [x[0] for x in calls])

    def test_old_auto_history_never_grants_current_permission(self):
        state = fixture()
        state['history_mode'] = 'auto'
        state['status'] = 'awaiting-user'
        state['current_stage'] = 'plan-craft'
        calls = []
        state = w.run_loop(state, w.Invocation(), lambda *args: calls.append(args))
        self.assertEqual(calls, [])
        self.assertEqual(state['status'], 'awaiting-user')

    def test_head_change_invalidates_results_and_round_limit_stops_retry(self):
        state = w.record(fixture(), 'passed', evidence=['proof'])
        state = w.retarget(state, {'head': 'c' * 40, 'tree': 'd' * 40})
        self.assertEqual(state['records'][0]['valid'], False)
        calls = []
        def fail(stage, state, args):
            calls.append(stage)
            return {'status': 'failed', 'evidence': ['red check']}
        state = w.run_loop(fixture(), w.Invocation(auto=True, max_rounds=2), fail)
        self.assertEqual(len(calls), 2)
        self.assertEqual(state['status'], 'blocked')

    def test_unknown_result_and_no_evidence_never_pass(self):
        for result in ({'status': 'passed'}, {'status': 'bogus', 'evidence': ['x']}):
            with self.subTest(result=result), self.assertRaises(ValueError):
                w.run_loop(fixture(), w.Invocation(auto=True), lambda *args: result)


class Consultations(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('CROSS_AGENT_TEST_SOURCE'), 'explicit standalone source not supplied; pair unverified')
    def test_actual_standalone_core_with_fake_read_only_agent(self):
        import importlib
        core_scripts = Path(os.environ['CROSS_AGENT_TEST_SOURCE']) / 'skills/cross-agent/scripts'
        sys.path.insert(0, str(core_scripts))
        self.addCleanup(lambda: sys.path.remove(str(core_scripts)))
        core = importlib.import_module('cross_agent')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); binary = root / 'bin'; binary.mkdir()
            (binary / 'python3').symlink_to(sys.executable)
            cli = binary / 'codex'
            cli.write_text('''#!/usr/bin/env python3
import sys,json,uuid
from pathlib import Path
sys.stdin.read()
sid=sys.argv[-2] if 'resume' in sys.argv else str(uuid.uuid4())
print(json.dumps({'type':'thread.started','thread_id':sid}))
print(json.dumps({'type':'session_meta','payload':{'model':'gpt-6.1-sol','reasoning_effort':'low'}}))
Path(sys.argv[sys.argv.index('-o')+1]).write_text(json.dumps({'schema_version':1,'status':'COMPLETED','output':'fixture opinion'}))
''')
            cli.chmod(0o700)
            policy = {'schema_version':1,'agents':{'codex':{'models':{'gpt-6.1-sol':['low']},
                'default_model':'gpt-6.1-sol','default_effort':'low','profiles':['read-only'],
                'capabilities':{'read-only':'supported'}}}}
            host = core.HostContext(core.load_config(host_config=policy, role='consultation', profile='read-only'),
                core.TaskContext(str(root/'registry'),str(root),'fixture-conversation'),
                'claude',str(root),str(root/'artifacts'),{'head':HEAD,'tree':TREE},
                environment={'PATH':str(binary),'HOME':str(root)},timeout_seconds=3)
            consultant = w.make_consultant(core, host)
            result = consultant('codex', {'question':'Which scope?'}, fixture())
            self.assertEqual(result['status'], 'COMPLETED', result)
            self.assertEqual(result['output'], 'fixture opinion')
            current = dict(host.target_identity)
            def measured(stage, state):
                return dict(current)
            def execute(stage, state, args):
                if stage == 'implement':
                    current.update(head='c'*40, tree='d'*40)
                    return {'status':'passed','evidence':['post-edit proof']}
                return {'status':'awaiting-user','question':'Decision for the changed target?'}
            def refreshed_consultant(family, question, state):
                identity = measured(None, state)
                self.assertEqual(identity, state['identity'])
                return w.make_consultant(core, replace(host, target_identity=identity))(family, question, state)
            state = fixture(); state['current_stage'] = 'implement'; state['consultants'] = ['codex']
            result = w.run_loop(state, w.Invocation(auto=True), execute,
                measure_identity=measured, consult=refreshed_consultant,
                host_family='claude', executor_family='claude')
            self.assertEqual(result['status'], 'awaiting-user')
            self.assertEqual(result['consultations'][0]['status'], 'COMPLETED')
            self.assertEqual(result['consultations'][0]['target_identity'], current)
            with patch.dict(os.environ, {'CROSS_AGENT_DELEGATED':'1'}), self.assertRaises(ValueError):
                consultant('codex', {'question':'Which scope?'}, fixture())

    def test_auto_attempts_every_other_family_before_one_question(self):
        calls = []
        def consult(family, question, state):
            calls.append(family)
            if family == 'antigravity':
                raise TimeoutError('unavailable')
            return {'status': 'COMPLETED', 'output': 'keep scope'}
        question = {'question': 'Change product requirements?', 'options': ['A', 'B'],
                    'evidence': ['scope conflict']}
        state = w.critical_question(fixture(), w.Invocation(auto=True), question,
                                   consult, host_family='codex', executor_family='codex')
        self.assertEqual(calls, ['antigravity', 'claude-code'])
        self.assertEqual(state['status'], 'awaiting-user')
        self.assertEqual(len(state['consultations']), 2)
        self.assertTrue(any(x['status'] == 'UNAVAILABLE' for x in state['consultations']))
        self.assertEqual(state['question']['question'], question['question'])

    def test_manual_question_and_cancel_do_not_call_consultants(self):
        consult = unittest.mock.Mock()
        state = w.critical_question(fixture(), w.Invocation(), {'question': 'Which?'}, consult)
        consult.assert_not_called()
        self.assertEqual(state['status'], 'awaiting-user')
        state = w.critical_question(fixture(), w.Invocation(auto=True),
            {'question': 'Which?'}, consult, cancelled=lambda: True)
        consult.assert_not_called()
        self.assertEqual(state['status'], 'blocked')

    def test_delegated_executor_returns_handoff_without_nested_launcher(self):
        consult = unittest.mock.Mock()
        state = w.critical_question(fixture(), w.Invocation(auto=True, delegated=True),
                                   {'question': 'Which?'}, consult)
        consult.assert_not_called()
        self.assertEqual(state['status'], 'awaiting-user')
        self.assertEqual(state['handoff']['kind'], 'CONSULTATION_REQUIRED')

    def test_host_opinion_for_delegated_other_executor_and_no_consensus_approval(self):
        calls = []
        def consult(family, question, state):
            calls.append(family)
            return {'status': 'COMPLETED', 'output': 'unanimous'}
        state = w.critical_question(fixture(), w.Invocation(auto=True), {'question': 'Which?'},
            consult, host_family='codex', executor_family='claude-code', host_opinion='host view')
        self.assertEqual(calls, ['antigravity'])
        self.assertEqual(state['status'], 'awaiting-user')
        self.assertEqual({x['family'] for x in state['consultations']}, {'codex', 'antigravity'})


class ReviewRegressionTests(unittest.TestCase):
    def test_r2_real_spec_and_plan_commits_and_same_tree_bookkeeping(self):
        for stage in ('specify', 'plan-craft', 'verify'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                def git(*args):
                    return subprocess.check_output(['/usr/bin/git','-C',str(root),*args], text=True,
                        stderr=subprocess.DEVNULL,env={'PATH':'/usr/bin:/bin','HOME':str(root),
                            'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'}).strip()
                git('init','-q');git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
                (root/'artifact.md').write_text('initial\n');git('add','artifact.md');git('commit','-qm','initial')
                def measure(*args):return {'head':git('rev-parse','HEAD'),'tree':git('rev-parse','HEAD^{tree}')}
                state=fixture();state['identity']=measure();state=w.record(state,'passed',stage='intake',evidence=['old proof'])
                before=dict(state['identity']);state['current_stage']=stage;state['status']='pending';calls=[]
                def execute(current,state,args):
                    calls.append(current)
                    if current==stage:
                        if stage!='verify':
                            (root/'artifact.md').write_text(stage+' document\n');git('add','artifact.md')
                        git('commit','--allow-empty','-qm',stage+' checkpoint')
                    return {'status':'passed','evidence':['current check']}
                result=w.run_loop(state,w.Invocation(auto=True,requirements_approved=True),execute,measure_identity=measure)
                self.assertEqual(result['current_stage'],'delivery');self.assertEqual(calls.count(stage),1)
                self.assertEqual(result['identity'],measure())
                if stage=='verify':
                    self.assertEqual(before['tree'],result['identity']['tree'])
                    self.assertTrue(result['records'][0]['valid'])
                    self.assertEqual(result['records'][0]['origin_identity'],before)
                else:self.assertFalse(result['records'][0]['valid'])

    def test_r2_interrupted_consultation_batch_is_not_answerable_or_resettable(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'state.json';state=w.store(path,fixture());calls=[]
            def consult(family,*args):calls.append(family);return {'status':'COMPLETED','output':'saved opinion'}
            def checkpoint(value):
                saved=w.store(path,value)
                if saved['consultations']:raise OSError('host interrupted after durable response')
                return saved
            with self.assertRaises(OSError):
                w.critical_question(state,w.Invocation(auto=True),{'question':'Which?'},consult,checkpoint=checkpoint)
            saved=w.load(path);self.assertEqual(calls,['antigravity']);self.assertNotIn('question',saved)
            self.assertEqual(saved['consultation_batch']['remaining'],['claude-code'])
            callback=unittest.mock.Mock()
            result=w.run_loop(saved,w.Invocation(auto=True),callback,consult=callback)
            callback.assert_not_called();self.assertEqual(result['status'],'blocked')
            with self.assertRaises(ValueError):w.answer_question(saved,'premature answer')
            with self.assertRaises(ValueError):w.critical_question(saved,w.Invocation(auto=True),{'question':'Reset?'},callback)
            callback.assert_not_called()
            refreshed=w.retarget(saved,{'head':'c'*40,'tree':'d'*40})
            self.assertNotIn('consultation_batch',refreshed)
            self.assertEqual(refreshed['stale_questions'][0]['consultation_batch']['remaining'],['claude-code'])

    def test_r2_inflight_attempt_requires_host_evidence_before_reconciliation(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'state.json';state=w.store(path,fixture());callback=unittest.mock.Mock()
            def checkpoint(value):
                saved=w.store(path,value)
                if saved['consultation_batch']['in_flight']:raise OSError('unknown call outcome')
                return saved
            with self.assertRaises(OSError):
                w.critical_question(state,w.Invocation(auto=True),{'question':'Which?'},callback,checkpoint=checkpoint)
            callback.assert_not_called();saved=w.load(path)
            self.assertEqual(saved['consultation_batch']['in_flight'],'antigravity')
            result=w.run_loop(saved,w.Invocation(auto=True),callback,consult=callback)
            callback.assert_not_called();self.assertEqual(result['status'],'blocked')
            with self.assertRaises(ValueError):
                w.reconcile_consultation(saved,'antigravity',{'status':'UNAVAILABLE'},evidence=[])
            fixed=w.reconcile_consultation(saved,'antigravity',{'status':'COMPLETED','output':'recovered opinion'},evidence=['verified prior result'])
            self.assertEqual(fixed['status'],'blocked');self.assertNotIn('question',fixed)
            fixed=w.reconcile_consultation(fixed,'claude-code',{'status':'UNAVAILABLE','reason':'verified unavailable'},evidence=['actual host attempt'])
            self.assertEqual(fixed['status'],'awaiting-user');self.assertEqual(len(fixed['consultations']),2)
            self.assertEqual(w.answer_question(fixed,'explicit user answer')['status'],'pending')

    def test_f1_read_only_target_change_stays_blocked(self):
        current = {'head':HEAD, 'tree':TREE}
        state = fixture(); state['current_stage'] = 'verify'
        def execute(*args):
            current.update(head='c'*40, tree='d'*40)
            return {'status':'passed','evidence':['stale readonly output']}
        result = w.run_loop(state, w.Invocation(auto=True), execute,
                           measure_identity=lambda *args:dict(current))
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(any(r['stage']=='verify' and r['status']=='passed' for r in result['records']))

    def test_f1_changed_findings_fix_repeats_verification_and_review(self):
        state = fixture(); state['current_stage'] = 'code-review'
        state = w.record(state, 'passed', evidence=['old review'])
        state['current_stage'] = 'cr-received'; state['status'] = 'pending'
        current = dict(state['identity']); calls = []
        def execute(stage, state, args):
            calls.append(stage)
            if len(calls)==1:
                current.update(head='c'*40, tree='d'*40)
            return {'status':'passed','evidence':['current proof']}
        result = w.run_loop(state, w.Invocation(auto=True), execute,
                           measure_identity=lambda *args:dict(current))
        self.assertEqual(calls, ['cr-received','verify','code-review','cr-received','review-verify'])
        self.assertFalse(result['records'][0]['valid'])
        self.assertEqual(result['status'], 'blocked')

    def test_f1_host_measurement_adopts_real_post_commit_before_verify(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            def git(*args):
                return subprocess.check_output(['/usr/bin/git', '-C', str(root), *args],
                    env={'PATH':'/usr/bin:/bin','HOME':str(root),
                         'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'},
                    stderr=subprocess.DEVNULL, text=True).strip()
            git('init', '-q')
            git('config', 'user.name', 'Fixture'); git('config', 'user.email', 'fixture@example.invalid')
            (root / 'code.py').write_text('value = 1\n'); git('add', 'code.py'); git('commit', '-qm', 'initial')
            def measured(stage, state):
                return {'head':git('rev-parse', 'HEAD'), 'tree':git('rev-parse', 'HEAD^{tree}')}
            state = fixture(); state['workspace'] = str(root); state['identity'] = measured(None, None)
            state = w.record(state, 'passed', stage='plan-review', evidence=['old proof'])
            state['current_stage'] = 'implement'; state['status'] = 'pending'
            calls = []
            def execute(stage, state, args):
                calls.append(stage)
                if stage == 'implement':
                    (root / 'code.py').write_text('value = 2\n'); git('add', 'code.py'); git('commit', '-qm', 'implementation')
                    return {'status':'passed','evidence':['post-edit result'], 'identity':measured(stage, state)}
                self.assertEqual(state['identity'], measured(stage, state))
                return {'status':'passed','evidence':['fresh checks']}
            result = w.run_loop(state, w.Invocation(auto=True), execute, measure_identity=measured)
            self.assertEqual(calls.count('implement'), 1)
            self.assertFalse(result['records'][0]['valid'])
            self.assertEqual(result['identity'], measured(None, None))
            self.assertEqual(result['current_stage'], 'delivery')

    def test_f1_missing_measurement_blocks_and_provider_cannot_choose_target(self):
        state = fixture(); state['current_stage'] = 'implement'
        callback = unittest.mock.Mock(return_value={'status':'passed','evidence':['model says pass']})
        result = w.run_loop(state, w.Invocation(auto=True), callback)
        callback.assert_not_called(); self.assertEqual(result['status'], 'blocked')
        with self.assertRaises(ValueError):
            w.run_loop(state, w.Invocation(auto=True), lambda *args:{'status':'passed',
                'evidence':['provider result'], 'identity':{'head':'e'*40,'tree':'f'*40}},
                measure_identity=lambda stage, state:dict(state['identity']))

    def test_f2_retarget_archives_stale_question_and_unstrands_state(self):
        old = fixture()['identity']
        state = w.critical_question(fixture(), w.Invocation(delegated=True), {'question':'Old target?'})
        state = w.retarget(state, {'head':'c'*40,'tree':'d'*40})
        self.assertNotIn('question', state); self.assertNotIn('handoff', state)
        self.assertEqual(state['stale_questions'][0]['identity'], old)
        self.assertEqual(state['stale_questions'][0]['question']['question'], 'Old target?')
        calls = []
        result = w.run_loop(state, w.Invocation(), lambda *args: calls.append(args) or {'status':'passed','evidence':['new target']})
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['status'], 'awaiting-user')

    def test_f3_cancel_preserves_first_completed_response_and_checkpoint(self):
        cancelled = [False]; snapshots = []
        def consult(*args):
            cancelled[0] = True
            return {'status':'COMPLETED','output':'retained opinion'}
        result = w.critical_question(fixture(), w.Invocation(auto=True), {'question':'Which?'},
            consult, cancelled=lambda:cancelled[0], checkpoint=lambda state:snapshots.append(copy.deepcopy(state)) or state)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['consultations'][0]['output'], 'retained opinion')
        self.assertTrue(any(s['consultations'] for s in snapshots))

    def test_f4_reconciled_terminal_stage_advances_once_and_manual_waits(self):
        for status in ('passed', 'skipped'):
            state = fixture(); state['current_stage'] = 'implement'; state['status'] = 'running'
            state = w.record(state, status, evidence=['host reconciled'], reason='verified no-op' if status=='skipped' else None)
            calls = []
            result = w.run_loop(state, w.Invocation(auto=True), lambda stage,*args:calls.append(stage) or
                {'status':'passed','evidence':['fresh proof']}, measure_identity=lambda stage,state:dict(state['identity']))
            self.assertNotIn('implement', calls); self.assertEqual(calls[0], 'verify')
            callback = unittest.mock.Mock()
            result = w.run_loop(state, w.Invocation(), callback, measure_identity=lambda stage,state:dict(state['identity']))
            callback.assert_not_called(); self.assertEqual(result['current_stage'], 'verify')
            self.assertEqual(result['status'], 'awaiting-user')

    def test_f4_fabricated_terminal_status_is_not_reconciliation(self):
        state = fixture(); state['current_stage'] = 'implement'; state['status'] = 'passed'
        with self.assertRaises(ValueError):
            w.run_loop(state, w.Invocation(auto=True), lambda *args:None,
                       measure_identity=lambda stage,state:dict(state['identity']))


if __name__ == '__main__':
    unittest.main()
