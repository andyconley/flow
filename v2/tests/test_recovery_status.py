"""Recovery reports retain blockers and describe operations without dispatching them."""
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import patch

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from poc.artifacts import Artifacts
from poc.glg import summarize
from poc.handoffs import Handoffs
from poc.project_context import resolve
from poc.work_lifecycle import build


class RecoveryStatusTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.artifacts = Artifacts(self.project, 'one')

    def summarize(self, values=None, tasks=()):
        snapshot = NS(values={'work_id': 'one', **(values or {})}, tasks=tasks, next=())
        with patch('poc.monitoring.report', return_value={}), patch('poc.monitoring.context_report', return_value={}):
            return summarize(snapshot, self.artifacts)

    def test_identical_nested_interrupt_is_one_decision_and_conflict_is_visible(self):
        value = {'kind': 'permission_required', 'detail': {'reason': 'Sign in required'}}
        interrupt = NS(id='same-id', value=value)
        nested = NS(values={}, tasks=(NS(interrupts=(interrupt,), state=None),))
        tasks = (NS(interrupts=(interrupt,), state=nested),)
        result = self.summarize(tasks=tasks)
        self.assertEqual(len(result['pending']), 1)
        self.assertFalse(result['recovery_problems'])
        self.assertEqual([option['action'] for option in result['pending'][0]['decision_options']], ['resume', 'stop'])
        self.assertIn('--decision-file', result['pending'][0]['command'])
        conflicting = NS(id='same-id', value={**value, 'detail': {'reason': 'Different blocker'}})
        nested.tasks = (NS(interrupts=(conflicting,), state=None),)
        result = self.summarize(tasks=tasks)
        self.assertEqual(len(result['pending']), 2)
        self.assertIn('Conflicting pending', result['recovery_problems'][0]['error'])

    def test_intent_and_outcome_are_grouped_under_assignment_operation(self):
        brief = self.artifacts.publish('briefs', 'brief', {})
        context = self.artifacts.publish('contexts', 'context', {})
        approval = self.artifacts.publish('decisions', 'approval', {})
        state = {'workspace': str(self.project), 'task': 'task', 'brief_ref': brief,
                 'context_ref': context, 'approval_ref': approval}
        boundary = Handoffs(self.artifacts)
        state.update(boundary.assign(state, 'implement'))
        calls = []
        def rejected():
            calls.append('boundary')
            return {'status': 'permission_required', 'submitted': False, 'reason': 'Authentication unavailable'}
        _, refs = boundary.call(state, 'implement', rejected)
        # Even aliases in a projection cannot imply two actual operations.
        refs['result_refs']['alias'] = refs['result_ref']
        result = self.summarize(refs)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(result['operations']), 1)
        operation = result['operations'][0]
        self.assertEqual(operation['operation_id'], 'implement-0-0')
        self.assertEqual(len(operation['records']), 2)
        self.assertFalse(operation['result']['submitted'])
        self.assertIn('not an execution count', operation['interpretation'])

    def test_blocked_review_without_findings_retains_reason_in_closure(self):
        brief = self.artifacts.publish('briefs', 'brief', {
            'goal': 'fixture', 'scope': ['fixture'], 'acceptance_criteria': ['checked'],
            'check_command': ['/usr/bin/true']})
        context = self.artifacts.publish('contexts', 'project', resolve(self.project))
        class Harness:
            def implement(self, state):
                return {'status': 'completed'}
            def review(self, state):
                return {'passed': False, 'blocked': True, 'reason': 'Review delivery budget expired', 'findings': []}
        graph = build(self.artifacts, Harness(), lambda _: {'passed': True}).compile(checkpointer=InMemorySaver())
        config = {'configurable': {'thread_id': 'one'}}
        graph.invoke({'work_id': 'one', 'job_id': 'one', 'workspace': str(self.project),
                      'brief_ref': brief, 'context_ref': context, 'budget_seconds': 600}, config)
        with patch('poc.monitoring.report', return_value={}):
            closed = graph.invoke(Command(resume={'action': 'approve', 'actor': 'fixture', 'brief_ref': brief}), config)
        payload = self.artifacts.read(closed['closure_ref'])['payload']
        self.assertEqual(payload['blocker']['stage'], 'review')
        self.assertEqual(payload['blocker']['reason'], 'Review delivery budget expired')
        self.assertEqual(payload['result']['findings'], [])
        self.assertEqual(self.summarize(closed)['blocker'], payload['blocker'])

    def test_explicit_stop_is_not_reported_as_failure(self):
        result = self.summarize({'phase': 'stopped', 'outcome': 'stopped', 'lifecycle_phase': 'closed'})
        self.assertEqual(result['termination'], 'intentional-stop')
        self.assertIsNone(result['blocker'])

    def test_expired_pending_budget_uses_nested_delivery_state(self):
        interrupt = NS(id='pause', value={'kind': 'permission_required'})
        nested = NS(values={'deadline': 1, 'phase': 'permission_required', 'resume_stage': 'review',
                            'review': {'reason': 'Sign in required'}},
                    tasks=(NS(interrupts=(interrupt,), state=None),))
        result = self.summarize({'lifecycle_phase': 'delivery'}, (NS(interrupts=(), state=nested),))
        self.assertTrue(result['budget']['expired'])
        self.assertEqual(result['blocker']['reason'], 'Sign in required')
        self.assertEqual([item['action'] for item in result['pending'][0]['decision_options']], ['stop'])

    def test_closed_review_shows_exact_recovery_approval_template(self):
        closure = self.artifacts.publish('closures', 'closure', {})
        brief = self.artifacts.publish('briefs', 'brief', {})
        result = self.summarize({'lifecycle_phase': 'closed', 'phase': 'blocked', 'candidate': 'exact-candidate',
                                 'review': {'reason': 'Expired'}, 'closure_ref': closure, 'brief_ref': brief})
        decision = result['recover_review']['decision']
        self.assertEqual(decision['action'], 'recover-review')
        self.assertEqual(decision['candidate_revision'], 'exact-candidate')
        self.assertEqual(decision['closure_ref'], closure)
        self.assertEqual(decision['brief_ref'], brief)
        self.assertEqual(decision['budget_seconds'], 600)


if __name__ == '__main__':
    unittest.main()
