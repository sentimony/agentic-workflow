"""Trusted host delivery bridge; G3 helpers are loaded only from this owner package."""
from dataclasses import asdict, dataclass
import copy
import importlib.util
import json
from pathlib import Path
import sys


def _owner_module(name, skill):
    path = Path(__file__).resolve().parents[2] / skill / 'scripts' / (name + '.py')
    if name in sys.modules:
        existing = sys.modules[name]
        if Path(existing.__file__).resolve() != path.resolve():
            raise ValueError('G3 module must belong to this installed owner package')
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _owner_module('delivery_gate', 'finalize')
evidence = _owner_module('post_merge_evidence', 'implement')
cleanup = _owner_module('cleanup_guard', 'finalize')
ACTIONS = ('pr', 'ready', 'wait', 'merge', 'deploy', 'health', 'evidence', 'cleanup', 'learnings')


@dataclass(frozen=True)
class ProductionContract:
    kind: str
    reason: str
    proof: str


@dataclass(frozen=True)
class DeliveryHost:
    actions: dict
    reconcile: object
    measure: object
    read_observation: object
    now: object
    max_age: float
    local_checks: object
    read_review: object
    verify_integration: object
    production: object
    store: object
    transport: object
    publication_authority: object
    cleanup_guard: object
    disposal_authority: object
    cleanup_observation: object
    permitted_actions: tuple = ()
    session_created: bool = False
    verify_cleanup: object = None


def _require(value, message):
    if not value:
        raise ValueError(message)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def validate(state):
    """Validate persisted progress; it contains receipts, never live authority."""
    data = state.get('delivery')
    if data is None:
        return
    _require(type(data) is dict and data.get('schema') == 'resolve-delivery-v1', 'Unknown delivery schema')
    _require(data.get('identity') == state['identity'], 'Delivery evidence belongs to another source identity')
    _require(type(data.get('step')) is int and 0 <= data['step'] <= len(ACTIONS), 'Unknown delivery step')
    _require(type(data.get('results')) is dict and set(data['results']) <= set(ACTIONS), 'Invalid delivery receipts')
    _require(type(data.get('complete')) is bool, 'Invalid completion state')
    _require(_text(data.get('attempt')), 'Missing delivery attempt identity')
    _require(type(data.get('base')) is str and len(data['base']) in (40, 64)
             and all(c in '0123456789abcdef' for c in data['base']), 'Full delivery base SHA required')
    intent = data.get('intent')
    if intent is not None:
        _require(type(intent) is dict and set(intent) == {'action', 'key', 'identity'}, 'Invalid action intent')
        _require(data['step'] < len(ACTIONS) and intent['action'] == ACTIONS[data['step']]
                 and intent['identity'] == state['identity'] and _text(intent['key']), 'Stale action intent')
    for step in ACTIONS[:data['step']]:
        receipt = data['results'].get(step)
        _require(type(receipt) is dict and type(receipt.get('evidence')) is list
                 and bool(receipt['evidence']) and all(_text(p) for p in receipt['evidence']),
                 'Missing completed action receipt')
    if 'merge' in data['results']:
        sha = data['results']['merge'].get('merge_sha', '')
        _require(type(sha) is str and len(sha) in (40,64) and all(c in '0123456789abcdef' for c in sha),
                 'Invalid saved integration identity')
    if data['complete']:
        _require(data['step'] == len(ACTIONS) and intent is None
                 and data.get('production_status') in ('succeeded', 'n/a'), 'Incomplete terminal delivery')
        _require(data.get('cleanup_status') == 'completed' and data.get('learnings_status') == 'completed',
                 'Completion requires cleanup and learnings')
        contract = data.get('production_contract', {})
        if data['production_status'] == 'succeeded':
            _require(contract.get('kind') == 'deploy' and data.get('evidence_status') == 'published'
                     and _text(data.get('evidence_path')) and type(data.get('deployment')) is dict,
                     'Completion needs canonical deployment evidence')
        else:
            _require(contract.get('kind') == 'none' and _text(contract.get('proof'))
                     and _text(contract.get('reason')) and 'deployment' not in data,
                     'Nonproduction completion needs explicit skip proof')


