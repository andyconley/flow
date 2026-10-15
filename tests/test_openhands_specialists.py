"""Regression coverage for stock specialist factories and inline model routing."""
import os
import re
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
os.environ.setdefault('OPENHANDS_SUPPRESS_BANNER', '1')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
from openhands_config import select, RuntimeConfigurationError
from openhands_runtime import build_agent, probe


@unittest.skipUnless(probe()['ready'], 'isolated pinned SDK required')
class SpecialistTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / '.flow/agents').mkdir(parents=True)
        for role in ('coordinator', 'worker', 'native'):
            (self.root / f'.flow/agents/{role}.md').write_text(f'# {role}\nCustom {role} specialist instructions.\n')
        self.environment = patch.dict(os.environ, {'OH_PERSISTENCE_DIR': str(self.root / 'sdk-settings')})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.profile_directory = patch('openhands.sdk.llm.llm_profile_store._DEFAULT_PROFILE_DIR', self.root / 'profiles')
        self.profile_directory.start()
        self.addCleanup(self.profile_directory.stop)
        self.config = {'default_profile': 'local', 'profiles': {
            'local': {'kind': 'local', 'model': 'openai/initial', 'base_url': 'http://localhost:8000/v1'},
            'other': {'kind': 'local', 'model': 'openai/other', 'base_url': 'http://localhost:8001/v1'},
            'native': {'kind': 'codex', 'permission_requests': 'stock-openhands', 'session_mode': 'read-only'}},
            'roles': {'coordinator': {'specialists': ['worker', 'native']},
                      'worker': {'specialists': []}, 'native': {'profile': 'native'}}}

    def build(self, profile=None):
        with patch('openhands_config.load_config', return_value=self.config):
            return build_agent(select(self.root, 'implement', 'coordinator', profile, config=self.config), self.root)

    @staticmethod
    def factories(agent):
        from openhands.sdk.subagent import get_agent_factory
        return {name: get_agent_factory(key).factory_func for name, key in
                re.findall(r'([\w-]+): use task subagent_type=(\S+)', agent.agent_context.system_message_suffix)}

    def test_mixed_roster_custom_roles_and_active_model_inheritance(self):
        from openhands.sdk.agent import ACPAgent
        parent = self.build()
        factories = self.factories(parent)
        active = parent.llm.model_copy(update={'model': 'openai/switched'})
        with patch('openhands_config.load_config', return_value=self.config):
            child = factories['worker'](active)
            native = factories['native'](active)
        self.assertEqual(child.llm.model, 'openai/switched')
        self.assertIn('Custom worker specialist instructions.', child.agent_context.system_message_suffix)
        self.assertIsInstance(native, ACPAgent)
        self.assertEqual(native.acp_session_mode, 'read-only')

    def test_explicit_child_binding_wins_and_registry_changes(self):
        parent = self.build()
        old = self.factories(parent)['worker']
        self.config['roles']['worker']['profile'] = 'other'
        rebound = self.build()
        new = self.factories(rebound)['worker']
        self.assertIsNot(old, new)
        with patch('openhands_config.load_config', return_value=self.config):
            self.assertEqual(new(parent.llm).llm.model, 'openai/other')

    def test_sdk_restricted_scope_still_rejects_native(self):
        from openhands.sdk import Conversation
        from openhands.sdk.subagent.scope import SubAgentScope
        from openhands.sdk.subagent import get_agent_factory
        from openhands.tools.task.manager import TaskManager
        agent = self.build()
        key = re.search(r'native: use task subagent_type=(\S+)', agent.agent_context.system_message_suffix)[1]
        parent = Conversation(agent=agent, workspace=self.root, visualizer=None)
        self.addCleanup(parent.close)
        manager = TaskManager(sub_agent_scope=SubAgentScope(tools=True))
        manager.attach_parent(parent)
        with self.assertRaisesRegex(ValueError, 'tools cannot be checked'):
            manager._get_sub_agent_from_factory(get_agent_factory(key))

    def routing(self):
        self.config['roles']['coordinator']['model_routing'] = {
            'classifier_profile': 'local', 'categories': [{'description': 'Coding tasks', 'profile': 'other'}]}

    def test_stock_classifier_switch_and_explicit_selection(self):
        from openhands.sdk import Conversation
        from openhands.sdk.llm import Message, TextContent
        from openhands.sdk.tool.builtins.classify_and_switch_llm import ClassifyAndSwitchLLMTool, ClassifyAndSwitchLLMAction
        self.routing()
        agent = self.build()
        tool = next(t for t in agent.tools if t.name == ClassifyAndSwitchLLMTool.__name__)
        parent = Conversation(agent=agent, workspace=self.root, persistence_dir=self.root / 'history', visualizer=None)
        self.addCleanup(parent.close)
        parent.send_message('Implement a parser')
        response = SimpleNamespace(message=Message(role='assistant', content=[TextContent(text='1')]))
        with patch('openhands.sdk.llm.LLM.completion', return_value=response):
            result = ClassifyAndSwitchLLMTool.create(**tool.params)[0].executor(ClassifyAndSwitchLLMAction(), parent)
        self.assertFalse(result.is_error, result)
        self.assertEqual(parent.agent.llm.model, 'openai/other')
        explicit = self.build('local')
        self.assertNotIn(ClassifyAndSwitchLLMTool.__name__, [t.name for t in explicit.tools])
        original = select(self.root, 'implement', 'coordinator', config=self.config)
        self.assertNotEqual(original.fingerprint(), replace(original, profile_override=True).fingerprint())

    def test_native_routing_rejected_with_delegation_guidance(self):
        self.routing()
        self.config['roles']['coordinator']['model_routing']['categories'][0]['profile'] = 'native'
        with self.assertRaisesRegex(RuntimeConfigurationError, 'use a specialist'):
            self.build()

    def test_unacknowledged_native_child_uses_interactive_proxy(self):
        self.config['profiles']['native'].pop('permission_requests')
        parent = self.build()
        child = self.factories(parent)['native'](parent.llm)
        self.assertIn('acp_permissions.py', child.acp_command[1])
        self.assertEqual(child.acp_session_mode, 'read-only')

    def test_nonrouting_fingerprint_preserves_release_session_bindings(self):
        import hashlib
        import json
        selection = select(self.root, 'implement', 'coordinator', config=self.config)
        legacy = {'role': selection.role, 'profile': selection.profile, 'provider': selection.provider,
                  'role_text': selection.role_file.read_text(), 'options': selection.role_options,
                  'workspace': selection.workspace}
        self.assertEqual(selection.fingerprint(), hashlib.sha256(json.dumps(legacy, sort_keys=True).encode()).hexdigest())

    def test_routing_target_change_updates_session_binding(self):
        self.routing()
        first = select(self.root, 'implement', 'coordinator', config=self.config).fingerprint()
        self.config['profiles']['other']['model'] = 'openai/replacement'
        second = select(self.root, 'implement', 'coordinator', config=self.config).fingerprint()
        self.assertNotEqual(first, second)

    def test_explicit_native_stage_selection_preserves_whole_stage_support(self):
        from openhands.sdk.agent import ACPAgent
        self.routing()
        agent = self.build('native')
        self.assertIsInstance(agent, ACPAgent)
        self.assertEqual(agent.acp_session_mode, 'read-only')

    def test_legacy_implicit_leaf_identifiers_remain_callable(self):
        import hashlib
        from openhands.sdk.subagent import get_agent_factory
        self.config['roles']['worker'].pop('specialists')
        parent = self.build()
        child = select(self.root, 'implement', 'worker', 'local', config=self.config)
        legacy = replace(child, role_options={**child.role_options, 'specialists': []})
        key = f"worker-{hashlib.sha256((str(self.root.resolve()) + legacy.fingerprint()).encode()).hexdigest()[:16]}"
        with patch('openhands_config.load_config', return_value=self.config):
            resumed = get_agent_factory(key).factory_func(parent.llm)
        self.assertEqual(resumed.llm.model, parent.llm.model)
        self.assertIn('native: use task', resumed.agent_context.system_message_suffix)

    def test_nested_skill_packages_keep_references_out_of_permanent_context(self):
        package = self.root / '.agents/skills/synced/bundle/nested-skill'
        (package / 'references').mkdir(parents=True)
        (package / 'SKILL.md').write_text('---\nname: nested-skill\ndescription: A custom nested skill\n---\nUse the reference only when needed.\n')
        (package / 'references/example.md').write_text('UNRELATED_EXAMPLE_SHOULD_NOT_BE_PERMANENT_CONTEXT')
        (self.root / 'AGENTS.md').write_text('Project instructions must remain available.')
        agent = self.build()
        skills = {skill.name: skill for skill in agent.agent_context.skills}
        self.assertIn('nested-skill', skills)
        self.assertTrue(skills['nested-skill'].is_agentskills_format)
        self.assertTrue(any('Project instructions must remain available.' in skill.content for skill in skills.values()))
        self.assertFalse(any('UNRELATED_EXAMPLE_SHOULD_NOT_BE_PERMANENT_CONTEXT' in skill.content for skill in skills.values()))
        self.assertTrue((package / 'references/example.md').is_file())

    def test_sdk_project_skill_precedence_over_user_collection(self):
        home = self.root / 'fake-home'
        user_package = home / '.agents/skills/shared-skill'
        project_package = self.root / '.openhands/skills/shared-skill'
        for package, body in ((user_package, 'User version'), (project_package, 'Project version')):
            package.mkdir(parents=True)
            (package / 'SKILL.md').write_text(f'---\nname: shared-skill\ndescription: A shared skill\n---\n{body}\n')
        with patch('paths.HOME', home):
            agent = self.build()
        skill = next(skill for skill in agent.agent_context.skills if skill.name == 'shared-skill')
        self.assertIn('Project version', skill.content)
        self.assertNotIn('User version', skill.content)
        self.assertFalse(agent.agent_context.load_project_skills)
        self.config['workspace'] = {'kind': 'remote', 'host': 'http://localhost:8787'}
        self.config['roles']['coordinator']['specialists'] = []
        remote = self.build()
        self.assertTrue(remote.agent_context.load_project_skills)

    def test_explicit_empty_profiles_are_rejected_at_every_precedence_level(self):
        for invalid in ('', None, 42):
            with self.subTest(specialist_profile=invalid):
                self.config['roles']['worker']['profile'] = invalid
                with self.assertRaisesRegex(RuntimeConfigurationError, 'invalid profile'):
                    self.build()
        self.config['roles']['worker'].pop('profile')
        with self.assertRaisesRegex(RuntimeConfigurationError, 'invalid profile'):
            self.build('')
        self.config['stages'] = {'implement': {'profile': ''}}
        with self.assertRaisesRegex(RuntimeConfigurationError, 'invalid profile'):
            self.build()
        self.assertEqual(self.build('local').llm.model, 'openai/initial')

    def test_stock_switch_and_inherited_child_keep_safe_candidate_condenser_caps(self):
        from openhands.sdk import Conversation
        from openhands.sdk.llm import Message, TextContent
        from openhands.sdk.tool.builtins.classify_and_switch_llm import ClassifyAndSwitchLLMTool, ClassifyAndSwitchLLMAction
        self.routing()
        self.config['profiles']['local'].update(max_input_tokens=65536, max_output_tokens=8192, condenser_max_tokens=57344)
        self.config['profiles']['other'].update(max_input_tokens=32768, max_output_tokens=8192, condenser_max_tokens=24576)
        agent = self.build()
        self.assertEqual(agent.condenser.max_tokens, 24576)
        self.assertEqual(self.build('local').condenser.max_tokens, 57344)
        parent = Conversation(agent=agent, workspace=self.root, persistence_dir=self.root / 'history', visualizer=None)
        self.addCleanup(parent.close)
        parent.send_message('Implement a parser')
        tool = next(t for t in agent.tools if t.name == ClassifyAndSwitchLLMTool.__name__)
        response = SimpleNamespace(message=Message(role='assistant', content=[TextContent(text='1')]))
        with patch('openhands.sdk.llm.LLM.completion', return_value=response):
            result = ClassifyAndSwitchLLMTool.create(**tool.params)[0].executor(ClassifyAndSwitchLLMAction(), parent)
        self.assertFalse(result.is_error, result)
        self.assertEqual(parent.agent.condenser.llm.model, 'openai/other')
        self.assertEqual(parent.agent.condenser._effective_max_tokens(parent.agent.llm), 24576)
        with patch('openhands_config.load_config', return_value=self.config):
            child = self.factories(agent)['worker'](parent.agent.llm)
        self.assertEqual(child.condenser.max_tokens, 24576)
        self.assertEqual(child.llm.model, 'openai/other')
        parent.switch_llm(agent.llm)
        self.assertEqual(parent.agent.condenser._effective_max_tokens(parent.agent.llm), 24576)

    def test_fresh_process_restores_routed_model_and_current_credentials(self):
        import json
        import subprocess
        from uuid import uuid4
        from openhands_runtime import conversation, local_llm
        self.routing()
        self.config['profiles']['other'].update(api_key_env='FLOW_LOCAL_TEST_TOKEN', max_input_tokens=32768,
                                              max_output_tokens=8192, condenser_max_tokens=24576)
        selection = select(self.root, 'implement', 'coordinator', config=self.config)
        identifier = uuid4()
        persistence = self.root / 'history'
        with patch('openhands_config.load_config', return_value=self.config), patch.dict(os.environ, {'FLOW_LOCAL_TEST_TOKEN': 'first-test-key'}):
            with conversation(selection, self.root, persistence, identifier, lambda event: None) as session:
                target = local_llm(select(self.root, 'implement', 'coordinator', 'other', config=self.config))
                session.switch_llm(target.model_copy(update={'usage_id': 'profile:other'}))
        config_file = self.root / 'config.json'
        config_file.write_text(json.dumps(self.config))
        code = """
import json, os, sys
from pathlib import Path
from uuid import UUID
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from openhands_config import select
from openhands_runtime import conversation
root = Path(sys.argv[2])
config = json.loads((root / 'config.json').read_text())
selection = select(root, 'implement', 'coordinator', config=config)
with patch('openhands_config.load_config', return_value=config):
    with conversation(selection, root, root / 'history', UUID(sys.argv[3]), lambda event: None) as session:
        assert session.agent.llm.model == 'openai/other'
        assert session.agent.llm.effective_max_input_tokens == 32768
        assert session.agent.condenser.max_tokens == 24576
        assert session.agent.llm.api_key.get_secret_value() == os.environ['FLOW_LOCAL_TEST_TOKEN']
        print('fresh process restored active profile and current credential')
"""
        environment = {**os.environ, 'OH_PERSISTENCE_DIR': str(self.root / 'fresh-sdk-settings'),
                       'FLOW_LOCAL_TEST_TOKEN': 'current-test-key'}
        result = subprocess.run([sys.executable, '-c', code, str(Path(__file__).resolve().parents[1] / 'cli'),
                                 str(self.root), str(identifier)], env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('fresh process restored active profile', result.stdout)

    def test_sdk_remote_definition_round_trip_cannot_preserve_acp_factory(self):
        from openhands.sdk import Agent
        from openhands.sdk.agent import ACPAgent
        from openhands.sdk.subagent import get_agent_factory
        from openhands.sdk.subagent.schema import AgentDefinition
        from openhands.sdk.subagent.registry import agent_definition_to_factory
        parent = self.build()
        key = re.search(r'native: use task subagent_type=(\S+)', parent.agent_context.system_message_suffix)[1]
        factory = get_agent_factory(key)
        self.assertIsInstance(factory.factory_func(parent.llm), ACPAgent)
        wire = AgentDefinition.model_validate(factory.definition.model_dump(mode='json'))
        reconstructed = agent_definition_to_factory(wire, work_dir=self.root)(parent.llm)
        self.assertIsInstance(reconstructed, Agent)
        self.assertNotIsInstance(reconstructed, ACPAgent)
        self.config['workspace'] = {'kind': 'remote', 'host': 'http://localhost:8787'}
        with self.assertRaisesRegex(RuntimeConfigurationError, 'SDK 1.54 remote transport'):
            self.build()
        self.config['roles']['coordinator']['specialists'] = []
        self.assertIsInstance(self.build(), Agent)
