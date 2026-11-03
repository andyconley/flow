import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from poc.artifacts import Artifacts, ArtifactError
from poc.attempt_evidence import receipt
from poc.review_findings import validate
from poc.work_review import packet


class WorkReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.artifacts = Artifacts(self.root, 'work')

    def test_trace_preserves_missing_superseded_and_invalid(self):
        old = self.artifacts.publish('briefs', 'brief', {'goal': 'old'})
        new = self.artifacts.publish('briefs', 'brief', {'goal': 'new'}, old)
        missing = {'path': '.glg/work/work/results/missing.json', 'revision': '0'*64}
        self.artifacts.publish('decisions', 'approve', {'target_ref': old, 'missing': missing})
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch('subprocess.Popen', side_effect=AssertionError('no execution')), patch.object(Artifacts, 'publish', side_effect=AssertionError('no writes')):
            result = packet(self.artifacts, {'brief_ref': new})
        self.assertIn('missing', [row['status'] for row in result['references']])
        self.assertIn('superseded', [row['status'] for row in result['references']])
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        (self.root / new['path']).write_text('{}')
        self.assertTrue(packet(self.artifacts, {})['diagnostics'])

    def test_findings_stale_and_legacy(self):
        path = self.root / 'code.py'; path.write_text('old')
        finding = {'id': 'F1', 'message': 'bug', 'evidence': 'observed', 'anchor': {'type': 'code', 'path': 'code.py', 'revision': hashlib.sha256(b'old').hexdigest()}, 'resolution': {'state': 'resolved', 'evidence': 'fixed'}}
        validate(['legacy', finding])
        self.artifacts.publish('results', 'review-1-0', {'effect': 'completed', 'result': {'outcome': 'request_changes', 'findings': ['legacy', finding]}})
        self.assertEqual(packet(self.artifacts, {})['findings'][1]['anchor_status'], 'current')
        path.write_text('fixed')
        rows = packet(self.artifacts, {})['findings']
        self.assertEqual(rows[0]['anchor_status'], 'unanchored')
        self.assertEqual(rows[1]['anchor_status'], 'stale')
        self.assertEqual(rows[1]['resolution']['state'], 'resolved')
        with self.assertRaises(ArtifactError): validate([{'message': 'no anchor'}])

    def test_attempt_isolation_and_distinctions(self):
        def run(index):
            path = self.root / f'{index}.jsonl'
            blocks = [{'type': 'toolRequest', 'id': str(index), 'toolCall': {'value': {'name': 'knowledge__search_cards', 'arguments': {'query': str(index)}}}}]
            if index != 3:
                blocks.append({'type': 'toolResponse', 'id': str(index), 'toolResult': {'status': 'error' if index == 2 else 'success', 'content': [{'text': json.dumps({'results': [] if index == 1 else ['card']})}]}})
            path.write_text(json.dumps({'message': {'content': blocks}})+'\n')
            return receipt({'output': str(path), 'knowledge_attached': True}, str(index))
        with ThreadPoolExecutor() as pool: rows = list(pool.map(run, range(4)))
        self.assertEqual([r['observations'][0]['state'] for r in rows], ['observed_retrieval', 'empty', 'failed', 'unobserved'])
        for index, row in enumerate(rows):
            self.assertEqual(row['attempt_id'], str(index))
            self.assertEqual(len(row['observations']), 1)
        self.assertEqual(receipt({}, 'missing')['knowledge']['state'], 'unavailable')
        self.assertEqual(receipt({'skill_availability': 'supplied'}, 'x')['skills']['state'], 'supplied')

    def test_timeline_keeps_uncertain_and_blocked_distinct(self):
        for index, state in enumerate(['uncertain', 'permission_required', 'scope_required', 'timeout', 'completed']):
            self.artifacts.publish('results', f'op-{index}', {'effect': 'completed', 'result': {'status': state, 'reason': state}})
        result = packet(self.artifacts, {}, {'next_action': 'Inspect blocker'})
        self.assertEqual({r['state'] for r in result['timeline']}, {'uncertain', 'permission_required', 'scope_required', 'timeout', 'completed'})
        self.assertTrue(all(r['next_action'] == 'Inspect blocker' for r in result['timeline']))

    def test_cli_views_are_read_only_under_operator_lock(self):
        import contextlib
        import io
        from poc import glg
        args = ['--project', str(self.root), '--work', 'work']
        def invoke(command, *extra):
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                glg.main([*args, command, *extra])
            return json.loads(stream.getvalue())
        with patch.object(glg, 'ROOT', self.root / 'runtime'):
            invoke('create', '--request', 'Review fixture')
            state = glg.storage(self.root, 'work')
            before = (state / 'workflow.sqlite').read_bytes()
            with glg.locked(state), patch.object(glg.NativeHarness, '_job', side_effect=AssertionError('model execution')), patch.object(Artifacts, 'publish', side_effect=AssertionError('artifact write')):
                trace = invoke('trace')
                timeline = invoke('timeline')
            self.assertFalse(trace['writes'])
            self.assertFalse(timeline['writes'])
            self.assertEqual(trace['current']['phase'], 'shaping')
            self.assertEqual(before, (state / 'workflow.sqlite').read_bytes())

    def test_observation_attaches_attempt_receipt_without_model(self):
        from poc.goose_job import GooseJob
        record = {'knowledge_attached': True, 'skill_availability': 'available'}
        with patch('poc.monitoring.attach'), patch('poc.monitoring.context_for_usage', return_value={'observations': []}):
            GooseJob()._observe(record, {'job_id': 'job', 'workspace': str(self.root)}, 'review', '2-1')
        self.assertEqual(record['evidence_receipt']['attempt_id'], 'job/review-2-1')
        self.assertEqual(record['evidence_receipt']['knowledge']['state'], 'available')
        self.assertEqual(record['evidence_receipt']['observations'], [])
