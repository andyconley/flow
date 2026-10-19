"""Observed native denial regression; fake transports only, no provider calls."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from poc.artifacts import Artifacts
from poc.codex_adapter_guard import guarded_source
from poc.goose_job import GooseJob
from poc.native_errors import PREFIX, boundary_error
from poc.project_context import resolve
from poc.work_lifecycle import build

ROOT = Path(__file__).resolve().parents[1]
from poc.runtime_env import node_binary
NODE = node_binary()
MESSAGE = "PermissionError: [Errno 1] Operation not permitted: '/fixture/.venv/pyvenv.cfg'"


class NativePermissionTests(unittest.TestCase):
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
                brief = a.publish('briefs', 'brief', {'goal': 'approved check', 'scope': ['local'], 'acceptance_criteria': ['check'], 'check_command': ['python3', '-m', 'unittest']})
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
