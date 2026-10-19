"""Production CLI dispatch, mock SDK only; zero live generation."""
import contextlib
import asyncio
import unittest
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sys
import subprocess
import shutil
from types import SimpleNamespace
from unittest.mock import patch

from tests import test_verification_evidence as evidence_tests
import flow as cli
import openhands_flow as workflow
import openhands_runtime
import review_output
import runstate
import verification as v

SAVED = json.loads((Path(__file__).parent / 'fixtures/review-reliability/saved-responses.json').read_text())


class ReviewReliabilityTests(unittest.TestCase):
    setUp = evidence_tests.EvidenceTests.setUp
    setUpForCase = evidence_tests.EvidenceTests.setUpForCase
    prepare = evidence_tests.EvidenceTests.prepare
    capture = evidence_tests.EvidenceTests.capture
    fix = evidence_tests.EvidenceTests.fix
    repair = evidence_tests.EvidenceTests.repair
    handoff = evidence_tests.EvidenceTests.handoff

    def command(self, *args):
        out = io.StringIO()
        with patch.object(sys, 'argv', ['flow', 'workflow', *args, '--project-root', str(self.root), '--json']), contextlib.redirect_stdout(out):
            code = cli.main()
        return code, json.loads(out.getvalue())

    def configure(self):
        (self.root / ".flow/runtime.toml").write_text('default_profile="test"\n[profiles.test]\nkind="local"\nmodel="ollama_chat/test"\nbase_url="http://127.0.0.1:11434"\n')
        (self.root / "review-task.md").write_text("Read-only review against approved addition criteria.")

    def execute_review(self, artifact=None, response='ACCEPT', new=False, waiting=False, confirm=False, hang=False):
        from openhands.sdk.conversation.state import ConversationExecutionStatus as Status
        (self.root / '.flow/runtime.toml').write_text('default_profile="test"\n[profiles.test]\nkind="local"\nmodel="ollama_chat/test"\nbase_url="http://127.0.0.1:11434"\n')
        (self.root / 'review-task.md').write_text('Read-only review against approved addition criteria.')
        stat = SimpleNamespace(get_combined_metrics=lambda: SimpleNamespace(model_dump=lambda **_: {}), model_dump=lambda **_: {'usage_to_metrics': {}})
        fake = SimpleNamespace(state=SimpleNamespace(execution_status=Status.WAITING_FOR_CONFIRMATION if confirm else Status.FINISHED, active_branch=lambda: []), conversation_stats=stat, send_message=lambda _: None)
        def run():
            if artifact is not None:
                (self.directory / 'review.md').write_text(artifact)
            fake.state.execution_status = Status.WAITING_FOR_CONFIRMATION if waiting else Status.FINISHED
            callback(SimpleNamespace(source='agent', tool_name='finish', action=SimpleNamespace(message=response)))
        fake.run = run
        stopped = None
        async def arun():
            nonlocal stopped
            if hang:
                stopped = asyncio.Event()
                await asyncio.wait_for(stopped.wait(), 2)
                fake.state.execution_status = Status.PAUSED
            else:
                run()
        fake.arun = arun
        def interrupt():
            self.interrupted = True
            stopped.set()
        fake.interrupt = interrupt
        @contextlib.contextmanager
        def conversation(selection, root, store, identity, progress):
            nonlocal callback
            callback = progress
            yield fake
        callback = None
        args = ['execute', 'checks', '--stage', 'review', '--task-file', 'review-task.md']
        if new: args.append('--new-session')
        if confirm: args.append('--confirm-pending')
        with patch.object(openhands_runtime, 'probe', return_value={'ready': True}), patch.object(openhands_runtime, 'conversation', conversation), patch('openhands.sdk.conversation.state.ConversationState.get_unmatched_actions', return_value=[]):
            return self.command(*args)

    def repair_review(self):
        identifier = runstate.status('checks', self.root)['review_outputs'][-1]['id']
        return self.command('repair', 'checks', '--check-id', 'review-output', '--specialist', 'quality-reviewer', '--scope', 'Write the missing explicit independent review artifact; do not edit implementation or criteria', '--reason', 'Incomplete review output', '--failure-evidence', f'.flow/runs/checks/review-outcomes/{identifier}.json')

    def ready(self):
        self.configure(); self.fix(); self.capture()

    def test_saved_failures_nonzero_no_approval_and_two_repairs_survive_resume(self):
        self.ready()
        for n, saved in enumerate(SAVED.values()):
            if n:
                self.assertEqual(self.repair_review()[0], 0)
                self.command('status', 'checks')
                workflow._transition(self.root, 'checks', 'pause'); workflow._transition(self.root, 'checks', 'resume')
            code, result = self.execute_review(response=saved['response'], new=n > 0)
            self.assertEqual(code, 1, result)
            self.assertEqual(result['session']['status'], 'incomplete_review')
            self.assertFalse(v.read_record(self.root, runstate.status('checks', self.root))['test_change_reviews'])
            self.assertEqual(runstate.status('checks', self.root)['state'], 'implementing')
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                self.handoff()
        identifier = runstate.status('checks', self.root)['review_outputs'][-1]['id']
        fresh = subprocess.run([sys.executable, cli.__file__, 'workflow', 'repair', 'checks', '--project-root', str(self.root), '--json', '--check-id', 'review-output', '--specialist', 'quality-reviewer', '--scope', 'Only complete review output', '--reason', 'Incomplete review', '--failure-evidence', f'.flow/runs/checks/review-outcomes/{identifier}.json'], capture_output=True, text=True)
        code, result = fresh.returncode, json.loads(fresh.stdout)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(code, 1)
        workflow._transition(self.root, 'checks', 'resume')
        self.assertEqual(self.execute_review(new=True)[0], 1)
        self.assertEqual(len(runstate.status('checks', self.root)['repair_attempts']), 2)

    def test_valid_review_can_repair_missing_artifact_without_approving_itself(self):
        self.ready()
        self.assertEqual(self.execute_review()[0], 1)
        self.assertEqual(self.repair_review()[0], 0)
        code, result = self.execute_review('Verdict: ACCEPT\nVerified approved addition behavior.\n', new=True)
        self.assertEqual(code, 0, result)
        self.assertEqual(runstate.status('checks', self.root)['state'], 'implementing')
        self.handoff()
        self.assertEqual(self.command('approve', 'checks', '--stage', 'review')[0], 0)
        self.assertEqual(runstate.status('checks', self.root)['state'], 'review_accepted')

    def test_reject_cannot_bypass_via_direct_lifecycle_transition(self):
        self.ready(); self.handoff()
        code, result = self.execute_review('Verdict: REJECT\nImplementation violates scope.\n')
        self.assertEqual(code, 0, result)  # complete review, not acceptance
        ok, _, errors = runstate.apply_transition('checks', 'accept-review', root=self.root, artifacts={'review': '.flow/runs/checks/review.md'})
        self.assertFalse(ok); self.assertIn('rejected', ' '.join(errors))
        self.assertEqual(self.command('approve', 'checks', '--stage', 'review')[0], 1)

    def test_confirmation_resume_reuses_attempt_and_deadline(self):
        self.ready()
        self.assertEqual(self.execute_review(waiting=True)[0], 0)
        before = runstate.status('checks', self.root)['review_outputs'][0]
        code, result = self.execute_review('Verdict: ACCEPT\nVerified addition.\n', confirm=True)
        self.assertEqual(code, 0, result)
        outputs = runstate.status('checks', self.root)['review_outputs']
        self.assertEqual(len(outputs), 1); self.assertEqual(outputs[0]['id'], before['id'])
        self.assertEqual(outputs[0]['deadline'], before['deadline'])

    def test_equivalent_import_repair_receipt_and_invalid_bindings(self):
        self.temp.cleanup(); self.setUpForCase(json.loads((Path(__file__).parent/'fixtures/verification-evaluation/v1/cases.json').read_text())['cases'][3])
        self.configure(); self.capture(); self.repair(); self.fix()
        (self.root/'check.py').write_text('from subject import add\nassert add(2, 3) == 5\n');self.capture()
        code, result = self.execute_review('Verdict: ACCEPT\nTest equivalence: EQUIVALENT\nImport spelling repaired; exact addition assertion retained. Implementation now satisfies approved addition criterion.\n')
        self.assertEqual(code, 0, result)
        session=result['session']['conversation_id']
        base=['review-test-change','checks','--reviewer','quality-reviewer','--rationale','Import-only repair with assertion retained','--evidence','.flow/runs/checks/review.md','--disposition','equivalent']
        self.assertEqual(self.command(*base,'--reviewer-session-id','producer')[0],1)
        self.assertEqual(self.command(*base,'--reviewer-session-id',session)[0],0)
        artifact=self.directory/'review.md';content=artifact.read_text();artifact.write_text(content+'altered\n')
        self.assertEqual(self.command(*base,'--reviewer-session-id',session)[0],1)
        artifact.write_text(content)
        (self.root/'subject.py').write_text('def add(a,b):\n    return 5\n')
        self.assertEqual(self.command(*base,'--reviewer-session-id',session)[0],1)
        self.fix()
        self.handoff()
        self.assertEqual(self.command('approve','checks','--stage','review')[0],0)

    def test_changed_assertions_material_review_never_mints_receipt(self):
        self.ready(); (self.root/'check.py').write_text('assert True\n');self.capture()
        code,result=self.execute_review('Verdict: REJECT\nTest equivalence: MATERIAL\nAddition assertion was deleted; separate user approval required.\n')
        self.assertEqual(code,0,result)
        self.assertEqual(self.command('review-test-change','checks','--reviewer','quality-reviewer','--reviewer-session-id',result['session']['conversation_id'],'--rationale','assertion deleted','--evidence','.flow/runs/checks/review.md','--disposition','equivalent')[0],1)
        with self.assertRaisesRegex(ValueError,'equivalence'):
            self.handoff()

    def test_deadline_and_stale_artifact_cannot_reset_with_new_session(self):
        self.ready(); (self.directory/'review.md').write_text('Verdict: ACCEPT\nOld output.\n')
        self.assertEqual(self.execute_review()[0],1)
        self.assertEqual(self.repair_review()[0],0)
        run=runstate.status('checks',self.root)
        run['review_outputs'][0]['deadline']='2000-01-01T00:00:00+00:00'
        runstate._write_run('checks',run,self.root)
        code,result=self.execute_review(new=True)
        self.assertEqual(code,1);self.assertIn('deadline',result['reason'])

    def test_sdk_interrupt_at_shared_deadline_does_not_accept_late_output(self):
        self.ready(); self.interrupted = False
        run_session = workflow._run_session
        def expire_running_review(session, review_result):
            # Exercise interruption of a running SDK, not variable fixture setup latency.
            review_result['deadline'] = (datetime.now(timezone.utc) + timedelta(milliseconds=50)).isoformat()
            return run_session(session, review_result)
        with patch.object(workflow, '_run_session', side_effect=expire_running_review):
            code, result = self.execute_review(hang=True)
        self.assertEqual(code, 1, result)
        self.assertTrue(self.interrupted)
        self.assertEqual(result['session']['status'], 'incomplete_review')
        self.assertIn('deadline', result['session']['review_output']['reason'])
        self.assertEqual(self.repair_review()[0], 1)

    def test_unusable_artifact_and_disposition_only_are_incomplete(self):
        self.ready()
        self.assertEqual(self.execute_review(SAVED['repetitive-output']['response'])[0], 1)
        self.assertEqual(self.repair_review()[0], 0)
        self.assertEqual(self.execute_review('Verdict: ACCEPT\n', new=True)[0], 1)
        self.assertEqual(self.repair_review()[0], 0)
        self.assertEqual(self.execute_review('Verdict: ACCEPT\nVerdict: REJECT\nContradictory dispositions.\n', new=True)[0], 1)

    def test_complete_cli_lifecycle_with_independent_equivalent_repair(self):
        # Restart only this disposable test run; exercise every host command via
        # the shipped CLI parser/dispatch, including check and receipt commands.
        shutil.rmtree(self.directory)
        self.configure()
        (self.root/'subject.py').write_text('def add(a,b):\n    return a - b\n')
        (self.root/'check.py').write_text('from subjec import add\nassert add(2, 3) == 5\n')
        self.assertEqual(self.command('init','checks')[0],0)
        for name in ['requirements.md','acceptance-criteria.md']:
            (self.directory/name).write_text('Addition: add(2,3)=5. Retain addition assertions; equivalent import repair allowed. Correct implementation logic to satisfy addition.')
        self.assertEqual(self.command('approve','checks','--stage','define')[0],0)
        # Standard lifecycle command enters planning; no SDK needed to supply
        # operator-reviewed fixture plan artifacts.
        with patch.object(sys,'argv',['flow','run','transition','checks','start-plan']), contextlib.chdir(self.root), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(),0)
        for name in ['plan.md','handoff.md','validation-plan.md']:
            (self.directory/name).write_text('Fix addition and import; retain exact assertion and obtain independent equivalence review.')
        (self.directory/'verification-plan.json').write_text(json.dumps({'schema_version':1,'repair_limit':2,'evaluation_inputs':['check.py'],'checks':[{'id':'behavior','criterion':'addition','argv':[sys.executable,'check.py']}]}))
        self.assertEqual(self.command('approve','checks','--stage','plan')[0],0)
        with patch.object(sys,'argv',['flow','run','transition','checks','start-implementation']), contextlib.chdir(self.root), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(),0)
        for name in ['implementation-evidence.md','handback.md']:
            (self.directory/name).write_text('Before/after import repair; addition assertion retained; actual host checks in verification.json.')
        check=['check','checks','--check-id','behavior','--session-id','producer','--assignment-id','addition-repair','--environment','Python offline fixture','--timeout','3']
        self.assertEqual(self.command(*check)[0],1)
        (self.directory/'failure.txt').write_text('ModuleNotFoundError in recorded host check.')
        self.assertEqual(self.command('repair','checks','--check-id','behavior','--specialist','lead-developer','--scope','Fix import spelling and addition without weakening assertion','--reason','Recorded import failure','--failure-evidence','.flow/runs/checks/failure.txt')[0],0)
        self.fix();(self.root/'check.py').write_text('from subject import add\nassert add(2, 3) == 5\n')
        self.assertEqual(self.command(*check)[0],0)
        code,result=self.execute_review('Verdict: ACCEPT\nTest equivalence: EQUIVALENT\nImport spelling only in test; exact addition assertion retained. Implementation fulfills approved addition criterion.\n')
        self.assertEqual(code,0,result)
        self.assertEqual(self.command('review-test-change','checks','--reviewer','quality-reviewer','--reviewer-session-id',result['session']['conversation_id'],'--rationale','Exact assertion retained after import spelling repair','--evidence','.flow/runs/checks/review.md','--disposition','equivalent')[0],0)
        self.assertEqual(self.command('approve','checks','--stage','implement')[0],0)
        self.assertEqual(self.command('approve','checks','--stage','review')[0],0)
        self.assertTrue(runstate.verify('checks',self.root)[0])

    def test_deadline_boundary_cannot_leave_complete_result_under_failed_session(self):
        self.ready()
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        with patch.object(review_output, 'timedelta', return_value=timedelta(seconds=1)), patch.object(workflow, 'datetime') as clock:
            clock.now.side_effect = [now, now + timedelta(seconds=2), now + timedelta(seconds=2)]
            code, result = self.execute_review('Verdict: ACCEPT\nVerified addition against approved assertions.\n')
        self.assertEqual(code, 1, result)
        self.assertEqual(result['session']['review_output']['status'], 'incomplete')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            self.handoff()