def _accept(action, outcome, state, host):
    _require(type(outcome) is dict and outcome.get('status') not in ('failed', 'blocked', 'queued', 'pending', 'unknown'),
             action + ' is incomplete or failed')
    proofs = outcome.get('evidence')
    _require(type(proofs) is list and proofs and all(_text(p) for p in proofs), action + ' proof required')
    data = state['delivery']
    if action in ('cleanup', 'learnings'):
        _require(outcome.get('status') == 'completed', action + ' requires explicit completion readback')
        if action == 'cleanup':
            _cleanup_postflight(outcome, state, host)
        data[action + '_status'] = 'completed'
    if action == 'pr':
        _require(type(outcome.get('pr')) is int and outcome['pr'] > 0, 'PR identity required')
        _require((outcome.get('head'), outcome.get('base')) == (state['identity']['head'], data['base']), 'PR target mismatch')
        expected = ('Fixes #' + str(state['number']), 'Fixes ' + state['issue_url'])
        _require(outcome.get('closing_reference') in expected, 'Issue closing reference required')
    elif action == 'merge':
        sha = outcome.get('merge_sha', '')
        _require(type(sha) is str and len(sha) in (40, 64) and all(c in '0123456789abcdef' for c in sha), 'Integration SHA required')
        _require(host.verify_integration(copy.deepcopy(outcome), copy.deepcopy(state)) is True,
                 'Actual integration readback required')
    elif action == 'deploy':
        merge = data['results']['merge']['merge_sha']
        _require(outcome.get('merge_sha') == merge and _text(outcome.get('id'))
                 and _text(outcome.get('version')), 'Deployment must bind to integration SHA')
        data['deployment'] = {key:outcome[key] for key in ('id', 'version')}
    elif action == 'health':
        deployment = data['deployment']
        _require(outcome.get('status') == 'succeeded' and outcome.get('merge_sha') == data['results']['merge']['merge_sha']
                 and outcome.get('deployment_id') == deployment['id'] and outcome.get('version') == deployment['version'],
                 'Production health/version mismatch')
        checks = outcome.get('checks')
        _require(type(checks) is list and checks and all(type(c) is dict and set(c) == {'command', 'result'}
                 and _text(c['command']) and c['result'] == 'passed' for c in checks), 'Successful health checks required')
        data['production_status'] = 'succeeded'
    data['results'][action] = copy.deepcopy(outcome)
    for artifact in proofs:
        if artifact not in state['artifacts']:
            state['artifacts'].append(artifact)
    if action == 'merge':
        state['artifacts'].append('integration:' + outcome['merge_sha'])
    data['step'] += 1
    data['intent'] = None
    state['blockers'] = []
    return state


def _production(host):
    contract = host.production
    _require(type(contract) is ProductionContract and contract.kind in ('deploy', 'none')
             and _text(contract.reason) and _text(contract.proof), 'Explicit verified project production contract required')
    return contract


def _perform(action, state, host):
    data = state['delivery']
    if action in ('ready', 'wait', 'merge'):
        observation = host.read_observation()
        record = gate.evaluate(observation, now=host.now)
        if action == 'ready':
            reviews = [r for r in state['records'] if r['stage'] == 'code-review']
            _require(reviews and reviews[-1]['valid'] and reviews[-1]['status'] == 'passed'
                     and reviews[-1]['identity'] == state['identity'] and reviews[-1]['evidence'],
                     'Current local independent review required before ready')
        if action == 'merge':
            review = host.read_review(copy.deepcopy(state))
            _require(type(review) is dict and review.get('head') == state['identity']['head']
                     and review.get('status') == 'passed' and _text(review.get('evidence')),
                     'Forge review missing, unavailable or stale; explicit project policy needed')
        return gate.run_guarded_transition(action, verified_head=state['identity']['head'],
            verified_base=data['base'], read_observation=host.read_observation,
            perform=lambda **pins:host.actions[action](copy.deepcopy(state)), now=host.now,
            max_age=host.max_age,record=record,verified_tree=state['identity']['tree'],
            local_checks=host.local_checks(copy.deepcopy(state)) if action == 'ready' else None)
    if action == 'evidence':
        contract = _production(host)
        if contract.kind == 'none':
            return {'evidence':[contract.proof], 'reason':contract.reason, 'production_status':'n/a'}
        health = data['results']['health']
        author = host.transport.current_author()
        record = {'schema':'evidence-record-v1', 'repo':'github.com/' + state['repository'],
            'pr':data['results']['pr']['pr'], 'task':state['task_id'], 'attempt':data['attempt'],
            'merge_sha':data['results']['merge']['merge_sha'], 'deployment':data['deployment'],
            'timestamp':host.now(),'checks':health['checks'],'production_status':'succeeded',
            'author':author,'previous_attempt':None}
        path = host.store.path_for({key:record[key] for key in ('repo','pr','task','attempt')})
        if path.exists():
            pending = host.store.load(path)['record']
            for key in ('repo','pr','task','attempt','merge_sha','deployment','checks','production_status'):
                _require(pending[key] == record[key], 'Saved evidence content differs from verified delivery')
        else:
            path = evidence.prepare(record, store=host.store)
            pending = host.store.load(path)['record']
        published = evidence.publish(path,store=host.store,transport=host.transport,
                                     authority=host.publication_authority(copy.deepcopy(pending)))
        _require(published.get('evidence_status') == 'published', 'Canonical evidence publication pending')
        data['evidence_status'] = 'published'
        data['evidence_path'] = str(path)
        return {'evidence':[published['canonical_url']], 'path':str(path)}
    if action == 'cleanup':
        return host.actions[action](copy.deepcopy(state))
    result = host.actions[action](copy.deepcopy(state))
    if action == 'learnings':
        _require(type(result) is dict and result.get('status') not in ('failed','blocked'), 'Learnings incomplete')
        data['learnings_status'] = 'completed'
    return result


