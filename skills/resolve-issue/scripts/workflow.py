"""Durable, host-controlled resolve-issue preparation up to the delivery gate.

No service client or shell executor lives here. The trusted host supplies current
permissions, issue snapshots, stage executors and the installed generic launcher.
Persisted mode and provider output never grant permissions. Delivery consumes the
installed owner's G3 helpers through explicit current project callbacks and proofs.
"""
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
import argparse
import copy
import fcntl
import json
import os
import re
import stat
import tempfile
import uuid

PRE_DELIVERY = ('intake', 'specify', 'plan-craft', 'plan-review', 'implement',
                'verify', 'code-review', 'cr-received', 'review-verify')
STAGES = PRE_DELIVERY + ('delivery',)
STAGE_EFFECTS = dict.fromkeys(PRE_DELIVERY, 'bookkeeping')
STAGE_EFFECTS.update(intake='read-only', specify='target-write', **{
    'plan-craft':'target-write', 'implement':'target-write', 'cr-received':'target-write'})
STATUSES = frozenset(('pending', 'running', 'passed', 'awaiting-user', 'blocked', 'failed', 'skipped'))
SHA = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')
REPO = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z')
HANDOFF_FIELDS = frozenset(('task_id', 'issue_id', 'mode', 'current_stage', 'next_stage',
    'workspace', 'identity', 'artifacts', 'scope', 'blockers', 'consultations'))
FAMILIES = {'codex': 'codex', 'claude': 'claude-code', 'claude-code': 'claude-code',
            'agy': 'antigravity', 'antigravity': 'antigravity'}


@dataclass(frozen=True)
class Invocation:
    """Only a fresh trusted host invocation can construct transition authority."""
    auto: bool = False
    approve_stage: object = None
    max_rounds: int = 3
    delegated: bool = False
    requirements_approved: bool = False
    permitted_stages: tuple = PRE_DELIVERY

    def __post_init__(self):
        if any(type(value) is not bool for value in (self.auto, self.delegated, self.requirements_approved)):
            raise ValueError('Invocation flags must be booleans')
        if type(self.max_rounds) is not int or self.max_rounds < 1:
            raise ValueError('Round limit must be positive')
        if self.approve_stage is not None and self.approve_stage not in STAGES:
            raise ValueError('Unknown transition approval')
        if any(stage not in STAGES for stage in self.permitted_stages):
            raise ValueError('Unknown permitted stage')


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Missing ' + label)
    return value


def _strings(value, label, required=False):
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise ValueError('Invalid ' + label)
    if required and not value:
        raise ValueError('Missing ' + label)
    return value


def _identity(value):
    if not isinstance(value, dict) or set(value) != {'head', 'tree'}:
        raise ValueError('Identity must contain full head and tree')
    if any(not isinstance(v, str) or not SHA.fullmatch(v) for v in value.values()):
        raise ValueError('Unknown or abbreviated identity')
    return value


def parse_issue(value, repository=None):
    _text(value, 'issue reference')
    match = re.fullmatch(r'https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/issues/([1-9][0-9]*)/?', value)
    if match:
        repo, number = match[1], int(match[2])
    elif re.fullmatch(r'#[1-9][0-9]*', value):
        if not isinstance(repository, str) or not REPO.fullmatch(repository):
            raise ValueError('Short issue needs one known repository')
        repo, number = repository, int(value[1:])
    else:
        raise ValueError('Expected GitHub issue URL or unambiguous #number')
    if repository is not None and repo.lower() != repository.lower():
        raise ValueError('Issue repository differs from the trusted checkout')
    return {'repository': repo, 'number': number, 'issue_id': f'{repo.lower()}#{number}',
            'issue_url': f'https://github.com/{repo}/issues/{number}'}


