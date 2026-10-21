import os,tempfile,unittest
from pathlib import Path
from local_profile_acceptance import run_case
class DelegationPipelineTests(unittest.TestCase):
 def test_real_coordinator_summon_worker_check_and_review_boundary(self):
  binary=os.environ.get('FLOW_TEST_RELEASE_GOOSE')
  if not binary:self.skipTest('set FLOW_TEST_RELEASE_GOOSE to verified shipped binary')
  for model in ['qwen3.8:27b-q4_K_M','gpt-oss:20b']:
   with self.subTest(model=model),tempfile.TemporaryDirectory() as d:
    result=run_case(Path(d),model,binary)
    self.assertEqual(result['goose_exit'],0,(Path(d)/'goose.stderr').read_text())
    self.assertEqual(result['phases'],['implementation','independent-check','independent-review'])
    self.assertEqual(result['independent_check']['exit'],0)
    self.assertTrue(result['tests_unchanged'])
    self.assertIn(model,result['request_models']);self.assertIn('fixture-coordinator',result['request_models'])
    self.assertEqual(result['review']['recipe']['goose_provider'],'claude-acp')
