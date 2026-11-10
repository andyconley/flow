"""Regression tests for what Flow hands Goose: recipe encoding, parameter size, blocked findings."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from poc import goose_job, project_context
from poc.contracts import task_input_digest
from poc.project_context import (DELEGATE_PARAMETER_LIMIT, RECIPE_PARAMETERS, context_budget,
                                 delegate_parameter_bytes, delegate_parameter_error, json_size, render, resolve)
from poc.runtime_env import goose_binary

ASTRAL = 'RAG corrected `✅ Complete` → `\U0001F7E2 On Track`'


def real_goose():
    binary = goose_binary()
    return binary if binary.is_file() and os.access(binary, os.X_OK) else None


def validate_recipe(path):
    result = subprocess.run([str(real_goose()), 'recipe', 'validate', str(path)], capture_output=True, text=True)
    return result.returncode == 0 and 'valid' in result.stdout + result.stderr and 'invalid' not in result.stdout + result.stderr


def document(path, content, authority='project'):
    import hashlib
    return {'path': path, 'revision': hashlib.sha256(content.encode()).hexdigest(), 'authority': authority, 'content': content}


class RecipeEncodingTests(unittest.TestCase):
    def test_store_writes_astral_characters_as_raw_utf8(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / 'contract.json'
            goose_job.store(path, {'instructions': ASTRAL})
            raw = path.read_bytes()
            self.assertIn('\U0001F7E2'.encode('utf-8'), raw)
            self.assertNotIn(b'\\ud83d', raw)
            self.assertEqual(ASTRAL, json.loads(raw.decode('utf-8'))['instructions'])

    @unittest.skipUnless(real_goose(), 'bundled Goose binary not available; set FLOW_V2_GOOSE_BINARY')
    def test_stored_contract_with_astral_character_passes_goose_validation(self):
        contract = {'version': '1.0.0', 'title': 'Flow implement contract', 'description': 'fixture',
                    'instructions': ASTRAL, 'prompt': ASTRAL, 'response': {'json_schema': {'type': 'object'}}}
        with tempfile.TemporaryDirectory() as t:
            escaped = Path(t) / 'escaped.json'
            escaped.write_text(json.dumps(contract))
            # The defect: Goose rejects the surrogate-pair form json.dumps writes by default.
            self.assertFalse(validate_recipe(escaped))
            stored = Path(t) / 'stored.json'
            goose_job.store(stored, contract)
            self.assertTrue(validate_recipe(stored))


class ContextBudgetTests(unittest.TestCase):
    def payload(self, *documents):
        return {'workspace': '/w', 'instruction_precedence': 'ancestor to project', 'documents': list(documents),
                'historical_flow': '/w/.flow'}

    def test_render_without_budget_keeps_full_text_in_original_order(self):
        value = self.payload(document('/AGENTS.md', 'outer'), document('/w/STATE.md', 'state', 'companion'))
        expected = '\n\n'.join(['Workspace: /w', 'ancestor to project',
                                f"Source: /AGENTS.md (project, {value['documents'][0]['revision']})\nouter",
                                f"Source: /w/STATE.md (companion, {value['documents'][1]['revision']})\nstate",
                                'Historical Flow artifacts remain at /w/.flow; verify referenced evidence, do not migrate active runs.'])
        self.assertEqual(expected, render(value))

    def test_budget_inlines_project_instructions_and_references_large_companion_state(self):
        state = document('/w/.flow/memory/STATE.md', 'closed entry\n' * 9000, 'companion')
        value = self.payload(document('/AGENTS.md', 'outer rules'), document('/w/CLAUDE.md', 'project rules'), state)
        budget = 20_000
        text = render(value, budget=budget)
        self.assertLessEqual(json_size(text), budget)
        self.assertIn('outer rules', text)
        self.assertIn('project rules', text)
        self.assertNotIn('closed entry', text)
        self.assertIn(f"Source: /w/.flow/memory/STATE.md (companion, {state['revision']})\nNot inlined:", text)

    def test_budget_prefers_most_specific_project_document(self):
        outer, inner = document('/AGENTS.md', 'o' * 6000), document('/w/AGENTS.md', 'i' * 6000)
        text = render(self.payload(outer, inner), budget=8000)
        self.assertIn('i' * 6000, text)
        self.assertNotIn('o' * 6000, text)
        self.assertLess(text.index('/AGENTS.md ('), text.index('/w/AGENTS.md ('))

    def test_kb_sized_context_fits_beside_an_approved_brief(self):
        # Shape of the snapshot that blocked 20261110-pr-data-store-c1-3b: 182 KB, 117 KB of it STATE.md.
        docs = [document(f'/d{i}/CLAUDE.md', 'rule\n' * 2500) for i in range(6)]
        docs.append(document('/w/.flow/memory/STATE.md', 'entry\n' * 19500, 'companion'))
        task = json.dumps({'goal': 'g', 'scope': ['s' * 16000]})
        suffix = '\nControlled input references:\n{}'
        self.assertIsNotNone(delegate_parameter_error(task, render(self.payload(*docs)) + suffix))
        bounded = render(self.payload(*docs), budget=context_budget(task, suffix)) + suffix
        self.assertIsNone(delegate_parameter_error(task + '\nOperation: implement\nCandidate revision: ' + 'a' * 64, bounded))


class ResolveTests(unittest.TestCase):
    def git(self, *args, cwd):
        subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True,
                       env={**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.com',
                            'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.com'})

    def test_nested_worktree_skips_its_own_repository_copies_of_project_documents(self):
        with tempfile.TemporaryDirectory() as t:
            main = Path(t).resolve() / 'kb'
            main.mkdir()
            self.git('init', '-q', '-b', 'main', cwd=main)
            (main / 'CLAUDE.md').write_text('main checkout rules')
            (main / 'AGENTS.md').write_text('main-only agents file')
            self.git('add', '.', cwd=main)
            self.git('commit', '-q', '-m', 'init', cwd=main)
            worktree = main / '.claude' / 'worktrees' / 'w'
            self.git('worktree', 'add', '-q', '-b', 'w', str(worktree), cwd=main)
            (worktree / 'CLAUDE.md').write_text('branch rules')
            paths = [d['path'] for d in resolve(worktree)['documents'] if d['path'].startswith(str(main))]
            self.assertIn(str(worktree / 'CLAUDE.md'), paths)
            self.assertNotIn(str(main / 'CLAUDE.md'), paths)
            # The worktree also has AGENTS.md from the commit, so the main copy is skipped too.
            self.assertNotIn(str(main / 'AGENTS.md'), paths)
            self.assertIn(str(worktree / 'AGENTS.md'), paths)

    def test_plain_subdirectory_project_keeps_repository_root_instructions(self):
        with tempfile.TemporaryDirectory() as t:
            repo = Path(t).resolve() / 'repo'
            service = repo / 'service'
            service.mkdir(parents=True)
            self.git('init', '-q', '-b', 'main', cwd=repo)
            (repo / 'AGENTS.md').write_text('repository rules')
            (service / 'AGENTS.md').write_text('service rules')
            self.git('add', '.', cwd=repo)
            self.git('commit', '-q', '-m', 'init', cwd=repo)
            paths = [d['path'] for d in resolve(service)['documents'] if d['path'].startswith(str(repo))]
            self.assertEqual([str(repo / 'AGENTS.md'), str(service / 'AGENTS.md')], paths)

    def test_subdirectory_of_nested_worktree_skips_only_the_other_checkouts_counterpart(self):
        with tempfile.TemporaryDirectory() as t:
            main = Path(t).resolve() / 'kb'
            (main / 'service').mkdir(parents=True)
            self.git('init', '-q', '-b', 'main', cwd=main)
            (main / 'AGENTS.md').write_text('main root rules')
            (main / 'service' / 'AGENTS.md').write_text('main service rules')
            self.git('add', '.', cwd=main)
            self.git('commit', '-q', '-m', 'init', cwd=main)
            worktree = main / '.claude' / 'worktrees' / 'w'
            self.git('worktree', 'add', '-q', '-b', 'w', str(worktree), cwd=main)
            (worktree / 'AGENTS.md').write_text('branch root rules')
            paths = [d['path'] for d in resolve(worktree / 'service')['documents'] if d['path'].startswith(str(main))]
            # main/service is not an ancestor, so it never loads; main/AGENTS.md is superseded
            # by the worktree's copy; the worktree's own root and service files both load.
            self.assertEqual([str(worktree / 'AGENTS.md'), str(worktree / 'service' / 'AGENTS.md')], paths)

    def test_unrelated_ancestor_documents_are_kept_and_exact_duplicates_dropped(self):
        with tempfile.TemporaryDirectory() as t:
            outer = Path(t).resolve() / 'outer'
            inner = outer / 'inner'
            inner.mkdir(parents=True)
            (outer / 'CLAUDE.md').write_text('same text')
            (inner / 'CLAUDE.md').write_text('same text')
            (outer / 'AGENTS.md').write_text('outer agents')
            (inner / 'AGENTS.md').write_text('inner agents')
            paths = [d['path'] for d in resolve(inner)['documents'] if d['path'].startswith(str(outer))]
            self.assertEqual([str(outer / 'AGENTS.md'), str(inner / 'AGENTS.md'), str(inner / 'CLAUDE.md')], paths)


class DelegateParameterTests(unittest.TestCase):
    def bound_recipe(self, root, task, context):
        from poc.role_renderer import bind_bundle
        source = root / f'source-{len(context)}'
        (source / 'recipes').mkdir(parents=True)
        recipe = {'version': '1.0.0', 'title': 'lead-developer', 'description': 'fixture',
                  'instructions': 'Context:\n{{ project_context | indent(2) }}\nTask:\n{{ task | indent(2) }}',
                  'prompt': 'Execute the task.',
                  'parameters': [{'key': k, 'input_type': 'string', 'requirement': 'required', 'description': d}
                                 for k, d in RECIPE_PARAMETERS]}
        (source / 'recipes' / 'lead-developer.yaml').write_text(yaml.safe_dump(recipe, sort_keys=False))
        destination = root / f'bound-{len(context)}'
        bind_bundle(source, destination, task, context)
        return destination / 'recipes' / 'lead-developer.yaml'

    @unittest.skipUnless(real_goose(), 'bundled Goose binary not available; set FLOW_V2_GOOSE_BINARY')
    def test_preflight_measure_agrees_with_goose_at_the_limit(self):
        task = 'Approved task\nOperation: implement'
        n = DELEGATE_PARAMETER_LIMIT - 400
        n += DELEGATE_PARAMETER_LIMIT - delegate_parameter_bytes(task, 'x' * n)
        at_limit = 'x' * n
        self.assertEqual(DELEGATE_PARAMETER_LIMIT, delegate_parameter_bytes(task, at_limit))
        self.assertIsNone(delegate_parameter_error(task, at_limit))
        over = at_limit + 'x' * 256
        self.assertIn('128 KiB', delegate_parameter_error(task, over))
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self.assertTrue(validate_recipe(self.bound_recipe(root, task, at_limit)))
            self.assertFalse(validate_recipe(self.bound_recipe(root, task, over)))

    def test_oversized_delegate_payload_is_refused_before_launch(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / 'runtime').mkdir()
            work = root / 'work'
            work.mkdir()
            bundle = root / 'bundle'
            (bundle / 'recipes').mkdir(parents=True)
            (bundle / 'recipes' / 'lead-developer.yaml').write_text('version: 1.0.0\ntitle: lead-developer\n')
            context = 'state\n' * 30000
            state = {'task': 'Approved fixture', 'workspace': str(work), 'project_context': context, 'job_id': 'oversized'}
            state['inputs'] = task_input_digest(state['task'], work, context)
            with patch.object(goose_job, 'ROOT', root), patch('poc.knowledge_tools.require_ready'), \
                    patch.object(goose_job.subprocess, 'Popen') as launch:
                result = goose_job.GooseJob(provider='chatgpt_codex', role_bundle=bundle)._run(state, 'implement', 'prompt')
            launch.assert_not_called()
            self.assertEqual('blocked', result['status'])
            self.assertEqual('delegate_preflight', result['source'])
            self.assertFalse(result['submitted'])
            self.assertIn('128 KiB', result['reason'])
            self.assertFalse((root / 'artifacts' / 'oversized' / 'implement-1-0.json').exists())


class BlockedFindingTests(unittest.TestCase):
    def test_malformed_structured_finding_keeps_coordinator_report(self):
        report = {'outcome': 'blocked', 'test_results': {'status': 'not_run'}, 'findings': [{
            'id': 'delegate-recipe-size-limit', 'message': 'lead-developer could not be started',
            'evidence': 'Serialized parameters exceed the 128 KiB limit.', 'resolution': {'state': 'open', 'evidence': 'x'}}]}
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            bundle = root / 'bundle'
            (bundle / 'recipes').mkdir(parents=True)
            (bundle / 'recipes' / 'lead-developer.yaml').write_text('version: 1.0.0\n')
            output = root / 'out.jsonl'
            event = {'type': 'message', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': json.dumps(report)}]}}
            output.write_text(json.dumps(event) + '\n' + json.dumps({'type': 'complete'}) + '\n')
            job = goose_job.GooseJob(provider='chatgpt_codex', role_bundle=bundle)
            with patch.object(job, '_run', return_value={'status': 'completed', 'output': str(output)}):
                result = job._role_operation({'task': 't', 'workspace': str(root)}, 'implement')
        self.assertEqual('blocked', result['status'])
        self.assertIn('Structured findings require', result['reason'])
        self.assertIn("coordinator reported outcome 'blocked'", result['reason'])
        self.assertIn('delegate-recipe-size-limit: lead-developer could not be started', result['reason'])
        self.assertEqual(['delegate-recipe-size-limit: lead-developer could not be started '
                          '(evidence: Serialized parameters exceed the 128 KiB limit.)'], result['findings'])
        from poc.handoffs import Handoffs
        Handoffs._validate_result('implement', result)


if __name__ == '__main__':
    unittest.main()