def intake(reference, snapshot, project, *, auto=False):
    """Read operator-supplied snapshots; issue body cannot supply project authority."""
    issue = parse_issue(reference, project.get('repository'))
    if (not isinstance(snapshot, dict) or snapshot.get('available') is not True or
            str(snapshot.get('repository', '')).lower() != issue['repository'].lower() or
            type(snapshot.get('number')) is not int or snapshot['number'] != issue['number']):
        raise ValueError('Issue snapshot unavailable or mismatched')
    _text(project.get('base'), 'verified base')
    identity = _identity({'head': project.get('head'), 'tree': project.get('tree')})
    task = _text(project.get('task_id'), 'task ID')
    workspace = _text(project.get('workspace'), 'workspace')
    if not Path(workspace).is_absolute():
        raise ValueError('Workspace must be absolute')
    if project.get('workspace_task_id') != task or project.get('workspace_dirty') is not False:
        raise ValueError('Workspace is not an isolated clean workspace of this task')
    scope = _strings(snapshot.get('scope'), 'approved scope', required=True)
    clear = snapshot.get('requirements_clear')
    if type(clear) is not bool or type(auto) is not bool:
        raise ValueError('Explicit requirement classification and mode required')
    consultants = project.get('consultants', [])
    if not isinstance(consultants, list) or any(c not in FAMILIES for c in consultants):
        raise ValueError('Unknown configured consultant family')
    result = dict(issue, schema_version=1, task_id=task, base=project['base'],
        workspace=workspace, identity=dict(identity), scope=list(scope),
        requirements_clear=clear, history_mode='auto' if auto else 'manual',
        production_contract=project.get('production_contract', 'unknown'),
        consultants=sorted({FAMILIES[c] for c in consultants}), current_stage='intake',
        status='pending', artifacts=[], blockers=[], consultations=[], records=[],
        rounds=0, revision=0)
    validate_state(result)
    return result


def validate_state(value):
    if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] != 1:
        raise ValueError('Unknown workflow schema')
    for key in ('task_id', 'issue_id', 'issue_url', 'repository', 'base', 'workspace'):
        _text(value.get(key), key)
    if parse_issue(value['issue_url'], value['repository'])['issue_id'] != value['issue_id'] or not Path(value['workspace']).is_absolute():
        raise ValueError('Issue/workspace identity mismatch')
    if value.get('current_stage') not in STAGES or value.get('status') not in STATUSES:
        raise ValueError('Unknown stage/status or unsupported delivery resume')
    if 'delivery' in value:
        from delivery_bridge import validate
        validate(value)
    elif value['current_stage'] == 'delivery' and value['status'] not in ('blocked', 'pending', 'awaiting-user'):
        raise ValueError('Delivery result requires durable delivery receipts')
    _identity(value.get('identity'))
    for key in ('artifacts', 'blockers', 'scope', 'consultants'):
        _strings(value.get(key), key, required=(key == 'scope'))
    if any(c not in set(FAMILIES.values()) for c in value['consultants']):
        raise ValueError('Unknown consultant identity')
    if type(value.get('requirements_clear')) is not bool or value.get('history_mode') not in ('auto', 'manual'):
        raise ValueError('Invalid historical mode/requirement classification')
    for key in ('revision', 'rounds'):
        if type(value.get(key)) is not int or value[key] < 0:
            raise ValueError('Invalid ' + key)
    if not isinstance(value.get('consultations'), list) or not isinstance(value.get('records'), list):
        raise ValueError('Invalid history')
    for entry in value['records']:
        if (not isinstance(entry, dict) or entry.get('stage') not in STAGES or
                entry.get('status') not in STATUSES or type(entry.get('valid')) is not bool):
            raise ValueError('Invalid stage record')
        _identity(entry.get('identity'))
        if 'pre_identity' in entry:
            _identity(entry['pre_identity'])
        if 'origin_identity' in entry:
            _identity(entry['origin_identity'])
            if entry.get('equivalence') != 'same-content-tree' or entry['origin_identity']['tree'] != entry['identity']['tree']:
                raise ValueError('Invalid source identity equivalence')
        if entry['valid'] and entry['identity'] != value['identity']:
            raise ValueError('Valid evidence belongs to another identity')
        _strings(entry.get('evidence'), 'stage evidence', required=entry['status'] in ('passed', 'failed', 'skipped'))
        if entry['status'] == 'skipped':
            _text(entry.get('reason'), 'verified skip reason')
    if 'consultation_batch' in value:
        batch = value['consultation_batch']
        if (not isinstance(batch, dict) or batch.get('status') not in ('incomplete','complete')
                or batch.get('identity') != value['identity'] or not isinstance(batch.get('question'), dict)):
            raise ValueError('Unknown or stale consultation batch')
        _text(batch.get('id'), 'consultation batch ID')
        _text(batch['question'].get('question'), 'consultation batch question')
        for key in ('required','completed','remaining'):
            _strings(batch.get(key), 'batch '+key)
            if len(set(batch[key])) != len(batch[key]) or any(f not in set(FAMILIES.values()) for f in batch[key]):
                raise ValueError('Unknown or repeated consultation recipient')
        if (set(batch['completed']) & set(batch['remaining']) or
                set(batch['completed']) | set(batch['remaining']) != set(batch['required']) or
                batch.get('in_flight') is not None and batch['in_flight'] not in batch['remaining']):
            raise ValueError('Inconsistent consultation batch progress')
        if batch['status']=='complete' and (batch['remaining'] or batch['in_flight'] is not None):
            raise ValueError('Incomplete batch cannot be marked complete')
        for family in batch['completed']:
            if sum(r.get('batch_id')==batch.get('id') and r.get('family')==family for r in value['consultations']) != 1:
                raise ValueError('Completed consultation evidence missing or duplicated')
    return value


