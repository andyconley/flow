"""Native account-state isolation with fake clients; no credentials or inference."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from poc import native_runtime, runtime_env


class ClaudeConfigTests(unittest.TestCase):
    def test_config_writes_stay_private_and_missing_auth_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); real_home = root/'original-home'; real_home.mkdir()
            global_config = real_home/'.claude.json'; global_config.write_text('original-account-state')
            project = root/'project'; project.mkdir(); run = root/'run'; run.mkdir()
            executable = root/'fake-claude'
            def fake(status):
                executable.write_text('#!/bin/sh\n'
                    'if [ "$1" = --setting-sources ]; then shift 2; fi\n'
                    'if [ "$1" = auth ]; then\n'
                    '  /bin/mkdir -p "$CLAUDE_CONFIG_DIR/.claude.json.lock"\n'
                    '  printf "{}" > "$CLAUDE_CONFIG_DIR/.claude.json"\n'
                    '  /bin/rmdir "$CLAUDE_CONFIG_DIR/.claude.json.lock"\n'
                    '  exit '+str(status)+'\nfi\n'
                    'printf "%s" "$CLAUDE_CONFIG_DIR"\n')
                executable.chmod(0o755)
            with patch.object(native_runtime, 'ROOT', root), patch.object(runtime_env, 'ROOT', root), \
                    patch.object(Path, 'home', return_value=real_home), \
                    patch.object(native_runtime, 'build'), \
                    patch.object(native_runtime, 'goose_binary', return_value=root/'goose'), \
                    patch.dict(os.environ, {'FLOW_V2_CLAUDE':str(executable)}):
                runtime_env.setup()
                fake(0)
                profile, env = native_runtime.prepare(project, run, root/'roles')
                first_marker = env['FLOW_V2_CLIENT_ERROR_FILE']
                wrapper = run/'native-runtime/claude'
                result = subprocess.run([str(wrapper), '--fixture'], env=env, capture_output=True, text=True, check=True)
                config = root/'runtime/claude-home'
                self.assertEqual(result.stdout, str(config))
                self.assertEqual((config/'.claude.json').read_text(), '{}')
                self.assertEqual(config.stat().st_mode & 0o777, 0o700)
                self.assertFalse(Path(first_marker).exists())
                fake(1)
                result = subprocess.run([str(wrapper), '--fixture'], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 77)
                error = json.loads(Path(first_marker).read_text())
                self.assertEqual(error['kind'], 'permission_required')
                self.assertEqual(error['error']['code'], 'AUTH_REQUIRED')
                self.assertEqual(Path(first_marker).stat().st_mode & 0o777, 0o600)
                _, fresh = native_runtime.prepare(project, run, root/'roles')
                self.assertNotEqual(fresh['FLOW_V2_CLIENT_ERROR_FILE'], first_marker)
                self.assertFalse(Path(fresh['FLOW_V2_CLIENT_ERROR_FILE']).exists())
            self.assertEqual(global_config.read_text(), 'original-account-state')
            self.assertNotIn('(allow file-write* (subpath "'+str(real_home)+'"))', profile.read_text())
