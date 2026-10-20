"""Real checkpoints, bounded clocks and fixture workers; never live providers."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from langgraph.types import Command
from poc import glg
from poc.artifacts import ArtifactError, Artifacts
from poc.contracts import digest_tree
from poc.recovery import PAUSE_POLICY, approve_recovery, budget_status
from tests import test_glg_lifecycle as fixtures
BRIEF, Harness = fixtures.BRIEF, fixtures.Harness


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.project = self.root/'project'; self.project.mkdir()
        self.h = Harness(); self.h.review = lambda state: {'passed': False, 'blocked': True, 'reason': 'Original delivery budget exhausted'}
        self.brief = self.root/'brief.json'; self.brief.write_text(json.dumps(BRIEF))
        self.patches = [patch.object(glg, 'ROOT', self.root), patch.object(glg, 'NativeHarness', return_value=self.h)]
        for p in self.patches: p.start(); self.addCleanup(p.stop)
        created = self.invoke('create', '--brief-file', str(self.brief))
        self.closed = self.invoke('approve', '--actor', 'Andy', '--revision', created['references']['brief_ref']['revision'])
        self.store = Artifacts(self.project, 'recovery')
        self.decision = {'action': 'recover-review', 'actor': 'Andy', 'reason': 'Exact preserved candidate approved for checks and review',
                         'brief_ref': self.closed['references']['brief_ref'], 'closure_ref': self.closed['references']['closure_ref'],
                         'candidate_revision': digest_tree(self.project), 'budget_seconds': 120}

    def invoke(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            glg.main(['--project', str(self.project), '--work', 'recovery', *args])
        return json.loads(out.getvalue())

    def recover(self, **updates):
        path = self.root/'decision.json'; path.write_text(json.dumps({**self.decision, **updates}))
        return self.invoke('resume', '--decision-file', str(path))

    def reject(self, **updates):
        before = len(list(self.store.root.rglob('*.json')))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit): self.recover(**updates)
        self.assertEqual(before, len(list(self.store.root.rglob('*.json'))))
        self.assertEqual(self.h.calls, 1)

    def test_expired_recovery_exact_candidate_checks_and_fresh_review_no_implementation(self):
        calls = []
        def review(state):
            calls.append(state)
            return {'passed': True, 'candidate': digest_tree(self.project), 'findings': []}
        self.h.review = review
        # The old fixed deadline has expired; a fresh explicitly bounded approval is required.
        with patch('poc.recovery.time.time', return_value=9999999999):
            recovered = self.recover()
        self.assertEqual(recovered['delivery_phase'], 'reviewed-and-ready')
        self.assertEqual(self.h.calls, 1); self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['recovery_candidate'], self.decision['candidate_revision'])
        self.assertEqual(calls[0]['budget_seconds'], 120)
        with glg.SqliteSaver.from_conn_string(str(glg.storage(self.project,'recovery')/'workflow.sqlite')) as saver:
            checkpoint=saver.get({'configurable':{'thread_id':'recovery'}})
            self.assertEqual(checkpoint['channel_values']['runtime_options']['budget_seconds'],120)
        self.assertEqual(calls[0]['pause_remaining'], None)
        record = self.store.read(recovered['references']['closure_ref'])
        self.assertEqual(record['supersedes'], self.decision['closure_ref'])
        self.reject()  # Same approval cannot apply to a later closure.

    def test_failed_checks_and_review_never_enter_implementation(self):
        self.h.review = lambda s: {'passed': False, 'candidate': digest_tree(self.project), 'findings': ['Needs correction']}
        failed = self.recover()
        self.assertEqual(failed['delivery_phase'], 'blocked'); self.assertEqual(self.h.calls, 1)
        self.assertIn('cannot implement', self.store.read(failed['references']['closure_ref'])['payload']['failure'])

    def test_check_failure_cannot_correct(self):
        with patch.object(glg.BriefChecker, 'run_state', return_value={'passed': False}):
            failed = self.recover()
        self.assertEqual(failed['delivery_phase'], 'blocked'); self.assertEqual(self.h.calls, 1)

    def test_wrong_revision_budget_actor_or_tampered_candidate_rejected_without_authority(self):
        for updates in ({'closure_ref': {}}, {'brief_ref': {}}, {'candidate_revision': 'wrong'}, {'budget_seconds': 0},
                        {'budget_seconds': True}, {'budget_seconds': 86401}, {'actor': ''}, {'reason': ''}):
            self.reject(**updates)
        (self.project/'change.txt').write_text('tampered'); self.reject()

    def test_tampered_prior_evidence_is_rejected(self):
        path = self.project/self.decision['brief_ref']['path']; path.write_text('{}')
        self.reject()

    def test_stale_checkpoint_closure_is_rejected(self):
        self.store.publish('closures', 'closure', {'outcome': 'blocked'}, supersedes=self.decision['closure_ref'])
        self.reject()

    def test_operator_lock_rejects_recovery(self):
        with glg.locked(glg.storage(self.project, 'recovery')): self.reject()

    def test_live_or_uncertain_native_evidence_rejects_recovery(self):
        from poc.recovery import require_quiescent
        for runtime in ({'quiescent': False}, {'scope_uncertain': True}, {'stop': {'alive': [123]}}, {'pid': 123}):
            with self.assertRaises(ArtifactError): require_quiescent({'runtime': runtime}, self.store)
        runtime = {'pid': 123, 'quiescent': True, 'processes': {'123': {'birth': 'old', 'parent': 1}}}
        with patch('poc.lifecycle.snapshot', return_value={123: {'birth': 'old', 'parent': 1}}), self.assertRaises(ArtifactError):
            require_quiescent({'runtime': runtime}, self.store)
        with patch('poc.lifecycle.snapshot', return_value={123: {'birth': 'reused pid', 'parent': 1}}):
            require_quiescent({'runtime': runtime}, self.store)

    def test_legacy_retry_requires_exact_candidate_authority(self):
        path = self.root/'decision.json'
        path.write_text(json.dumps({'action': 'retry-review', 'actor': 'Andy', 'reason': 'retry'}))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.invoke('resume', '--decision-file', str(path))
        self.assertEqual(self.h.calls, 1)

    def test_cli_rejects_expired_resume_before_decision_but_can_stop(self):
        now = [100]
        def invoke(*args):
            capture = io.StringIO()
            with contextlib.redirect_stdout(capture):
                glg.main(['--project', str(self.project), '--work', 'paused', *args])
            return json.loads(capture.getvalue())
        def implement(state):
            now[0] = 1000
            return {'status': 'permission_required', 'reason': 'Access denied after deadline'}
        self.h.implement = implement
        with patch('poc.workflow.time.time', side_effect=lambda: now[0]):
            created = invoke('create', '--brief-file', str(self.brief), '--budget-seconds', '1')
            paused = invoke('approve', '--actor', 'Andy', '--revision', created['references']['brief_ref']['revision'])
            self.assertTrue(paused['budget']['expired'])
            store = Artifacts(self.project, 'paused')
            before = len(list(store.root.rglob('*.json')))
            path = self.root/'decision.json'; path.write_text(json.dumps({'action': 'resume', 'actor': 'Andy'}))
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit): invoke('resume', '--decision-file', str(path))
            self.assertEqual(before, len(list(store.root.rglob('*.json'))))
            path.write_text(json.dumps({'action': 'stop', 'actor': 'Andy'}))
            stopped = invoke('resume', '--decision-file', str(path))
            self.assertEqual(stopped['outcome'], 'stopped')

    def test_recovery_mutation_during_checks_stops_before_review(self):
        def check(state):
            (self.project/'change.txt').write_text('changed by check')
            return {'passed': True}
        self.h.review = lambda s: self.fail('Changed candidate reviewed')
        # The handoff guard rejects the review assignment before any review invocation.
        with patch.object(glg.BriefChecker, 'run_state', side_effect=check):
            self.assertEqual(self.recover()['delivery_phase'], 'blocked')
        self.assertEqual(self.h.calls, 1)

    def test_substantive_rejection_cannot_be_recovered_again(self):
        self.h.review=lambda s:{'passed':False,'candidate':digest_tree(self.project),'findings':['Real defect requires correction']}
        rejected=self.recover()
        self.assertIsNone(rejected['recover_review'])
        decision={**self.decision,'closure_ref':rejected['references']['closure_ref']}
        before=len(list(self.store.root.rglob('*.json')))
        self.h.review=lambda s:self.fail('Rejected unchanged candidate reviewed again')
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):self.recover(**decision)
        self.assertEqual(before,len(list(self.store.root.rglob('*.json'))));self.assertEqual(1,self.h.calls)

    def test_eligibility_rejects_findings_and_exhausted_corrections(self):
        from poc.recovery import review_delivery_recoverable
        state={'lifecycle_phase':'closed','phase':'blocked','resume_stage':'review','candidate':'a','review':{'blocked':True,'passed':False}}
        self.assertTrue(review_delivery_recoverable(state))
        for delta in ({'findings':['defect']},{'failure':'3 correction rounds exhausted'}, {'review':{'blocked':True,'outcome':'request_changes'}}, {'review':{'passed':False,'findings':[]}}):
            self.assertFalse(review_delivery_recoverable({**state,**delta}))


class NativeRecoveryBudgetTests(unittest.TestCase):
    def test_existing_harness_uses_new_approved_budget_after_recovery(self):
        from poc.goose_job import GooseJob
        harness=glg.NativeHarness({'provider':'codex-acp','model':'fixture','budget_seconds':60})
        with patch('poc.runtime_env.setup'),patch.object(GooseJob,'review',autospec=True,side_effect=lambda job,state:{'timeout':job.timeout}):
            self.assertEqual(60,harness.review({'budget_seconds':60})['timeout'])
            self.assertEqual(600,harness.review({'budget_seconds':600,'recovery_ref':{'path':'fixture','revision':'approved'}})['timeout'])
            self.assertEqual(60,harness.options['budget_seconds'])



class PauseBudgetTests(fixtures.LifecycleTests):
    def test_new_work_freezes_at_persisted_host_pause(self):
        self.initial['budget_policy'] = PAUSE_POLICY
        original = self.h.implement
        self.h.implement = lambda s: {'status': 'permission_required', 'reason': 'Sign in separately'} if not s.get('resume_epoch') else original(s)
        with patch('poc.work_lifecycle.time.time', return_value=100):
            self.g.invoke(self.initial, self.cfg); self.approve()
        from poc.recovery import delivery_state
        snapshot = self.g.get_state(self.cfg, subgraphs=True)
        state = delivery_state(snapshot)
        self.assertEqual(state['pause_remaining'], 600)
        self.assertFalse(budget_status(state, now=999999)['expired'])
        with patch('poc.workflow.time.time', return_value=10000):
            result = self.g.invoke(Command(resume={'action': 'resume', 'actor': 'Andy'}), self.cfg)
        self.assertEqual(result['deadline'], 10600)
        self.assertEqual(result['phase'], 'reviewed-and-ready')

    def test_uncertain_reconciliation_policy_keeps_original_deadline_explicit(self):
        state = {'budget_policy': PAUSE_POLICY, 'deadline': 100}
        status = budget_status(state, now=200)
        self.assertTrue(status['expired']); self.assertFalse(status['paused'])
        self.assertIn('Uncertain-effect reconciliation retains the original deadline', status['human_waiting_policy'])

    def test_interpreter_missing_at_approval_has_no_implementation_or_decision(self):
        brief = {**BRIEF, 'check_command': ['./missing/python3', '-m', 'unittest']}
        reference = self.artifacts.publish('briefs', 'brief', brief, supersedes=self.brief)
        self.initial['brief_ref'] = reference
        self.g.invoke(self.initial, self.cfg)
        with self.assertRaisesRegex(ValueError, 'missing or not executable'):
            self.g.invoke(Command(resume={'action': 'approve', 'actor': 'Andy', 'brief_ref': reference}), self.cfg)
        self.assertEqual(self.h.calls, 0)
        self.assertEqual(list((self.artifacts.root/'decisions').glob('*.json')), [])

    def test_legacy_expired_resume_records_no_decision_and_stop_still_closes(self):
        self.h.implement = lambda s: {'status': 'permission_required', 'reason': 'Sign in separately'}
        with patch('poc.work_lifecycle.time.time', return_value=100):
            self.g.invoke(self.initial, self.cfg); self.approve()
        before = len(self.artifacts.revisions('decisions', 'delivery-implement-0-0'))
        with patch('poc.workflow.time.time', return_value=10000), self.assertRaisesRegex(ArtifactError, 'expired'):
            self.g.invoke(Command(resume={'action': 'resume', 'actor': 'Andy'}), self.cfg)
        self.assertEqual(before, len(self.artifacts.revisions('decisions', 'delivery-implement-0-0')))
        # CLI pre-validates before submitting a Command, avoiding persisted resume writes.
