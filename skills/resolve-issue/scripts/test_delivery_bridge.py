"""Host callback delivery using real local G3 helpers and fake forge/deployment data."""
import copy
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import workflow as w
import delivery_bridge as d


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        tools=self.root/'tools';tools.mkdir()
        self.git_binary=shutil.which('git')
        (tools/'git').symlink_to(self.git_binary)
        self.env={'PATH':str(tools),'HOME':str(self.root),'GIT_CONFIG_NOSYSTEM':'1',
                  'GIT_CONFIG_GLOBAL':os.devnull,'LANG':'C','LC_ALL':'C'}
        environment=patch.dict(os.environ,self.env,clear=True)
        environment.start();self.addCleanup(environment.stop)
        self.repo = self.root/'repo'; self.repo.mkdir()
        self.git('init','-q'); self.git('config','user.name','Fixture')
        self.git('config','user.email','fixture@example.invalid')
        (self.repo/'.gitignore').write_text('.delivery-evidence/\n')
        (self.repo/'owned').write_text('content')
        self.git('add','.'); self.git('commit','-qm','Fixture')
        self.head=self.git('rev-parse','HEAD'); self.tree=self.git('rev-parse','HEAD^{tree}')
        self.git('branch','integrated')
        self.git('branch','feature')
        self.state=w.intake('#33',{'repository':'fixture/project','number':33,'available':True,
            'scope':['approved'],'requirements_clear':True}, {'repository':'fixture/project',
            'base':self.head,'head':self.head,'tree':self.tree,'workspace':str(self.repo),
            'task_id':'task33','workspace_task_id':'task33','workspace_dirty':False})
        self.state=w.record(self.state,'passed',stage='code-review',evidence=['independent local review'])
        self.state['current_stage']='delivery'; self.state['status']='pending'
        self.calls=[];self.saved=[];self.comments=[]
        self.observation={'schema':'gate-observation-v1','head':self.head,'base':self.head,
            'observed_at':100,'deadline':200,'policy':{'source':'fixture','retrieval':'ok',
            'coverage':'complete','coverage_evidence':'complete policy','absence_proof':'none required','required':[]},
            'project_checks':[], 'checks':{'source':'fixture','head':self.head,'complete':True,'items':[]},
            'mergeability':{'source':'fixture','head':self.head,'base':self.head,'state':'CLEAN'},
            'native_gate':{'source':'fixture','head':self.head,'base':self.head,'state':'passed','bypass':False}}
        self.host=d.DeliveryHost(actions={step:self.action(step) for step in d.ACTIONS},
            reconcile=lambda step,intent,state:{'status':'unknown'},
            measure=lambda state: {'head':self.head,'tree':self.tree,'base':self.head},
            read_observation=lambda:copy.deepcopy(self.observation),now=lambda:110,max_age=30,
            local_checks=lambda state:d.gate.LocalCheckEvidence(self.head,self.head,self.tree,('fixture-check',),100,True,True,True),
            read_review=lambda state:{'head':self.head,'status':'passed','evidence':'forge review full SHA'},
            verify_integration=lambda result,state:result['merge_sha']==self.head,
            production=d.ProductionContract('deploy','explicit fixture deployment','project contract v1'),
            store=d.evidence.PendingStore(self.repo),transport=self,
            publication_authority=lambda record:d.evidence.PublicationAuthority(
                record['repo'],record['pr'],record['task'],record['attempt'],1,'fixture',record['content_sha256'],True),
            cleanup_guard=d.cleanup.CleanupGuard(self.repo,git=self.git_binary,env=self.env),
            disposal_authority=self.disposal_authority,
            cleanup_observation=self.cleanup_observation,
            verify_cleanup=self.verify_cleanup,
            permitted_actions=d.ACTIONS)
        self.inv=w.Invocation(auto=True,permitted_stages=w.PRE_DELIVERY+('delivery',))

    def disposal_authority(self,state):
        data=state['delivery']
        tasks=()
        if data.get('production_status')=='succeeded':
            record=self.host.store.load(Path(data['evidence_path']))['record']
            tasks=(d.cleanup.EvidenceRequirement(33,'task33',data['attempt'],self.head,record['content_sha256']),)
        return d.cleanup.DisposalAuthority('github.com/fixture/project','feature',
            'refs/heads/integrated',True,False,d.cleanup.PostMergeInventory(tasks,'project contract','explicit remaining task inventory'))

    def cleanup_observation(self,state):
        path=state['delivery'].get('evidence_path')
        records=[] if path is None else [self.host.store.load(Path(path))['record']]
        return {'repo':'github.com/fixture/project','destination_sha':self.head,'post_merge_evidence':records}

    def git(self,*args):
        return subprocess.check_output([self.git_binary,'-C',str(self.repo),*args],stderr=subprocess.DEVNULL,env=self.env).decode().strip()

    def action(self,step):
        def call(state):
            self.calls.append(step)
            if step=='pr': return {'pr':33,'head':self.head,'base':self.head,'closing_reference':'Fixes #33','evidence':['PR lookup/create']}
            if step=='cleanup':
                binding=copy.deepcopy(state['delivery'].get('cleanup_binding'))
                authority=self.host.disposal_authority(state)
                if authority.allow_workspace_remove:
                    self.git('worktree','remove',state['workspace'])
                if authority.allow_branch_delete:
                    self.git('branch','-D',authority.branch)
                return {'status':'completed','cleanup':binding,'evidence':['actual resource absence']}
            if step=='merge': return {'merge_sha':self.head,'evidence':['pinned squash readback']}
            if step=='deploy': return {'id':'deployment33','version':self.head,'merge_sha':self.head,'evidence':['deploy readback']}
            if step=='health': return {'status':'succeeded','deployment_id':'deployment33','version':self.head,
                'merge_sha':self.head,'checks':[{'command':'fixture health','result':'passed'}],'evidence':['health proof']}
            return {'status':'completed','evidence':[step+' proof']}
        return call

    def verify_cleanup(self,receipt,state):
        binding=receipt.get('cleanup')
        if binding!=state['delivery'].get('cleanup_binding') or not isinstance(binding,dict):
            return False
        authority=self.host.disposal_authority(state)
        return (not authority.allow_branch_delete or self.git('branch','--list',authority.branch)=='') and (
            not authority.allow_workspace_remove or not Path(state['workspace']).exists())

    def checkpoint(self,state):
        stored=w.store(self.root/'private'/'state.json',state)
        self.saved.append(copy.deepcopy(stored))
        return stored

    def run_delivery(self,state=None,inv=None):
        return w.run_loop(state or self.state,inv or self.inv,lambda *args:self.fail('pre-delivery executor called'),
            checkpoint=self.checkpoint,delivery_host=self.host)

    def current_author(self):return {'id':1,'login':'fixture'}
    def lookup(self,repo,pr,key):return {'complete':True,'absence_confirmed':True,'matches':copy.deepcopy(self.comments)}
    def create(self,repo,pr,body,key):
        self.comments.append({'id':1,'repo':repo,'pr':pr,'author_id':1,'author_login':'fixture','body':body,'url':'https://github.com/fixture/project/pull/33#issuecomment-1'})
        return 1
    def update(self,comment,body):self.comments[0]['body']=body
    def read(self,comment):return copy.deepcopy(self.comments[0])

    def test_auto_finishes_only_after_real_gate_evidence_and_cleanup_decision(self):
        result=self.run_delivery()
        self.assertEqual(result['status'],'passed')
        self.assertTrue(result['delivery']['complete'])
        self.assertEqual(result['delivery']['production_status'],'succeeded')
        self.assertEqual(result['delivery']['evidence_status'],'published')
        self.assertEqual(self.calls,['pr','ready','wait','merge','deploy','health','cleanup','learnings'])
        self.assertEqual(len(self.comments),1)
        for action in ('pr','merge','deploy'):
            self.assertTrue(any((s.get('delivery',{}).get('intent') or {}).get('action')==action for s in self.saved))
        self.assertIsNone(w.handoff(result,self.inv)['next_stage'])
        self.run_delivery(result)
        self.assertEqual(self.calls.count('merge'),1)

    def test_unknown_production_stops_for_existing_consultation_boundary(self):
        self.host=replace(self.host,production=None)
        result=self.run_delivery()
        self.assertIn(result['status'],('blocked','awaiting-user'))
        self.assertNotIn('deploy',self.calls)
        self.assertFalse(result.get('delivery',{}).get('complete',False))

    def test_default_invocation_never_inherits_auto_delivery_permission(self):
        result=self.run_delivery(inv=w.Invocation(auto=True))
        self.assertEqual(result['status'],'blocked');self.assertEqual(self.calls,[])

    def test_missing_policy_and_changed_head_prevent_merge(self):
        for mutate in ('policy','head'):
            with self.subTest(mutate=mutate):
                state=copy.deepcopy(self.state);self.calls.clear()
                (self.root/'private'/'state.json').unlink(missing_ok=True)
                obs=copy.deepcopy(self.observation)
                if mutate=='policy':
                    obs['policy']['retrieval']='denied';obs['native_gate']=None
                else:obs['head']='c'*40
                self.host=replace(self.host,read_observation=lambda:obs)
                result=self.run_delivery(state)
                self.assertEqual(result['status'],'blocked');self.assertNotIn('merge',self.calls)

    def test_unknown_merge_outcome_never_repeats_without_reconcile(self):
        actions=dict(self.host.actions)
        def uncertain(state):
            self.calls.append('merge');raise TimeoutError('write result unknown')
        actions['merge']=uncertain;self.host=replace(self.host,actions=actions)
        result=self.run_delivery()
        self.assertEqual(result['status'],'blocked');self.assertEqual(self.calls.count('merge'),1)
        result=self.run_delivery(result)
        self.assertEqual(self.calls.count('merge'),1)
        self.host=replace(self.host,reconcile=lambda step,intent,state:{'status':'completed','result':{'merge_sha':self.head,'evidence':['authoritative merge readback']}})
        result=self.run_delivery(result)
        self.assertEqual(result['status'],'passed');self.assertEqual(self.calls.count('merge'),1)

    def test_explicit_nonproduction_never_fabricates_deployment_or_published_prod(self):
        self.host=replace(self.host,production=d.ProductionContract('none','docs only','verified project classification'))
        result=self.run_delivery()
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['delivery']['production_status'],'n/a')
        self.assertNotIn('deploy',self.calls);self.assertNotIn('health',self.calls)
        self.assertNotIn('deployment',result['delivery']);self.assertEqual(self.comments,[])

    def test_manual_resume_needs_fresh_transition_permission(self):
        result=self.run_delivery(inv=replace(self.inv,auto=False))
        self.assertEqual(result['status'],'awaiting-user');self.assertEqual(self.calls,[])
        result=self.run_delivery(result,replace(self.inv,auto=False,approve_stage='delivery'))
        self.assertEqual(result['status'],'awaiting-user');self.assertEqual(self.calls,['pr'])
        for step in ('ready','wait'):
            result=self.run_delivery(result,replace(self.inv,auto=False,approve_stage='delivery'))
            self.assertEqual(result['status'],'awaiting-user')
            self.assertEqual(self.calls[-1],step)
            self.assertNotIn('merge',self.calls)
            self.assertNotIn('deploy',self.calls)
        result=self.run_delivery(result,w.Invocation())
        self.assertEqual(result['status'],'blocked');self.assertEqual(self.calls,['pr','ready','wait'])

    def test_failed_health_and_cleanup_cannot_claim_completion(self):
        for step in ('health','cleanup'):
            with self.subTest(step=step):
                (self.root/'private'/'state.json').unlink(missing_ok=True)
                actions={name:self.action(name) for name in d.ACTIONS}
                actions[step]=lambda state:{'status':'failed','evidence':['failed proof']}
                self.host=replace(self.host,actions=actions)
                result=self.run_delivery(copy.deepcopy(self.state))
                self.assertFalse(result.get('delivery',{}).get('complete',False))
                self.assertIn(result['status'],('blocked','failed'))

    def test_full_auto_stage_loop_reaches_delivery_with_explicit_project_capabilities(self):
        self.state['current_stage']='intake'
        result=w.run_loop(self.state,self.inv,
            lambda stage,state,args:{'status':'passed','evidence':[stage+' proof']},
            measure_identity=lambda stage,state:dict(state['identity']),
            checkpoint=self.checkpoint,delivery_host=self.host)
        self.assertTrue(result['delivery']['complete'])
        self.assertEqual(result['status'],'passed')

    def test_intent_is_on_disk_before_callback_and_unknown_pr_deploy_are_not_repeated(self):
        original=self.host
        for action in ('pr','deploy'):
            with self.subTest(action=action):
                (self.root/'private'/'state.json').unlink(missing_ok=True)
                self.calls.clear();self.comments.clear()
                actions=dict(original.actions)
                def uncertain(state):
                    saved=w.load(self.root/'private'/'state.json')
                    self.assertEqual(saved['delivery']['intent']['action'],action)
                    self.calls.append(action)
                    raise TimeoutError('unknown result')
                actions[action]=uncertain
                self.host=replace(original,actions=actions)
                result=self.run_delivery(copy.deepcopy(self.state))
                self.assertEqual(self.calls.count(action),1)
                result=self.run_delivery(result)
                self.assertEqual(self.calls.count(action),1)
                self.assertEqual(result['status'],'blocked')

    def test_authoritative_absence_allows_one_retry_with_fresh_permission(self):
        actions=dict(self.host.actions)
        def uncertain(state):
            self.calls.append('merge');raise TimeoutError('unknown result')
        actions['merge']=uncertain;self.host=replace(self.host,actions=actions)
        result=self.run_delivery()
        actions['merge']=self.action('merge')
        self.host=replace(self.host,actions=actions,reconcile=lambda *args:{
            'status':'absent','authoritative':True,'evidence':'settled complete merge lookup'})
        result=self.run_delivery(result)
        self.assertEqual(result['status'],'passed');self.assertEqual(self.calls.count('merge'),2)

    def test_uncertain_evidence_write_recovers_actual_g3_record_without_duplicate_comment(self):
        original=self.create
        def uncertain(*args):
            original(*args);raise d.evidence.TransportError('unknown write outcome')
        self.create=uncertain
        result=self.run_delivery()
        self.assertEqual(result['status'],'blocked');self.assertNotIn('cleanup',self.calls)
        self.assertEqual(len(self.comments),1)
        self.create=original
        self.host=replace(self.host,now=lambda:111)
        result=self.run_delivery(result)
        self.assertEqual(result['status'],'passed');self.assertEqual(len(self.comments),1)

    def test_changed_contract_cannot_turn_uncertain_deployment_into_na(self):
        actions=dict(self.host.actions)
        actions['deploy']=lambda state:(_ for _ in ()).throw(TimeoutError('unknown deployment'))
        self.host=replace(self.host,actions=actions)
        result=self.run_delivery()
        self.host=replace(self.host,production=d.ProductionContract('none','new claim','different contract'))
        resumed=self.run_delivery(result)
        self.assertEqual(resumed['status'],'blocked')
        self.assertIn('changed',resumed['blockers'][0])
        self.assertNotEqual(resumed['delivery'].get('production_status'),'n/a')

    def test_queued_or_wrong_version_health_never_counts_as_production(self):
        original=self.host
        for change in ({'status':'queued'},{'version':'different'}):
            with self.subTest(change=change):
                (self.root/'private'/'state.json').unlink(missing_ok=True)
                actions=dict(original.actions)
                actions['health']=lambda state:{**self.action('health')(state),**change}
                self.host=replace(original,actions=actions)
                result=self.run_delivery(copy.deepcopy(self.state))
                self.assertEqual(result['status'],'blocked')
                self.assertFalse(result['delivery']['complete'])

    def test_delivery_needs_durable_checkpoint_and_cannot_bypass_pending_question(self):
        result=w.run_loop(self.state,self.inv,lambda *args:self.fail('called'),delivery_host=self.host)
        self.assertEqual(result['status'],'blocked');self.assertEqual(self.calls,[])
        state=copy.deepcopy(self.state);state['question']={'question':'Owner decision?'}
        result=self.run_delivery(state)
        self.assertEqual(result['question'],state['question']);self.assertEqual(self.calls,[])

    def test_retarget_cannot_discard_uncertain_external_action(self):
        actions=dict(self.host.actions)
        actions['merge']=lambda state:(_ for _ in ()).throw(TimeoutError('unknown merge'))
        self.host=replace(self.host,actions=actions)
        result=self.run_delivery()
        with self.assertRaisesRegex(ValueError,'Reconcile'):
            w.retarget(result,{'head':'c'*40,'tree':'d'*40})


    def test_ready_and_wait_obtain_remote_review_without_requiring_it_first(self):
        self.observation['mergeability']['state']='DRAFT'
        actions=dict(self.host.actions)
        def ready(state):
            self.observation['mergeability']['state']='CLEAN'
            return self.action('ready')(state)
        actions['ready']=ready
        self.host=replace(self.host,actions=actions,read_review=lambda state:{
            'head':self.head,'status':'pending','evidence':'review starts after ready'})
        result=self.run_delivery()
        self.assertEqual(self.calls,['pr','ready','wait'])
        self.assertEqual(result['status'],'blocked')
        self.assertIn('Forge review',result['blockers'][0])

    def test_ready_requires_existing_local_independent_review(self):
        self.state['records']=[]
        result=self.run_delivery()
        self.assertEqual(result['status'],'blocked')
        self.assertNotIn('ready',self.calls)

    def test_completed_merge_reconciles_after_real_base_advance(self):
        actions=dict(self.host.actions)
        advanced=[]
        def merged(state):
            self.calls.append('merge')
            self.git('commit','--allow-empty','-qm','Actual integration')
            advanced.append(self.git('rev-parse','HEAD'))
            self.git('branch','-f','integrated',advanced[0])
            raise TimeoutError('merge response lost')
        actions['merge']=merged
        self.host=replace(self.host,actions=actions)
        result=self.run_delivery()
        reconciled=[]
        def reconcile(action,intent,state):
            reconciled.append(action)
            return {'status':'completed','result':{'merge_sha':advanced[0],
                'evidence':['actual destination commit readback']}}
        self.host=replace(self.host,measure=lambda state:{'head':self.head,'tree':self.tree,'base':advanced[0]},
            reconcile=reconcile,verify_integration=lambda receipt,state:receipt['merge_sha']==self.git('rev-parse','integrated'),
            permitted_actions=('merge',))
        result=self.run_delivery(result)
        self.assertEqual(reconciled,['merge'])
        self.assertEqual(result['delivery']['results']['merge']['merge_sha'],advanced[0])
        self.assertEqual(self.calls.count('merge'),1)

    def test_absent_merge_after_base_advance_still_cannot_retry(self):
        actions=dict(self.host.actions)
        def uncertain(state):
            self.calls.append('merge');raise TimeoutError('unknown merge')
        actions['merge']=uncertain
        self.host=replace(self.host,actions=actions)
        result=self.run_delivery()
        reconciled=[]
        def reconcile(*args):
            reconciled.append('merge')
            return {'status':'absent','authoritative':True,'evidence':'settled lookup'}
        self.host=replace(self.host,reconcile=reconcile,
            measure=lambda state:{'head':self.head,'tree':self.tree,'base':'c'*40})
        result=self.run_delivery(result)
        self.assertEqual(reconciled,['merge'])
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(self.calls.count('merge'),1)

    def test_session_created_capability_reaches_actual_linked_worktree_guard(self):
        workspace=self.root/'linked'
        self.git('worktree','add','-q',str(workspace),'feature')
        state=copy.deepcopy(self.state);state['workspace']=str(workspace)
        self.host=replace(self.host,production=d.ProductionContract('none','docs only','project proof'),
            cleanup_guard=d.cleanup.CleanupGuard(workspace,git=self.git_binary,env=self.env),
            disposal_authority=lambda state:replace(self.disposal_authority(state),allow_workspace_remove=True),
            session_created=True,permitted_actions=d.ACTIONS[:d.ACTIONS.index('cleanup')+1])
        result=self.run_delivery(state)
        self.assertEqual(result['delivery']['results']['cleanup']['status'],'completed')
        self.assertFalse(workspace.exists())

    def test_saved_session_created_cannot_authorize_workspace_removal(self):
        workspace=self.root/'linked'
        self.git('worktree','add','-q',str(workspace),'feature')
        self.state['workspace']=str(workspace);self.state['session_created']=True
        self.host=replace(self.host,production=d.ProductionContract('none','docs only','project proof'),
            cleanup_guard=d.cleanup.CleanupGuard(workspace,git=self.git_binary,env=self.env),
            disposal_authority=lambda state:replace(self.disposal_authority(state),allow_workspace_remove=True))
        result=self.run_delivery()
        self.assertEqual(result['status'],'blocked')
        self.assertTrue(workspace.exists());self.assertNotIn('cleanup',self.calls)

    def test_completed_cleanup_reconciles_actual_deleted_branch_once(self):
        actions=dict(self.host.actions);receipts=[]
        def deleted(state):
            saved=w.load(self.root/'private'/'state.json')
            self.assertEqual(saved['delivery'].get('cleanup_binding'),state['delivery'].get('cleanup_binding'))
            receipts.append(self.action('cleanup')(state))
            raise TimeoutError('cleanup response lost')
        actions['cleanup']=deleted;self.host=replace(self.host,actions=actions)
        result=self.run_delivery()
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(self.git('branch','--list','feature'),'')
        self.host=replace(self.host,reconcile=lambda *args:{'status':'completed','result':receipts[0]})
        result=self.run_delivery(result)
        self.assertEqual(result['status'],'passed')
        self.assertEqual(self.calls.count('cleanup'),1)

    def test_recovered_cleanup_requires_matching_receipt_and_current_postflight(self):
        actions=dict(self.host.actions);receipts=[]
        def deleted(state):
            receipts.append(self.action('cleanup')(state))
            raise TimeoutError('cleanup response lost')
        actions['cleanup']=deleted;self.host=replace(self.host,actions=actions)
        result=self.run_delivery()
        self.host=replace(self.host,reconcile=lambda *args:{'status':'completed','result':receipts[0]},
            verify_cleanup=None)
        result=self.run_delivery(result)
        self.assertEqual(result['status'],'blocked');self.assertEqual(self.calls.count('cleanup'),1)
        self.host=replace(self.host,verify_cleanup=self.verify_cleanup)
        receipts[0]['cleanup']['authority']['branch']='different'
        result=self.run_delivery(result)
        self.assertEqual(result['status'],'blocked');self.assertEqual(self.calls.count('cleanup'),1)

    def test_removed_workspace_recovery_needs_no_guard_for_deleted_path(self):
        workspace=self.root/'linked'
        self.git('worktree','add','-q',str(workspace),'feature')
        self.state['workspace']=str(workspace)
        actions=dict(self.host.actions);receipts=[]
        def removed(state):
            receipts.append(self.action('cleanup')(state))
            raise TimeoutError('workspace removal response lost')
        actions['cleanup']=removed
        self.host=replace(self.host,actions=actions,
            production=d.ProductionContract('none','docs only','project proof'),
            cleanup_guard=d.cleanup.CleanupGuard(workspace,git=self.git_binary,env=self.env),
            disposal_authority=lambda state:replace(self.disposal_authority(state),allow_workspace_remove=True),
            session_created=True)
        result=self.run_delivery()
        self.assertFalse(workspace.exists());self.assertEqual(result['status'],'blocked')
        self.host=replace(self.host,cleanup_guard=None,
            reconcile=lambda *args:{'status':'completed','result':receipts[0]})
        result=self.run_delivery(result)
        self.assertEqual(result['status'],'passed');self.assertEqual(self.calls.count('cleanup'),1)


if __name__=='__main__':unittest.main()