def record(state, status, *, evidence=None, reason=None, stage=None, pre_identity=None):
    validate_state(state)
    if status not in STATUSES:
        raise ValueError('Unknown stage result')
    evidence = _strings(evidence if evidence is not None else [], 'stage evidence',
                        required=status in ('passed', 'failed', 'skipped'))
    if status == 'skipped':
        _text(reason, 'verified skip reason')
    result = copy.deepcopy(state)
    result['records'].append({'stage': stage or state['current_stage'], 'status': status,
        'identity': dict(state['identity']), 'evidence': list(evidence), 'reason': reason,
        'valid': True})
    if pre_identity is not None:
        result['records'][-1]['pre_identity'] = dict(_identity(pre_identity))
    result['status'] = status
    validate_state(result)
    return result


def handoff(state, invocation):
    validate_state(state)
    return validate_handoff({key: copy.deepcopy(state[key]) for key in HANDOFF_FIELDS
        if key not in ('mode', 'next_stage')} | {
        'mode': 'auto' if invocation.auto else 'manual',
        'next_stage': None if state.get('delivery', {}).get('complete') else state['current_stage']})


def validate_handoff(value):
    if not isinstance(value, dict) or set(value) != HANDOFF_FIELDS:
        raise ValueError('Incomplete handoff')
    for key in ('task_id', 'issue_id', 'workspace'):
        _text(value[key], key)
    if value['mode'] not in ('auto', 'manual') or value['current_stage'] not in STAGES:
        raise ValueError('Unknown handoff mode or stage')
    if value['next_stage'] not in STAGES and value['next_stage'] is not None:
        raise ValueError('Unknown next stage')
    _identity(value['identity'])
    for key in ('artifacts', 'scope', 'blockers'):
        _strings(value[key], key, required=key == 'scope')
    if not isinstance(value['consultations'], list):
        raise ValueError('Missing consultation history')
    return value


def _next(state):
    stage = state['current_stage']
    if stage == 'delivery':
        return None
    if stage == 'intake' and state['requirements_clear']:
        return 'plan-craft'
    return STAGES[STAGES.index(stage) + 1]


def retarget(state, identity):
    validate_state(state)
    _identity(identity)
    result = copy.deepcopy(state)
    if result['identity'] != identity:
        if 'delivery' in result:
            if result['delivery'].get('intent') or 'merge' in result['delivery']['results']:
                raise ValueError('Reconcile existing delivery actions before changing their source target')
            result.setdefault('stale_deliveries', []).append(result.pop('delivery'))
        if any(key in result for key in ('question','handoff','consultation_batch')):
            result.setdefault('stale_questions', []).append({
                'identity': dict(result['identity']),
                'question': result.pop('question', None),
                'handoff': result.pop('handoff', None),
                'consultation_batch': result.pop('consultation_batch', None)})
        result['identity'] = dict(identity)
        for entry in result['records']:
            entry['valid'] = False
        result['current_stage'] = 'verify' if any(r['stage'] == 'implement' for r in result['records']) else 'intake'
        result['status'] = 'pending'
        result['blockers'] = []
    return result


