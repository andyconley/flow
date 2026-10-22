"""Frozen explicit Goose choice; single-profile approvals remain immutable."""
from pathlib import Path
import tempfile
import unittest
import yaml
from poc.implementation_profiles import fingerprint,validate,bind,apply_environment


def member(name,provider,model):
    row={'name':name,'provider':provider,'model':model}
    row['sha256']=fingerprint(row)
    return row


def pool(members):
    row={'name':'approved-worker-pool','provider':'pool','model':'goose-selected','profiles':members}
    row['sha256']=fingerprint(row)
    return row


class ImplementationPoolTests(unittest.TestCase):
    def test_pool_is_frozen_including_each_choice(self):
        row=pool([member('native','codex-acp','gpt'),member('claude','claude-acp','sonnet')])
        self.assertEqual(validate(row),row)
        row['profiles'][0]['model']='unapproved'
        with self.assertRaisesRegex(ValueError,'snapshot changed'):validate(row)

    def test_duplicate_and_nested_choices_rejected(self):
        one=member('native','codex-acp','gpt')
        with self.assertRaisesRegex(ValueError,'Duplicate'):validate(pool([one,one]))
        with self.assertRaisesRegex(ValueError,'Nested'):validate(pool([pool([one])]))

    def test_attempt_pool_exact_providers_and_independent_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);recipes=root/'recipes';recipes.mkdir()
            template={'instructions':'approved task','settings':{'goose_provider':'claude-acp','goose_model':'sonnet'}}
            (recipes/'lead-developer.yaml').write_text(yaml.safe_dump(template))
            (recipes/'quality-reviewer.yaml').write_text('independent')
            (recipes/'unapproved.yaml').write_text('unapproved')
            row=pool([member('native','codex-acp','gpt'),member('claude','claude-acp','sonnet')])
            bind(root,row)
            self.assertEqual({p.stem for p in recipes.iterdir()},{'implement-native','implement-claude','quality-reviewer'})
            self.assertEqual((recipes/'quality-reviewer.yaml').read_text(),'independent')
            for selected in row['profiles']:
                settings=yaml.safe_load((recipes/('implement-'+selected['name']+'.yaml')).read_text())['settings']
                self.assertEqual(settings,{'goose_provider':selected['provider'],'goose_model':selected['model']})

    def test_native_pool_rejected_without_silent_fallback(self):
        with self.assertRaisesRegex(ValueError,'require a Goose coordinator'):
            apply_environment({},pool([member('native','codex-acp','gpt')]),'codex-acp','gpt')

    def test_single_profile_remains_single(self):
        row=member('native','codex-acp','gpt')
        self.assertEqual(validate(row)['provider'],'codex-acp')
        self.assertNotIn('profiles',row)

class LocalPoolTests(unittest.TestCase):
    def local(self,name,model,digest):
        row={'name':name,'provider':'ollama','model':model,'endpoint':'http://127.0.0.1:11434','context_tokens':32768,'output_tokens':-1,'condenser_max_tokens':28672,'model_digest':digest}
        row['sha256']=fingerprint(row)
        return row

    def test_two_local_models_share_settings_but_preserve_both_digests(self):
        row=pool([self.local('correct','qwen:test','a'*64),self.local('fast','gpt:test','b'*64)])
        env=apply_environment({},row,'chatgpt_codex','gpt-native')
        self.assertEqual(env['GOOSE_INPUT_LIMIT'],'32768')
        self.assertEqual(env['GOOSE_AUTO_COMPACT_THRESHOLD'],'0.875')
        self.assertNotIn('GOOSE_MAX_TOKENS',env)
        import json
        self.assertEqual(json.loads(env['FLOW_V2_IMPLEMENTATION_POOL']),row)

    def test_incompatible_local_transports_rejected_before_dispatch(self):
        first=self.local('correct','qwen:test','a'*64);second=self.local('fast','gpt:test','b'*64)
        second['context_tokens']=16384;second['condenser_max_tokens']=14336
        second['sha256']=fingerprint({k:v for k,v in second.items() if k!='sha256'})
        with self.assertRaisesRegex(ValueError,'share explicitly frozen'):validate(pool([first,second]))

    def test_actual_goose_config_subdirectory_cap_conflict_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'config';config.mkdir()
            (config/'config.yaml').write_text('GOOSE_MAX_TOKENS: 2048\n')
            row=pool([self.local('correct','qwen:test','a'*64)])
            with self.assertRaisesRegex(ValueError,'output override conflicts'):
                apply_environment({'GOOSE_PATH_ROOT':tmp},row,'chatgpt_codex','native')

class NativeSummonPromptTests(unittest.TestCase):
    def test_native_worker_receives_bound_task_and_schema_in_user_prompt(self):
        from unittest.mock import patch
        from poc.role_renderer import bind_bundle
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';(source/'recipes').mkdir(parents=True)
            recipe={'version':'1.0.0','title':'native','description':'fixture','instructions':'Approved task: {{ task }}. Context: {{ project_context }}','prompt':'Generic system-only placeholder','parameters':[{'key':'task','input_type':'string','requirement':'required','description':'task'},{'key':'project_context','input_type':'string','requirement':'required','description':'context'}],'settings':{'goose_provider':'codex-acp','goose_model':'gpt-native'},'response':{'json_schema':{'type':'object','properties':{'verdict':{'type':'string'}},'required':['verdict']}}}
            (source/'recipes/native.yaml').write_text(yaml.safe_dump(recipe))
            with patch('poc.knowledge.home',return_value=root/'empty-knowledge'):
                bind_bundle(source,root/'bound','Implement only fixture.py','Use frozen tests')
            bound=yaml.safe_load((root/'bound/recipes/native.yaml').read_text())
            self.assertIn('Approved task: {{ task }}',bound['prompt'])
            self.assertIn('verdict',bound['prompt'])
            self.assertIn('without nested delegation',bound['prompt'])
            self.assertEqual({p['key']:p['default'] for p in bound['parameters']},{'task':'Implement only fixture.py','project_context':'Use frozen tests'})