def _cleanup_authority(state, host):
    data = state['delivery']
    authority = host.disposal_authority(copy.deepcopy(state))
    _require(type(authority) is cleanup.DisposalAuthority and authority.repo == 'github.com/' + state['repository'],
             'Current trusted disposal authority required')
    _require(type(authority.inventory) is cleanup.PostMergeInventory,
             'Current trusted cleanup inventory required')
    _require(authority.allow_branch_delete or authority.allow_workspace_remove,
             'Cleanup scope must explicitly select an action')
    _require(not authority.allow_workspace_remove or host.session_created is True,
             'Current host must attest session-created workspace')
    if data.get('production_status') == 'succeeded':
        current = host.store.load(Path(data['evidence_path']))['record']
        expected = cleanup.EvidenceRequirement(data['results']['pr']['pr'], state['task_id'],
            data['attempt'], data['results']['merge']['merge_sha'], current['content_sha256'])
        _require(expected in authority.inventory.tasks, 'Current production evidence missing from cleanup inventory')
    return authority


def _cleanup_binding(state, authority):
    data = state['delivery']
    return {'attempt': data['attempt'], 'key': data['attempt'] + ':cleanup',
            'identity': copy.deepcopy(state['identity']), 'workspace': state['workspace'],
            'authority': json.loads(json.dumps(asdict(authority))),
            'decision': copy.deepcopy(data['cleanup_decision'])}


def _cleanup_decision(state, host):
    data = state['delivery']
    authority = _cleanup_authority(state, host)
    _require(type(host.cleanup_guard) is cleanup.CleanupGuard, 'Actual G3 cleanup guard required')
    _require(str(host.cleanup_guard.repo) == state['workspace'], 'Cleanup workspace mismatch')
    decision = host.cleanup_guard.disposal_decision(authority=authority,
        observe=lambda:host.cleanup_observation(copy.deepcopy(state)),
        session_created=host.session_created)
    for required, name in ((authority.allow_branch_delete, 'branch_decision'),
                           (authority.allow_workspace_remove, 'workspace_decision')):
        if required:
            _require(decision.get(name, {}).get('status') == 'eligible',
                     'Cleanup blocked: ' + decision.get('reason', 'unknown'))
    data['cleanup_decision'] = decision
    data['cleanup_binding'] = _cleanup_binding(state, authority)
    return decision


def _cleanup_postflight(outcome, state, host):
    """Validate disposal readback without requiring deleted resources to exist."""
    authority = _cleanup_authority(state, host)
    binding = state['delivery'].get('cleanup_binding')
    _require(type(binding) is dict and binding == _cleanup_binding(state, authority),
             'Cleanup intent/current authority binding mismatch')
    intent = state['delivery']['intent']
    _require(intent and intent['action'] == 'cleanup' and intent['key'] == binding['key']
             and intent['identity'] == binding['identity'], 'Bound cleanup intent required')
    for required, name in ((authority.allow_branch_delete, 'branch_decision'),
                           (authority.allow_workspace_remove, 'workspace_decision')):
        if required:
            _require(binding['decision'].get(name, {}).get('status') == 'eligible',
                     'Persisted authorized cleanup decision required')
    _require(outcome.get('cleanup') == binding, 'Cleanup receipt resource binding mismatch')
    _require(callable(host.verify_cleanup)
             and host.verify_cleanup(copy.deepcopy(outcome), copy.deepcopy(state)) is True,
             'Actual cleanup post-deletion readback required')