def _cancelled(state):
    result = copy.deepcopy(state)
    result['status'] = 'blocked'
    result['blockers'] = ['User cancelled; no further stage or consultation started']
    return result


def _complete_batch(state):
    batch = state['consultation_batch']
    if batch['remaining'] or batch['in_flight'] is not None:
        raise ValueError('Consultation batch is not complete')
    batch['status'] = 'complete'
    if not any(reason.startswith('User cancelled') for reason in state['blockers']):
        state['question'] = copy.deepcopy(batch['question'])
        state['status'] = 'awaiting-user'
        state['blockers'] = []
    return state


def _retain_attempt(state, family, response, evidence=None):
    batch = state['consultation_batch']
    if family not in batch['remaining'] or batch['in_flight'] not in (None,family):
        raise ValueError('Consultation attempt is duplicated or another outcome remains unknown')
    if not isinstance(response, dict) or response.get('status') not in (
            'COMPLETED','UNAVAILABLE','FAILED','BLOCKED','CONSULTATION_REQUIRED','USER_INPUT_REQUIRED'):
        raise ValueError('Missing or invalid consultant result')
    attempt = dict(response, family=family, target_identity=dict(state['identity']), batch_id=batch['id'])
    if evidence is not None:
        attempt['reconciliation_evidence'] = list(evidence)
    state['consultations'].append(attempt)
    batch['completed'].append(family)
    batch['remaining'].remove(family)
    batch['in_flight'] = None
    return _complete_batch(state) if not batch['remaining'] else state


def reconcile_consultation(state, family, response, *, evidence):
    """Host records an independently recovered attempt; never launches or retries it.

    Evidence references attest an actual result/stop or verified non-start. This
    function cannot establish OS cleanup. Unknown outcomes must remain blocked.
    Remaining families require separately authorized host attempts and evidence.
    """
    validate_state(state)
    _strings(evidence, 'actual host consultation evidence', required=True)
    batch = state.get('consultation_batch')
    if batch is None or batch['status'] != 'incomplete':
        raise ValueError('No incomplete consultation batch to reconcile')
    result = copy.deepcopy(state)
    result = _retain_attempt(result, family, response, evidence)
    if result['consultation_batch']['status'] != 'complete':
        result['status'] = 'blocked'
        result['blockers'] = ['Incomplete consultation batch requires actual host reconciliation']
        result.pop('question', None)
    return validate_state(result)


def critical_question(state, invocation, question, consult=None, *, host_family='codex',
                      executor_family=None, host_opinion=None, cancelled=lambda: False, checkpoint=None):
    validate_state(state)
    if 'question' in state or state.get('consultation_batch', {}).get('status') == 'incomplete':
        raise ValueError('Existing question/batch requires an explicit answer or host reconciliation; no reset')
    if not isinstance(question, dict):
        raise ValueError('Critical question must be an object')
    _text(question.get('question'), 'critical question')
    result = copy.deepcopy(state)
    def save(value):
        return validate_state(checkpoint(value)) if checkpoint else value
    if cancelled():
        return save(_cancelled(result))
    result['history_mode'] = 'auto' if invocation.auto else 'manual'
    delegated = invocation.delegated or bool(os.environ.get('CROSS_AGENT_DELEGATED')) or bool(os.environ.get('CROSS_REVIEW_DEPTH'))
    if delegated or not invocation.auto:
        result['status'] = 'awaiting-user'
        result['question'] = copy.deepcopy(question)
        if delegated:
            result['handoff'] = {'kind':'CONSULTATION_REQUIRED','question':copy.deepcopy(question),
                                 'task_id':result['task_id'],'issue_id':result['issue_id']}
        return save(result)
    if host_family not in FAMILIES or (executor_family is not None and executor_family not in FAMILIES):
        raise ValueError('Unknown host/executor family')
    host, executor = FAMILIES[host_family], FAMILIES[executor_family or host_family]
    required = [family for family in result['consultants'] if family != executor]
    result['consultation_batch'] = {'id':str(uuid.uuid4()),'status':'incomplete',
        'identity':dict(result['identity']),'question':copy.deepcopy(question),
        'required':list(required),'completed':[],'remaining':list(required),'in_flight':None}
    result['status'] = 'running'
    result = save(result) if required else save(_complete_batch(result))
    for family in required:
        if cancelled():
            return save(_cancelled(result))
        result['consultation_batch']['in_flight'] = family
        result = save(result)
        if family == host:
            answer = {'status':'COMPLETED' if host_opinion else 'UNAVAILABLE', 'output':host_opinion,
                      'reason':None if host_opinion else 'Host opinion unavailable'}
        else:
            try:
                answer = consult(family, copy.deepcopy(question), copy.deepcopy(result)) if consult else None
                if not isinstance(answer, dict) or answer.get('status') not in (
                        'COMPLETED','UNAVAILABLE','FAILED','BLOCKED','CONSULTATION_REQUIRED','USER_INPUT_REQUIRED'):
                    raise ValueError('Missing or invalid consultant result')
            except (TimeoutError,OSError,ValueError) as exc:
                answer = {'status':'UNAVAILABLE','reason':str(exc)}
        result = save(_retain_attempt(result, family, answer))
    return save(_cancelled(result)) if cancelled() else result


