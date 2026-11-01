import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HELPER = Path(__file__).with_name('reply_disposition.py')
SHA = 'a' * 40
KEY = {'schema_version': 1, 'repository': 'owner/repo', 'pr_number': 42, 'head_sha': SHA,
       'origin_review_id': 101, 'original_id': 'R1-F1', 'path': 'src/a.py',
       'disposition': 'REJECT', 'reason': 'Evidence supports this behavior.', 'owner': None}
FAKE = '''#!/usr/bin/env python3
import json, os, pathlib, sys
p = pathlib.Path(os.environ['FAKE_DIR']); state = json.loads((p/'state.json').read_text())
a = sys.argv[1:]
if a[:2] == ['repo', 'view']: print(json.dumps({'nameWithOwner':'owner/repo'})); sys.exit(0)
method = a[a.index('-X')+1] if '-X' in a else 'GET'; endpoint = a[1]
entry = {'method': method, 'endpoint': endpoint, 'comment_id': None, 'disposition': None, 'exit': 0}
if method == 'POST':
    payload = json.load(sys.stdin); marker = payload['body'].split('<!-- cr-received-disposition:v1 ', 1)[1].split(' -->', 1)[0]; data = json.loads(marker); entry['disposition'] = data['disposition']; entry['key'] = [data['repository'], data['pr_number'], data['origin_review_id'], data['original_id']]; entry['comment_id'] = 11
    if state.get('ambiguous'): state['replies'].append({'id': 99, 'user': {'login': 'host'}, 'body': payload['body'], 'in_reply_to_id': 11}); (p/'state.json').write_text(json.dumps(state)); entry['exit'] = 1
    result = {'id': 99}
elif endpoint == 'user': result = {'login': 'host'}
elif '/collaborators/' in endpoint: result = {'permission': 'write'} if 'forged' not in endpoint else {'permission': 'read'}
elif endpoint.endswith('/pulls/42'):
    count = state.get('head_reads', 0) + 1; state['head_reads'] = count; (p/'state.json').write_text(json.dumps(state))
    result = {'number': state.get('pr',42), 'head': {'sha': ('b'*40 if state.get('head_changes') and count > 1 else state.get('head', 'a'*40))}}
elif endpoint.endswith('/pulls/comments/11'): result = {'id': state.get('root_id',11), 'pull_request_review_id': state.get('root_review_id',101), 'pull_request_url': state.get('root_url','https://api.github.com/repos/owner/repo/pulls/42'), 'path':state.get('root_path','src/a.py'), 'body':state.get('root_body','**Minor** R1-F1\\nFinding evidence.'), 'user': {'login': state.get('author','yngwald')}}
elif endpoint.endswith('/pulls/42/reviews/101'): result = {'id':101,'user':{'login':'yngwald'},'commit_id':'a'*40,'body':state['ledger']}
elif '/pulls/42/comments?' in endpoint:
    page = int(endpoint.rsplit('page=', 1)[1]); result = state['replies'] if page == 2 else ([{'id': i+1000,'body':'ordinary','user':{'login':'other'}} for i in range(100)] if state.get('paginate') and page == 1 else [])
else: entry['exit'] = 1; result = {}
with (p/'trace.jsonl').open('a') as f: f.write(json.dumps(entry)+'\\n')
print(json.dumps(result)); sys.exit(entry['exit'])
'''

class ReplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.p = Path(self.tmp.name)
        gh = self.p/'gh'; gh.write_text(FAKE); gh.chmod(0o700)
        ledger = {'envelope_version':1,'schema_version':1,'repository':'owner/repo','pr_number':42,'head_sha':SHA,'published_review_id':101,'review_source_id':101,'findings':[{'origin_review_id':101,'original_id':'R1-F1','path':'src/a.py','severity':'Minor'}], 'previous_findings':[], 'run_id':303, 'duration_seconds':None, 'action_progress':[], 'disposition_events':[]}
        self.ledger = ledger
        self.state = {'ledger':'<!-- claude-review-ledger:v1 '+json.dumps(ledger)+' -->','replies':[], 'paginate':True}
        (self.p/'reason').write_text(KEY['reason'])
    def marker(self, **changes):
        payload = dict(KEY, **changes)
        return '<!-- cr-received-disposition:v1 '+json.dumps(payload)+' -->'
    def run_helper(self, *extra):
        (self.p/'state.json').write_text(json.dumps(self.state))
        env = dict(os.environ, PATH=str(self.p)+os.pathsep+os.environ['PATH'], FAKE_DIR=str(self.p))
        cmd = [sys.executable,str(HELPER),'--repository','owner/repo','--pr','42','--head',SHA,'--origin-review-id','101','--original-id','R1-F1','--path','src/a.py','--root-comment-id','11','--disposition','REJECT','--reason-file',str(self.p/'reason'),*extra]
        out = subprocess.run(cmd, env=env, capture_output=True, text=True)
        trace = [json.loads(x) for x in (self.p/'trace.jsonl').read_text().splitlines()] if (self.p/'trace.jsonl').exists() else []
        self.assertFalse(any('/issues' in x['endpoint'] or 'resolve' in x['endpoint'] or x['method'] in ('PUT','PATCH','DELETE') for x in trace))
        return out, [x for x in trace if x['method'] == 'POST']
    def test_posts_once(self):
        out, writes = self.run_helper(); self.assertEqual(out.returncode,0,out.stderr); self.assertEqual(len(writes),1); self.assertEqual(writes[0]['endpoint'], 'repos/owner/repo/pulls/42/comments/11/replies'); self.assertEqual(writes[0]['key'], ['owner/repo', 42, 101, 'R1-F1']); self.assertEqual(writes[0]['disposition'], 'REJECT')
    def test_duplicate(self):
        self.state['replies']=[{'id':22,'user':{'login':'host'},'body':self.marker(), 'in_reply_to_id':11}]
        out,writes=self.run_helper(); self.assertEqual(out.returncode,0,out.stderr); self.assertIn('use_existing',out.stdout); self.assertEqual(writes,[])
    def test_conflicts(self):
        for change in ({'disposition':'DEFER','owner':'owner'}, {'head_sha':'b'*40}, {'reason':'different'}):
            with self.subTest(change=change):
                (self.p/'trace.jsonl').unlink(missing_ok=True); self.state['replies']=[{'id':22,'user':{'login':'host'},'body':self.marker(**change), 'in_reply_to_id':11}]
                out,writes=self.run_helper(); self.assertNotEqual(out.returncode,0); self.assertIn('marker_conflict',out.stdout); self.assertEqual(writes,[])
    def test_invalid_target(self):
        for field,value in [('head','b'*40),('author','other'),('pr',43)]:
            with self.subTest(field=field):
                (self.p/'trace.jsonl').unlink(missing_ok=True); self.state[field]=value
                out,writes=self.run_helper(); self.assertNotEqual(out.returncode,0); self.assertEqual(writes,[]); del self.state[field]
    def test_forged_marker(self):
        self.state['replies']=[{'id':22,'user':{'login':'forged'},'body':self.marker(), 'in_reply_to_id':11}]
        out,writes=self.run_helper(); self.assertNotEqual(out.returncode,0); self.assertEqual(writes,[])
    def test_ambiguous(self):
        self.state['ambiguous']=True
        out,writes=self.run_helper(); self.assertEqual(out.returncode,0,out.stderr); self.assertIn('use_existing',out.stdout); self.assertEqual(len(writes),1)
    def test_head_changes_before_post(self):
        self.state['head_changes'] = True
        out, writes = self.run_helper(); self.assertNotEqual(out.returncode, 0); self.assertEqual(writes, [])
    def test_other_finding_marker_does_not_authorize_reuse(self):
        self.state['replies']=[{'id':22,'user':{'login':'host'},'body':self.marker(original_id='R2-F1'), 'in_reply_to_id':11}]
        out, writes = self.run_helper(); self.assertEqual(out.returncode, 0); self.assertEqual(len(writes), 1)
    def test_malformed_envelopes_fail_closed(self):
        mutations = [
            lambda x: x.update(schema_version=True), lambda x: x.update(envelope_version=True),
            lambda x: x.update(review_source_id=True), lambda x: x.update(pr_number=True),
            lambda x: x.update(published_review_id=True), lambda x: x.update(run_id=True),
            lambda x: x.update(duration_seconds=True), lambda x: x.update(extra='unknown'),
            lambda x: x.pop('previous_findings'), lambda x: x.update(head_sha='bad'),
            lambda x: x['findings'][0].update(origin_review_id=True),
            lambda x: x['findings'][0].update(severity='high'),
            lambda x: x['findings'][0].update(path='../src/a.py'),
            lambda x: x['findings'][0].update(extra='unknown'),
            lambda x: x['previous_findings'].append({'origin_review_id':True}),
            lambda x: x['action_progress'].append({'origin_review_id':101}),
            lambda x: x['disposition_events'].append({'origin_review_id':101}),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                (self.p/'trace.jsonl').unlink(missing_ok=True)
                ledger = json.loads(json.dumps(self.ledger)); mutate(ledger)
                self.state['ledger'] = '<!-- claude-review-ledger:v1 '+json.dumps(ledger)+' -->'
                out, writes = self.run_helper(); self.assertNotEqual(out.returncode, 0, out.stdout); self.assertEqual(writes, [])
    def test_heading_identity_and_severity(self):
        for body in ('**Minor** R1-F2\nProse mentions R1-F1.',
                     '**Important** R1-F1\nEvidence.',
                     'Introduction\n**Minor** R1-F1\nEvidence.',
                     '**Minor** R1-F1\n**Minor** R1-F2\nEvidence.',
                     '**Minor** R1-F1extra\nEvidence.'):
            with self.subTest(body=body):
                (self.p/'trace.jsonl').unlink(missing_ok=True); self.state['root_body'] = body
                out, writes = self.run_helper(); self.assertNotEqual(out.returncode, 0, out.stdout); self.assertEqual(writes, [])
    def test_invalid_root_fields(self):
        for field, value in [('root_id', True), ('root_review_id', True), ('root_url', 'https://api.github.com/repos/owner/repo/pulls/43'), ('root_path', '../src/a.py'), ('root_body', 'R2-F1: finding')]:
            with self.subTest(field=field):
                (self.p/'trace.jsonl').unlink(missing_ok=True); self.state[field]=value
                out, writes=self.run_helper(); self.assertNotEqual(out.returncode,0); self.assertEqual(writes,[]); del self.state[field]
    def test_valid_nested_envelope(self):
        self.ledger['previous_findings'] = [{'origin_review_id': 100, 'original_id': 'R0-F1', 'path': 'src/b.py', 'severity': 'Minor', 'status': 'NOT_ADDRESSED', 'defer_decision': 'ACCEPTED', 'reason': 'Tracked.', 'owner': 'team'}]
        self.ledger['previous_findings'][0]['original_id'] = 'R2-F1'
        self.ledger['action_progress'] = [{'origin_review_id':100, 'original_id':'R2-F1', 'path':'src/b.py', 'issue':{'state':'SUCCEEDED','number':1,'url':'https://github.com/owner/repo/issues/1'}, 'reply':{'state':'PENDING','comment_id':None}, 'resolve':{'state':'PENDING','thread_id':None}, 'error':None}]
        self.ledger['disposition_events'] = [{'origin_review_id':100, 'original_id':'R2-F1', 'path':'src/b.py', 'disposition':'DEFER', 'reason':'Tracked.', 'source_comment_id':12, 'source_author':'host', 'source_updated_at':'2026-10-30T12:30:00Z'}]
        self.state['ledger']='<!-- claude-review-ledger:v1 '+json.dumps(self.ledger)+' -->'
        out, writes=self.run_helper(); self.assertEqual(out.returncode,0,out.stdout); self.assertEqual(len(writes),1)
    def test_invalid_input_and_mapping(self):
        for args in [('--pr','0'),('--original-id','R2-F1'),('--path','../x'),('--head','abc'),('--disposition','DEFER')]:
            with self.subTest(args=args):
                (self.p/'trace.jsonl').unlink(missing_ok=True)
                out,writes=self.run_helper(*args); self.assertNotEqual(out.returncode,0); self.assertEqual(writes,[])

if __name__ == '__main__': unittest.main()
