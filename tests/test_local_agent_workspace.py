import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
from local_agent_workspace import LocalAgentWorkspace
from verifier_contracts import validate_candidate
from delivery_cancel import DeliveryCancelled


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'a.py').write_text('old')
        self.workspace = LocalAgentWorkspace(self.root, ['a.py','b.py'], ['a.py','b.py'],
            self.root/'artifacts', test_callback=lambda: {'status':'passed','output_excerpt':'actual callback'},
            assignment_scopes={'one': {'read_paths':['a.py'], 'write_paths':['a.py']},
                'two': {'read_paths':['a.py','b.py'], 'write_paths':['b.py']},
                'review': {'read_paths':['a.py','b.py'], 'write_paths':[]}})

    def call(self, agent, name, **args):
        return self.workspace.callback(agent, name, args)

    def test_creation_iterative_write_and_scope_denial(self):
        self.assertEqual(self.call('one','write_file',path='a.py',content='new')['status'], 'denied')
        digest = self.call('one','read_files',paths=['a.py'])['files'][0]['sha256']
        self.assertEqual(self.call('one','write_file',path='a.py',content='new',expected_sha256=digest)['status'], 'written')
        self.assertEqual(self.call('two','write_file',path='b.py',content='created')['status'], 'written')
        self.assertEqual(self.call('two','write_file',path='a.py',content='bad')['status'], 'denied')
        self.assertEqual(self.call('two','read_files',paths=['../outside'])['status'], 'denied')
        self.call('one','read_files',paths=['a.py'])
        self.assertEqual(self.call('one','write_file',path='a.py',content='next')['status'], 'written')

    def test_current_source_review_invalidated_after_edit(self):
        self.call('two','write_file',path='b.py',content='created')
        self.assertEqual(self.call('review','submit_review',approved=True,findings='good')['status'],'denied')
        self.call('review','read_files',paths=['a.py','b.py'])
        self.call('review','run_tests')
        review=self.call('review','submit_review',approved=True,findings='Actual source and tests meet requirements')
        validate_candidate(review['candidate'])
        self.call('one','read_files',paths=['a.py'])
        self.call('one','write_file',path='a.py',content='new')
        self.assertFalse(self.workspace.reviews)
        self.assertEqual(self.call('review','submit_review',approved=True,findings='good')['status'],'denied')

    def test_failed_test_cannot_support_approval(self):
        self.workspace.test_callback=lambda: {'status':'failed','output_excerpt':'failing assertion'}
        self.call('review','read_files',paths=['a.py'])
        self.call('review','run_tests')
        self.assertEqual(self.call('review','submit_review',approved=True,findings='good')['status'],'denied')
        result=self.call('review','submit_review',approved=False,findings='Observed failing assertion')
        validate_candidate(result['candidate'])

    def test_real_hash_handoff_and_stale_rejection(self):
        self.assertEqual(self.call('one','submit_handoff',summary='nothing')['status'],'denied')
        self.call('one','read_files',paths=['a.py'])
        self.call('one','write_file',path='a.py',content='new')
        handoff=self.call('one','submit_handoff',summary='Use new API in b.py')
        self.assertEqual(handoff['status'],'handoff_recorded')
        self.assertEqual(self.call('two','read_handoff')['status'],'handoff_read')
        (self.root/'a.py').write_text('external')
        self.assertEqual(self.call('two','read_handoff')['status'],'denied')

    def test_durable_handoff_restore_requires_new_consumer_read(self):
        self.call('one','read_files',paths=['a.py'])
        self.call('one','write_file',path='a.py',content='new')
        self.call('one','submit_handoff',summary='Use new API')
        self.call('two','read_handoff')
        restored=LocalAgentWorkspace(self.root, ['a.py','b.py'], ['a.py','b.py'],
            self.root/'artifacts', assignment_scopes=self.workspace.assignment_scopes)
        self.assertIn('one',restored.handoffs)
        self.assertEqual(restored.writes['one'],{'a.py'})
        self.assertFalse(restored.reads)
        self.assertFalse(restored.handoff_reads)
        self.assertFalse(restored.tests)
        self.assertEqual(restored.callback('two','read_handoff',{})['status'],'handoff_read')
        (self.root/'a.py').write_text('stale')
        with self.assertRaisesRegex(ValueError,'source changed'):
            LocalAgentWorkspace(self.root, ['a.py','b.py'], ['a.py','b.py'],
                self.root/'artifacts', assignment_scopes=self.workspace.assignment_scopes)

    def test_changed_producer_source_invalidates_consumer_handoff_read(self):
        self.call('one','read_files',paths=['a.py'])
        self.call('one','write_file',path='a.py',content='new')
        self.call('one','submit_handoff',summary='Use new API')
        self.call('two','read_handoff')
        self.call('two','write_file',path='b.py',content='consumer edit')
        self.assertIn('two',self.workspace.handoff_reads)
        self.call('one','read_files',paths=['a.py'])
        self.call('one','write_file',path='a.py',content='changed producer')
        self.assertNotIn('two',self.workspace.handoff_reads)

    def test_handoff_artifact_tampering_is_not_restored(self):
        self.call('one','read_files',paths=['a.py'])
        self.call('one','write_file',path='a.py',content='new')
        artifact=self.call('one','submit_handoff',summary='Use new API')
        path=Path(artifact['artifact_path'])
        path.write_text(path.read_text().replace('Use new API','fabricated'))
        with self.assertRaisesRegex(ValueError,'differs from durable'):
            LocalAgentWorkspace(self.root, ['a.py','b.py'], ['a.py','b.py'],
                self.root/'artifacts', assignment_scopes=self.workspace.assignment_scopes)

    def test_serialized_overlapping_handoffs_restore_and_read_only_dependencies(self):
        scopes = {'one': {'read_paths':['a.py'], 'write_paths':['a.py'], 'handoff_dependencies':[]},
            'two': {'read_paths':['a.py'], 'write_paths':['a.py'], 'handoff_dependencies':['one']},
            'three': {'read_paths':['a.py'], 'write_paths':[], 'handoff_dependencies':['two']}}
        self.workspace.assignment_scopes = scopes
        for producer, content in [('one', 'first'), ('two', 'second')]:
            if producer == 'two':
                self.assertEqual(self.call(producer, 'read_handoff')['status'], 'handoff_read')
            self.call(producer, 'read_files', paths=['a.py'])
            self.assertEqual(self.call(producer, 'write_file', path='a.py', content=content)['status'], 'written')
            self.assertEqual(self.call(producer, 'submit_handoff', summary='Observed output')['status'], 'handoff_recorded')
        result = self.call('three', 'read_handoff')
        self.assertEqual(result['status'], 'handoff_read')
        self.assertEqual([item['producer'] for item in result['handoffs']], ['two'])
        restored = LocalAgentWorkspace(self.root, ['a.py','b.py'], ['a.py','b.py'],
            self.root/'artifacts', assignment_scopes=scopes)
        self.assertEqual(restored.callback('three', 'read_handoff', {})['status'], 'handoff_read')
        self.assertEqual(restored.callback('two', 'read_handoff', {})['status'], 'denied')
        self.assertFalse(restored.reads)
        self.assertFalse(restored.tests)
        (self.root/'a.py').write_text('external mutation')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            LocalAgentWorkspace(self.root, ['a.py','b.py'], ['a.py','b.py'],
                self.root/'artifacts', assignment_scopes=scopes)

    def test_symlink_and_external_scope_are_denied(self):
        (self.root/'b.py').symlink_to(self.root/'a.py')
        self.assertEqual(self.call('two','write_file',path='b.py',content='bad')['status'],'denied')
        self.workspace.assignment_scopes['one']['write_paths']=['outside.py']
        self.assertEqual(self.call('one','write_file',path='outside.py',content='bad')['status'],'denied')

    def test_cancellation_propagates_without_failed_test_evidence(self):
        def cancelled():
            raise DeliveryCancelled('stop')
        self.workspace.test_callback=cancelled
        with self.assertRaises(DeliveryCancelled):
            self.call('one','run_tests')
        self.assertFalse(self.workspace.tests)

    def test_actual_fixed_test_command(self):
        self.workspace.test_callback=None
        self.workspace.test_argv=[sys.executable,'-c','print("actual test")']
        result=self.call('one','run_tests')
        self.assertEqual(result['status'],'passed')
        self.assertIn('actual test',result['output_excerpt'])
        self.assertEqual(result['source_digest'], self.workspace.current_source_digest)


if __name__=='__main__':
    unittest.main()
