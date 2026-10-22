"""Regression coverage for persisted research repair and verification honesty."""
import json
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from langgraph.types import Command
from poc.artifacts import Artifacts, ArtifactError, BRIEF_SCHEMA, validate_brief
from poc.glg import BriefChecker, outcome_exit, work_outcome
from poc.verification import preflight, evidence
import test_stage_coordination as stages

BRIEF = {'goal': 'goal', 'scope': ['scope'], 'acceptance_criteria': ['works'],
         'check_command': [sys.executable, '-c', 'print("ok")']}


class RepairTests(stages.StageCoordinationTests):
    def test_invalid_result_survives_restart_and_targeted_repair(self):
        calls = self.calls
        def shape(*args):
            calls.append('plan')
            return {'status': 'completed', 'content': 'expensive specialist findings',
                    'brief': {k: v for k, v in BRIEF.items() if k != 'check_command'}}
        self.h.shape = shape
        assignment = self.assign('plan')
        self.run_stage('plan', assignment)
        snapshot = self.graph.get_state(self.cfg)
        pause = snapshot.tasks[0].interrupts[0].value
        self.assertEqual(pause['kind'], 'repair-brief')
        self.assertIn('check_command', pause['errors'])
        self.assertEqual(self.artifacts.read(pause['research_ref'])['payload']['content'], 'expensive specialist findings')
        self.assertTrue((self.project / pause['repair_ref']['path']).is_file())
        # Reopen graph from persisted checkpoint; repeated resume cannot dispatch.
        from poc.work_lifecycle import build
        self.graph = build(Artifacts(self.project, 'stages'), self.h, lambda _: None).compile(checkpointer=self.saver)
        self.graph.invoke(None, self.cfg); self.graph.invoke(None, self.cfg)
        self.assertEqual(calls, ['plan'])
        repaired = self.artifacts.publish('briefs', 'brief', BRIEF)
        self.graph.invoke(Command(resume={'action': 'brief', 'brief_ref': repaired}), self.cfg)
        self.assertEqual(calls, ['plan'])
        state = self.graph.get_state(self.cfg).values
        self.assertEqual(state['brief_ref'], repaired)
        self.assertEqual(state['lifecycle_phase'], 'awaiting-approval')
        self.assertNotIn('approval_ref', state)
        with self.assertRaises(ArtifactError):
            self.graph.invoke(Command(resume={'action': 'approve', 'actor': 'Andy', 'brief_ref': {**repaired, 'revision': '0'*64}}), self.cfg)

    def test_repair_stop_is_terminal(self):
        self.h.shape = lambda *args: {'status': 'completed', 'content': 'research', 'brief': {}}
        assignment = self.assign('plan'); self.run_stage('plan', assignment)
        self.graph.invoke(Command(resume={'action': 'stop', 'actor': 'Andy', 'reason': 'stop'}), self.cfg)
        snapshot = self.graph.get_state(self.cfg)
        self.assertEqual(snapshot.values['lifecycle_phase'], 'stopped')
        self.assertFalse(snapshot.next)
        self.assertFalse(snapshot.tasks)

    def test_adapter_salvages_only_invalid_brief_and_retains_raw_output(self):
        from poc.goose_job import GooseJob
        output = self.root/'output.jsonl'
        report = {'outcome': 'completed', 'content': 'research retained', 'brief': {'goal': 'draft'}}
        output.write_text(json.dumps({'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': json.dumps(report)}]}}))
        state = {**self.graph.get_state(self.cfg).values, 'stage_authorization_ref': {'revision': 'a'*64}}
        job = GooseJob()
        rejected = {'status': 'blocked', 'exit': 0, 'quiescent': True, 'response_contract': {'passed': False}, 'output': str(output)}
        with patch.object(job, '_run', return_value=rejected):
            result = job.shape(state, 'plan', {})
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['brief'], {'goal': 'draft'})
        for bad in ({**report, 'content': ' '}, {**report, 'outcome': 'bogus'}):
            output.write_text(json.dumps({'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': json.dumps(bad)}]}}))
            with patch.object(job, '_run', return_value=rejected):
                self.assertEqual(job.shape(state, 'plan', {})['status'], 'blocked')
        output.unlink()
        self.assertIn('research retained', result['runtime']['output_content'])
        rejected['exit'] = 2
        with patch.object(job, '_run', return_value=rejected):
            self.assertEqual(job.shape(state, 'plan', {})['status'], 'blocked')

    def test_cli_repair_and_stop_preserve_outcomes(self):
        from poc import glg
        def shape(*args):
            self.calls.append('plan')
            return {'status': 'completed', 'content': 'retained research', 'brief': {'goal': 'incomplete'}}
        self.h.shape = shape
        def invoke(*tail):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = glg.main(['--project', str(self.project), '--work', 'cli', *tail])
            return code, json.loads(output.getvalue())
        with patch.object(glg, 'ROOT', self.root), patch.object(glg, 'NativeHarness', return_value=self.h):
            invoke('create', '--request', 'research')
            _, assigned = invoke('assign', '--stage', 'plan', '--question', 'plan')
            reference = assigned['stage_assignments']['plan']
            decision = self.root/'decision.json'
            decision.write_text(json.dumps({'action': 'run-stage', 'stage': 'plan', 'actor': 'Andy', 'assignment_ref': reference}))
            code, paused = invoke('resume', '--decision-file', str(decision))
            self.assertEqual((code, paused['outcome']), (2, 'brief-invalid'))
            self.assertEqual(invoke('resume')[0], 2)
            repaired = self.root/'brief.json'; repaired.write_text(json.dumps(BRIEF))
            code, shaped = invoke('brief', '--file', str(repaired))
            self.assertEqual((code, shaped['outcome']), (0, 'awaiting-approval'))
            self.assertEqual(self.calls, ['plan'])
            code, stopped = invoke('stop', '--actor', 'Andy')
            self.assertEqual((code, stopped['outcome']), (2, 'stopped'))


