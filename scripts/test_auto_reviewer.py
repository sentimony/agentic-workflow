"""Check the local reusable review caller without network access."""
import copy
import json
import os
from pathlib import Path
import subprocess
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/auto-reviewer.yaml'
PIN = 'v0.0.5'
NAME = 'Auto Reviewer'
CI_JOB = 'validate'


def load():
    script = "require 'yaml'; require 'json'; w=YAML.load_file(ARGV[0], aliases: true); w['on']=w.delete(true) if w.key?(true); puts JSON.generate(w)"
    return json.loads(subprocess.check_output([os.environ.get('RUBY', 'ruby'), '-e', script, str(WORKFLOW)], text=True))


def validate(w):
    assert w['name'] == NAME
    assert set(w['jobs']) == {'auto_review'}
    events = w['on']
    assert set(events) == {'workflow_run', 'pull_request', 'workflow_dispatch'}
    assert events['workflow_run'] == {'workflows': ['CI'], 'types': ['completed']}
    assert events['pull_request']['types'] == ['opened', 'reopened', 'ready_for_review', 'review_requested', 'closed']
    inputs = events['workflow_dispatch']['inputs']
    assert set(inputs) == {'pr'}
    assert inputs['pr']['description'] == 'PR number' and inputs['pr']['required'] is False
    assert w['permissions'] == {'actions': 'read', 'contents': 'write', 'pull-requests': 'write', 'issues': 'read', 'statuses': 'write'}
    assert 'concurrency' not in w
    assert set(w['jobs']) == {'auto_review'}
    job = w['jobs']['auto_review']
    assert set(job) == {'uses', 'with', 'secrets'}
    assert job['uses'] == 'sentimony/github-workflows/.github/workflows/auto-reviewer-shared.yaml@' + PIN
    assert job['with'] == {'required-ci-job': CI_JOB, 'pr': "${{ inputs.pr || '' }}"}
    assert job['secrets'] == {'AUTO_REVIEWER_YNGWALD': '${{ secrets.AUTO_REVIEWER_YNGWALD }}',
                              'CLAUDE_CODE_OAUTH_TOKEN': '${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}'}


class CallerContractTest(unittest.TestCase):
    def test_actual_caller(self):
        validate(load())

    def test_rejects_legacy_pr_number(self):
        for scope in ('dispatch', 'with'):
            with self.subTest(scope=scope):
                w = copy.deepcopy(load())
                if scope == 'dispatch':
                    w['on']['workflow_dispatch']['inputs']['pr_number'] = {'description': 'Legacy PR number', 'required': False}
                else:
                    w['jobs']['auto_review']['with']['pr_number'] = '42'
                with self.assertRaises(AssertionError):
                    validate(w)

    def test_rejects_wrong_workflow_ref_and_secret_contract(self):
        for mutation in ('legacy_secret', 'missing_secret', 'extra_secret', 'old_ref', 'wrong_path'):
            with self.subTest(mutation=mutation):
                w = copy.deepcopy(load())
                job = w['jobs']['auto_review']
                if mutation == 'legacy_secret':
                    job['secrets']['YNGWALD_PR_TOKEN'] = job['secrets'].pop('AUTO_REVIEWER_YNGWALD')
                elif mutation == 'missing_secret':
                    del job['secrets']['AUTO_REVIEWER_YNGWALD']
                elif mutation == 'extra_secret':
                    job['secrets']['EXTRA'] = '${{ secrets.EXTRA }}'
                elif mutation == 'old_ref':
                    job['uses'] = job['uses'].replace('@'+PIN, '@v0.0.1')
                else:
                    job['uses'] = job['uses'].replace('/auto-reviewer-shared.yaml@', '/wrong-workflow.yaml@')
                with self.assertRaises(AssertionError):
                    validate(w)

    def test_rejects_inherit_steps_runner_and_concurrency(self):
        for mutation in ('inherit', 'steps', 'runs-on', 'job_concurrency', 'workflow_concurrency'):
            with self.subTest(mutation=mutation):
                w = copy.deepcopy(load())
                job = w['jobs']['auto_review']
                if mutation == 'inherit': job['secrets'] = 'inherit'
                elif mutation == 'workflow_concurrency': w['concurrency'] = 'review'
                else: job[{'job_concurrency': 'concurrency'}.get(mutation, mutation)] = []
                with self.assertRaises(AssertionError): validate(w)


if __name__ == '__main__':
    unittest.main()