def answer_question(state, answer):
    """Only the trusted host calls this after an actual user answer, never consensus."""
    validate_state(state)
    if state.get('consultation_batch', {}).get('status') == 'incomplete':
        raise ValueError('Consultations incomplete; host reconciliation required before answering')
    if state['status'] != 'awaiting-user' or 'question' not in state:
        raise ValueError('No user question to answer')
    _text(answer, 'explicit user answer')
    result = copy.deepcopy(state)
    result['user_answers'] = result.get('user_answers', []) + [answer]
    result.pop('question', None)
    result.pop('handoff', None)
    result.pop('consultation_batch', None)
    result['status'] = 'pending'
    return result


def _terminal_record(state):
    records = [r for r in state['records'] if r['stage'] == state['current_stage']]
    if not records:
        raise ValueError('Terminal status has no reconciled stage record')
    entry = records[-1]
    if (entry['status'] != state['status'] or not entry['valid'] or
            entry['identity'] != state['identity'] or not entry['evidence']):
        raise ValueError('Reconciled stage evidence is stale or incomplete')
    if entry['status'] == 'skipped':
        _text(entry.get('reason'), 'verified reconciliation skip reason')
    if 'pre_identity' in entry:
        _identity(entry['pre_identity'])
    return entry


def _advance(state, invocation, entry):
    result = copy.deepcopy(state)
    stage = result['current_stage']
    if stage == 'intake' and result['requirements_clear']:
        result = record(result, 'skipped', evidence=entry['evidence'], stage='specify',
                        reason='Trusted issue intake confirms clear approved requirements')
    if stage == 'cr-received' and entry.get('pre_identity', result['identity'])['tree'] != result['identity']['tree']:
        result['current_stage'] = 'verify'
        result['rounds'] += 1
    else:
        result['current_stage'] = _next(result)
    result['status'] = 'pending' if invocation.auto else 'awaiting-user'
    return result