class VerificationTests(unittest.TestCase):
    def test_schema_and_runtime_validate_same_required_fields(self):
        for field in BRIEF_SCHEMA['required']:
            with self.subTest(field=field), self.assertRaises(ArtifactError):
                validate_brief({k: v for k, v in BRIEF.items() if k != field})
        planned = {k: v for k, v in BRIEF.items() if k != 'check_command'}
        validate_brief({**planned, 'verification_plan': 'Build then run acceptance tests'}, executable=False)
        with self.assertRaises(ArtifactError): validate_brief({**BRIEF, 'coverage': []})

    def test_minimal_path_and_prerequisites(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'PATH': ''}):
            self.assertTrue(preflight(directory, BRIEF)['ready'])
            readiness = preflight(directory, {**BRIEF, 'prerequisites': ['missing-browser']})
            self.assertFalse(readiness['ready']); self.assertIn('missing-browser', str(readiness['errors']))
            self.assertFalse(preflight(directory, {**BRIEF, 'check_command': ['missing-checker']})['ready'])
            self.assertEqual(readiness['cwd'], str(Path(directory).resolve()))

    def test_exit_two_timeout_and_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            artifacts = Artifacts(directory, 'checks')
            ref = artifacts.publish('briefs', 'brief', {**BRIEF, 'check_command': [sys.executable, '-c', 'raise SystemExit(2)']})
            state = {'brief_ref': ref, 'workspace': directory, 'deadline': time.time()+10}
            checker = BriefChecker(artifacts)
            result = checker.run_state(state)
            self.assertFalse(result['passed']); self.assertEqual(result['exit'], 2)
            self.assertEqual(result['brief_ref'], ref)
            self.assertEqual(result['check_scope'], 'smoke'); self.assertFalse(result['acceptance_proven'])
            self.assertEqual(len(result['uncovered']), 1)
            with patch('poc.glg.subprocess.run', side_effect=subprocess.TimeoutExpired('check', 10)):
                self.assertEqual(checker.run_state(state)['outcome'], 'timeout')
            mapped = {**BRIEF, 'check_scope': 'acceptance', 'coverage': [{'criterion': 'works', 'method': 'manual', 'evidence': 'Inspect browser rendering'}]}
            report = evidence(mapped, directory, ref, {'passed': True})
            self.assertFalse(report['acceptance_proven']); self.assertTrue(report['manual_review_required'])

    def test_draft_cli_persists_plan_but_rejects_implementation_approval(self):
        from poc import glg
        draft = {k: v for k, v in BRIEF.items() if k != 'check_command'}
        draft['verification_plan'] = 'Build fresh output then test all requirements'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); project = root/'project'; project.mkdir()
            source = root/'draft.json'; source.write_text(json.dumps(draft))
            args = ['--project', str(project), '--work', 'draft']
            output = io.StringIO()
            with patch.object(glg, 'ROOT', root), patch.object(glg, 'NativeHarness', return_value=object()):
                with contextlib.redirect_stdout(output):
                    self.assertEqual(glg.main([*args, 'create', '--brief-file', str(source)]), 0)
                proposed = json.loads(output.getvalue())['references']['brief_ref']
                self.assertEqual(Artifacts(project, 'draft').read(proposed)['payload'], draft)
                with self.assertRaises(SystemExit) as raised, contextlib.redirect_stderr(io.StringIO()):
                    glg.main([*args, 'approve', '--actor', 'Andy', '--revision', proposed['revision']])
                self.assertEqual(raised.exception.code, 2)

    def test_native_expired_budget_is_timeout_before_submission(self):
        from poc.goose_job import GooseJob
        from poc.contracts import task_input_digest
        with tempfile.TemporaryDirectory() as directory:
            state = {'workspace': directory, 'task': 'test', 'inputs': task_input_digest('test', directory), 'deadline': time.time()-1}
            result = GooseJob()._run_impl(state, 'implement', 'test')
            self.assertEqual(result['status'], 'timeout')

    def test_review_timeout_remains_distinct_in_graph(self):
        from poc.workflow import build
        from poc.contracts import digest_tree
        class Harness:
            def implement(self, state): return {'status': 'completed'}
            def review(self, state): return {'passed': False, 'outcome': 'timeout', 'blocked': True}
        with tempfile.TemporaryDirectory() as directory:
            graph = build(Harness(), lambda _: {'passed': True}).compile()
            result = graph.invoke({'workspace': directory, 'inputs': 'approved', 'approved': 'approved', 'deadline': time.time()+30})
            self.assertEqual(result['outcome'], 'timeout')
            self.assertEqual(result['phase'], 'timeout')

    def test_managed_entrypoint_propagates_child_exit(self):
        for code in (0, 2, 3):
            script = """
import contextlib, runpy, tempfile
from pathlib import Path
from unittest.mock import patch
import poc.managed, poc.glg, poc.knowledge
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory); (root/'base.json').write_text('{}')
    with patch.object(poc.managed, 'lock', return_value=contextlib.nullcontext()), patch.object(poc.knowledge, 'home', return_value=root), patch.object(poc.knowledge, 'trigger', return_value={}), patch.object(poc.glg, 'main', return_value=EXIT):
        runpy.run_module('poc.entry', run_name='__main__')
""".replace('EXIT', str(code))
            result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True)
            self.assertEqual(result.returncode, code, result.stderr)

    def test_blocked_stage_and_stopped_are_not_success(self):
        for status in ('blocked', 'permission_required', 'scope_required', 'timeout'):
            outcome = work_outcome({'stage_result': {'status': status}}, [{'value': {'kind': 'shape-request'}}])
            self.assertEqual(outcome, status)
            self.assertEqual(outcome_exit({'outcome': outcome}), 2)
        self.assertEqual(work_outcome({'lifecycle_phase': 'stopped'}, []), 'stopped')

    def test_truthful_exit_categories(self):
        self.assertEqual(outcome_exit({'pending': [{'value': {'kind': 'repair-brief'}}]}), 2)
        self.assertEqual(outcome_exit({'pending': [{'value': {'kind': 'reconcile-effect'}}]}), 3)
        for outcome in ('failed', 'timeout', 'uncertain', 'blocked'):
            self.assertEqual(outcome_exit({'outcome': outcome}), 2)
        self.assertEqual(outcome_exit({'outcome': 'awaiting-approval'}), 0)
