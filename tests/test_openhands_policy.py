"""Offline policy/dispatch integration. No OAuth, native processes or model sends."""
import os
os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
os.environ.setdefault('OPENHANDS_SUPPRESS_BANNER', '1')
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
import openhands_config as config
from flowtoml import read_toml
from openhands_policy import specialist_selections


def _render_provider_candidates(candidates):
    """Serialize only a provider_candidates array back to TOML.

    Keeps fixtures scoped to the provider-candidate catalog under test instead
    of copying the whole framework manifest (which would also carry
    framework-owned sections like [agent_capabilities] and
    [session_model_profiles] into the overlay/project layers).
    """
    def render_value(value):
        if isinstance(value, bool):
            return 'true' if value else 'false'
        if isinstance(value, int):
            return str(value)
        if isinstance(value, str):
            return json.dumps(value)
        if isinstance(value, list):
            return '[' + ', '.join(render_value(item) for item in value) + ']'
        raise TypeError(f'unsupported provider_candidates value: {value!r}')
    blocks = []
    for candidate in candidates:
        lines = ['[[provider_candidates]]']
        lines.extend(f'{key} = {render_value(value)}' for key, value in candidate.items())
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks) + '\n'


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.overlay = self.root / 'user'
        self.overlay.mkdir()
        (self.overlay / 'flow.toml').write_text('[local_machine]\nmodel="llama3.1:8b"\ncontext_tokens=16384\n')
        self.cfg = config.load_config(self.root, self.overlay)

    def select(self):
        return config.select(self.root, 'implement', config=self.cfg, user_overlay=self.overlay)

    def test_default_coordinator_and_per_role_models(self):
        parent = self.select()
        self.assertEqual(parent.provider['kind'], 'local')
        self.assertEqual(parent.provider['model'], 'ollama_chat/llama3.1:8b')
        children = specialist_selections(self.root, parent, self.cfg, user_overlay=self.overlay)
        self.assertEqual(children['lead-developer'].provider['model'], 'ollama_chat/llama3.1:8b')
        self.assertEqual(children['lead-developer--codex-hosted'].provider['model'], 'gpt-5.6-terra')
        self.assertEqual(children['quality-reviewer'].provider['model'], 'opus')
        self.assertEqual(children['tech-writer--claude-hosted'].provider['model'], 'haiku')
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

    def test_existing_local_stage_preserves_machine_model_and_context(self):
        (self.overlay / 'runtime.toml').write_text('[stages.implement]\nprofile="studio"\n'
            '[profiles.studio]\nkind="local"\nmodel="ollama_chat/gemma4-26b-dev:latest"\n'
            'base_url="http://127.0.0.1:11434"\nmax_input_tokens=65536\n')
        selected = config.select(self.root, 'implement', user_overlay=self.overlay)
        self.assertEqual(selected.profile, 'studio')
        self.assertEqual(selected.provider['max_input_tokens'], 65536)
        self.assertTrue(selected.role_options['policy_dispatch'])
        self.assertTrue(selected.routing_profiles)

    def test_missing_local_configuration_fails_without_subscription_probe(self):
        (self.overlay / 'flow.toml').unlink()
        with patch('openhands_policy.subscription_readiness') as auth:
            report = config.wiring_report(self.root, self.overlay)
        auth.assert_not_called()
        self.assertIn("profile 'ollama' is not configured", report['implementation']['error'])

    def test_policy_can_reorder_hosted_providers_without_model_choice(self):
        parent = self.select()
        self.cfg['profiles'].pop('ollama')
        (self.overlay / 'flow.toml').write_text('[provider_selection]\nprovider_order=["ollama","codex","claude"]\n')
        children = specialist_selections(self.root, parent, self.cfg, user_overlay=self.overlay)
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
        auth.assert_not_called()
        self.assertEqual(agent.llm.model, 'ollama_chat/llama3.1:8b')
        self.assertEqual(agent.condenser.max_tokens, parent.provider['condenser_max_tokens'])

    def test_coordinator_keeps_explicit_skills_and_instructions_without_ambient_catalog(self):
        from dataclasses import replace
        from openhands_runtime import build_agent, _context
        from openhands.sdk.context import Skill
        from openhands.sdk.skills.trigger import PathTrigger, KeywordTrigger
        from openhands.sdk import Message, TextContent
        ambient = {f"ambient-{i}": Skill(name=f"ambient-{i}", content="Worker expertise",
            description=" ".join(f"topic{j}" for j in range(100)), is_agentskills_format=True)
            for i in range(79)}
        ambient['explicit-name'] = Skill(name='explicit-name', content='Named expertise',
            description='Required named skill', is_agentskills_format=True)
        ambient['user-guidance'] = Skill(name='user-guidance', content='Required user guidance')
        ambient['optional-trigger'] = Skill(name='optional-trigger', content='Optional expertise',
            trigger=KeywordTrigger(keywords=['optional']))
        rules = {'project-guidance': Skill(name='project-guidance', content='Required AGENTS guidance'),
            'scoped-rule': Skill(name='scoped-rule', content='Scoped instructions',
                                trigger=PathTrigger(paths=['src/**']))}
        explicit = self.root / 'explicit-path/SKILL.md'
        explicit.parent.mkdir()
        explicit.write_text('---\nname: explicit-path\ndescription: Required path skill\n---\nInstructions')
        (self.root / '.flow').mkdir()
        (self.root / '.flow/PROJECT.md').write_text('Required project context')
        parent = self.select()
        parent = replace(parent, role_options={**parent.role_options, 'skills': ['explicit-path/SKILL.md']})
        children = specialist_selections(self.root, parent, self.cfg, user_overlay=self.overlay)
        parent = replace(parent, routing_profiles={name: child.fingerprint() for name, child in children.items()})
        with patch('paths.HOME', self.root / 'empty-home'), patch('paths.USER_OVERLAY_DIR', self.overlay), \
             patch('openhands.sdk.skills.load_available_skills', side_effect=lambda root, **kw: dict(ambient if kw['include_user'] else rules)), \
             patch('openhands_runtime.role_context', return_value=({'skills': ['explicit-name']}, 'Required role instructions')), \
             patch('openhands_config.load_config', return_value=self.cfg), \
             patch('openhands_runtime.specialist_selections', return_value=children):
            agent = build_agent(parent, self.root)
            worker_context = _context(parent, self.root)
        names = {skill.name for skill in agent.agent_context.skills}
        self.assertEqual(names, {'explicit-name', 'explicit-path', 'user-guidance', 'project-guidance', 'scoped-rule'})
        self.assertTrue(set(ambient) <= {skill.name for skill in worker_context.skills})
        prompt = agent.agent_context.get_system_message_suffix()
        for text in ['Required role instructions', 'Required project context', 'Required user guidance', 'Required AGENTS guidance']:
            self.assertIn(text, prompt)
        self.assertNotIn('ambient-', prompt)
        self.assertFalse(agent.agent_context.load_user_skills)
        self.assertFalse(agent.agent_context.load_project_skills)
        small = agent.llm.get_token_count([Message(role='system', content=[TextContent(text=prompt)])])
        broad = agent.llm.get_token_count([Message(role='system', content=[TextContent(text=worker_context.get_system_message_suffix())])])
        self.assertLess(small, agent.condenser.max_tokens)
        self.assertGreater(broad, agent.condenser.max_tokens)

    def test_checked_task_schema_reloads_in_fresh_process(self):
        import subprocess
        from openhands_accounting import register_policy_task_tool, RoleTaskAction
        from openhands.sdk.tool import Tool, resolve_tool
        from openhands.sdk.event.llm_convertible import SystemPromptEvent
        from openhands.sdk import TextContent
        name = register_policy_task_tool()
        tool = resolve_tool(Tool(name=name, params={'bindings': {'lead-developer': 'fixed'}}), SimpleNamespace())[0]
        event = SystemPromptEvent(system_prompt=TextContent(text='Preserved coordinator instructions'), tools=[tool])
        saved = self.root / 'system-event.json'
        saved.write_text(event.model_dump_json())
        self.assertEqual(RoleTaskAction.__qualname__, 'RoleTaskAction')
        code = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from openhands_accounting import register_policy_task_tool, RoleTaskAction
