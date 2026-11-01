"""Installed workflow policy for standalone cross-agent protocol v1.

Inputs are trusted host envelopes plus untrusted provider output. This adapter
never launches a provider, resolves a sibling launcher, or executes a callback.
Review grammar and identity recipes remain owned by this installed workflow.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import tempfile

OWNER_ID = 'sentimony.agentic-workflow'
ADAPTER_ID = 'review'
VERSION = 1
CAPABILITIES = ('prepare', 'validate', 'intake')
REFS = Path(__file__).resolve().parents[1] / 'references'
IDENTITY_FIELDS = {'schema_version', 'repository', 'head', 'tree', 'boundary',
                   'base', 'record_host', 'document'}


def _git(repo, *args, index=None):
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent',
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
    if index is not None:
        env['GIT_INDEX_FILE'] = str(index)
    process = subprocess.run(['/usr/bin/git', '--no-optional-locks', '-C', str(repo), *args],
                             env=env, capture_output=True, check=False)
    if process.returncode:
        raise ValueError('fingerprint failed: ' + process.stderr.decode(errors='replace'))
    return process.stdout


def capture_identity(repo, *, document=None, record_host=None, base=None):
    """Use cr-request's committed-tree recipe with a private temporary index."""
    repo = Path(repo).resolve()
    root = Path(os.fsdecode(_git(repo, 'rev-parse', '--show-toplevel')).strip()).resolve()
    head = os.fsdecode(_git(root, 'rev-parse', '--verify', 'HEAD^{commit}')).strip()
    identity = {'schema_version': 1, 'repository': str(root), 'head': head,
                'boundary': 'document' if document else 'committed-tree'}
    if base is not None:
        if not isinstance(base, str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', base):
            raise ValueError('identity base must be a full commit ID')
        identity['base'] = os.fsdecode(_git(root, 'rev-parse', '--verify', base + '^{commit}')).strip()
    host = None
    if record_host:
        host = Path(record_host)
        host = host.resolve() if host.is_absolute() else (root / host).resolve()
        identity['record_host'] = str(host)
    with tempfile.TemporaryDirectory(prefix='owner-review-index-') as temp:
        index = Path(temp) / 'index'
        _git(root, 'read-tree', head, index=index)
        if host is not None and host.is_relative_to(root):
            _git(root, 'rm', '-q', '--cached', '--ignore-unmatch', '--',
                 str(host.relative_to(root)), index=index)
        identity['tree'] = os.fsdecode(_git(root, 'write-tree', index=index)).strip()
    if document:
        path = Path(document)
        path = path.resolve() if path.is_absolute() else (root / path).resolve()
        if not path.is_file():
            raise ValueError('requested review document is missing')
        identity['document'] = {'path': str(path),
                                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    return identity


def check_identity(identity):
    if (not isinstance(identity, dict) or set(identity) - IDENTITY_FIELDS or
            type(identity.get('schema_version')) is not int or identity['schema_version'] != 1 or
            any(not isinstance(identity.get(k), str) or not identity[k]
                for k in ('repository', 'head', 'tree', 'boundary'))):
        raise ValueError('legacy or invalid identity requires an explicit new review')
    document = identity.get('document')
    if document is not None and (not isinstance(document, dict) or
            set(document) != {'path', 'sha256'} or
            any(not isinstance(document.get(k), str) or not document[k] for k in document)):
        raise ValueError('invalid document identity')
    current = capture_identity(identity['repository'], document=(document or {}).get('path'),
                               record_host=identity.get('record_host'), base=identity.get('base'))
    if _content_identity(current) != _content_identity(identity):
        raise ValueError('stale review target identity')
    allowed = {identity.get('record_host'), (document or {}).get('path')}
    dirty = _git(current['repository'], 'diff', '--name-only', '-z', 'HEAD', '--')
    dirty += _git(current['repository'], 'ls-files', '--others', '--exclude-standard', '-z')
    for item in dirty.split(b'\0'):
        if item and str((Path(current['repository']) / os.fsdecode(item)).resolve()) not in allowed:
            raise ValueError('dirty implementation requires a fresh committed review target')
    return current


def _content_identity(identity):
    """HEAD is provenance; content validity uses the selected tree/document."""
    return {key: value for key, value in identity.items() if key != 'head'}


def validate_review(text, identity):
    """Validate the installed cr-request contract, including qualified finding IDs."""
    if not isinstance(text, str):
        raise ValueError('incomplete review: output must be text')
    labels = ('Target reviewed', 'Reviewer model', 'Coverage', 'Intent', 'System', 'Craft',
              'Summary', 'Merge readiness', 'Findings', 'Evidence attribution',
              'Not checkable from the diff', 'Set aside', 'Open questions', 'Strengths')
    for label in labels:
        if not re.search(r'(?m)^' + re.escape(label) + r':', text):
            raise ValueError('incomplete review: missing ' + label)
    for axis in ('Intent', 'System', 'Craft'):
        if not re.search(r'(?m)^' + axis + r':\s*(PASS|FINDINGS|UNASSESSED)\s*-\s*\S', text):
            raise ValueError('incomplete review axis: ' + axis)
    summary = re.search(r'(?m)^Summary: Critical (\d+) \| Important (\d+) \| Minor (\d+)\s*$', text)
    if summary is None:
        raise ValueError('invalid review summary')
    findings = list(re.finditer(r'(?m)^\s*(R\d+-(?:[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*-)?F\d+) \[(Critical|Important|Minor)\]', text))
    ids = [finding.group(1) for finding in findings]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate qualified finding ID')
    counts = {severity: sum(f.group(2) == severity for f in findings)
              for severity in ('Critical', 'Important', 'Minor')}
    if list(counts.values()) != [int(n) for n in summary.groups()]:
        raise ValueError('review summary and findings disagree')
    for position, finding in enumerate(findings):
        block = text[finding.start():findings[position + 1].start()
                     if position + 1 < len(findings) else len(text)]
        for label in ('Location', 'Issue', 'Impact', 'Evidence', 'Evidence source'):
            if not re.search(r'(?m)^\s*' + label + r':\s*\S', block):
                raise ValueError('incomplete finding: ' + label)
    target_line = re.search(r'(?m)^Target reviewed:\s*(.+)$', text)
    if (target_line is None or identity['tree'] not in target_line.group(1) or
            ((identity.get('document') or {}).get('sha256') and
             identity['document']['sha256'] not in target_line.group(1))):
        raise ValueError('review does not name current target identity')
    return {'finding_ids': ids, 'counts': counts}


def select_review_intake(records, task_id, review_path=None, identity=None):
    if not isinstance(records, list) or not isinstance(task_id, str) or not task_id:
        raise ValueError('clarify review intake: current task and review records required')
    candidates = [r for r in records if isinstance(r, dict) and r.get('task_id') == task_id
                  and r.get('role') == 'review' and r.get('status') == 'COMPLETED'
                  and r.get('review_path') and not r.get('resolved', False)]
    if review_path is not None:
        if identity is None:
            raise ValueError('clarify review intake: explicit path requires identity')
        candidates = [r for r in candidates if r.get('review_path') == str(review_path)
                      and r.get('identity', r.get('target_identity')) == identity]
    if len(candidates) != 1:
        raise ValueError('clarify review intake: expected one unresolved review for current task')
    chosen = candidates[0]
    path = Path(chosen['review_path'])
    saved = chosen.get('identity', chosen.get('target_identity'))
    if not path.is_absolute() or not path.is_file():
        raise ValueError('review artifact unavailable')
    sidecar = json.loads((path.parent / 'identity.json').read_text('utf-8'))
    if sidecar != saved:
        raise ValueError('stale review: identity sidecar mismatch')
    check_identity(saved)
    validate_review(path.read_text('utf-8'), saved)
    return chosen


def _sections(text, names):
    found, current = {}, None
    for line in text.splitlines():
        if line.startswith('## '):
            current = line[3:].strip()
            found.setdefault(current, [])
        if current is not None:
            found[current].append(line)
    if any(name not in found for name in names):
        raise ValueError('installed review contract sections unavailable')
    return ['\n'.join(found[name]).rstrip() for name in names]


def standard_sections(mode='implementation'):
    if mode not in ('implementation', 'plan'):
        raise ValueError('unsupported owner review mode')
    parts = _sections((REFS / 'brief.md').read_text('utf-8'),
                      ('Reviewer instructions', 'Result contract', 'Severity'))
    kept, skip = [], False
    for line in parts[0].splitlines():
        if line.startswith('### '):
            skip = line.strip() in (('### Re-review kind', '### Document kind')
                                   if mode != 'plan' else ('### Re-review kind',))
        if not skip:
            kept.append(line)
    parts[0] = '\n'.join(kept)
    parts[1] = parts[1].split('\n\n`Not checkable', 1)[0]
    if mode == 'implementation':
        parts += _sections((REFS / 'lenses.md').read_text('utf-8'), ('Intent', 'System', 'Craft'))
    return '\n\n'.join(parts)


def validate_resolution(text, chosen):
    """Require original finding decisions and the installed receiver return block."""
    saved = chosen.get('identity', chosen.get('target_identity'))
    checked = validate_review(Path(chosen['review_path']).read_text('utf-8'), saved)
    fields = ('Changed paths', 'Previous verification', 'Checks to rerun', 'Re-review',
              'Blocking', 'Deferred', 'Rulings for the execution record', 'Durable rulings', 'Route')
    for label in fields:
        if not re.search(r'(?m)^' + re.escape(label) + r':\s*\S', text):
            raise ValueError('incomplete review resolution: missing ' + label)
    if not re.search(r'(?m)^Route:\s*(verify|specify|plan-craft)(?:\s*\([^\n]+\))?\s*$', text):
        raise ValueError('invalid review resolution route')
    for finding in checked['finding_ids']:
        if not re.search(r'(?m)^.*(?<![A-Za-z0-9_-])' + re.escape(finding) +
                r'(?![A-Za-z0-9_-]).*\b(?:ACCEPT|REJECT|PARTIAL|DEFER|ESCALATE|OUTDATED)\b', text):
            raise ValueError('incomplete review resolution: missing disposition for ' + finding)
    return checked['finding_ids']


def _stop(status, reason):
    return {'accepted': False, 'status': status, 'reason': reason}


def _current_intake(request, context):
    selector = request.get('task_selection', {}).get('task_selector')
    task_id = context.get('active_task_id') if selector is None else selector
    if task_id == 'new':
        raise ValueError('clarify review intake: a new task has no prior review')
    return select_review_intake(context.get('review_records'), task_id,
                                context.get('review_path'), context.get('intake_identity'))


def _binding_path(request, context, *, create=False):
    nonce = context.get('intake_binding_id')
    root = Path(context.get('artifact_root', ''))
    if not isinstance(nonce, str) or not nonce.strip() or len(nonce) > 200 or not root.is_absolute():
        raise ValueError('execution requires host intake_binding_id and artifact_root')
    root = root.resolve()
    repo = Path(request['target_identity']['repository']).resolve()
    if root.is_relative_to(repo):
        try:
            _git(repo, 'check-ignore', '-q', '--', str(root))
        except ValueError as exc:
            raise ValueError('binding artifacts must be outside the target or Git-ignored') from exc
    directory = root / '.owner-intake-bindings'
    if create:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if (not directory.is_dir() or directory.is_symlink() or
            directory.stat().st_uid != os.getuid()):
        raise ValueError('owner intake binding directory unavailable')
    key = json.dumps({'nonce': nonce, 'host': request.get('host'),
                      'target': request['target_identity']}, sort_keys=True)
    return directory / (hashlib.sha256(key.encode()).hexdigest() + '.json')


@contextmanager
def _binding_lock(path):
    fd = os.open(str(path) + '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a+b') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _read_binding(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'r', encoding='utf-8') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError('invalid owner intake binding file')
        return json.load(stream)


def _write_binding(path, value):
    fd, temporary = tempfile.mkstemp(prefix='.intake-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, sort_keys=True)
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


def _prepare_binding(request, context, chosen):
    original = chosen.get('identity', chosen.get('target_identity'))
    if _content_identity(original) != _content_identity(request['target_identity']):
        raise ValueError('selected review and execution target disagree')
    path = _binding_path(request, context, create=True)
    review_path = Path(chosen['review_path']).resolve(strict=True)
    receipt = {'schema_version': 1, 'owner_id': OWNER_ID, 'adapter_id': ADAPTER_ID,
        'binding_id': context['intake_binding_id'], 'host': request.get('host'),
        'task_id': chosen['task_id'], 'review_path': str(review_path),
        'original_identity': original, 'request_identity': request['target_identity'],
        'review_sha256': hashlib.sha256(review_path.read_bytes()).hexdigest(),
        'sidecar_sha256': hashlib.sha256((review_path.parent / 'identity.json').read_bytes()).hexdigest(),
        'status': 'prepared', 'run': None}
    with _binding_lock(path):
        if path.exists() or path.is_symlink():
            raise ValueError('intake binding already used; host must provide a fresh invocation ID')
        _write_binding(path, receipt)
    return receipt


def _capture_post_identity(original):
    document = original.get('document')
    current = capture_identity(original['repository'], record_host=original.get('record_host'),
                               base=original.get('base'))
    if document:
        path = Path(document['path'])
        current['boundary'] = 'document'
        current['document'] = {'path': str(path), 'sha256':
                               hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None}
    with tempfile.TemporaryDirectory(prefix='owner-post-index-') as temporary:
        index = Path(temporary) / 'index'
        _git(current['repository'], 'read-tree', 'HEAD', index=index)
        _git(current['repository'], 'add', '-A', index=index)
        host = Path(original['record_host']) if original.get('record_host') else None
        repo = Path(current['repository'])
        if host is not None and host.is_relative_to(repo):
            _git(repo, 'rm', '-q', '--cached', '--ignore-unmatch', '--',
                 str(host.relative_to(repo)), index=index)
        current['working_tree'] = os.fsdecode(_git(repo, 'write-tree', index=index)).strip()
    current['dirty_paths'] = [os.fsdecode(item) for item in
        (_git(current['repository'], 'diff', '--name-only', '-z', 'HEAD', '--') +
         _git(current['repository'], 'ls-files', '--others', '--exclude-standard', '-z')).split(b'\0') if item]
    return current


def _post_content(identity):
    return {key: value for key, value in identity.items()
            if key not in ('head', 'tree', 'dirty_paths')}


def _finish_execution(request, context, result, stage):
    path = _binding_path(request, context)
    with _binding_lock(path):
        receipt = _read_binding(path)
        if (not isinstance(receipt, dict) or type(receipt.get('schema_version')) is not int or
                receipt.get('schema_version') != 1 or receipt.get('owner_id') != OWNER_ID or
                receipt.get('adapter_id') != ADAPTER_ID or
                receipt.get('status') not in ('prepared', 'validated', 'completed') or
                receipt.get('binding_id') != context['intake_binding_id'] or
                receipt.get('host') != request.get('host') or
                receipt.get('request_identity') != request['target_identity'] or
                receipt.get('task_id') != request.get('task_id')):
            raise ValueError('execution does not match prepared intake binding')
        run = {key: request.get(key) for key in ('task_id', 'session_id', 'run_id', 'provider_id')}
        if any(not isinstance(value, str) or not value for value in run.values()):
            raise ValueError('execution run identity unavailable')
        if receipt['run'] is not None and receipt['run'] != run:
            raise ValueError('intake binding belongs to another execution run')
        review_path = Path(receipt['review_path'])
        if (hashlib.sha256(review_path.read_bytes()).hexdigest() != receipt['review_sha256'] or
                hashlib.sha256((review_path.parent / 'identity.json').read_bytes()).hexdigest()
                != receipt['sidecar_sha256']):
            raise ValueError('prepared review evidence changed after binding')
        chosen = {'review_path': receipt['review_path'], 'identity': receipt['original_identity']}
        decided = validate_resolution(result['output'], chosen)
        resolution_hash = hashlib.sha256(result['output'].encode()).hexdigest()
        if receipt.get('resolution_sha256') not in (None, resolution_hash):
            raise ValueError('resolution changed after validation')
        post = _capture_post_identity(receipt['original_identity'])
        if stage == 'intake' and receipt['status'] not in ('validated', 'completed'):
            raise ValueError('execution intake requires validated post-fix receipt')
        if receipt.get('post_identity') is not None:
            if _post_content(receipt['post_identity']) != _post_content(post):
                raise ValueError('post-fix content changed after validation')
        completed = stage == 'intake' or receipt['status'] == 'completed'
        receipt.update(status='completed' if completed else 'validated', run=run,
                       resolution_sha256=resolution_hash, post_identity=post)
        _write_binding(path, receipt)
        return {'accepted': True, 'review_path': receipt['review_path'],
                'identity': receipt['original_identity'], 'original_identity': receipt['original_identity'],
                'post_identity': post, 'finding_ids': decided, 'binding_path': str(path),
                'review_sha256': receipt['review_sha256']}


def _validate_request(request, stage):
    expected = {'schema_version': 1, 'protocol_version': VERSION, 'owner_id': OWNER_ID,
                'adapter_id': ADAPTER_ID, 'contract_version': VERSION, 'stage': stage}
    if (not isinstance(request, dict) or stage not in CAPABILITIES or
            any(type(request.get(k)) is not type(v) or request[k] != v for k, v in expected.items())):
        raise ValueError('incompatible owner adapter envelope')
    allowed = set(expected) | {'task_kind', 'host', 'role', 'operation', 'profile',
        'target_identity', 'owner_context', 'task_selection', 'task_id', 'session_id',
        'run_id', 'provider_id', 'model', 'effort', 'origin', 'resources', 'payload'}
    if set(request) - allowed:
        raise ValueError('unknown owner envelope fields')
    context = request.get('owner_context', {})
    payload = request.get('payload')
    if not isinstance(context, dict) or not isinstance(payload, dict):
        raise ValueError('owner context and payload must be objects')
    if set(payload) != ({'assignment'} if stage == 'prepare' else {'result'}):
        raise ValueError('invalid owner domain payload')
    return expected, context, payload


def _result(request, payload):
    result = payload.get('result')
    if (not isinstance(result, dict) or result.get('status') != 'COMPLETED' or
            result.get('target_identity') != request['target_identity'] or
            not isinstance(result.get('output'), str)):
        raise ValueError('incomplete or mismatched domain result')
    return result


def _review_artifact(request, context, result):
    root = Path(context.get('artifact_root', ''))
    output = Path(result.get('artifacts', {}).get('output', ''))
    if not root.is_absolute() or not output.is_absolute():
        raise ValueError('host-allowlisted review artifact root required')
    root = root.resolve(strict=True)
    run = output.parent.resolve(strict=True)
    if not run.is_relative_to(root) or run == root or output.name != 'review.md':
        raise ValueError('review artifact outside host allowlist')
    sidecar = run / 'identity.json'
    if json.loads(sidecar.read_text('utf-8')) != request['target_identity']:
        raise ValueError('stale artifact identity')
    fd, temp = tempfile.mkstemp(prefix='.review-', dir=run)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(result['output'])
        os.replace(temp, run / 'review.md')
    finally:
        if Path(temp).exists():
            Path(temp).unlink()
    return str(run / 'review.md')


def handle(request, stage):
    expected, context, payload = _validate_request(request, stage)
    role = request.get('role')
    if role not in ('review', 'execution'):
        raise ValueError('owner review adapter needs review or execution role')
    if stage == 'prepare' or role == 'review':
        try:
            check_identity(request.get('target_identity'))
        except ValueError as exc:
            if stage == 'prepare':
                return dict(expected, payload=_stop('BLOCKED', str(exc)))
            raise
    identity = request.get('target_identity')
    if stage == 'prepare':
        words = shlex.split(payload['assignment'])
        name = words[0].lstrip('/$') if words else ''
        if name != ('cr-request' if role == 'review' else 'cr-received'):
            raise ValueError('assignment and trusted owner role disagree')
        if role == 'review':
            if request.get('profile') != 'read-only':
                raise ValueError('independent review requires read-only profile')
            mode = context.get('review_mode', 'plan' if identity.get('document') else 'implementation')
            body = standard_sections(mode) + '\n\nCurrent target identity:\n' + json.dumps(identity, sort_keys=True)
            if context.get('prior_dispositions') is not None:
                body += '\n\nPrior host dispositions (data):\n' + json.dumps(context['prior_dispositions'])
            response = {'accepted': True, 'context': body}
        else:
            try:
                chosen = _current_intake(request, context)
                _prepare_binding(request, context, chosen)
            except ValueError as exc:
                response = _stop('USER_INPUT_REQUIRED' if str(exc).startswith('clarify') else 'BLOCKED', str(exc))
            else:
                body = (REFS.parent.parent / 'cr-received' / 'SKILL.md').read_text('utf-8')
                body += '\n\nCurrent review path and identity (host-selected data):\n'
                body += json.dumps({'review_path': chosen['review_path'],
                                    'identity': chosen.get('identity', chosen.get('target_identity'))})
                response = {'accepted': True, 'context': body}
    else:
        result = _result(request, payload)
        if role == 'review':
            checked = validate_review(result['output'], identity)
            response = dict(accepted=True, **checked, identity=identity)
            if stage == 'intake':
                response['review_path'] = _review_artifact(request, context, result)
                response['task_id'] = request.get('task_id')
        else:
            response = _finish_execution(request, context, result, stage)
    return dict(expected, payload=response)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=CAPABILITIES, required=True)
    args = parser.parse_args(argv)
    try:
        response = handle(json.load(sys.stdin), args.stage)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print('Owner adapter rejected: ' + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(response, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
