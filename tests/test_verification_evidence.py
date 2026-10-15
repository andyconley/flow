"""Frozen-behavior regression and adversarial gates; no live-model claims."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import ModuleType
from unittest.mock import patch
from argparse import Namespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
import openhands_flow as flow
import runstate
import verification as v
from delivery_control import run_lock

FIXTURES = Path(__file__).parent / 'fixtures/verification-evaluation/v1/cases.json'
REPO = Path(__file__).resolve().parents[1]


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.directory = self.root / '.flow/runs/checks'
        self.args = Namespace(project_root=self.root, work_id='checks', stage=None, disposition=[])
        self.case = json.loads(FIXTURES.read_text())['cases'][0]
        self.prepare()

    def prepare(self, case=None):
        case = case or self.case
        for path, content in case['files'].items():
            (self.root / path).write_text(content)
        flow.initialize(self.args)
        for name in ('requirements.md', 'acceptance-criteria.md'):
            (self.directory / name).write_text(case['task'])
        self.args.stage = 'define'
        flow.approve(self.args)
        flow._transition(self.root, 'checks', 'start-plan')
        for name in ('plan.md', 'handoff.md', 'validation-plan.md'):
            (self.directory / name).write_text(case['task'])
        (self.directory / 'verification-plan.json').write_text(json.dumps({
            'schema_version': 1, 'repair_limit': 2, 'evaluation_inputs': ['check.py'],
            'checks': [{'id': 'behavior', 'criterion': case['criterion'], 'argv': [sys.executable, 'check.py']}]}))
        self.args.stage = 'plan'
        flow.approve(self.args)
        flow._transition(self.root, 'checks', 'start-implementation')
        for name in ('implementation-evidence.md', 'handback.md'):
            (self.directory / name).write_text('Actual verification is linked in verification.json')

    def capture(self, session='producer'):
        args = Namespace(**{**vars(self.args), 'check_id': 'behavior', 'session_id': session,
                            'assignment_id': 'bounded-assignment', 'environment': 'Python test fixture', 'timeout': 3})
        return flow.check(args)

    def fix(self):
        (self.root / 'subject.py').write_text('def add(a, b):\n    return a + b\n')

    def handoff(self):
        self.args.stage = 'implement'
        return flow.approve(self.args)

    def repair(self):
        proof = self.directory / 'failure.txt'
        proof.write_text('Check failure / review finding; preserve the approved behavior.')
        return flow.repair(Namespace(**{**vars(self.args), 'check_id': 'behavior', 'specialist': 'lead-developer',
                        'scope': 'fix only the failed behavior', 'reason': 'frozen check failure',
                        'failure_evidence': proof.relative_to(self.root).as_posix()}))

    def test_specialist_output_contract_excludes_host_evidence_but_gate_requires_it(self):
        run = runstate.status('checks', self.root)
        prompt = flow._stage_prompt(self.root, self.directory, run, 'implement', 'frozen task')
        output_section = prompt.split('Produce the following durable stage outputs,')[1].split('Flow owns lifecycle approvals;')[0]
        self.assertIn('implementation-evidence.md', output_section)
        self.assertIn('handback.md', output_section)
        self.assertNotIn('verification.json', output_section)
        self.assertIn('Specialists must not create, edit, or synthesize verification.json', prompt)
        self.assertNotIn('verification', flow.specialist_outputs(run, 'implement'))
        self.assertIn('verification', flow.stage_outputs(run, 'implement'))
        self.assertIn('verification_plan', flow.specialist_outputs(run, 'plan'))
        # Ownership wording must not weaken the real acceptance gate.
        with self.assertRaisesRegex(flow.RuntimeConfigurationError, 'missing, failed or stale'):
            self.handoff()
        for relative in ('scaffolds/default/commands/flow-implement.md',
                         'scaffolds/default/templates/implementation-handoff.md',
                         'scaffolds/default/templates/agent-brief.md'):
            content = (REPO / relative).read_text()
            self.assertIn('verification.json', content)
            self.assertTrue('must not' in content or 'never create' in content)

    def test_frozen_fixture_and_measures_unchanged(self):
        freeze = json.loads((REPO / 'docs/evidence/verification-v1/freeze.json').read_text())
        for path, expected in freeze['files'].items():
            self.assertEqual(hashlib.sha256((REPO / path).read_bytes()).hexdigest(), expected)

    def test_successful_handoff_seals_exact_evidence_and_logs(self):
        self.fix()
        self.assertEqual(self.capture()['status'], 'passed')
        out = self.handoff()
        self.assertIn('verification', out['approved_artifact_digests'])
        (self.directory / 'review.md').write_text('Independent behavior review passed')
        self.args.stage = 'review'
        self.assertEqual(flow.approve(self.args)['state'], 'review_accepted')
        self.assertTrue(runstate.verify('checks', self.root)[0])

    def test_nonempty_markdown_cannot_replace_check_evidence_or_direct_transition(self):
        with self.assertRaisesRegex(ValueError, 'verification'):
            self.handoff()
        ok, _, errors = runstate.apply_transition('checks', 'mark-handback-ready', root=self.root)
        self.assertFalse(ok)
        self.assertTrue(errors)
        self.assertEqual(v.report(self.root, runstate.status('checks', self.root))['handoff_rejections'], 2)
        self.assertTrue(runstate.verify('checks', self.root)[0])

    def test_tracked_dirty_untracked_deleted_and_mode_changes_invalidate(self):
        self.fix()
        subprocess.run(['git', '-C', str(self.root), 'add', 'subject.py', 'check.py'], check=True)
        for mutate, restore in (
            (lambda: (self.root / 'subject.py').write_text('bad'), self.fix),
            (lambda: (self.root / 'new-input').write_text('untracked'), lambda: (self.root / 'new-input').unlink()),
            (lambda: (self.root / 'subject.py').unlink(), self.fix),
            (lambda: (self.root / 'subject.py').chmod(0o755), lambda: (self.root / 'subject.py').chmod(0o644))):
            self.capture()
            mutate()
            with self.assertRaisesRegex(ValueError, 'stale'):
                self.handoff()
            restore()
        self.capture()
        self.handoff()

    def test_change_after_entering_review_blocks_acceptance_and_verify(self):
        self.fix(); self.capture(); self.handoff()
        (self.root / 'subject.py').write_text('def add(a,b): return 0\n')
        (self.directory / 'review.md').write_text('looks fine')
        self.args.stage = 'review'
        with self.assertRaisesRegex(ValueError, 'stale'):
            flow.approve(self.args)
        self.assertFalse(runstate.verify('checks', self.root)[0])

    def test_test_weakening_pass_is_rejected_without_equivalence_review(self):
        (self.root / 'check.py').write_text('assert True\n')
        self.assertEqual(self.capture()['status'], 'passed')
        with self.assertRaisesRegex(ValueError, 'independent equivalence review'):
            self.handoff()
        run = runstate.status('checks', self.root)
        with self.assertRaisesRegex(ValueError, 'separate user approval'):
            v.review_change(self.root, run, 'reviewer', 'independent', 'lower the bar',
                            '.flow/runs/checks/handback.md', 'material')
        with self.assertRaisesRegex(ValueError, 'independent'):
            v.review_change(self.root, run, 'same producer', 'producer', 'equivalent',
                            '.flow/runs/checks/handback.md', 'equivalent')

    def test_legitimate_harness_repair_preserves_criteria_and_needs_review(self):
        self.temp.cleanup(); self.setUpForCase(json.loads(FIXTURES.read_text())['cases'][3])
        criteria = (self.directory / 'acceptance-criteria.md').read_bytes()
        failure = self.capture()
        self.assertNotEqual(failure['exit_code'], 0)
        self.repair()
        (self.root / 'check.py').write_text('from subject import add\nassert add(2, 3) == 5\n')
        self.fix(); success = self.capture()
        with self.assertRaisesRegex(ValueError, 'equivalence review'):
            self.handoff()
        proof = self.directory / 'repair-proof.md'
        proof.write_text(f"Import misspelling only; assertion unchanged. Before: {failure['log']}; after: {success['log']}")
        v.review_change(self.root, runstate.status('checks', self.root), 'quality-reviewer', 'separate-review',
                        'Corrects module spelling while retaining exact addition assertion', proof.relative_to(self.root).as_posix(), 'equivalent')
        self.handoff()
        self.assertEqual((self.directory / 'acceptance-criteria.md').read_bytes(), criteria)

    def setUpForCase(self, case):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.directory = self.root / '.flow/runs/checks'
        self.args = Namespace(project_root=self.root, work_id='checks', stage=None, disposition=[])
        self.prepare(case)

    def test_repair_budget_survives_fresh_process_session_and_pause_resume(self):
        self.capture()
        with self.assertRaisesRegex(ValueError, 'targeted repair'):
            self.capture('new-unallocated-session')
        for index in range(2):
            self.repair()
            flow._transition(self.root, 'checks', 'pause')
            flow._transition(self.root, 'checks', 'resume')
            command = [sys.executable, str(REPO / 'cli/flow.py'), 'workflow', 'check', 'checks',
                       '--project-root', str(self.root), '--check-id', 'behavior', '--session-id', f'fresh-{index}',
                       '--assignment-id', 'repair', '--environment', 'fixture', '--json']
            completed = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        run = runstate.status('checks', self.root)
        self.assertEqual(run['state'], 'blocked')
        self.assertEqual(len(run['repair_attempts']), 2)
        flow._transition(self.root, 'checks', 'resume')
        self.assertEqual(self.repair()['status'], 'blocked')
        self.assertEqual(len(runstate.status('checks', self.root)['repair_attempts']), 2)
        self.assertTrue(runstate.verify('checks', self.root)[0])

    def test_counter_reset_cannot_silently_discard_history(self):
        self.capture(); self.repair()
        run = runstate.status('checks', self.root)
        run['repair_attempts'] = []
        runstate._write_run('checks', run, self.root)
        with self.assertRaisesRegex(ValueError, 'history'):
            flow._run(self.root, 'checks')

    def test_criteria_edits_and_validation_plan_edits_are_still_blocked(self):
        for filename in ('acceptance-criteria.md', 'validation-plan.md', 'verification-plan.json'):
            path = self.directory / filename; before = path.read_bytes()
            path.write_bytes(before + b'weakened')
            with self.assertRaisesRegex(ValueError, 'changed after approval'):
                flow._run(self.root, 'checks')
            path.write_bytes(before)

    def test_log_tampering_and_symlink_cannot_authorize(self):
        self.fix(); result = self.capture()
        path = self.root / result['log']['path']
        original = path.read_bytes(); path.write_bytes(b'forged')
        with self.assertRaisesRegex(ValueError, 'log changed'):
            self.handoff()
        path.write_bytes(original); path.unlink(); path.symlink_to(self.directory / 'handback.md')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.handoff()

    def test_mid_check_workspace_mutation_never_counts_as_pass(self):
        self.fix()
        # The approved command itself changes another workspace input.
        (self.root / 'check.py').write_text("from pathlib import Path\nPath('subject.py').write_text('changed')\n")
        self.assertEqual(self.capture()['status'], 'failed')

    def test_empty_or_partial_results_cannot_authorize(self):
        self.fix(); self.capture()
        path = self.directory / 'verification.json'
        record = json.loads(path.read_text()); record['checks'][0]['environment'] = ''
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'environment'):
            self.handoff()

    def test_reporting_keeps_missing_cost_tokens_and_review_time_unknown(self):
        self.capture(); self.repair()
        report = v.report(self.root, runstate.status('checks', self.root))
        self.assertEqual(report['repair_attempts'], 1)
        self.assertEqual(report['failed_checks'], 1)
        for key in ('actual_billed_cost', 'sdk_estimated_cost', 'aggregate_generated_tokens', 'human_review_seconds'):
            self.assertIsNone(report[key])
        rows = [{'work_id': 'checks', 'sdk_estimated_cost': 1.25}, {'work_id': 'other', 'sdk_estimated_cost': 99}]
        joined = v.report(self.root, runstate.status('checks', self.root), rows)
        self.assertEqual(joined['observed_sdk_estimated_cost'], 1.25)
        self.assertIsNone(joined['sdk_estimated_cost'])
        rows.append({'work_id': 'checks', 'sdk_estimated_cost': None})
        self.assertIsNone(v.report(self.root, runstate.status('checks', self.root), rows)['observed_sdk_estimated_cost'])

    def test_historical_workflow_is_not_silently_upgraded(self):
        run = runstate.status('checks', self.root); run.pop('verification_revision')
        runstate._write_run('checks', run, self.root)
        with self.assertRaisesRegex(ValueError, 'revision differs'):
            flow._run(self.root, 'checks')
        # An actual pre-increment workflow has no marker in its creation event.
        history = self.directory / 'events.jsonl'
        events = [json.loads(line) for line in history.read_text().splitlines()]
        events[0].pop('verification_revision')
        history.write_text(''.join(json.dumps(e) + '\n' for e in events))
        self.assertEqual(flow.show(self.args)['verification_status'], 'historical_unbound')

    def test_timeout_is_failure_and_cannot_authorize(self):
        (self.root / 'check.py').write_text('import time\ntime.sleep(30)\n')
        run = runstate.status('checks', self.root)
        result = v.capture(self.root, run, 'behavior', 'producer', 'assignment', 'fixture', timeout=0.05)
        self.assertEqual(result['exit_code'], 124)
        with self.assertRaisesRegex(ValueError, 'failed or stale'):
            self.handoff()

    def test_equivalence_review_is_invalidated_by_another_test_change(self):
        self.fix()
        (self.root / 'check.py').write_text('from subject import add\nassert add(2, 3) == 5\n# reviewed\n')
        self.capture()
        run = runstate.status('checks', self.root)
        v.review_change(self.root, run, 'reviewer', 'review-session', 'comment only',
                        '.flow/runs/checks/handback.md', 'equivalent')
        (self.root / 'check.py').write_text('assert True\n')
        self.capture()
        with self.assertRaisesRegex(ValueError, 'equivalence review'):
            self.handoff()

    def test_head_change_is_detected(self):
        self.fix(); self.capture()
        subprocess.run(['git', '-C', str(self.root), 'add', 'subject.py', 'check.py'], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                        'commit', '-qm', 'fixture'], check=True)
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.handoff()
        self.capture(); self.handoff()

    def test_repair_requires_a_recorded_check_and_narrowed_assignment(self):
        with self.assertRaisesRegex(ValueError, 'record the check'):
            self.repair()
        self.capture()
        with self.assertRaisesRegex(ValueError, 'narrowed_scope'):
            flow._transition(self.root, 'checks', 'request-refinement', dispositions={
                'failed_check': 'behavior', 'specialist': 'lead-developer'})

    def test_check_inside_active_sdk_run_fails_promptly_instead_of_deadlocking(self):
        with run_lock(self.directory):
            result = subprocess.run([sys.executable, str(REPO / 'cli/flow.py'), 'workflow', 'check', 'checks',
                '--project-root', str(self.root), '--check-id', 'behavior', '--session-id', 'worker',
                '--assignment-id', 'nested', '--environment', 'fixture', '--json'],
                capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 1)
        self.assertIn('workflow busy', result.stdout)
        self.assertFalse((self.directory / 'verification.json').exists())

    def test_lost_result_cannot_reuse_a_repair_allocation(self):
        self.capture()
        self.repair()
        before = v.workspace(self.root)
        with patch('verification.workspace', side_effect=[before, RuntimeError('lost result')]):
            with self.assertRaisesRegex(RuntimeError, 'lost result'):
                self.capture('crashed-session')
        run = runstate.status('checks', self.root)
        pending = v.latest(v.read_record(self.root, run))['behavior']
        self.assertEqual(pending['status'], 'incomplete')
        self.assertIsNone(pending['exit_code'])
        summary = v.report(self.root, run)
        self.assertIsNone(summary['check_elapsed_seconds'])
        self.assertEqual(summary['failed_checks'], 1)
        self.assertEqual(summary['incomplete_checks'], 1)
        with self.assertRaisesRegex(ValueError, 'targeted repair'):
            self.capture('fresh-session')
        self.repair()
        self.fix()
        self.capture('recovery-session')
        self.handoff()
        self.assertEqual(len(runstate.status('checks', self.root)['repair_attempts']), 2)

    def test_same_timestamp_rejections_remain_distinct_occurrences(self):
        with patch.object(flow.runstate, '_now', return_value='2026-10-15T00:00:00Z'):
            for _ in range(2):
                with self.assertRaisesRegex(flow.RuntimeConfigurationError, 'missing, failed or stale'):
                    self.handoff()
        run = runstate.status('checks', self.root)
        self.assertEqual(v.report(self.root, run)['handoff_rejections'], 2)

    def test_repair_commit_recovers_missing_journal_without_refunding_allocation(self):
        # Discovery may reload sys.modules["runstate"]; inject into Flow's actual
        # executing module, not a newly imported object with the same name.
        self.capture()
        detached = ModuleType('runstate')
        detached._append_event = lambda *args, **kwargs: None
        with patch.dict(sys.modules, {'runstate': detached}), patch.object(
                flow.runstate, '_append_event', side_effect=OSError('journal unavailable')):
            with self.assertRaisesRegex(OSError, 'journal unavailable'):
                self.repair()
        _, run = flow._run(self.root, 'checks')
        self.assertEqual(len(run['repair_attempts']), 1)
        self.assertEqual(sum('repair_attempt' in e for e in runstate.history('checks', self.root)), 1)
        # A new process must recover the same committed allowance.
        result = subprocess.run([sys.executable, str(REPO / 'cli/flow.py'), 'workflow', 'status', 'checks',
            '--project-root', str(self.root), '--json'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.capture('resumed')
        self.repair()
        self.capture('second-repair')
        self.assertEqual(self.repair()['status'], 'blocked')
        self.assertEqual(sum('repair_attempt' in e for e in runstate.history('checks', self.root)), 2)

    def test_plan_commit_recovers_missing_journal_and_keeps_approved_baseline(self):
        # Recreate the fixture through planning, stopping before plan approval.
        # Re-entering approval in an isolated new work id avoids changing criteria.
        self.args.work_id = 'plan-crash'
        flow.initialize(self.args)
        directory = self.root / '.flow/runs/plan-crash'
        for name in ('requirements.md', 'acceptance-criteria.md', 'plan.md', 'handoff.md',
                     'validation-plan.md', 'verification-plan.json'):
            (directory / name).write_bytes((self.directory / name).read_bytes())
        self.args.stage = 'define'
        flow.approve(self.args)
        flow._transition(self.root, 'plan-crash', 'start-plan')
        self.args.stage = 'plan'
        detached = ModuleType('runstate')
        detached._append_event = lambda *args, **kwargs: None
        with patch.dict(sys.modules, {'runstate': detached}), patch.object(
                flow.runstate, '_append_event', side_effect=OSError('journal unavailable')):
            with self.assertRaisesRegex(OSError, 'journal unavailable'):
                flow.approve(self.args)
        _, run = flow._run(self.root, 'plan-crash')
        self.assertEqual(run['state'], 'plan_approved')
        baseline = run['evaluation_baseline']
        flow._transition(self.root, 'plan-crash', 'start-implementation')
        _, run = flow._run(self.root, 'plan-crash')
        self.assertEqual(run['evaluation_baseline'], baseline)
        self.assertEqual(sum(e['event'] == 'approve-plan' for e in runstate.history('plan-crash', self.root)), 1)

    def test_plan_read_rechecks_the_exact_approved_bytes_before_execution(self):
        run = runstate.status('checks', self.root)
        path = self.directory / 'verification-plan.json'
        plan = json.loads(path.read_text())
        plan['checks'][0]['argv'] = [sys.executable, '-c', "open('unapproved-command', 'w').write('ran')"]
        path.write_text(json.dumps(plan))
        with self.assertRaisesRegex(ValueError, 'changed after approval'):
            v.capture(self.root, run, 'behavior', 'producer', 'assignment', 'fixture')
        self.assertFalse((self.root / 'unapproved-command').exists())

    def test_repeated_lost_results_exhaust_the_same_persistent_budget(self):
        self.capture()
        for index in range(2):
            self.repair()
            before = v.workspace(self.root)
            with patch('verification.workspace', side_effect=[before, RuntimeError('lost result')]):
                with self.assertRaisesRegex(RuntimeError, 'lost result'):
                    self.capture(f'crashed-session-{index}')
        with self.assertRaisesRegex(ValueError, 'targeted repair'):
            self.capture('third-session')
        self.assertEqual(self.repair()['status'], 'blocked')
        run = runstate.status('checks', self.root)
        self.assertEqual(len(run['repair_attempts']), 2)
        self.assertEqual(len(v.read_record(self.root, run)['checks']), 3)
