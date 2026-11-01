#!/usr/bin/env python3
"""Post one bounded host REJECT reply to a verified GitHub review thread."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile

MARKER = re.compile(r'<!--\s*cr-received-disposition:v1\s+(\{.*?\})\s*-->', re.S)
LEDGER = re.compile(r'<!--\s*claude-review-ledger:v1\s+(\{.*?\})\s*-->', re.S)
FIELDS = {'schema_version', 'repository', 'pr_number', 'head_sha', 'origin_review_id', 'original_id', 'path', 'disposition', 'reason', 'owner'}

class Stop(Exception):
    pass

def unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out: raise ValueError('duplicate JSON key')
        out[key] = value
    return out

def parse_json(s):
    return json.loads(s, object_pairs_hook=unique)

def gh(endpoint, method='GET', payload=None):
    args = ['gh', 'api', endpoint, '-X', method]
    if payload is not None:
        with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as f:
            json.dump(payload, f); f.flush(); f.seek(0)
            p = subprocess.run(args + ['--input', '-'], stdin=f, capture_output=True, text=True)
    else:
        p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode: raise Stop('api_failure')
    try: return parse_json(p.stdout)
    except (ValueError, TypeError): raise Stop('invalid_api_response')

def authorized(repo, actor):
    if not isinstance(actor, str) or not re.fullmatch(r'[A-Za-z0-9-]+', actor): return False
    result = gh(f'repos/{repo}/collaborators/{actor}/permission')
    return result.get('permission') in ('admin', 'maintain', 'write')

def positive(value):
    try: n = int(value)
    except ValueError: raise argparse.ArgumentTypeError('must be a positive integer')
    if n <= 0: raise argparse.ArgumentTypeError('must be a positive integer')
    return n

def validate_payload(v):
    return (isinstance(v, dict) and set(v) == FIELDS and type(v['schema_version']) is int and v['schema_version'] == 1
        and type(v['pr_number']) is int and v['pr_number'] > 0 and type(v['origin_review_id']) is int and v['origin_review_id'] > 0
        and isinstance(v['repository'], str) and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', v['repository'])
        and isinstance(v['head_sha'], str) and re.fullmatch(r'[0-9a-f]{40}', v['head_sha'])
        and isinstance(v['original_id'], str) and re.fullmatch(r'R[1-9][0-9]*-(?:[A-Za-z0-9_-]+-)?F[1-9][0-9]*', v['original_id'])
        and valid_path(v['path']) and v['disposition'] in ('ACCEPT','REJECT','PARTIAL','DEFER','ESCALATE','OUTDATED')
        and isinstance(v['reason'], str) and bool(v['reason'].strip())
        and (v['owner'] is None or isinstance(v['owner'], str) and bool(v['owner'].strip()))
        and (v['disposition'] != 'DEFER' or v['owner'] is not None))

def valid_path(path):
    return (isinstance(path, str) and bool(path) and '\\' not in path and not path.startswith('/')
            and all(x not in ('', '.', '..', '.git', '.cross-review') for x in path.split('/')))

def is_positive(value):
    return type(value) is int and value > 0


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def finding_identity(item):
    return (is_positive(item.get('origin_review_id'))
            and isinstance(item.get('original_id'), str)
            and re.fullmatch(r'R[1-9][0-9]*-(?:[A-Za-z0-9_-]+-)?F[1-9][0-9]*', item['original_id'])
            and valid_path(item.get('path')))


def valid_envelope(v):
    fields = {'schema_version', 'repository', 'pr_number', 'head_sha', 'review_source_id',
              'findings', 'previous_findings', 'envelope_version', 'published_review_id',
              'run_id', 'duration_seconds', 'action_progress', 'disposition_events'}
    if not isinstance(v, dict) or set(v) != fields: return False
    if (type(v['schema_version']) is not int or v['schema_version'] != 1
        or type(v['envelope_version']) is not int or v['envelope_version'] != 1
        or not isinstance(v['repository'], str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', v['repository'])
        or not is_positive(v['pr_number']) or not isinstance(v['head_sha'], str)
        or not re.fullmatch(r'[0-9a-f]{40}', v['head_sha'])
        or not is_positive(v['published_review_id']) or not is_positive(v['review_source_id'])
        or v['published_review_id'] != v['review_source_id'] or not is_positive(v['run_id'])
        or not (v['duration_seconds'] is None or type(v['duration_seconds']) is int and v['duration_seconds'] >= 0)
        or any(not isinstance(v[k], list) for k in ('findings', 'previous_findings', 'action_progress', 'disposition_events'))): return False
    base = {'origin_review_id', 'original_id', 'path', 'severity'}
    previous = base | {'status', 'defer_decision', 'reason', 'owner'}
    seen = {}
    for current, item in [(True, x) for x in v['findings']] + [(False, x) for x in v['previous_findings']]:
        if not isinstance(item, dict): return False
        if set(item) != (base if current else previous) or not finding_identity(item) or item['severity'] not in ('Critical', 'Important', 'Minor'): return False
        if current and item['origin_review_id'] != v['published_review_id']: return False
        if not current:
            status, defer, owner = item['status'], item['defer_decision'], item['owner']
            if (status not in ('ADDRESSED', 'NOT_ADDRESSED') or defer not in ('NONE', 'PROPOSED', 'ACCEPTED', 'DECLINED')
                or not nonempty(item['reason']) or not (owner is None or nonempty(owner))
                or defer in ('PROPOSED', 'ACCEPTED') and owner is None
                or defer == 'ACCEPTED' and (status != 'NOT_ADDRESSED' or item['severity'] == 'Critical')
                or status == 'ADDRESSED' and defer != 'NONE'): return False
        key = (item['origin_review_id'], item['original_id'])
        if key in seen: return False
        seen[key] = item['path']
    def known(item):
        return finding_identity(item) and seen.get((item['origin_review_id'], item['original_id'])) == item['path']
    states = ('NOT_REQUESTED', 'PENDING', 'SUCCEEDED', 'WRITE_FAILED')
    for item in v['action_progress']:
        if (not isinstance(item, dict) or set(item) != {'origin_review_id', 'original_id', 'path', 'issue', 'reply', 'resolve', 'error'}
            or not known(item) or not (item['error'] is None or nonempty(item['error']))): return False
        for name, keys, ident in (('issue', {'state', 'number', 'url'}, 'number'), ('reply', {'state', 'comment_id'}, 'comment_id'), ('resolve', {'state', 'thread_id'}, 'thread_id')):
            action = item[name]
            if not isinstance(action, dict) or set(action) != keys or action['state'] not in states: return False
            value = action[ident]
            if not (value is None or (nonempty(value) if name == 'resolve' else is_positive(value))): return False
            if action['state'] == 'SUCCEEDED' and value is None: return False
            if name == 'issue' and (not (action['url'] is None or nonempty(action['url'])) or action['state'] == 'SUCCEEDED' and action['url'] is None): return False
    for item in v['disposition_events']:
        if (not isinstance(item, dict) or set(item) != {'origin_review_id', 'original_id', 'path', 'disposition', 'reason', 'source_comment_id', 'source_author', 'source_updated_at'}
            or not known(item) or item['disposition'] not in ('ACCEPT', 'REJECT', 'PARTIAL', 'DEFER', 'ESCALATE', 'OUTDATED')
            or not nonempty(item['reason']) or not is_positive(item['source_comment_id'])
            or not nonempty(item['source_author']) or not isinstance(item['source_updated_at'], str)
            or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z', item['source_updated_at'])): return False
        try:
            from datetime import datetime
            datetime.fromisoformat(item['source_updated_at'].replace('Z', '+00:00'))
        except ValueError: return False
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repository', required=True, help='Configured owner/repo')
    p.add_argument('--pr', required=True, type=positive)
    p.add_argument('--head', required=True, help='Full expected current PR SHA')
    p.add_argument('--origin-review-id', required=True, type=positive)
    p.add_argument('--original-id', required=True, help='Original finding ID, e.g. R1-F1')
    p.add_argument('--path', required=True, help='Original finding repository-relative path')
    p.add_argument('--root-comment-id', required=True, type=positive)
    p.add_argument('--disposition', required=True, choices=['REJECT'])
    p.add_argument('--reason-file', required=True, help='UTF-8 file with human-readable evidence')
    a = p.parse_args()
    try:
        reason = Path(a.reason_file).read_text(encoding='utf-8').strip()
        expected = dict(schema_version=1, repository=a.repository, pr_number=a.pr, head_sha=a.head,
                        origin_review_id=a.origin_review_id, original_id=a.original_id, path=a.path,
                        disposition=a.disposition, reason=reason, owner=None)
        if not validate_payload(expected) or '-->' in reason or 'cr-received-disposition:v1' in reason: raise Stop('invalid_input')
        # The checkout configuration, not reviewer output, establishes the repository.
        configured = subprocess.run(['gh','repo','view','--json','nameWithOwner'], capture_output=True, text=True)
        if configured.returncode or parse_json(configured.stdout).get('nameWithOwner') != a.repository: raise Stop('repository_mismatch')
        prefix = f'repos/{a.repository}'
        key = (a.repository, a.pr, a.origin_review_id, a.original_id)
        lock_dir = Path(tempfile.gettempdir()) / f'aw-reply-{os.getuid()}'
        lock_dir.mkdir(mode=0o700, exist_ok=True)
        st = lock_dir.lstat()
        if not lock_dir.is_dir() or lock_dir.is_symlink() or st.st_uid != os.getuid() or st.st_mode & 0o077: raise Stop('unsafe_lock')
        lock_name = hashlib.sha256(json.dumps(key).encode()).hexdigest()
        fd = os.open(lock_dir / lock_name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            def head():
                pr = gh(f'{prefix}/pulls/{a.pr}')
                if not is_positive(pr.get('number')) or pr.get('number') != a.pr or pr.get('head', {}).get('sha') != a.head: raise Stop('head_or_pr_mismatch')
            head()
            actor = gh('user').get('login')
            if not authorized(a.repository, actor): raise Stop('actor_unauthorized')
            root = gh(f'{prefix}/pulls/comments/{a.root_comment_id}')
            if (not is_positive(root.get('id')) or root.get('id') != a.root_comment_id or root.get('user', {}).get('login') != 'yngwald'
                or not is_positive(root.get('pull_request_review_id')) or root.get('pull_request_review_id') != a.origin_review_id or root.get('path') != a.path
                or root.get('pull_request_url') != f'https://api.github.com/{prefix}/pulls/{a.pr}'
                or root.get('in_reply_to_id') is not None): raise Stop('root_mismatch')
            body = root.get('body')
            heading_pattern = r'^\*\*(Critical|Important|Minor)\*\* (R[1-9][0-9]*-(?:[A-Za-z0-9_-]+-)?F[1-9][0-9]*)(?=\s|$)'
            if not isinstance(body, str): raise Stop('root_mismatch')
            heading = re.match(heading_pattern, body)
            if not heading or heading.group(2) != a.original_id or len(re.findall(heading_pattern, body, re.M)) != 1: raise Stop('root_mismatch')
            review = gh(f'{prefix}/pulls/{a.pr}/reviews/{a.origin_review_id}')
            markers = LEDGER.findall(review.get('body', ''))
            if len(markers) != 1: raise Stop('finding_mapping_invalid')
            ledger = parse_json(markers[0])
            if (not is_positive(review.get('id')) or review.get('id') != a.origin_review_id or review.get('user', {}).get('login') != 'yngwald'
                or not valid_envelope(ledger)
                or ledger.get('repository') != a.repository or ledger.get('pr_number') != a.pr
                or ledger.get('published_review_id') != a.origin_review_id or ledger.get('review_source_id') != a.origin_review_id
                or ledger.get('head_sha') != review.get('commit_id')): raise Stop('finding_mapping_invalid')
            matches = [x for x in ledger.get('findings', []) if isinstance(x, dict) and x.get('origin_review_id') == a.origin_review_id and x.get('original_id') == a.original_id and x.get('path') == a.path]
            if len(matches) != 1 or heading.group(1) != matches[0]['severity']: raise Stop('finding_mapping_invalid')
            def existing():
                found = []
                page = 1
                while True:
                    comments = gh(f'{prefix}/pulls/{a.pr}/comments?per_page=100&page={page}')
                    if not isinstance(comments, list): raise Stop('invalid_api_response')
                    for comment in comments:
                        if comment.get('in_reply_to_id') != a.root_comment_id: continue
                        body = comment.get('body', '')
                        if 'cr-received-disposition:v1' not in body: continue
                        raw = MARKER.findall(body)
                        if len(raw) != 1: raise Stop('invalid_marker')
                        try: old = parse_json(raw[0])
                        except ValueError: raise Stop('invalid_marker')
                        if not validate_payload(old): raise Stop('invalid_marker')
                        oldkey = (old['repository'], old['pr_number'], old['origin_review_id'], old['original_id'])
                        if oldkey != key: continue
                        if not authorized(a.repository, comment.get('user', {}).get('login')): raise Stop('marker_actor_unauthorized')
                        found.append((comment.get('id'), old))
                    if len(comments) < 100: break
                    page += 1
                if len(found) > 1: raise Stop('multiple_markers')
                if found:
                    ident, old = found[0]
                    if type(ident) is not int or ident <= 0: raise Stop('invalid_marker')
                    if old != expected:
                        print(json.dumps({'status':'marker_conflict','needs_ruling':True,'comment_id':ident,'old':old,'new':expected}))
                        return 'conflict'
                    print(json.dumps({'status':'use_existing','comment_id':ident}))
                    return 'existing'
                return None
            status = existing()
            if status: return 1 if status == 'conflict' else 0
            head()
            body = 'REJECT: ' + reason + '\n\n<!-- cr-received-disposition:v1 ' + json.dumps(expected, ensure_ascii=True, separators=(',', ':')) + ' -->'
            try:
                result = gh(f'{prefix}/pulls/{a.pr}/comments/{a.root_comment_id}/replies', 'POST', {'body':body})
                if type(result.get('id')) is not int or result['id'] <= 0: raise Stop('ambiguous_post')
            except Stop:
                status = existing()
                if status == 'existing': return 0
                if status == 'conflict': return 1
                raise Stop('ambiguous_post_needs_ruling')
            print(json.dumps({'status':'posted','comment_id':result['id']})); return 0
    except (Stop, OSError, ValueError, TypeError, KeyError) as e:
        print(json.dumps({'status':'needs_ruling','reason':str(e) if isinstance(e, Stop) else 'invalid_input_or_api'})); return 1

if __name__ == '__main__': sys.exit(main())
