from pathlib import Path
import unittest,tempfile,json
from unittest.mock import patch
from poc import native_enrichment as module, provider_policy,implementation_profiles,provider_preflight
class Enrichment(unittest.TestCase):
 def test_exact_quotes_and_authored_preservation(self):
  with tempfile.TemporaryDirectory() as t:
   stage=Path(t)/'generations/test';(stage/'notes').mkdir(parents=True)
   prose='Review the actual changed code and verify every reported behavior against evidence before accepting it.'
   originals={}
   for name in ['one','two']:
    body='---\ntitle: '+name+'\ncard_id: flow:entry/'+name+'\npermalink: '+name+'\n---\n\n'+prose+'\n';originals[name]=body;(stage/'notes'/(name+'.md')).write_text(body)
   def runner(prompt,schema,where):return {'sources':[{'source_id':'flow:entry/one','relationships':[{'target_id':'flow:entry/two','type':'reinforces','source_quote':prose,'target_quote':prose,'reason':'Shared evidence requirement'}]},{'source_id':'flow:entry/two','relationships':[]}]}
   result=module.enrich(stage,runner);self.assertEqual(result['accepted'],1)
   for name,body in originals.items():self.assertEqual(module.k.source((stage/'notes'/(name+'.md')).read_text()),body)
   bad=runner('','',stage);bad['sources'][0]['relationships'][0]['source_quote']='invented claim'
   accepted,rejected=module.validate(bad,module.records(stage));self.assertEqual(len(rejected),1);self.assertEqual(accepted['flow:entry/one'],[])
   result=module.enrich(stage,lambda *x:self.fail('cache miss'));self.assertEqual(result['origin'],'validated-cache')
class NativePolicy(unittest.TestCase):
 def test_saved_pool_and_recipe_cannot_override_machine_policy(self):
  with tempfile.TemporaryDirectory() as t:
   home=Path(t);config=home/'.flow/user/runtime.toml';config.parent.mkdir(parents=True);config.write_text('[execution_policy]\nnative_only = true\n')
   with patch('pathlib.Path.home',return_value=home):
    for provider in ['codex-acp','claude-acp','chatgpt_codex']:provider_policy.require(provider)
    row={'name':'old','provider':'ollama','model':'tiny'};row['sha256']=implementation_profiles.fingerprint(row)
    pool={'name':'old-pool','provider':'pool','model':'goose-selected','profiles':[row]};pool['sha256']=implementation_profiles.fingerprint(pool)
    with self.assertRaises(ValueError):implementation_profiles.validate(pool)
    recipes=home/'bundle/recipes';recipes.mkdir(parents=True);(recipes/'old.yaml').write_text('settings:\n  goose_provider: ollama\n  goose_model: tiny\n')
    with self.assertRaises(provider_preflight.PreflightError):provider_preflight.planned(recipes.parent,'codex-acp','current')
if __name__=='__main__':unittest.main()

class NativeKnowledgeInstallation(unittest.TestCase):
 def test_model_probe_is_never_required_and_existing_runtime_is_reused(self):
  from poc import install_knowledge as gate
  import sys
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);(root/'settings.json').write_text(json.dumps({'python':sys.executable,'ollama':'http://127.0.0.1:11434','model_digest':'old-local-model'}))
   with patch('poc.provider_policy.native_knowledge',return_value=True),patch.object(gate,'checked_model_digest',side_effect=AssertionError('local probe')),patch.object(gate.k,'reconcile_shared'),patch.object(gate.k,'process',return_value={'state':'ready','pending':False}) as process:
    self.assertEqual(gate.resolve_model_mode(root,'download','download'),('download','offline'))
    result=gate.provision(root,'offline');self.assertTrue(result['ready']);self.assertEqual(result['mode'],'native-lexical');process.assert_called_once_with(root)
    self.assertEqual(gate.provision(root,'defer')['state'],'deferred')
 def test_uncertain_update_still_blocks_native_knowledge(self):
  from poc import knowledge_tools
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)/'state/knowledge';root.mkdir(parents=True);(root.parent.parent/'knowledge-provision-uncertain.json').write_text('{}')
   with patch.object(knowledge_tools.knowledge,'home',return_value=root),patch('poc.provider_policy.native_knowledge',return_value=True):
    with self.assertRaises(knowledge_tools.KnowledgeUnavailable):knowledge_tools.require_ready()
 def test_update_ask_skips_local_model_readiness(self):
  from poc import managed,install_knowledge as gate
  from unittest.mock import Mock
  import os
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);release=root/'release';(release/'knowledge').mkdir(parents=True);(release/'knowledge/manifest.json').write_text('{}');(release/'v2/poc').mkdir(parents=True);(release/'v2/poc/install_knowledge.py').write_text('MODEL_ACQUISITION_PROTOCOL = 1')
   def launch(command,**kwargs):
    self.assertEqual(command[command.index('--mode')+1],'offline');Path(command[command.index('--result')+1]).write_text(json.dumps({'state':'ready','ready':True}));return Mock(pid=123,returncode=0,poll=lambda:0)
   with patch('poc.provider_policy.native_knowledge',return_value=True),patch('poc.knowledge_health.doctor',side_effect=AssertionError('local doctor')),patch.object(gate,'checked_model_digest',side_effect=AssertionError('local probe')),patch.object(managed.subprocess,'Popen',side_effect=launch),patch('poc.lifecycle.ProcessScope'),patch.dict(os.environ,{'FLOW_INSTALL_KNOWLEDGE_FD':'0'}):
    self.assertTrue(managed.provision_knowledge(release,root,'ask')['ready'])
