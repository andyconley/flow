"""Managed launch regressions: extraction settings never select agent inference."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from poc import glg, native_runtime, runtime_env


class KnowledgeProviderIsolationTests(unittest.TestCase):
    def test_dedicated_extraction_endpoint_does_not_replace_agent_endpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = root / 'knowledge'
            store.mkdir()
            (store / 'settings.json').write_text(json.dumps({'ollama': 'http://127.0.0.1:11435'}))
            with patch.object(runtime_env, 'ROOT', root), patch.dict(os.environ, {
                'FLOW_KNOWLEDGE_HOME': str(store), 'OLLAMA_HOST': 'http://127.0.0.1:11434'
            }), patch('poc.device_context.ollama_environment', return_value={}):
                self.assertEqual('http://127.0.0.1:11434', runtime_env.environment(provider='ollama')['OLLAMA_HOST'])
                self.assertNotIn('OLLAMA_HOST', runtime_env.environment(provider='codex-acp'))
                with patch.dict(os.environ, clear=True):
                    self.assertNotIn('OLLAMA_HOST', runtime_env.environment(provider='ollama'))

    def test_managed_harness_setup_preserves_local_provider_before_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / 'home'
            home.mkdir()
            config = root / 'runtime/codex-home/config.toml'
            config.parent.mkdir(parents=True)
            original = ('# User-maintained local inference selection\n'
                        'model = "gpt-oss:20b"\nmodel_provider = "local"\n'
                        'cli_auth_credentials_store = "file"\n'
                        '[model_providers.local]\nname = "Local"\n'
                        'base_url = "http://127.0.0.1:11434/v1"\n'
                        'requires_openai_auth = false\nwire_api = "responses"\n')
            config.write_text(original)
            with patch.object(runtime_env, 'ROOT', root), patch.object(native_runtime, 'ROOT', root), \
                    patch.object(Path, 'home', return_value=home):
                harness = glg.NativeHarness({'provider': 'codex-acp', 'model': 'gpt-oss:20b', 'budget_seconds': 60})
                self.assertEqual('codex-acp', harness._job().provider)
                runtime_env.setup()  # repeated jobs/restarts must be harmless
                self.assertEqual(('local', 'http://127.0.0.1:11434/v1'), native_runtime.local_codex_provider())
                self.assertEqual(original, config.read_text())

    def test_fresh_setup_initializes_config_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(runtime_env, 'ROOT', root), patch.object(Path, 'home', return_value=root):
                runtime_env.setup()
                config = root / 'runtime/codex-home/config.toml'
                self.assertEqual('cli_auth_credentials_store = "file"\n', config.read_text())
                config.write_text('# preserved manual settings\nmodel = "custom"\n')
                runtime_env.setup()
                self.assertEqual('# preserved manual settings\nmodel = "custom"\n', config.read_text())
