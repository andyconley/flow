"""Offline coverage for initial expertise-search instructions on delegated roles."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

from poc.role_renderer import bind_bundle
from poc.runtime_env import goose_binary

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'role-bundle'
TASK = 'Assess the approved persistence boundary. Literal {{ 9 * 9 }} stays literal.'
CONTEXT = 'Preserve compatibility and the approved role boundaries.'
REQUIRED = (
    'before beginning substantive task work, call search_cards',
    'your own specialist role as the role filter',
    'actual approved assignment and relevant project context',
    'Review the returned guidance and use it where applicable',
    'successful search returns no relevant guidance',
    'retrieval fails, report that failure explicitly',
    'do not describe it as no relevant results or claim successful retrieval',
    'further search_cards queries and traverse_cards',
)


class KnowledgeInstructionBindingTests(unittest.TestCase):
    def bind(self, root, configured=True):
        knowledge = root / 'knowledge'
        if configured:
            knowledge.mkdir()
            for name in ('settings.json', 'CURRENT.json'):
                (knowledge / name).write_text('{}')
        with patch('poc.knowledge.home', return_value=knowledge):
            return bind_bundle(SOURCE, root / 'bound', TASK, CONTEXT)

    def test_every_role_and_acp_prompt_requires_initial_task_specific_search(self):
        before = {p.relative_to(SOURCE): p.read_bytes()
                  for p in SOURCE.rglob('*') if p.is_file()}
        with tempfile.TemporaryDirectory() as temporary:
            bound = self.bind(Path(temporary))
            recipes = sorted((bound / 'recipes').glob('*.yaml'))
            self.assertEqual({p.stem for p in recipes},
                             {p.stem for p in (SOURCE / 'recipes').glob('*.yaml')})
            self.assertEqual(len(recipes), 13)
            for path in recipes:
                with self.subTest(role=path.stem):
                    original = yaml.safe_load((SOURCE / 'recipes' / path.name).read_text())
                    recipe = yaml.safe_load(path.read_text())
                    for phrase in REQUIRED:
                        self.assertIn(phrase, recipe['instructions'])
                    self.assertIn(original['instructions'], recipe['instructions'])
                    for key in ('extensions', 'response'):
                        self.assertEqual(recipe[key], original[key])
                    for key in ('goose_provider', 'goose_model', 'temperature'):
                        self.assertEqual(recipe['settings'].get(key),
                                         original['settings'].get(key))
                    defaults = {p['key']: p['default'] for p in recipe['parameters']}
                    self.assertEqual(defaults['task'], TASK)
                    self.assertEqual(defaults['project_context'], CONTEXT)
                    if recipe['settings']['goose_provider'].endswith('-acp'):
                        for phrase in REQUIRED:
                            self.assertIn(phrase, recipe['prompt'])
                        self.assertIn('without nested delegation', recipe['prompt'])
        after = {p.relative_to(SOURCE): p.read_bytes()
                 for p in SOURCE.rglob('*') if p.is_file()}
        self.assertEqual(after, before)

    def test_unconfigured_knowledge_keeps_existing_binding_behavior(self):
        with tempfile.TemporaryDirectory() as temporary:
            bound = self.bind(Path(temporary), configured=False)
            for path in (bound / 'recipes').glob('*.yaml'):
                recipe = yaml.safe_load(path.read_text())
                self.assertNotIn('Maintained knowledge:', recipe['instructions'])

    @unittest.skipUnless(goose_binary().is_file(), 'locked Goose fixture unavailable')
    def test_real_goose_renders_requirement_and_literal_task_for_every_role(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bound = self.bind(root)
            env = dict(os.environ, GOOSE_PATH_ROOT=str(root / 'goose'),
                       GOOSE_DISABLE_KEYRING='1', HOME=str(root / 'home'))
            Path(env['HOME']).mkdir()
            for path in sorted((bound / 'recipes').glob('*.yaml')):
                with self.subTest(role=path.stem):
                    result = subprocess.run(
                        [str(goose_binary()), 'run', '--recipe', str(path), '--render-recipe'],
                        cwd=root, env=env, capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    recipe = yaml.safe_load(result.stdout)
                    for phrase in REQUIRED:
                        self.assertIn(phrase, recipe['instructions'])
                    self.assertIn(TASK, recipe['instructions'])
                    self.assertIn(CONTEXT, recipe['instructions'])
                    if recipe['settings']['goose_provider'].endswith('-acp'):
                        for phrase in REQUIRED:
                            self.assertIn(phrase, recipe['prompt'])
                        self.assertIn(TASK, recipe['prompt'])
                        self.assertIn(CONTEXT, recipe['prompt'])


if __name__ == '__main__':
    unittest.main()
