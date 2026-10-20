"""Real SQLite/subgraph integration with simulated workers; no model calls."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from poc.artifacts import Artifacts, ArtifactError, validate_brief
from poc.contracts import digest_tree
from poc.handoffs import Handoffs
from poc.project_context import resolve
from poc.work_lifecycle import build
from poc import glg


BRIEF = {'goal': 'Improve the feature', 'scope': ['One approved change'],
         'acceptance_criteria': ['Checks pass without weakening behavior'],
         'check_command': [sys.executable, '-c', 'print("ok")'],
         'historical_references': ['.flow/runs/old/requirements.md']}


class Harness:
    def __init__(self):
        self.calls = 0
        self.reviews = 0
        self.crash = False
    def implement(self, state):
        self.calls += 1
        (Path(state['workspace']) / 'change.txt').write_text('implemented')
        if self.crash:
            raise RuntimeError('crash after write before result publication')
        return {'status': 'completed', 'findings': [], 'test_results': {}}
    def review(self, state):
        self.reviews += 1
        return {'passed': True, 'candidate': digest_tree(state['workspace']), 'findings': []}
    def reconcile(self, state):
        raise AssertionError('Controlled unresolved effects need explicit reconciliation')


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'project'; self.project.mkdir()
        self.artifacts = Artifacts(self.project, 'one')
        self.h = Harness()
        self.cfg = {'configurable': {'thread_id': 'one'}, 'recursion_limit': 100}
        self.cm = SqliteSaver.from_conn_string(str(self.root / 'workflow.sqlite'))
        self.saver = self.cm.__enter__(); self.addCleanup(self.cm.__exit__, None, None, None)
        self.g = build(self.artifacts, self.h, lambda path: {'passed': True}).compile(checkpointer=self.saver)
        self.context = self.artifacts.publish('contexts', 'project', resolve(self.project))
        self.brief = self.artifacts.publish('briefs', 'brief', BRIEF)
        self.initial = {'work_id': 'one', 'job_id': 'unique-one', 'workspace': str(self.project),
                        'request': 'Please investigate', 'brief_ref': self.brief, 'context_ref': self.context,
                        'budget_seconds': 600, 'lifecycle_phase': 'shaping'}

    def approve(self):
        return self.g.invoke(Command(resume={'action': 'approve', 'actor': 'Andy', 'brief_ref': self.brief}), self.cfg)

    def test_approval_binds_exact_revision_then_delivery_and_closure(self):
        paused = self.g.invoke(self.initial, self.cfg)
        self.assertIn('__interrupt__', paused); self.assertEqual(self.h.calls, 0)
        result = self.approve()
        self.assertEqual(result['lifecycle_phase'], 'closed')
        self.assertEqual(result['phase'], 'reviewed-and-ready')
        self.assertEqual((self.h.calls, self.h.reviews), (1, 1))
        self.assertEqual(len(result['assignment_refs']), 3)
        self.assertEqual(len(result['result_refs']), 3)
        for operation, reference in result['result_refs'].items():
            record = self.artifacts.read(reference)
            self.assertEqual(record['payload']['effect'], 'completed')
            self.assertEqual(record['payload']['assignment_ref'], result['assignment_refs'][operation])
        closure = self.artifacts.read(result['closure_ref'])['payload']
        self.assertEqual(closure['acceptance'], 'not-recorded')
        self.assertEqual(closure['historical_references'], BRIEF['historical_references'])
        self.g.invoke(None, self.cfg)
        self.assertEqual((self.h.calls, self.h.reviews), (1, 1))

    def test_refinement_supersedes_without_old_approval_or_execution(self):
        self.g.invoke(self.initial, self.cfg)
        revised = self.artifacts.publish('briefs', 'brief', {**BRIEF, 'goal': 'Refined goal'}, supersedes=self.brief)
        result = self.g.invoke(Command(resume={'action': 'brief', 'brief_ref': revised}), self.cfg)
        self.assertEqual(result['brief_ref'], revised); self.assertEqual(self.h.calls, 0)
        with self.assertRaisesRegex(ArtifactError, 'exact proposed'):
            self.approve()
        self.assertEqual(self.h.calls, 0)
        self.assertEqual(self.artifacts.read(self.brief)['payload']['goal'], BRIEF['goal'])

    def test_shaping_assignment_stage_and_separate_approval_do_not_authorize_delivery(self):
        initial = {k: v for k, v in self.initial.items() if k != 'brief_ref'}
        self.g.invoke(initial, self.cfg)
        assignment = self.artifacts.publish('assignments', 'define', {'stage': 'define', 'question': 'Which users?'})
        self.g.invoke(Command(resume={'action': 'assign', 'assignment_ref': assignment}), self.cfg)
        stage = self.artifacts.publish('shaping', 'define', {'stage': 'define', 'content': 'Observed evidence', 'assignment_ref': assignment})
        self.g.invoke(Command(resume={'action': 'stage', 'shaping_ref': stage}), self.cfg)
        result = self.g.invoke(Command(resume={'action': 'approve-stage', 'stage': 'define', 'actor': 'Andy'}), self.cfg)
        self.assertIn('__interrupt__', result); self.assertNotIn('approval_ref', result)
        self.assertEqual(self.h.calls, 0)

    def test_crash_uncertain_effect_pauses_after_reopen_and_never_replays(self):
        self.g.invoke(self.initial, self.cfg); self.h.crash = True
        with self.assertRaisesRegex(RuntimeError, 'crash after write'):
            self.approve()
        self.saver.conn.close()
        with SqliteSaver.from_conn_string(str(self.root / 'workflow.sqlite')) as fresh:
            g = build(self.artifacts, self.h, lambda path: {'passed': True}).compile(checkpointer=fresh)
            result = g.invoke(None, self.cfg)
            self.assertIn('__interrupt__', result); self.assertEqual(self.h.calls, 1)
            # Owner inspected actual effect; supply recovered outcome, no second invocation.
            result = g.invoke(Command(resume={'actor': 'Andy', 'effect': 'completed', 'evidence': 'Inspected change.txt and job outcome',
                                             'result': {'status': 'completed'}}), self.cfg)
        self.assertEqual(result['phase'], 'reviewed-and-ready'); self.assertEqual(self.h.calls, 1)

    def test_completed_result_reused_after_checkpoint_gap(self):
        state = {**self.initial, 'task': 'task', 'approval_ref': self.artifacts.publish('decisions', 'approved', {'action': 'approve'})}
        boundary = Handoffs(self.artifacts); state.update(boundary.assign(state, 'implement'))
        result, refs = boundary.call(state, 'implement', lambda: self.h.implement(state))
        # The file exists, but pretend the node's checkpoint did not commit refs.
        cached, cached_refs = boundary.call(state, 'implement', lambda: self.fail('Completed invocation replayed'))
        self.assertEqual(cached, result); self.assertEqual(cached_refs, refs)
        self.assertEqual(self.h.calls, 1)

    def test_delivery_permission_decision_is_controlled_and_resumes_same_scope(self):
        original = self.h.implement
        def permission_once(state):
            if not state.get('resume_epoch'):
                return {'status': 'permission_required', 'reason': 'Actual access denied'}
            return original(state)
        self.h.implement = permission_once
        self.g.invoke(self.initial, self.cfg)
        paused = self.approve()
        self.assertIn('__interrupt__', paused)
        snapshot = self.g.get_state(self.cfg, subgraphs=True)
        self.assertTrue(glg.summarize(snapshot, self.artifacts)['pending'])
        result = self.g.invoke(Command(resume={'action': 'resume', 'actor': 'Andy',
                                               'reason': 'Access fixed; same approved scope'}), self.cfg)
        self.assertEqual(result['phase'], 'reviewed-and-ready')
        decisions = [self.artifacts.read(ref)['payload'] for ref in result['decision_refs']]
        self.assertEqual([item['action'] for item in decisions], ['approve', 'resume'])
        self.assertEqual(self.h.calls, 1)

    def test_changed_candidate_cannot_reuse_completed_checks(self):
        state = {**self.initial, 'task': 'task', 'approval_ref': self.artifacts.publish('decisions', 'approved', {'action': 'approve'})}
        boundary = Handoffs(self.artifacts); state.update(boundary.assign(state, 'check'))
        boundary.call(state, 'check', lambda: {'passed': True})
        (self.project / 'change.txt').write_text('different candidate')
        result, _ = boundary.call(state, 'check', lambda: self.fail('Old assignment reran'))
        self.assertFalse(result['passed']); self.assertEqual(result['outcome'], 'scope_required')

    def test_uncertain_not_started_requires_evidence_then_same_assignment_runs(self):
        state = {**self.initial, 'task': 'task', 'approval_ref': self.artifacts.publish('decisions', 'approved', {'action': 'approve'})}
        boundary = Handoffs(self.artifacts)
        state.update(boundary.assign(state, 'implement'))
        operation = self.artifacts.read(state['assignment_ref'])['id']
        boundary._result(operation, state, None, 'uncertain', None, 'Interrupted before submit')
        from langgraph.graph import StateGraph, START, END
        from poc.contracts import State
        b = StateGraph(State)
        def execute(s):
            result, refs = boundary.call(s, 'implement', lambda: self.h.implement(s))
            return {**refs, 'result': result}
        b.add_node('execute', execute); b.add_edge(START, 'execute'); b.add_edge('execute', END)
        g = b.compile(checkpointer=self.saver)
        self.assertIn('__interrupt__', g.invoke(state, self.cfg)); self.assertEqual(self.h.calls, 0)
        result = g.invoke(Command(resume={'actor': 'Andy', 'effect': 'not_started', 'evidence': 'No job or edits exist'}), self.cfg)
        self.assertEqual(self.h.calls, 1)
        self.assertEqual(self.artifacts.read(result['result_ref'])['payload']['effect'], 'completed')

    def test_artifact_change_is_detected_and_conflicting_heads_are_not_guessed(self):
        self.artifacts.publish('briefs', 'brief', {**BRIEF, 'goal': 'Unrelated fork'})
        with self.assertRaisesRegex(ArtifactError, 'Conflicting'):
            self.artifacts.leaf('briefs', 'brief')
        (self.project / self.brief['path']).write_text('{}')
        with self.assertRaisesRegex(ArtifactError, 'modified'):
            self.artifacts.read(self.brief)

    def test_candidate_excludes_control_records_but_detects_code_changes(self):
        before = digest_tree(self.project)
        self.artifacts.publish('decisions', 'example', {'action': 'approve'})
        self.assertEqual(before, digest_tree(self.project))
        (self.project / 'change.txt').write_text('code')
        self.assertNotEqual(before, digest_tree(self.project))

    def test_context_stacks_and_keeps_flow_history(self):
        (self.root / 'AGENTS.md').write_text('parent instructions')
        (self.project / 'CODEX.md').write_text('project instructions')
        (self.project / '.flow').mkdir()
        (self.project / '.flow/PROJECT.md').write_text('Flow context')
        value = resolve(self.project)
        self.assertEqual([x['content'] for x in value['documents']][-3:], ['parent instructions', 'project instructions', 'Flow context'])
        self.assertTrue(value['historical_flow'].endswith('/.flow'))

    def test_invalid_paths_briefs_and_foreign_references_rejected(self):
        with self.assertRaises(ArtifactError): Artifacts(self.project, '../escape')
        with self.assertRaises(ArtifactError): validate_brief({**BRIEF, 'check_command': 'echo unsafe'})
        other = Artifacts(self.project, 'two')
        with self.assertRaises(ArtifactError): other.read(self.brief)

    def test_native_host_cli_end_to_end_acceptance_status_and_index(self):
        brief_file = self.root / 'brief.json'; brief_file.write_text(json.dumps(BRIEF))
        arguments = ['--project', str(self.project), '--work', 'cli-work']
        outputs = []
        def invoke(*tail):
            capture = io.StringIO()
            with contextlib.redirect_stdout(capture): glg.main([*arguments, *tail])
            value = json.loads(capture.getvalue()); outputs.append(value); return value
        with patch.object(glg, 'ROOT', self.root), patch.object(glg, 'NativeHarness', return_value=self.h):
            paused = invoke('create', '--request', 'Investigate the request')
            self.assertEqual(self.h.calls, 0)
            invoke('assign', '--stage', 'define', '--question', 'Find relevant evidence')
            note = self.root / 'findings.md'; note.write_text('Evidence, uncertainty and acceptance recommendations')
            invoke('stage', '--stage', 'define', '--file', str(note))
            shaped = invoke('brief', '--file', str(brief_file))
            revision = shaped['references']['brief_ref']['revision']
            closed = invoke('approve', '--actor', 'Andy', '--revision', revision)
            self.assertEqual(closed['phase'], 'closed')
            self.assertFalse(closed['recovery_problems'])
            invoke('resume')
            self.assertEqual(self.h.calls, 1)
            accepted = invoke('accept', '--actor', 'Andy', '--revision', closed['references']['closure_ref']['revision'])
            record = Artifacts(self.project, 'cli-work').read(accepted['references']['closure_ref'])
            self.assertEqual(record['payload']['acceptance'], 'accepted')
            self.assertEqual(record['supersedes'], closed['references']['closure_ref'])
            invoke('index')
            self.assertIn('cli-work', (self.project / '.glg/INDEX.md').read_text())
            self.assertEqual(invoke('status')['phase'], 'closed')

    def test_explicit_blocked_review_retry_rechecks_without_reimplementation(self):
        brief_file = self.root / 'brief.json'; brief_file.write_text(json.dumps(BRIEF))
        decision_file = self.root / 'retry.json'
        decision_file.write_text(json.dumps({'action': 'retry-review', 'actor': 'Andy', 'reason': 'Adapter fixed; unchanged candidate'}))
        original_review = self.h.review
        def review(state):
            result = original_review(state)
            return {**result, 'candidate': None} if self.h.reviews == 1 else result
        self.h.review = review
        args = ['--project', str(self.project), '--work', 'retry-case']
        def invoke(*tail):
            capture = io.StringIO()
            with contextlib.redirect_stdout(capture): glg.main([*args, *tail])
            return json.loads(capture.getvalue())
        with patch.object(glg, 'ROOT', self.root), patch.object(glg, 'NativeHarness', return_value=self.h):
            paused = invoke('create', '--brief-file', str(brief_file))
            blocked = invoke('approve', '--actor', 'Andy', '--revision', paused['references']['brief_ref']['revision'])
            self.assertEqual(blocked['delivery_phase'], 'blocked')
            retry = json.loads(decision_file.read_text())
            retry.update(closure_ref=blocked['references']['closure_ref'], brief_ref=blocked['references']['brief_ref'], candidate_revision=digest_tree(self.project))
            decision_file.write_text(json.dumps(retry))
            candidate = self.project / 'change.txt'; before = candidate.read_bytes(); candidate.write_text('changed')
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                invoke('resume', '--decision-file', str(decision_file))
            candidate.write_bytes(before)
            closed = invoke('resume', '--decision-file', str(decision_file))
            self.assertEqual(closed['delivery_phase'], 'reviewed-and-ready')
            self.assertEqual((self.h.calls, self.h.reviews), (1, 2))
            record = Artifacts(self.project, 'retry-case').read(closed['references']['closure_ref'])
            self.assertEqual(record['supersedes'], blocked['references']['closure_ref'])

    def test_nested_reported_review_revision_is_normalized_without_invention(self):
        from poc.goose_job import GooseJob
        path = self.root / 'review.jsonl'
        value = {'outcome': 'approve', 'findings': [], 'test_results': {'candidate_revision': 'actual-revision'}}
        def write(value):
            path.write_text(json.dumps({'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': json.dumps(value)}]}})+'\n')
        write(value)
        job = GooseJob(role_bundle=self.root)
        with patch.object(job, '_run', return_value={'status': 'completed', 'output': str(path)}):
            self.assertEqual(job.review({'task': 'task', 'workspace': str(self.project)})['candidate'], 'actual-revision')
            write({**value, 'test_results': {}})
            self.assertIsNone(job.review({'task': 'task', 'workspace': str(self.project), 'candidate': 'expected'})['candidate'])
