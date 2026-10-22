"""Real CLI/checkpoint recovery across independent Python processes; no inference."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

from poc.artifacts import Artifacts


class ProcessRecoveryTests(unittest.TestCase):
    def test_missing_check_command_repair_survives_process_reopening(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root/'project'; project.mkdir()
            runtime = root/'runtime'; runtime.mkdir()
            driver = root/'fixture_cli.py'
            driver.write_text(textwrap.dedent('''
                import json, sys
                from pathlib import Path
                from unittest.mock import patch
                from poc import glg
                runtime = Path(sys.argv[1])
                class FixtureHarness:
                    def shape(self, state, stage, assignment):
                        with (runtime/'research-launches.jsonl').open('a') as stream:
                            stream.write(json.dumps({'stage': stage})+'\\n')
                        return {'status': 'completed', 'content': 'expensive specialist research retained',
                                'runtime': {'output_content': 'raw specialist/tool evidence'},
                                'brief': {'goal': 'goal', 'scope': ['scope'], 'acceptance_criteria': ['works']}}
                    def implement(self, state):
                        raise AssertionError('Repair must not implement or implicitly approve')
                with patch.object(glg, 'ROOT', runtime), patch.object(glg, 'NativeHarness', return_value=FixtureHarness()):
                    raise SystemExit(glg.main(sys.argv[2:]))
            '''))
            environment = dict(os.environ)
            environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
            environment['FLOW_KNOWLEDGE_HOME'] = str(root/'unused-knowledge')
            args = [sys.executable, str(driver), str(runtime), '--project', str(project), '--work', 'process-repair']
            def invoke(*tail, expected=0):
                result = subprocess.run([*args, *tail], env=environment, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, expected, result.stderr)
                return json.loads(result.stdout)
            invoke('create', '--request', 'research then propose a brief')
            assigned = invoke('assign', '--stage', 'plan', '--question', 'Plan this request')
            revision = assigned['stage_assignments']['plan']['revision']
            paused = invoke('run-stage', '--stage', 'plan', '--actor', 'Andy', '--revision', revision, expected=2)
            self.assertEqual(paused['outcome'], 'brief-invalid')
            repair = paused['pending'][0]['value']
            self.assertIn('check_command', repair['errors'])
            # Every invocation closes its process/SQLite connection. Reopening
            # status and resume must retain evidence without launching research.
            status = invoke('status')
            self.assertEqual(status['outcome'], 'brief-invalid')
            self.assertFalse(status['recovery_problems'])
            invoke('resume', expected=2); invoke('resume', expected=2)
            artifacts = Artifacts(project, 'process-repair')
            persisted = artifacts.read(repair['research_ref'])['payload']
            self.assertEqual(persisted['content'], 'expensive specialist research retained')
            self.assertEqual(persisted['runtime']['output_content'], 'raw specialist/tool evidence')
            recovery = artifacts.read(repair['repair_ref'])['payload']
            self.assertEqual(recovery['research_ref'], repair['research_ref'])
            self.assertNotIn('check_command', recovery['proposed_brief'])
            brief = root/'repaired.json'
            brief.write_text(json.dumps({**recovery['proposed_brief'], 'check_command': [sys.executable, '-c', 'print("ok")']}))
            repaired = invoke('brief', '--file', str(brief))
            self.assertEqual(repaired['outcome'], 'awaiting-approval')
            invoke('resume')
            reopened = invoke('status')
            self.assertEqual(reopened['references']['brief_ref'], repaired['references']['brief_ref'])
            self.assertNotIn('approval_ref', reopened['references'])
            self.assertFalse(reopened['recovery_problems'])
            self.assertEqual(len((runtime/'research-launches.jsonl').read_text().splitlines()), 1)
            self.assertEqual(artifacts.read(repair['research_ref'])['payload'], persisted)
