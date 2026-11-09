"""Check the local reusable review caller without network access."""
import copy
import json
import os
from pathlib import Path
import subprocess
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/auto-reviewer.yaml'
PIN = 'v0.0.1'
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
    assert set(inputs) == {'pr', 'pr_number'}
    for key, description in [('pr', 'PR number'), ('pr_number', 'Legacy PR number')]:
        assert inputs[key]['description'] == description and inputs[key]['required'] is False
    assert w['permissions'] == {'actions': 'read', 'contents': 'write', 'pull-requests': 'write', 'issues': 'read', 'statuses': 'write'}
    assert 'concurrency' not in w
    assert set(w['jobs']) == {'auto_review'}
    job = w['jobs']['auto_review']
    assert set(job) == {'uses', 'with', 'secrets'}
    assert job['uses'] == 'sentimony/github-workflows/.github/workflows/auto-reviewer.yaml@' + PIN
    assert job['with'] == {'required-ci-job': CI_JOB, 'pr': "${{ inputs.pr || '' }}", 'pr_number': "${{ inputs.pr_number || '' }}"}
    assert job['secrets'] == {key: '${{ secrets.' + key + ' }}' for key in ('YNGWALD_PR_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN')}


class CallerContractTest(unittest.TestCase):
    def test_actual_caller(self):
        validate(load())

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
