"""Adversarial gateway ownership checks; stock execution is covered separately."""
import json
import unittest
from pathlib import Path
from tests import test_chartered_delivery_gateway as fixture_module
from tests.v9_coordinator import coordinate
from delivery_control import DeliveryControlError
from execution_contracts import ContractError
from execution_ledger import ExecutionLedger


class V9OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.V9CharteredRouteTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def snapshot(self):
        ledger = ExecutionLedger(self.fixture.run / 'execution' / 'ledger.sqlite')
        attempt = next(p.name for p in (self.fixture.run / 'execution').iterdir() if p.is_dir())
        return ledger.snapshot(attempt)

    def test_stale_completion_cannot_seal_new_owner_run(self):
        def stale(envelope, task, on_action, **kwargs):
            result = coordinate(envelope, task, on_action, **kwargs)
            path = self.fixture.run / 'run.json'
            state = json.loads(path.read_text())
            state['delivery']['owner_generation'] += 1
            path.write_text(json.dumps(state))
            return result
        with self.assertRaisesRegex(DeliveryControlError, 'stale'):
            self.fixture._execute_v9_topology(with_collector=False, independent_verifier=False, coordinator=stale)
        self.assertEqual(self.snapshot()['status'], 'started')
        self.assertIsNone(self.snapshot()['receipt_path'])

    def test_cancel_racing_completion_cannot_be_overwritten(self):
        def cancel(envelope, task, on_action, **kwargs):
            result = coordinate(envelope, task, on_action, **kwargs)
            ledger = ExecutionLedger(self.fixture.run / 'execution' / 'ledger.sqlite')
            ledger.terminate_v9_attempt(envelope['attempt_id'], 'cancelled', generation=1, actor='test',
                                       explanation='cancel at final proposal', cause='operator_cancelled',
                                       receipt_path=Path(envelope['checkpoint_dir']).parent/'receipt.json')
            return result
        with self.assertRaises(ContractError):
            self.fixture._execute_v9_topology(with_collector=False, independent_verifier=False, coordinator=cancel)
        self.assertEqual(self.snapshot()['status'], 'cancelled')

    def test_changed_retained_artifact_after_verification_cannot_complete(self):
        def tamper(envelope, task, on_action, **kwargs):
            result = coordinate(envelope, task, on_action, **kwargs)
            (self.fixture.worktree/'target.py').write_text('changed after verifier\n')
            return result
        with self.assertRaises(ContractError):
            self.fixture._execute_v9_topology(with_collector=False, independent_verifier=False, coordinator=tamper)
        self.assertEqual(self.snapshot()['status'], 'started')
        self.assertIsNone(self.snapshot()['receipt_path'])

    def test_repeated_worker_proposal_cannot_execute_twice(self):
        attempts = []
        def repeated(envelope, task, on_action, **kwargs):
            def duplicate(proposal):
                result = on_action(proposal)
                attempts.append(proposal['assignment_id'])
                on_action(proposal)
                return result
            return coordinate(envelope, task, duplicate, **kwargs)
        result, snapshot, _ = self.fixture._execute_v9_topology(
            with_collector=False, independent_verifier=False, coordinator=repeated)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(attempts, ['editor'])
        self.assertEqual([a['request']['assignment_id'] for a in snapshot['actions']].count('editor'), 1)