def run(state, invocation, host, checkpoint, cancelled=lambda: False):
    """Continue with fresh host capabilities and an intent saved before each action."""
    import uuid
    result = copy.deepcopy(state)
    def save():
        nonlocal result
        validate(result)
        result = checkpoint(result)
        return result
    def blocked(reason):
        if 'delivery' in result:
            result['delivery']['complete'] = False
        result['status'] = 'blocked'; result['blockers'] = [str(reason)]
        return save() if callable(checkpoint) else result
    if ('delivery' not in invocation.permitted_stages or type(host) is not DeliveryHost
            or not callable(checkpoint)):
        return blocked('Current invocation needs delivery scope, installed G3 host and durable checkpoint')
    if 'question' in result or result['rounds'] >= invocation.max_rounds:
        return blocked('Outstanding decision or exhausted round budget')
    if not invocation.auto and invocation.approve_stage != 'delivery':
        result['status']='awaiting-user'
        return save()
    if 'delivery' not in result:
        measured = host.measure(copy.deepcopy(result))
        if (measured.get('head'),measured.get('tree')) != (result['identity']['head'],result['identity']['tree']):
            return blocked('Source changed; retarget and repeat verify/review')
        result['delivery']={'schema':'resolve-delivery-v1','identity':copy.deepcopy(result['identity']),
            'base':measured['base'],'attempt':uuid.uuid4().hex,'step':0,'results':{},'intent':None,'complete':False}
        save()
    validate(result)
    data = result['delivery']
    while data['step'] < len(ACTIONS):
        action = ACTIONS[data['step']]
        if cancelled():
            return blocked('Cancelled; reconcile any saved intent before retry')
        if action not in host.permitted_actions:
            return blocked('Current project/invocation does not authorize action: ' + action)
        if action in ('deploy','health','evidence'):
            try:
                contract=_production(host)
                binding={'kind':contract.kind,'reason':contract.reason,'proof':contract.proof}
                _require(data.get('production_contract',binding)==binding, 'Project production contract changed during delivery')
                data['production_contract']=binding
            except ValueError as error:return blocked(error)
            if contract.kind=='none' and action in ('deploy','health'):
                data['production_status']='n/a'
                data['results'][action]={'evidence':[contract.proof],'reason':contract.reason,'skipped':True}
                data['step']+=1;data['intent']=None;save();data=result['delivery'];continue
        try:
            if data['intent'] is not None and action != 'evidence':
                reconciliation = host.reconcile(action,copy.deepcopy(data['intent']),copy.deepcopy(result))
                _require(type(reconciliation) is dict, 'Invalid reconciliation result')
                if reconciliation.get('status') == 'completed':
                    outcome=reconciliation.get('result')
                    _accept(action,outcome,result,host)
                    # Completion flags are derived here too after a recovered action.
                    if action=='cleanup':data['cleanup_status']='completed'
                    if action=='learnings':data['learnings_status']='completed'
                    save();data=result['delivery']
                    if not invocation.auto and data['step'] < len(ACTIONS):
                        result['status']='awaiting-user';return save()
                    continue
                _require(reconciliation.get('status') == 'absent' and reconciliation.get('authoritative') is True
                         and _text(reconciliation.get('evidence')), 'Unknown action outcome; authoritative reconciliation required')
                data['intent']=None
            if data['step'] <= ACTIONS.index('merge'):
                measured = host.measure(copy.deepcopy(result))
                if (measured.get('head'),measured.get('tree'),measured.get('base')) != (result['identity']['head'],result['identity']['tree'],data['base']):
                    return blocked('Head/base changed; retarget and repeat verify/review')
            if action == 'cleanup':
                _require(callable(host.verify_cleanup), 'Current cleanup postflight verifier required')
                _cleanup_decision(result, host)
            data['intent']={'action':action,'key':data['attempt']+':'+action,'identity':copy.deepcopy(result['identity'])}
            result['status']='running';save();data=result['delivery']
            outcome=_perform(action,result,host)
            _accept(action,outcome,result,host)
            result['status']='pending';save();data=result['delivery']
            if not invocation.auto and data['step'] < len(ACTIONS):
                result['status']='awaiting-user';return save()
        except (ValueError, TypeError, KeyError, OSError, evidence.TransportError) as error:
            return blocked(error)
    try:
        contract = _production(host)
        _require(data.get('production_contract') == {'kind':contract.kind,'reason':contract.reason,'proof':contract.proof},
                 'Project production contract changed during delivery')
        _require(host.verify_integration(copy.deepcopy(data['results']['merge']),copy.deepcopy(result)) is True,
                 'Integration readback no longer verifies completion')
        if data.get('production_status') == 'succeeded':
            saved = host.store.load(Path(data['evidence_path']))['record']
            _require(saved.get('evidence_status') == 'published'
                     and saved.get('merge_sha') == data['results']['merge']['merge_sha']
                     and saved.get('deployment') == data['deployment'], 'Canonical evidence no longer verifies completion')
    except (ValueError, TypeError, KeyError, OSError) as error:
        return blocked(error)
    data['complete']=True
    result['status']='passed'
    result['blockers']=[]
    return save()
