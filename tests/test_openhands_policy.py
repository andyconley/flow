"""Offline policy/dispatch integration. No OAuth, native processes or model sends."""
import os
os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
os.environ.setdefault('OPENHANDS_SUPPRESS_BANNER', '1')
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
import openhands_config as config
from openhands_policy import specialist_selections


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.overlay = self.root / 'user'
        self.overlay.mkdir()
        self.cfg = config.load_config(self.root, self.overlay)

    def select(self):
        return config.select(self.root, 'implement', config=self.cfg, user_overlay=self.overlay)

    def test_default_coordinator_and_per_role_models(self):
        parent = self.select()
        self.assertEqual(parent.provider['kind'], 'openai-subscription')
        self.assertEqual(parent.provider['model'], 'gpt-5.6-terra')
        children = specialist_selections(self.root, parent, self.cfg, user_overlay=self.overlay)
        self.assertEqual(children['lead-developer'].provider['model'], 'gpt-5.6-terra')
        self.assertEqual(children['quality-reviewer'].provider['model'], 'opus')
        self.assertEqual(children['tech-writer'].provider['model'], 'haiku')
        self.assertTrue(all(c.role_options['specialists'] == [] for c in children.values()))

    def test_override_mixes_providers_and_changes_binding(self):
        old = self.select().fingerprint()
        self.cfg['roles'] = {'test-engineer': {'profile': 'codex', 'context': ['extra.md']}}
        parent = self.select()
        children = specialist_selections(self.root, parent, self.cfg, user_overlay=self.overlay)
        self.assertEqual(children['test-engineer'].provider['kind'], 'codex')
        self.assertNotEqual(parent.fingerprint(), old)
        self.cfg['profiles']['codex']['model'] = 'custom'
        self.assertEqual(specialist_selections(self.root, self.select(), self.cfg,
            user_overlay=self.overlay)['test-engineer'].provider['model'], 'custom')

    def test_existing_default_and_stage_bindings_preserved(self):
        (self.overlay / 'runtime.toml').write_text('default_profile="codex"\n')
        loaded = config.load_config(self.root, self.overlay)
        self.assertNotIn('implement', loaded.get('stages', {}))
        selected = config.select(self.root, 'implement', config=loaded, user_overlay=self.overlay)
        self.assertEqual(selected.provider['kind'], 'codex')

    def test_policy_can_reorder_hosted_providers_without_model_choice(self):
        (self.overlay / 'flow.toml').write_text('[provider_selection]\nprovider_order=["ollama","codex","claude"]\n')
        children = specialist_selections(self.root, self.select(), self.cfg, user_overlay=self.overlay)
        self.assertEqual(children['lead-developer'].provider['kind'], 'codex')
        self.assertEqual(children['lead-developer'].provider['model'], 'gpt-5.6-terra')

    def test_no_eligible_policy_and_empty_roster_fail_closed(self):
        (self.overlay / 'flow.toml').write_text('[provider_selection]\nallowed_candidates=[]\n')
        with self.assertRaisesRegex(config.RuntimeConfigurationError, 'no policy-eligible'):
            self.select()
        (self.overlay / 'flow.toml').unlink()
        self.cfg['roles'] = {'lead-developer': {'specialists': []}}
        with self.assertRaisesRegex(config.RuntimeConfigurationError, 'at least one'):
            self.select()

    def test_checked_task_rejects_global_registry_and_provider_overrides(self):
        from openhands_accounting import register_policy_task_tool
        from openhands.sdk.tool import Tool, resolve_tool
        from openhands.tools.task.definition import TaskObservation
        from pydantic import ValidationError
        name = register_policy_task_tool()
        tool = resolve_tool(Tool(name=name, params={'bindings': {'test-engineer': 'fixed-factory'}}), SimpleNamespace())[0]
        with self.assertRaises(ValidationError):
            tool.action_type(prompt='test', subagent_type='test-engineer', profile='claude')
        denied = tool.executor(tool.action_type(prompt='test', subagent_type='general-purpose'))
        self.assertTrue(denied.is_error)
        delegate = Mock(return_value=TaskObservation.from_text(text='done', task_id='one', subagent='fixed-factory', status='completed'))
        tool.executor.delegate = delegate
        result = tool.executor(tool.action_type(prompt='test', subagent_type='test-engineer'))
        self.assertFalse(result.is_error)
        self.assertEqual(delegate.call_args.args[0].subagent_type, 'fixed-factory')
        denied = tool.executor(tool.action_type(prompt='test', subagent_type='test-engineer', resume='foreign-task'))
        self.assertTrue(denied.is_error)

    def test_coordinator_uses_sdk_agent_and_no_native_harness(self):
        from openhands_runtime import build_agent
        from openhands.sdk import Agent, LLM
        parent = self.select()
        llm = LLM(model='openai/test', api_key='offline')
        with patch('openhands_config.load_config', return_value=self.cfg), patch('openhands_runtime.specialist_selections', return_value=specialist_selections(self.root,parent,self.cfg,user_overlay=self.overlay)), patch('openhands.sdk.llm.auth.openai.create_subscription_llm_from_config', return_value=llm) as auth:
            agent = build_agent(parent, self.root)
        self.assertIsInstance(agent, Agent)
        self.assertEqual(len(agent.tools), 1)
        self.assertIn('bindings', agent.tools[0].params)
        self.assertEqual(auth.call_args.args[0].auth_type, 'subscription')
        self.assertEqual(auth.call_args.args[0].reasoning_effort, 'medium')

    def test_missing_login_and_native_coordinator_fail_before_stage_entry(self):
        import openhands_flow as flow
        import runstate
        from tests import verification_fixture
        from argparse import Namespace
        verification_fixture.prepare(self.root)
        args = Namespace(project_root=self.root, work_id='example', stage=None, disposition=[])
        flow.initialize(args)
        before = (self.root / '.flow/runs/example/run.json').read_bytes()
        args.stage = 'implement'
        args.role = args.profile = None
        with patch('openhands_config.load_config', return_value=self.cfg), patch('openhands_policy.subscription_readiness', return_value={'credential_file_present': False}), patch('openhands_runtime.conversation') as conversation:
            with self.assertRaisesRegex(config.RuntimeConfigurationError, 'sign-in required'):
                flow.execute(args)
            conversation.assert_not_called()
        self.assertEqual(before, (self.root / '.flow/runs/example/run.json').read_bytes())
        args.profile = 'claude'
        with patch('openhands_config.load_config', return_value=self.cfg):
            with self.assertRaisesRegex(config.RuntimeConfigurationError, 'SDK coordinator'):
                flow.execute(args)
        self.assertEqual(before, (self.root / '.flow/runs/example/run.json').read_bytes())

    def test_local_profile_derived_but_not_granted_sdk_eligibility(self):
        (self.overlay / 'flow.toml').write_text('[local_machine]\nmodel="llama3.1:8b"\n')
        cfg = config.load_config(self.root, self.overlay)
        self.assertEqual(cfg['profiles']['ollama']['model'], 'ollama_chat/llama3.1:8b')
        children = specialist_selections(self.root, self.select(), cfg, user_overlay=self.overlay)
        self.assertTrue(all(c.provider['kind'] in {'claude', 'codex'} for c in children.values()))
        cfg['roles'] = {'test-engineer': {'profile': 'ollama'}}
        children = specialist_selections(self.root, self.select(), cfg, user_overlay=self.overlay)
        self.assertEqual(children['test-engineer'].provider['kind'], 'local')
        self.assertNotIn('task', children['test-engineer'].role_options['tools'])

    def test_worker_override_cannot_replace_or_nest_coordinator(self):
        self.cfg['roles'] = {'lead-developer': {'profile': 'codex', 'policy_dispatch': True}}
        parent = self.select()
        self.assertEqual(parent.provider['kind'], 'openai-subscription')
        children = specialist_selections(self.root, parent, self.cfg, user_overlay=self.overlay)
        self.assertEqual(children['lead-developer'].provider['kind'], 'codex')
        self.assertNotIn('policy_dispatch', children['lead-developer'].role_options)

    def test_report_includes_resolved_implementation(self):
        report = config.wiring_report(self.root, self.overlay)
        self.assertEqual(report['implementation']['coordinator']['kind'], 'openai-subscription')
        self.assertEqual(report['implementation']['workers']['lead-developer']['model'], 'gpt-5.6-terra')

    def test_eligible_local_candidate_routes_by_tier(self):
        (self.overlay / 'flow.toml').write_text('[local_machine]\nmodel="local-tool-model"\ncontext_tokens=16384\n'
            '[[provider_candidates]]\ncandidate_id="ollama-approved"\nprovider="ollama"\n'
            'model="local-tool-model"\nenabled=true\ntier="working"\n'
            'operations=["edit"]\ncapabilities=["structured_output","structured_edit","sdk_tool_calling"]\n'
            '[[provider_candidates]]\ncandidate_id="codex-hosted"\nprovider="codex"\n'
            'model="ignored-native-catalog-model"\nenabled=true\ntier="judgment"\n'
            'operations=["edit"]\ncapabilities=["structured_output","structured_edit"]\n')
        cfg = config.load_config(self.root, self.overlay)
        parent = config.select(self.root, 'implement', config=cfg, user_overlay=self.overlay)
        children = specialist_selections(self.root, parent, cfg, user_overlay=self.overlay)
        self.assertEqual(children['lead-developer'].provider['kind'], 'local')
        self.assertEqual(children['quality-reviewer'].provider['kind'], 'codex')

    def test_explicit_claude_order_overrides_mixed_defaults(self):
        (self.overlay / 'flow.toml').write_text('[provider_selection]\nprovider_order=["ollama","claude","codex"]\n')
        children = specialist_selections(self.root, self.select(), self.cfg, user_overlay=self.overlay)
        self.assertTrue(all(c.provider['kind'] == 'claude' for c in children.values()))

    def test_short_local_context_is_visible_and_falls_back(self):
        (self.overlay / 'flow.toml').write_text('[local_machine]\nmodel="llama3.1:8b"\ncontext_tokens=8192\n')
        report = config.wiring_report(self.root, self.overlay)
        self.assertFalse(report['local_candidates'][0]['local_capability_eligible'])
        self.assertTrue(any('16384' in reason for reason in report['local_candidates'][0]['ineligibility_reasons']))
        self.assertEqual(report['implementation']['workers']['lead-developer']['profile'], 'codex')
        self.assertEqual(report['implementation']['workers']['quality-reviewer']['profile'], 'claude')

    def test_local_slot_and_failed_task_use_bound_hosted_fallback(self):
        import fcntl
        from openhands_accounting import register_policy_task_tool
        from openhands.sdk.tool import Tool, resolve_tool
        from openhands.tools.task.definition import TaskObservation
        with patch('pathlib.Path.home', return_value=self.root):
            tool = resolve_tool(Tool(name=register_policy_task_tool(), params={'bindings': {
                'lead-developer': {'primary': 'local-fixed', 'fallback': 'codex-fixed', 'local': True}}}), SimpleNamespace())[0]
            ok = TaskObservation.from_text(text='done', task_id='one', subagent='codex-fixed', status='completed')
            tool.executor.delegate = Mock(return_value=ok)
            (self.root / '.flow/state').mkdir(parents=True)
            with (self.root / '.flow/state/openhands-local-worker.lock').open('a') as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                tool.executor(tool.action_type(prompt='implement', subagent_type='lead-developer'))
                self.assertEqual(tool.executor.delegate.call_args.args[0].subagent_type, 'codex-fixed')
            failed = TaskObservation.from_text(text='failed with possible edits', task_id='two', subagent='local-fixed', status='error', is_error=True)
            tool.executor.delegate = Mock(return_value=failed)
            result = tool.executor(tool.action_type(prompt='implement', subagent_type='lead-developer'))
            self.assertIn('no automatic replay', result.text)
            self.assertEqual(tool.executor.delegate.call_count, 1)
            tool.executor.delegate = Mock(return_value=ok)
            tool.executor(tool.action_type(prompt='review partial edits and continue', subagent_type='lead-developer'))
            self.assertEqual(tool.executor.delegate.call_args.args[0].subagent_type, 'codex-fixed')

    def test_local_sdk_profile_forwards_actual_ollama_context(self):
        from openhands_runtime import local_llm
        self.cfg['profiles']['local'] = {'kind': 'local', 'model': 'ollama_chat/llama3.1:8b',
            'base_url': 'http://127.0.0.1:11434', 'max_input_tokens': 16384,
            'max_output_tokens': 2048, 'reasoning_effort': 'none'}
        selected = config.select(self.root, 'implement', 'lead-developer', 'local',
            config=self.cfg, user_overlay=self.overlay)
        llm = local_llm(selected)
        self.assertEqual(llm.max_input_tokens, 16384)
        self.assertEqual(llm.litellm_extra_body['options']['num_ctx'], 16384)
        self.assertEqual(llm.litellm_extra_body['options']['num_predict'], 2048)
        self.assertEqual(llm.reasoning_effort, 'none')
