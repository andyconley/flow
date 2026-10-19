import json,tempfile,unittest
from pathlib import Path
from poc.evidence import final_object,delegations
from poc.contracts import digest_tree
from poc.goose_job import store,GooseJob

class EvidenceTests(unittest.TestCase):
 def test_exit_and_prose_do_not_approve(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'events';p.write_text('banner\n'+json.dumps({'type':'message','message':{'role':'assistant','content':[{'type':'text','text':'All good!'}]}})+'\n')
   self.assertEqual(final_object(p),{})
 def test_stream_chunks_form_one_final_verdict(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'events'
   p.write_text('\n'.join(json.dumps({'message':{'role':'assistant','content':[{'type':'text','text':chunk}]}}) for chunk in ['{"passed":','true,"candidate":"abc"}']))
   self.assertEqual(final_object(p),{'passed':True,'candidate':'abc'})
 def test_explicit_final_json_fence_with_preamble(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'events';p.write_text(json.dumps({'message':{'role':'assistant','content':[{'type':'text','text':'Review notes.\n```json\n{"passed": false, "findings": ["bug"]}\n```'}]}}))
   self.assertEqual(final_object(p),{'passed':False,'findings':['bug']})
 def test_actual_delegation_pairs(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'events';events=[{'message':{'content':[{'type':'toolRequest','id':'id1','toolCall':{'value':{'name':'summon__delegate','arguments':{'provider':'codex-acp','model':'current'}}}}]}},{'message':{'content':[{'type':'toolResponse','id':'id1','toolResult':{'status':'success','value':{}}}]}}]
   p.write_text('\n'.join(json.dumps(e) for e in events));calls=delegations(p)
   self.assertEqual(calls[0]['provider'],'codex-acp');self.assertTrue(calls[0]['response_observed'])
 def test_intent_survives_and_blocks_blind_retry(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'attempt.json';store(p,{'inputs':'abc','status':'uncertain'})
   self.assertEqual(GooseJob().reconcile_record(p)['status'],'blocked')
 def test_digest_excludes_git_not_skill_inputs(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);(root/'x').write_text('a');initial=digest_tree(root)
   (root/'.git').mkdir();(root/'.git/config').write_text('metadata');self.assertEqual(digest_tree(root),initial)
   (root/'x').write_text('b');self.assertNotEqual(digest_tree(root),initial)
