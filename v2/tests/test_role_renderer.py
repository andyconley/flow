import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import yaml

from poc.role_renderer import catalog, compose, render, write_bundle
from poc.runtime_env import goose_binary

ROOT = Path(__file__).resolve().parents[1]
FLOW = ROOT.parent
GOOSE = goose_binary()


class RoleRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lead = compose(FLOW, ROOT, 'lead-developer', 'codex')
        cls.review = compose(FLOW, ROOT, 'quality-reviewer', 'claude', stage='review')

    def test_canonical_role_and_composed_expertise_are_preserved(self):
        for composed in (self.lead, self.review):
            agent, recipe = render(composed, 'codex')
            self.assertIn(composed['body'], agent)
            self.assertIn(composed['body'], recipe['instructions'])
        for text in ('Plan a reversible delivery path', 'Plan in proportion to risk', 'Fowler', 'Required behavior:'):
            self.assertIn(text, self.lead['body'])
        self.assertIn('APPROVE | REQUEST CHANGES', self.review['body'])

    def test_project_and_user_precedence_reuses_flow_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, overlay = Path(tmp)/'project', Path(tmp)/'overlay'
            project.mkdir(); (overlay/'agents').mkdir(parents=True)
            user = overlay/'agents/lead-developer.md'
            original = Path(self.lead['source']).read_text()
            user.write_text(original + '\nUSER_OVERRIDE_MARKER\n')
            composed = compose(FLOW, project, 'lead-developer', 'codex', overlay)
            self.assertEqual(composed['source'], str(user.resolve()))
            self.assertIn('USER_OVERRIDE_MARKER', composed['body'])
            self.assertIn('Plan a reversible delivery path', composed['body'])
            path = project/'.flow/agents/lead-developer.md'; path.parent.mkdir(parents=True)
            path.write_text(original + '\nPROJECT_OVERRIDE_MARKER\n')
            composed = compose(FLOW, project, 'lead-developer', 'codex', overlay)
            self.assertEqual(composed['source'], str(path.resolve()))
            self.assertIn('PROJECT_OVERRIDE_MARKER', composed['body'])
            self.assertNotIn('USER_OVERRIDE_MARKER', composed['body'])
            self.assertIn('Plan a reversible delivery path', composed['body'])

    def test_task_context_is_separate_and_tools_are_equal(self):
        _, implement = render(self.lead, 'codex')
        _, review = render(self.review, 'claude', responsibility='review')
        self.assertEqual(implement['extensions'], review['extensions'])
        self.assertEqual(implement['settings']['max_turns'], review['settings']['max_turns'])
        for recipe in (implement, review):
            self.assertEqual({p['key'] for p in recipe['parameters']}, {'task', 'project_context'})
            self.assertIn('{{ project_context | indent(2) }}', recipe['instructions'])
            self.assertIn('{{ task | indent(2) }}', recipe['instructions'])
            self.assertNotIn('read-only', recipe['instructions'])
        self.assertNotIn('{{ project_context | indent(2) }}', self.lead['body'])
        self.assertIn('Independently review', review['instructions'])

    def test_provider_model_translation_and_explicit_ollama(self):
        _, recipe = render(self.lead, 'codex', model='current')
        self.assertEqual(recipe['settings']['goose_provider'], 'codex-acp')
        self.assertEqual(recipe['settings']['goose_model'], 'current')
        _, recipe = render(self.review, 'claude', model='opus')
        self.assertEqual(recipe['settings']['goose_provider'], 'claude-acp')
        self.assertEqual(recipe['settings']['goose_model'], 'opus')
        _, cross = render(self.review, 'codex')
        self.assertEqual(cross['settings']['goose_model'], 'current')
        with self.assertRaises(ValueError):
            render(self.lead, 'ollama')
        _, recipe = render(self.lead, 'ollama', model='configured-local-model')
        self.assertEqual(recipe['settings']['goose_model'], 'configured-local-model')

    @unittest.skipUnless(GOOSE.is_file(), "prepare the locked Goose binary for recipe validation; no inference required")
    def test_real_goose_accepts_recipes_and_rejects_invalid_result_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, GOOSE_PATH_ROOT=tmp, GOOSE_DISABLE_KEYRING='1')
            for composed, provider in [(self.lead, 'codex'), (self.review, 'claude')]:
                _, path = write_bundle(tmp, composed, provider)
                result = subprocess.run([str(GOOSE), 'recipe', 'validate', str(path)], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                recipe = yaml.safe_load(path.read_text())
                schema = recipe['response']['json_schema']
                self.assertFalse(schema['additionalProperties'])
                self.assertEqual(set(schema['required']), {'success','summary','verdict','findings','verification','limitations'})
                self.assertEqual(schema['properties']['success'], {'type': 'boolean'})
                schema['properties']['success']['type'] = 'not-a-json-schema-type'
                path.write_text(json.dumps(recipe))
                result = subprocess.run([str(GOOSE), 'recipe', 'validate', str(path)], env=env, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)

    @unittest.skipUnless(GOOSE.is_file(), "prepare the locked Goose binary for recipe validation; no inference required")
    def test_real_goose_renders_quoted_multiline_task_parameters_without_inference(self):
        context = 'Project "quoted": value\nSecond line: {"path": "a/b"}\n---\nUnicode Zoë'
        task = 'Add --json yielding {"name":"Ada","greeting":"Hello, Ada!"}.\nPreserve \\n and "quotes".'
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, GOOSE_PATH_ROOT=tmp, GOOSE_DISABLE_KEYRING='1')
            for composed, provider in [(self.lead, 'codex'), (self.review, 'claude')]:
                _, path = write_bundle(tmp, composed, provider)
                result = subprocess.run([str(GOOSE), 'run', '--recipe', str(path), '--render-recipe',
                                         '--params', 'project_context='+context, '--params', 'task='+task],
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                rendered = yaml.safe_load(result.stdout)
                self.assertIn(context, rendered['instructions'])
                self.assertIn(task, rendered['instructions'])
                self.assertIn(composed['body'], rendered['instructions'])

    @unittest.skipUnless(GOOSE.is_file(), "prepare the locked Goose binary for recipe validation; no inference required")
    def test_all_catalog_roles_preserve_content_and_render_in_real_goose(self):
        entries = catalog(FLOW, ROOT)
        self.assertEqual(len(entries), 13)
        names = {entry['role'] for entry in entries}
        self.assertEqual(names, {p.stem for p in (ROOT/'role-bundle/recipes').glob('*.yaml')})
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, GOOSE_PATH_ROOT=tmp, GOOSE_DISABLE_KEYRING='1')
            for entry in entries:
                role = entry['role']
                responsibility = 'implement' if role == 'lead-developer' else 'review' if role.endswith('-reviewer') else 'role'
                composed = compose(FLOW, ROOT, role, entry['profile'], stage='review' if role.endswith('-reviewer') else 'implement')
                # Distributed role audit references are repository-relative.
                composed['body'] = composed['body'].replace(str(FLOW) + '/', '')
                agent, path = write_bundle(tmp, composed, entry['provider'], responsibility=responsibility)
                self.assertIn(composed['body'], agent.read_text(), role)
                recipe = yaml.safe_load(path.read_text())
                checked = yaml.safe_load((ROOT/'role-bundle/recipes'/path.name).read_text())
                self.assertEqual(recipe, checked, role)
                self.assertEqual(recipe['extensions'], yaml.safe_load((ROOT/'role-bundle/recipes/lead-developer.yaml').read_text())['extensions'])
                result = subprocess.run([str(GOOSE),'recipe','validate',str(path)],env=env,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,role+result.stdout+result.stderr)
                context = 'Project context: "separate"\n{"standards": "project-specific"}'
                task = 'Approved task: "use this role"\nAcceptance: {"done": true}'
                result = subprocess.run([str(GOOSE),'run','--recipe',str(path),'--render-recipe',
                    '--params','project_context='+context,'--params','task='+task],env=env,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,role+result.stdout+result.stderr)
                instructions = yaml.safe_load(result.stdout)['instructions']
                self.assertIn(composed['body'], instructions, role)
                self.assertIn(context,instructions,role)
                self.assertIn(task,instructions,role)
                if responsibility == 'role':
                    self.assertIn('using your own role instructions and expertise',instructions)
                    self.assertNotIn('Task responsibility:\nImplement the approved task',instructions)

    def test_custom_native_profile_retains_resolved_provider_model(self):
        composed = dict(self.review, profile='custom-claude-profile', provider_kind='claude', model='opus')
        _, recipe = render(composed, 'claude')
        self.assertEqual(recipe['settings']['goose_model'], 'opus')