register_policy_task_tool()
register_policy_task_tool()
from openhands.sdk.event.llm_convertible import SystemPromptEvent
from pydantic import ValidationError
original = Path(sys.argv[2]).read_bytes()
event = SystemPromptEvent.model_validate_json(original)
assert event.tools[0].action_type is RoleTaskAction
action = event.tools[0].action_type(prompt='Continue approved task', subagent_type='lead-developer')
assert action.subagent_type == 'lead-developer'
try:
    event.tools[0].action_type(prompt='Override', subagent_type='lead-developer', profile='codex')
except ValidationError:
    pass
else:
    raise AssertionError('provider override accepted after reload')
assert SystemPromptEvent.model_validate_json(event.model_dump_json()).tools[0].action_type is RoleTaskAction
assert Path(sys.argv[2]).read_bytes() == original
"""
        result = subprocess.run([sys.executable, '-c', code, str(Path(config.__file__).parent), str(saved)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_runtime_probe_module_stays_importable_without_sdk(self):
        import subprocess
        result = subprocess.run([sys.executable, '-S', '-c',
            'import sys; sys.path.insert(0, sys.argv[1]); import openhands_runtime',
            str(Path(config.__file__).parent)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

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
        self.cfg['profiles']['explicit-subscription'] = {'kind': 'openai-subscription'}
        self.cfg['stages']['implement']['profile'] = 'explicit-subscription'
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
        cfg['profiles']['ollama']['max_input_tokens'] = 16384
        children = specialist_selections(self.root, self.select(), cfg, user_overlay=self.overlay)
        self.assertEqual(children['test-engineer'].provider['kind'], 'local')
        self.assertNotIn('task', children['test-engineer'].role_options['tools'])

    def test_worker_override_cannot_replace_or_nest_coordinator(self):
        self.cfg['roles'] = {'lead-developer': {'profile': 'codex', 'policy_dispatch': True}}
        parent = self.select()
        self.assertEqual(parent.provider['kind'], 'local')
        children = specialist_selections(self.root, parent, self.cfg, user_overlay=self.overlay)
        self.assertEqual(children['lead-developer'].provider['kind'], 'codex')
        self.assertNotIn('policy_dispatch', children['lead-developer'].role_options)

    def test_same_role_exposes_all_three_provider_factories(self):
        from openhands_runtime import build_agent
        from openhands.sdk.subagent import get_agent_factory
        parent = self.select()
        children = specialist_selections(self.root, parent, self.cfg, user_overlay=self.overlay)
        targets = {f'lead-developer--{name}' for name in ('ollama-local', 'codex-hosted', 'claude-hosted')}
        self.assertTrue(targets <= children.keys())
        with patch('openhands_config.load_config', return_value=self.cfg), patch('openhands_runtime.specialist_selections', return_value=children):
            agent = build_agent(parent, self.root)
        bindings = agent.tools[0].params['bindings']
        with patch('openhands_runtime.build_agent', side_effect=lambda child, root: child):
            actual = []
            for target in sorted(targets):
                binding = bindings[target]
                key = binding['primary'] if isinstance(binding, dict) else binding
                actual.append(get_agent_factory(key).factory_func(agent.llm).provider['kind'])
        self.assertEqual(set(actual), {'local', 'claude', 'codex'})

    def test_disable_invalid_endpoint_and_tier_exclusions_are_visible(self):
        self.cfg['profiles']['ollama']['base_url'] = 'invalid'
        parent = config.Selection('lead-developer', 'ollama', {}, Path(__file__), {}, {})
        diagnostics = []
        workers = specialist_selections(self.root, parent, self.cfg, user_overlay=self.overlay, diagnostics=diagnostics)
        self.assertNotIn('lead-developer--ollama-local', workers)
        self.assertEqual(workers['lead-developer'].profile, 'codex')
        self.assertIn('base_url', str(diagnostics))
        self.cfg['profiles']['ollama']['base_url'] = 'http://localhost:11434'
        (self.root / '.flow').mkdir()
        (self.root / '.flow/flow.toml').write_text('[provider_selection]\ndisabled_candidates=["ollama-local"]\n')
        diagnostics = []
        workers = specialist_selections(self.root, parent, self.cfg, user_overlay=self.overlay, diagnostics=diagnostics)
        self.assertNotIn('lead-developer--ollama-local', workers)
        self.assertIn('candidate_disabled', str(diagnostics))

    def test_invalid_machine_is_reported_with_hosted_worker_choices(self):
        (self.overlay / 'flow.toml').write_text('[local_machine]\nmodel="local"\ncontext_tokens="bad"\n')
        report = config.wiring_report(self.root, self.overlay)
        self.assertIn('positive integer', report['local_configuration_error'])
        self.assertEqual(report['implementation']['workers']['lead-developer']['profile'], 'codex')
        self.assertIn('positive integer', str(report['implementation']['routing_decisions']))

    def test_project_catalog_cannot_silently_erase_user_disable(self):
        framework_candidates = read_toml(config.FRAMEWORK_ROLES.parent / 'flow.toml')['provider_candidates']
        disabled_candidates = [dict(candidate, enabled=False) if candidate.get('candidate_id') == 'ollama-local'
                                else candidate for candidate in framework_candidates]
        (self.overlay / 'flow.toml').write_text(_render_provider_candidates(disabled_candidates))
        (self.root / '.flow').mkdir()
        (self.root / '.flow/flow.toml').write_text(_render_provider_candidates(framework_candidates))
        parent = config.Selection('lead-developer', 'ollama', {}, Path(__file__), {}, {})
        workers = specialist_selections(self.root, parent, self.cfg, user_overlay=self.overlay)
        self.assertNotIn('lead-developer--ollama-local', workers)
        self.assertEqual(workers['lead-developer'].profile, 'codex')

    def test_native_default_and_explicit_interactive_override(self):
        selected = config.select(self.root, 'implement', 'test-engineer', 'codex', config=self.cfg, user_overlay=self.overlay)
        self.assertEqual(selected.provider['permission_requests'], 'stock-openhands')
        self.cfg['profiles']['codex']['permission_requests'] = 'interactive'
        selected = config.select(self.root, 'implement', 'test-engineer', 'codex', config=self.cfg, user_overlay=self.overlay)
        self.assertEqual(selected.provider['permission_requests'], 'interactive')

    def test_sdk_confirmation_only_changes_for_explicit_interactive_workspace(self):
        from dataclasses import replace
        from uuid import uuid4
        import openhands_runtime
        parent = self.select()
        with patch.object(openhands_runtime, 'build_agent'), patch('openhands.sdk.Conversation') as constructor:
            with openhands_runtime.conversation(parent, self.root, self.root / 'history', uuid4(), lambda _: None):
                pass
            constructor.return_value.set_confirmation_policy.assert_not_called()
            with openhands_runtime.conversation(replace(parent, workspace={'confirmation': 'always'}), self.root, self.root / 'history', uuid4(), lambda _: None):
                pass
            self.assertEqual(constructor.return_value.set_confirmation_policy.call_args.args[0].__class__.__name__, 'AlwaysConfirm')

    def test_resumed_session_forces_never_confirm_over_stale_persisted_policy(self):
        from uuid import uuid4
        import openhands_runtime
        from openhands.sdk.conversation.impl.local_conversation import LocalConversation
        parent = self.select()
        history = self.root / 'history'
        conversation_id = uuid4()
        persisted = Path(LocalConversation.get_persistence_dir(history, conversation_id))
        persisted.mkdir(parents=True)
        # Simulate a conversation whose persisted SDK state was serialized
        # under an old explicit AlwaysConfirm binding. Omitting the setter
        # alone would leave this stale value in effect on resume.
        (persisted / 'base_state.json').write_text('{"confirmation_policy": {"kind": "AlwaysConfirm"}}')
        with patch.object(openhands_runtime, 'build_agent'), patch('openhands.sdk.Conversation') as constructor:
            with openhands_runtime.conversation(parent, self.root, history, conversation_id, lambda _: None):
                pass
            self.assertEqual(constructor.return_value.set_confirmation_policy.call_args.args[0].__class__.__name__, 'NeverConfirm')

    def test_report_includes_resolved_implementation(self):
        report = config.wiring_report(self.root, self.overlay)
        self.assertEqual(report['implementation']['coordinator']['kind'], 'local')
        self.assertEqual(report['subscription'], {'required': False})
        self.assertEqual(report['implementation']['workers']['lead-developer']['model'], 'ollama_chat/llama3.1:8b')
        self.assertEqual(report['implementation']['workers']['lead-developer--codex-hosted']['model'], 'gpt-5.6-terra')

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
        parent = self.select()
        self.cfg['profiles'].pop('ollama')
        (self.overlay / 'flow.toml').write_text('[provider_selection]\nprovider_order=["ollama","claude","codex"]\n')
        children = specialist_selections(self.root, parent, self.cfg, user_overlay=self.overlay)
        self.assertTrue(all(child.provider['kind'] == 'claude' for name, child in children.items() if '--' not in name))
        self.assertIn('lead-developer--codex-hosted', children)

    def test_short_local_context_is_visible_and_falls_back(self):
        (self.overlay / 'flow.toml').write_text('[local_machine]\nmodel="llama3.1:8b"\ncontext_tokens=8192\n')
        report = config.wiring_report(self.root, self.overlay)
        self.assertFalse(report['local_candidates'][0]['local_capability_eligible'])
        self.assertTrue(any('16384' in reason for reason in report['local_candidates'][0]['ineligibility_reasons']))
        self.assertEqual(report['implementation']['workers']['lead-developer']['profile'], 'codex')
        self.assertEqual(report['implementation']['workers']['quality-reviewer']['profile'], 'claude')

    def test_coordinator_selects_alternate_after_busy_or_failed_task(self):
        import fcntl
        from openhands_accounting import register_policy_task_tool
        from openhands.sdk.tool import Tool, resolve_tool
        from openhands.tools.task.definition import TaskObservation
        with patch('pathlib.Path.home', return_value=self.root):
            tool = resolve_tool(Tool(name=register_policy_task_tool(), params={'bindings': {
                'lead-developer': {'primary': 'local-fixed', 'local': True},
                'lead-developer--codex': 'codex-fixed', 'lead-developer--claude': 'claude-fixed'}}), SimpleNamespace())[0]
            ok = TaskObservation.from_text(text='done', task_id='one', subagent='codex-fixed', status='completed')
            tool.executor.delegate = Mock(return_value=ok)
            (self.root / '.flow/state').mkdir(parents=True)
            with (self.root / '.flow/state/openhands-local-worker.lock').open('a') as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = tool.executor(tool.action_type(prompt='implement', subagent_type='lead-developer'))
                self.assertTrue(result.is_error)
                tool.executor.delegate.assert_not_called()
            failed = TaskObservation.from_text(text='failed with possible edits', task_id='two', subagent='local-fixed', status='error', is_error=True)
            tool.executor.delegate = Mock(return_value=failed)
            result = tool.executor(tool.action_type(prompt='implement', subagent_type='lead-developer'))
            self.assertIn('no automatic replay', result.text)
            self.assertEqual(tool.executor.delegate.call_count, 1)
            tool.executor.delegate = Mock(return_value=ok)
            tool.executor(tool.action_type(prompt='review partial edits and continue', subagent_type='lead-developer--codex'))
            self.assertEqual(tool.executor.delegate.call_args.args[0].subagent_type, 'codex-fixed')
            result = tool.executor(tool.action_type(prompt='resume as a different provider', subagent_type='lead-developer--claude', resume='one'))
            self.assertTrue(result.is_error)
            tool.executor(tool.action_type(prompt='independent review', subagent_type='lead-developer--claude'))
            self.assertEqual(tool.executor.delegate.call_args.args[0].subagent_type, 'claude-fixed')

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

    def test_user_enabled_unverified_local_can_implement_without_fabricated_capability(self):
        (self.overlay / 'flow.toml').write_text('[local_machine]\nmodel="llama3.1:8b"\ncontext_tokens=16384\n'
            '[[provider_candidates]]\ncandidate_id="local-user"\nprovider="ollama"\n'
            'model="llama3.1:8b"\nenabled=true\ntier="working"\noperations=["edit"]\n'
            'capabilities=["structured_edit"]\nsdk_tool_use="user-enabled-unverified"\n'
            '[[provider_candidates]]\ncandidate_id="codex-hosted"\nprovider="codex"\n'
            'enabled=true\ntier="judgment"\noperations=["edit"]\n')
        cfg = config.load_config(self.root, self.overlay)
        parent = config.select(self.root, 'implement', config=cfg, user_overlay=self.overlay)
        workers = specialist_selections(self.root, parent, cfg, user_overlay=self.overlay)
        self.assertEqual(workers['lead-developer'].provider['kind'], 'local')
        self.assertEqual(workers['lead-developer--codex-hosted'].profile, 'codex')
        report = config.wiring_report(self.root, self.overlay)['local_candidates'][0]
        self.assertTrue(report['local_capability_eligible'])
        self.assertEqual(report['tool_use_state'], 'user-enabled-unverified')
        self.assertIn('not verified', report['tool_use_verification'])
        from openhands_policy import local_eligibility
        self.assertTrue(local_eligibility({'sdk_tool_use': 'user-enabled-unverified'}, {'max_input_tokens':8192}))
        self.assertTrue(local_eligibility({'sdk_tool_use': 'typo'}, {'max_input_tokens':16384}))