def run_loop(state, invocation, execute, *, consult=None, host_family='codex',
             executor_family=None, host_opinion=None, cancelled=lambda: False,
             checkpoint=None, measure_identity=None, stage_effects=None, delivery_host=None):
    """Drive host callbacks; measurement is a separate trusted host capability.

    Write stages require independent pre/post measurement. Model/stage output may
    attest only that measured identity, never choose the workflow's next target.
    """
    result = copy.deepcopy(validate_state(state))
    effects = dict(STAGE_EFFECTS)
    if stage_effects is not None:
        if (not isinstance(stage_effects, dict) or set(stage_effects)-set(PRE_DELIVERY) or
                any(effect not in ('read-only','bookkeeping','target-write') for effect in stage_effects.values())):
            raise ValueError('Invalid trusted host stage effect policy')
        effects.update(stage_effects)
    def save(value):
        return validate_state(checkpoint(value)) if checkpoint else value
    def question(value, payload):
        return critical_question(value, invocation, payload, consult,
            host_family=host_family, executor_family=executor_family,
            host_opinion=host_opinion, cancelled=cancelled, checkpoint=checkpoint)
    if result.get('consultation_batch', {}).get('status') == 'incomplete':
        result['status'] = 'blocked'
        result['blockers'] = ['Incomplete/in-flight consultation batch requires actual host reconciliation; no automatic retry']
        result.pop('question', None)
        return save(result)
    if result['status'] == 'running' and result['current_stage'] != 'delivery':
        result['status'] = 'blocked'
        result['blockers'] = ['Interrupted stage result unknown; reconcile current identity/evidence before retry']
        return save(result)
    while True:
        if cancelled():
            return save(_cancelled(result))
        stage = result['current_stage']
        if stage == 'delivery':
            if 'question' in result:
                return save(result)
            if delivery_host is None:
                result['status'] = 'blocked'
                result['blockers'] = ['Current delivery requires explicit project G3 host callbacks and permissions']
                return save(result)
            from delivery_bridge import run
            return run(result, invocation, delivery_host, checkpoint, cancelled)
        if stage not in invocation.permitted_stages:
            result['status'] = 'blocked'
            result['blockers'] = ['Current project/invocation does not authorize stage: ' + stage]
            return save(result)
        if result['status'] == 'blocked' or 'question' in result:
            return save(result)
        if result['status'] == 'awaiting-user' and not invocation.auto and invocation.approve_stage != stage:
            return save(result)
        if result['rounds'] >= invocation.max_rounds:
            result['status'] = 'blocked'
            result['blockers'] = ['Round limit reached; explicit new scope/permission required']
            return save(result)
        effect = effects[stage]
        writing = effect == 'target-write'
        if effect != 'read-only' and not callable(measure_identity):
            result['status'] = 'blocked'
            result['blockers'] = ['Trusted host identity measurement required before write stage: ' + stage]
            return save(result)
        if measure_identity is not None:
            measured = dict(_identity(measure_identity(stage, copy.deepcopy(result))))
            if measured != result['identity']:
                result['status'] = 'blocked'
                result['blockers'] = ['Current target changed outside this stage; explicitly retarget before continuing']
                return save(result)
        if result['status'] in ('passed', 'skipped'):
            entry = _terminal_record(result)
            if stage == 'specify' and not invocation.requirements_approved:
                return question(result, {'question':'Approve the clarified product requirements?',
                    'evidence':entry['evidence'], 'options':['Approve','Revise']})
            result = save(_advance(result, invocation, entry))
            if not invocation.auto:
                return result
            continue
        result['history_mode'] = 'auto' if invocation.auto else 'manual'
        result['status'] = 'running'
        result = save(result)
        pre_identity = dict(result['identity'])
        outcome = execute(stage, copy.deepcopy(result), ['--auto'] if invocation.auto else [])
        if not isinstance(outcome, dict) or outcome.get('status') not in ('passed', 'failed', 'blocked', 'awaiting-user'):
            raise ValueError('Invalid stage outcome')
        post_identity = dict(_identity(measure_identity(stage, copy.deepcopy(result)))) if measure_identity is not None else pre_identity
        if (effect == 'read-only' and post_identity != pre_identity or
                effect == 'bookkeeping' and post_identity['tree'] != pre_identity['tree']):
            result['status'] = 'blocked'
            result['blockers'] = ['Target changed during a read-only stage; explicitly retarget and repeat its evidence']
            return save(result)
        if outcome.get('identity', post_identity) != post_identity:
            raise ValueError('Stage evidence differs from the independently measured identity')
        if post_identity != pre_identity:
            if post_identity['tree'] == pre_identity['tree']:
                result['identity'] = dict(post_identity)
                for entry in result['records']:
                    if entry['valid']:
                        entry.setdefault('origin_identity', dict(entry['identity']))
                        entry['identity'] = dict(post_identity)
                        entry['equivalence'] = 'same-content-tree'
            else:
                result = retarget(result, post_identity)
            result['current_stage'] = stage
            result['status'] = 'running'
        if outcome['status'] == 'awaiting-user':
            return question(result, outcome)
        if stage == 'specify' and outcome['status'] == 'passed' and not invocation.requirements_approved:
            return question(result, {'question':'Approve the clarified product requirements?',
                'evidence':outcome.get('evidence', []), 'options':['Approve','Revise']})
        result = record(result, outcome['status'], evidence=outcome.get('evidence'),
            reason=outcome.get('reason'), pre_identity=pre_identity if writing else None)
        if outcome['status'] == 'blocked':
            result['blockers'] = [_text(outcome.get('reason'), 'block reason')]
            return save(result)
        if outcome['status'] == 'failed':
            result['rounds'] += 1
            if not invocation.auto:
                result['status'] = 'awaiting-user'
                return save(result)
            if stage in ('verify', 'code-review', 'cr-received', 'review-verify'):
                result['current_stage'] = 'implement'
            result = save(result)
            continue
        result = save(_advance(result, invocation, result['records'][-1]))
        if not invocation.auto:
            return result


