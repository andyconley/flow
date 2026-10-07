"""Actual pipe boundary tests for retained local-agent parent authorization."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
from local_agent import LocalAgentPool, LocalAgentSession, MafTransportError
from local_resources import ResourceMonitor, ResourcePressureError
from tests.maf_env import MAF_PYTHON, requires_maf

WORKER = '''
import sys,json
read=lambda:json.loads(sys.stdin.readline())
def emit(x):
 x['protocol_version']=1
 print(json.dumps(x),flush=True)
c=read();emit({'type':'ready'});turn=0
while True:
 command=read()
 if command.get('type')=='close':break
 turn+=1
 emit({'type':'model_request','number':turn,'request':{'messages':[{'role':'user','content':command['task']}]}})
 auth=read()
 if not auth['allowed']:
  emit({'type':'error','error':'send denied'});continue
 emit({'type':'model_send','number':turn})
 emit({'type':'tool','name':'read_files','arguments':{'paths':['app.py']}})
 result=read()
 emit({'type':'model_response','number':turn,'responses':[{'prompt_eval_count':10,'eval_count':3}]})
 emit({'type':'result','text':str(turn)+':'+str(result['result'])})
'''


class LocalAgentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        real_popen = subprocess.Popen
        def child(_args, **kwargs):
            return real_popen([sys.executable, '-c', WORKER], **kwargs)
        self.patch = patch('local_agent.subprocess.Popen', side_effect=child)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.options = dict(model='local-model', runtime_python=sys.executable,
                            artifact_dir=Path(self.directory.name), tools=['read_files'], turn_timeout=5)

    def test_retained_turn_and_separate_assignment_identity(self):
        pool = LocalAgentPool(**self.options)
        self.addCleanup(pool.close)
        callback = lambda name, arguments: {'actual': arguments['paths']}
        first = pool.run('coder', 'instructions', 'first', callback)
        second = pool.run('coder', 'instructions', 'second', callback)
        reviewer = pool.run('reviewer', 'readonly', 'review', callback)
        self.assertEqual(first['session_id'], second['session_id'])
        self.assertNotEqual(first['session_id'], reviewer['session_id'])
        self.assertTrue(second['text'].startswith('2:'))
        self.assertEqual(len(second['model_requests']), 1)
        self.assertEqual(len(second['model_responses']), 1)
        history = Path(second['history_path']).read_text()
        self.assertIn('first', history)
        self.assertIn('second', history)
        self.assertNotIn('review', history)

    def test_gate_denial_has_no_send_or_tool_and_no_automatic_retry(self):
        session = LocalAgentSession(assignment_id='coder', instructions='instructions', **self.options)
        callback_calls = []
        with self.assertRaisesRegex(RuntimeError, 'send denied'):
            session.run('task', lambda *args: callback_calls.append(args), observer=lambda event: False)
        self.assertFalse(callback_calls)
        self.assertFalse(any(event['type'] == 'model_send' for event in session.events))
        with self.assertRaisesRegex(MafTransportError, 'uncertain sends'):
            session.run('retry', lambda *args: None)

    def test_observed_callback_not_child_result_is_returned(self):
        session = LocalAgentSession(assignment_id='reviewer', instructions='review', **self.options)
        self.addCleanup(session.close)
        observed = []
        result = session.run('review', lambda name, args: {'sha256': 'actual-parent-hash'},
                             observer=lambda event: observed.append(event['type']))
        self.assertEqual(result['tool_observations'][0]['result']['sha256'], 'actual-parent-hash')
        self.assertLess(observed.index('model_request'), observed.index('model_send'))
        self.assertIn('model_response', observed)

    def test_resource_stop_after_actual_send_terminates_child_without_replay(self):
        monitors = []
        def factory(**options):
            monitor = ResourceMonitor(interval_seconds=100,
                collector=lambda: {'monotonic': time.monotonic(), 'pressure_raw': None,
                                   'telemetry_incomplete': True}, **options)
            monitors.append(monitor)
            return monitor
        session = LocalAgentSession(assignment_id='coder', instructions='instructions',
                                   resource_monitor_factory=factory, **self.options)
        callback_calls = []
        def observe(event):
            if event['type'] == 'model_send':
                monitors[0].observe({'monotonic': time.monotonic(), 'pressure_raw': 4})
        with self.assertRaises(ResourcePressureError):
            session.run('task', lambda *args: callback_calls.append(args), observer=observe)
        self.assertFalse(callback_calls)
        self.assertIsNotNone(session.process.poll())
        self.assertTrue(any(e['type'] == 'model_send' for e in session.events))
        self.assertIn('resource_observation', session.log_path.read_text())
        with self.assertRaises(MafTransportError):
            session.run('replay', lambda *args: None)

    def test_pressure_interrupts_blocked_pipe_read(self):
        from local_agent import _read_message
        import os
        read_fd, write_fd = os.pipe()
        monitor = ResourceMonitor()
        timer = threading.Timer(.03, lambda: monitor.observe(
            {'monotonic': time.monotonic(), 'pressure_raw': 4}))
        timer.start()
        started = time.monotonic()
        try:
            with self.assertRaises(ResourcePressureError):
                _read_message(read_fd, started + 5, bytearray(), monitor.check)
            self.assertLess(time.monotonic() - started, 1)
        finally:
            timer.join()
            os.close(read_fd)
            os.close(write_fd)

    def test_changed_instructions_do_not_rebind_retained_session(self):
        pool = LocalAgentPool(**self.options)
        self.addCleanup(pool.close)
        pool.run('coder', 'initial', 'task', lambda *args: {})
        with self.assertRaisesRegex(ValueError, 'instructions changed'):
            pool.run('coder', 'changed', 'task', lambda *args: {})


@requires_maf
class ActualMafToolBindingTests(unittest.TestCase):
    def test_generated_nullable_digest_schema_reaches_parent_with_stale_read_protection(self):
        # Invoke the real pinned SDK's generated FunctionTool without a chat
        # client or provider request. This exercises argument binding before RPC.
        script = '''
import asyncio,json,sys,tempfile
from pathlib import Path
sys.path.insert(0,sys.argv[1]);sys.path.insert(0,str(Path(sys.argv[1])/'cli'))
from agent_framework import tool
from runtime.maf_runner import local_agent as child
from local_agent_workspace import LocalAgentWorkspace
async def check():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);source=root/'app.py';source.write_text('original = 1\\n')
        workspace=LocalAgentWorkspace(root,['app.py'],['app.py','created.py'],root/'evidence')
        rpc_arguments=[]
        def rpc(name,args):
            rpc_arguments.append(args)
            return json.dumps(workspace.callback('coder',name,args))
        child.rpc=rpc
        function=tool(child.write_file)
        parameters=function.to_json_schema_spec()['function']['parameters']
        workspace.callback('coder','read_files',{'paths':['app.py']})
        accepted=json.loads(await function.invoke(arguments={'path':'app.py','content':'updated = 2\\n','expected_sha256':None},skip_parsing=True))
        workspace.callback('coder','read_files',{'paths':['app.py']})
        source.write_text('externally_changed = 3\\n')
        denied=json.loads(await function.invoke(arguments={'path':'app.py','content':'overwrite = 4\\n','expected_sha256':None},skip_parsing=True))
        created=json.loads(await function.invoke(arguments={'path':'created.py','content':'created = True\\n','expected_sha256':None},skip_parsing=True))
        return {'parameters':parameters,'accepted':accepted,'denied':denied,'created':created,
                'rpc_arguments':rpc_arguments,'source':source.read_text()}
print(json.dumps(asyncio.run(check())))
'''
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([MAF_PYTHON, '-c', script, str(root)], cwd=root,
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        observed = json.loads(result.stdout)
        field = observed['parameters']['properties']['expected_sha256']
        self.assertIn({'type': 'null'}, field['anyOf'])
        self.assertNotIn('expected_sha256', observed['parameters']['required'])
        self.assertIsNone(field['default'])
        self.assertEqual(observed['accepted']['status'], 'written')
        self.assertEqual(observed['created']['status'], 'written')
        self.assertTrue(all(args['expected_sha256'] is None for args in observed['rpc_arguments']))
        self.assertEqual(observed['denied']['status'], 'denied')
        self.assertIn('Read the actual current file', observed['denied']['reason'])
        self.assertEqual(observed['source'], 'externally_changed = 3\n')


if __name__ == '__main__':
    unittest.main()
