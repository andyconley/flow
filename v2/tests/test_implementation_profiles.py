"""Frozen worker selection and actual lifecycle approval, without model inference."""
import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import yaml
from poc import implementation_profiles as profiles
from poc.role_renderer import bind_bundle
from poc.contracts import digest_tree
from poc.artifacts import Artifacts,ArtifactError
from poc.work_lifecycle import build
from poc.project_context import resolve as project_context
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from test_glg_lifecycle import BRIEF,Harness
ROOT=Path(__file__).resolve().parents[1]

class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.user=self.root/'.flow/user';self.user.mkdir(parents=True)
        self.project=self.root/'project';self.project.mkdir()
        self.runtime=self.user/'runtime.toml'
        self.runtime.write_text('[profiles.correct]\nkind="local"\nmodel="ollama_chat/qwen3.8:27b-q4_K_M"\nbase_url="http://127.0.0.1:11434"\nmax_input_tokens=32768\nmax_output_tokens=-1\ncondenser_max_tokens=28672\n[profiles.fast]\nkind="local"\nmodel="ollama_chat/gpt-oss:20b"\nbase_url="http://127.0.0.1:11434"\nmax_input_tokens=32768\nmax_output_tokens=-1\n[profiles.codex]\nkind="codex"\n[profiles.claude]\nkind="claude"\n')
        self.patch=patch('poc.knowledge.local_model_digest',return_value='a'*64);self.mock=self.patch.start();self.addCleanup(self.patch.stop)

    def selected(self,name='correct'):return profiles.resolve(self.project,name,self.root)

    def test_only_attempt_local_implementation_changes_and_review_stays_native(self):
        original=ROOT/'role-bundle';before=digest_tree(original)
        for name,model in [('correct','qwen3.8:27b-q4_K_M'),('fast','gpt-oss:20b')]:
            selected=self.selected(name)
            bound=bind_bundle(original,self.root/name,'test task','context')
            review=(bound/'recipes/quality-reviewer.yaml').read_bytes()
            profiles.bind(bound,selected)
            recipe=yaml.safe_load((bound/'recipes/lead-developer.yaml').read_text())
            self.assertEqual(recipe['settings']['goose_provider'],'ollama');self.assertEqual(recipe['settings']['goose_model'],model)
            self.assertEqual((bound/'recipes/quality-reviewer.yaml').read_bytes(),review)
            self.assertEqual(recipe['extensions'],yaml.safe_load((original/'recipes/lead-developer.yaml').read_text())['extensions'])
        self.assertEqual(digest_tree(original),before)

    def test_profile_edits_do_not_change_selected_work_and_tampering_is_rejected(self):
        selected=self.selected();self.runtime.write_text(self.runtime.read_text().replace('qwen3.8:27b-q4_K_M','gpt-oss:20b'))
        self.assertEqual(selected['model'],'qwen3.8:27b-q4_K_M')
        self.assertEqual(self.selected()['model'],'gpt-oss:20b')
        selected['model']='different'
        with self.assertRaisesRegex(ValueError,'snapshot changed'):profiles.validate(selected)

    def test_local_environment_keeps_output_openended_context_and_endpoint(self):
        selected=self.selected();env=profiles.apply_environment({'GOOSE_MAX_TOKENS':'8192'},selected,'chatgpt_codex','native-model')
        self.assertEqual(env['GOOSE_INPUT_LIMIT'],'32768');self.assertNotIn('GOOSE_MAX_TOKENS',env)
        self.assertEqual(env['GOOSE_AUTO_COMPACT_THRESHOLD'],'0.875');self.assertEqual(env['OLLAMA_HOST'],'http://127.0.0.1:11434')
        with self.assertRaisesRegex(ValueError,'distinct local coordinator'):profiles.apply_environment({},selected,'ollama','different-model')
        original={'GOOSE_INPUT_LIMIT':'65536'};self.assertIs(profiles.apply_environment(original,None,'chatgpt_codex','native'),original)

    def test_native_choices_remain_explicit_and_local_endpoints_are_not_external(self):
        self.assertEqual(self.selected('codex')['provider'],'codex-acp');self.assertEqual(self.selected('claude')['provider'],'claude-acp')
        self.runtime.write_text(self.runtime.read_text().replace('http://127.0.0.1:11434','https://example.org'))
        self.mock.reset_mock()
        with self.assertRaisesRegex(ValueError,'loopback'):self.selected()
        self.mock.assert_not_called()

    def lifecycle(self,selected):
        artifacts=Artifacts(self.project,'work')
        context=project_context(self.project);context['implementation_profile']=selected
        initial={'work_id':'work','job_id':'job','workspace':str(self.project),'request':'test','brief_ref':artifacts.publish('briefs','brief',BRIEF),'context_ref':artifacts.publish('contexts','project',context),'budget_seconds':600,'runtime_options':{'implementation_profile':selected}}
        harness=Harness();seen=[];original=harness.implement
        def implement(state):seen.append(dict(state));return original(state)
        harness.implement=implement
        cm=SqliteSaver.from_conn_string(str(self.root/'state.sqlite'));saver=cm.__enter__();self.addCleanup(cm.__exit__,None,None,None)
        graph=build(artifacts,harness,lambda _: {'passed':True}).compile(checkpointer=saver)
        config={'configurable':{'thread_id':'work'},'recursion_limit':100}
        return graph,config,artifacts,initial,seen

    def test_real_graph_approval_seals_profile_and_delivery_receives_identity(self):
        selected=self.selected();graph,config,artifacts,initial,seen=self.lifecycle(selected)
        paused=graph.invoke(initial,config)
        self.assertEqual(paused['__interrupt__'][0].value['implementation_profile'],selected)
        result=graph.invoke(Command(resume={'action':'approve','actor':'tester','brief_ref':initial['brief_ref']}),config)
        self.assertEqual(result['lifecycle_phase'],'closed')
        self.assertEqual(seen[0]['implementation_profile_digest'],selected['sha256'])
        self.assertIn(selected['sha256'],seen[0]['project_context'])
        self.assertEqual(artifacts.read(result['approval_ref'])['payload']['implementation_profile'],selected)

    def test_graph_refuses_replaced_profile_before_implementation(self):
        selected=self.selected();graph,config,artifacts,initial,seen=self.lifecycle(selected)
        graph.invoke(initial,config)
        graph.update_state(config,{'runtime_options':{'implementation_profile':self.selected('fast')}})
        with self.assertRaisesRegex(ArtifactError,'profile changed'):
            graph.invoke(Command(resume={'action':'approve','actor':'tester','brief_ref':initial['brief_ref']}),config)
        self.assertFalse(seen)

    def test_preflight_loopback_grant_does_not_modify_worker_sandbox(self):
        selected=self.selected();sandbox=self.root/'worker.sb';sandbox.write_text('(version 1)\n(deny network*)\n')
        before=sandbox.read_bytes();scope=profiles.preflight_scope(sandbox,self.root,selected)
        self.assertEqual(sandbox.read_bytes(),before)
        self.assertIn('localhost:11434',scope.read_text())
        self.assertIsNone(profiles.preflight_scope(sandbox,self.root,None))

    def test_cli_creation_exposes_and_persists_explicit_profile_only(self):
        import contextlib,io
        from poc import glg
        selected=self.selected()
        args=['--project',str(self.project),'--work','selected','create','--request','scope work','--implementation-profile','correct']
        capture=io.StringIO()
        with patch.object(glg,'ROOT',self.root),patch('poc.implementation_profiles.resolve',return_value=selected),contextlib.redirect_stdout(capture):
            glg.main(args)
        report=json.loads(capture.getvalue());self.assertEqual(report['implementation_profile'],selected)
        state_dir=glg.storage(self.project,'selected')
        with patch.object(glg,'ROOT',self.root):state_dir=glg.storage(self.project,'selected')
        with SqliteSaver.from_conn_string(str(state_dir/'workflow.sqlite')) as saver:
            values=saver.get({'configurable':{'thread_id':'selected'}})['channel_values']
        self.assertEqual(values['runtime_options']['implementation_profile'],selected)
        self.assertEqual(values['runtime_options']['provider'],'chatgpt_codex')
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            glg.main(['--project',str(self.project),'--work','selected','resume','--implementation-profile','fast'])

    def test_actual_job_binds_selected_worker_only_and_refuses_identity_changes(self):
        from poc import goose_job
        from poc.contracts import task_input_digest
        from poc.provider_preflight import PreflightError
        selected=self.selected();(self.root/'runtime').mkdir()
        state={'task':'fixture','workspace':str(self.project),'project_context':'approved fixture','job_id':'job','implementation_profile_digest':selected['sha256']}
        state['inputs']=task_input_digest(state['task'],self.project,state['project_context'])
        job=goose_job.GooseJob(provider='chatgpt_codex',model='gpt-5.6-sol',role_bundle=ROOT/'role-bundle',implementation_profile=selected)
        observed=[]
        def prepared(workspace,run_dir,bundle,**options):
            recipe=yaml.safe_load((bundle/'recipes/lead-developer.yaml').read_text())
            observed.append((recipe['settings'],options))
            return self.root/'scope.sb',{}
        with patch.object(goose_job,'ROOT',self.root),patch('poc.knowledge_tools.require_ready'),patch('poc.native_runtime.prepare',side_effect=prepared),patch('poc.provider_preflight.check',side_effect=PreflightError('scope_required','fixture stops before inference')),patch('poc.goose_job.subprocess.Popen') as launch:
            for kind in ['implement','review']:
                result=job._run_impl(state,kind,'fixture prompt');self.assertFalse(result['submitted'])
            changed={**state,'implementation_profile_digest':'changed'}
            result=job._run_impl(changed,'implement','fixture prompt')
            self.assertIn('approved work configuration',result['reason']);launch.assert_not_called()
        self.assertEqual(observed[0][0]['goose_provider'],'ollama');self.assertEqual(observed[0][0]['goose_model'],selected['model'])
        self.assertEqual(observed[0][1]['implementation_profile'],selected)
        self.assertEqual(observed[1][0]['goose_provider'],'codex-acp');self.assertNotIn('implementation_profile',observed[1][1])

    def test_persistent_positive_override_is_refused_instead_of_hiding_a_cap(self):
        selected=self.selected();goose=self.root/'goose';goose.mkdir()
        config=goose/'config.yaml';config.write_text('GOOSE_MAX_TOKENS: 2048\n')
        before=config.read_bytes()
        with self.assertRaisesRegex(ValueError,'Persistent Goose output override'):
            profiles.apply_environment({'GOOSE_PATH_ROOT':str(goose)},selected,'chatgpt_codex','native')
        self.assertEqual(config.read_bytes(),before)
