"""Observed native denial regression; fake transports only, no provider calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from poc.artifacts import Artifacts
from poc.codex_adapter_guard import guarded_source, build as build_guard
from poc.goose_job import GooseJob
from poc.native_errors import PREFIX, boundary_error
from poc.project_context import resolve
from poc.work_lifecycle import build

ROOT = Path(__file__).resolve().parents[1]
from poc.runtime_env import node_binary
NODE = node_binary()
MESSAGE = "PermissionError: [Errno 1] Operation not permitted: '/fixture/.venv/pyvenv.cfg'"


class NativePermissionTests(unittest.TestCase):
    def setUp(self):
        # Mock provider tests own their store; installed consumer HOME is seeded
        # but deliberately unprovisioned. Keep real readiness behavior elsewhere.
        fixture = tempfile.TemporaryDirectory(prefix='flow-mock-knowledge-')
        self.addCleanup(fixture.cleanup)
        env = patch.dict(os.environ, FLOW_KNOWLEDGE_HOME=fixture.name)
        env.start(); self.addCleanup(env.stop)

    def test_private_auth_preflight_stops_job_and_preserves_explicit_blocker(self):
        from poc.contracts import task_input_digest
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'runtime').mkdir()
            workspace = root/'workspace'; workspace.mkdir()
            marker = root/'client-error.json'
            error = {'schema_version':1,'kind':'permission_required',
                     'source':'claude_native_auth_preflight',
                     'error':{'code':'AUTH_REQUIRED','message':'Private native sign-in required'}}
            class Process:
                pid = 999; returncode = None
                def poll(self): return self.returncode
                def wait(self, timeout=None): self.returncode = 77; return 77
            class Scope:
                stopped = 0
                def __init__(self, pid): self.known = {}
                def observe(self): return {}
                def stop(self): Scope.stopped += 1; return {'stopped':True}
            def launch(*args, **kwargs):
                marker.write_text(json.dumps(error)); return Process()
            state = {'task':'approved task','workspace':str(workspace),'project_context':'context',
                     'inputs':task_input_digest('approved task',workspace,'context'),'job_id':'private-auth'}
            job = GooseJob(role_bundle=ROOT/'role-bundle')
            with patch('poc.goose_job.ROOT',root), patch('poc.goose_job.ProcessScope',Scope), \
                    patch('poc.goose_job.subprocess.Popen',side_effect=launch) as start, \
                    patch.object(job,'_observe'), \
                    patch('poc.native_runtime.prepare',return_value=(root/'worker.sb',
                          {'PATH':'/usr/bin','FLOW_V2_CLIENT_ERROR_FILE':str(marker)})):
                result = job._run(state,'implement','approved prompt')
                self.assertEqual(result['status'],'permission_required')
                self.assertEqual(result['native_error'],error)
                self.assertEqual(Scope.stopped,1)
                self.assertEqual(job._run(state,'implement','approved prompt'),result)
                self.assertEqual(start.call_count,1)

    def test_guard_rejects_unqualified_adapter_source(self):
        with self.assertRaises(ValueError):
            guarded_source("unknown adapter implementation")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dist").mkdir()
            (root / "package.json").write_text(json.dumps({"version": "999.0.0"}))
            (root / "dist/index.js").write_text("unknown")
            with self.assertRaises(ValueError):
                build_guard(root / "dist/index.js", root / "guard.mjs")
            (root / "package.json").write_text(json.dumps({"version": "2.2.2"}))
            with self.assertRaises(ValueError):
                build_guard(root / "dist/index.js", root / "guard.mjs")
            self.assertFalse((root / "guard.mjs").exists())

    def test_actual_guarded_command_renderer_keeps_denial_and_diagnostic(self):
        source = guarded_source((ROOT/'runtime/adapters/node_modules/@agentclientprotocol/codex-acp/dist/index.js').read_text())
        body = source.split('  commandEndRawOutput(end) {', 1)[1].split('\n  }', 1)[0]
        cases = [{'terminal': False, 'exitCode': 1, 'output': MESSAGE},
                 {'terminal': True, 'exitCode': 1, 'output': MESSAGE},
                 {'terminal': False, 'exitCode': 0, 'output': MESSAGE},
                 {'terminal': False, 'exitCode': 1, 'output': 'ordinary assertion failed'},
                 {'terminal': False, 'exitCode': 1, 'output': 'quoted PermissionError in ordinary application prose'}]
        program = 'const render=new Function("end",'+json.dumps(body)+');console.log(JSON.stringify('+json.dumps(cases)+'.map(render)));'
        result = subprocess.run([NODE, '-e', program], capture_output=True, text=True, check=True)
        outputs = json.loads(result.stdout)
        for output in outputs[:2]:
            self.assertEqual(output['goose.native.boundary']['code'], 'EPERM')
            self.assertEqual(output['goose.native.boundary']['message'], MESSAGE)
            self.assertEqual(output['output'], MESSAGE)
        for output in outputs[2:]:
            self.assertNotIn('goose.native.boundary', output)

    def test_only_explicit_structured_errors_are_classified(self):
        for kind in ('permission_required', 'scope_required'):
            error = {'schema_version': 1, 'kind': kind, 'error': {'code': 'EPERM', 'message': MESSAGE}, 'tool_call_id': 'one'}
            text = json.dumps({'type': 'error', 'error': 'Request failed: '+PREFIX+json.dumps(error)})
            self.assertEqual(boundary_error(text), error)
            prose = json.dumps({'type': 'message', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': PREFIX+json.dumps(error)}]}})
            self.assertIsNone(boundary_error(prose))
        for text in ('', 'no tool telemetry', 'PermissionError: not structured', '{"type":"error","error":"generic failure"}'):
            self.assertIsNone(boundary_error(text))

    def test_real_job_record_enters_graph_pause_without_another_dispatch(self):
        for kind in ('permission_required', 'scope_required'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); (root/'runtime').mkdir(); project = root/'project'; project.mkdir()
                a = Artifacts(project, 'denial')
                brief = a.publish('briefs', 'brief', {'goal': 'approved check', 'scope': ['local'], 'acceptance_criteria': ['check'], 'check_command': [sys.executable, '-m', 'unittest']})
                context = a.publish('contexts', 'project', resolve(project))
                error = {'schema_version': 1, 'kind': kind, 'source': 'acp_tool', 'tool_call_id': 'denied-1', 'error': {'code': 'EPERM', 'message': MESSAGE}}
                class Process:
                    pid = 999; returncode = 1
                    def poll(self): return 1
                    def wait(self, timeout=None): return 1
                class Scope:
                    def __init__(self, pid): self.known = {}
                    def observe(self): return {}
                def launch(*args, **kwargs):
                    kwargs['stdout'].write(json.dumps({'type': 'error', 'error': PREFIX+json.dumps(error)})+'\n')
                    kwargs['stdout'].flush()
                    return Process()
                job = GooseJob(role_bundle=ROOT/'role-bundle')
                with patch('poc.goose_job.ROOT', root), patch('poc.goose_job.ProcessScope', Scope), patch('poc.goose_job.subprocess.Popen', side_effect=launch) as start, patch('poc.native_runtime.prepare', return_value=(root/'worker.sb', {'PATH': '/usr/bin'})):
                    with SqliteSaver.from_conn_string(str(root/'workflow.sqlite')) as saver:
                        graph = build(a, job, lambda path: self.fail('Check ran after denied implementation')).compile(checkpointer=saver)
                        config = {'configurable': {'thread_id': 'denial'}}
                        graph.invoke({'work_id': 'denial', 'job_id': 'denial', 'workspace': str(project), 'context_ref': context, 'brief_ref': brief, 'lifecycle_phase': 'shaping', 'budget_seconds': 600}, config)
                        result = graph.invoke(Command(resume={'action': 'approve', 'actor': 'operator', 'brief_ref': brief}), config)
                        pending = result['__interrupt__'][0].value
                        self.assertEqual(pending['kind'], kind)
                        self.assertEqual(pending['detail']['native_error'], error)
                        self.assertEqual(start.call_count, 1)
                        graph.invoke(None, config)
                        self.assertEqual(start.call_count, 1)
                        records = list((root/'artifacts/denial').glob('implement-*.json'))
                        self.assertEqual(len(records), 1)
                        record = json.loads(records[0].read_text())
                        self.assertEqual(record['status'], kind); self.assertEqual(record['native_error'], error)
                        # Cached denied operation remains typed and never resubmits.
                        # Inputs are verified before reuse; test the same saved operation via its actual assignment task/context.
                        substate = graph.get_state(config, subgraphs=True).tasks[0].state.values
                        self.assertEqual(job._run(substate, 'implement', 'unused')['status'], kind)
                        self.assertEqual(start.call_count, 1)