def make_consultant(core, host):
    """Use the actual host-allowlisted generic launcher, without review domain binding."""
    if host.config.role != 'consultation' or host.config.profile != 'read-only' or host.integration or host.integration_required:
        raise ValueError('Consultations require generic read-only host context without review binding')
    def consult(family, question, state):
        if os.environ.get('CROSS_AGENT_DELEGATED') or os.environ.get('CROSS_REVIEW_DEPTH'):
            raise ValueError('Delegated executor must return consultation handoff to its host')
        if family not in set(FAMILIES.values()):
            raise ValueError('Unknown consultant family')
        if host.target_identity != state['identity']:
            raise ValueError('Consultation target identity is stale')
        request = core.parse_request(family + ' [consultation]')
        request = replace(request, assignment=json.dumps({'question': question,
            'issue_id': state['issue_id'], 'scope': state['scope']}, sort_keys=True))
        context = replace(host.task_context, canonical_issue=state['issue_url'])
        response = core.dispatch(request, replace(host, task_context=context)).to_dict()
        records = response.get('results')
        if not isinstance(records, list) or len(records) != 1 or records[0].get('family') != family:
            raise ValueError('Consultation launcher returned an unexpected recipient')
        return records[0]
    return consult


@contextmanager
def _lock(path):
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if parent.is_symlink() or not parent.is_dir() or parent.stat().st_uid != os.getuid() or parent.stat().st_mode & 0o077:
        raise ValueError('State directory must be private and owned')
    fd = os.open(str(path) + '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def load(path):
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'r', encoding='utf-8') as stream:
        st = os.fstat(stream.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise ValueError('Unsafe state file')
        return validate_state(json.load(stream))


def store(path, state):
    path = Path(path)
    validate_state(state)
    with _lock(path):
        if path.exists():
            current = load(path)
            if current['revision'] != state['revision'] or any(current[k] != state[k] for k in ('task_id', 'issue_id', 'workspace')):
                raise ValueError('Stale writer or mismatched task state')
        elif state['revision'] != 0:
            raise ValueError('Missing prior state; no implicit reset')
        result = copy.deepcopy(state)
        result['revision'] += 1
        fd, temporary = tempfile.mkstemp(prefix='.workflow-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(result, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if Path(temporary).exists():
                Path(temporary).unlink()
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    start = commands.add_parser('intake', help='Validate local snapshots and save an initial state')
    start.add_argument('issue')
    start.add_argument('--issue-snapshot', required=True)
    start.add_argument('--project-snapshot', required=True)
    start.add_argument('--state', required=True)
    start.add_argument('--auto', action='store_true')
    show = commands.add_parser('handoff', help='Read state without resuming stored permissions')
    show.add_argument('--state', required=True)
    show.add_argument('--auto', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'intake':
        state = intake(args.issue, json.loads(Path(args.issue_snapshot).read_text()),
                       json.loads(Path(args.project_snapshot).read_text()), auto=args.auto)
        if Path(args.state).exists():
            existing = load(args.state)
            if any(existing[k] != state[k] for k in ('task_id', 'issue_id', 'workspace')):
                raise ValueError('Existing state belongs to another task')
            if existing['repository'].casefold() != state['repository'].casefold():
                raise ValueError('Existing state belongs to another repository')
            if any(existing[key] != state[key] for key in ('base', 'scope', 'requirements_clear')):
                raise ValueError('Base, approved scope or requirements classification changed; explicit new intake decision required')
            resumed = retarget(existing, state['identity'])
            resumed['consultants'] = list(state['consultants'])
            resumed['production_contract'] = copy.deepcopy(state['production_contract'])
            state = store(args.state, resumed)
        else:
            state = store(args.state, state)
    else:
        state = load(args.state)
    print(json.dumps(handoff(state, Invocation(auto=args.auto)), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
