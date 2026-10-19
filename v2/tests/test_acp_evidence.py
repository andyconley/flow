"""Exercise actual transport bytes with a local fake adapter; no inference."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from poc.runtime_env import node_binary

PROXY = Path(__file__).resolve().parents[1]/'poc/acp_evidence.mjs'


class AcpEvidenceTests(unittest.TestCase):
    def run_proxy(self, root, source, stdin=b''):
        adapter = root/'adapter.mjs'; adapter.write_text(source)
        result = subprocess.run([str(node_binary()), str(PROXY), str(root/'evidence'),
                                 str(adapter)], input=stdin, capture_output=True, timeout=10)
        files = list((root/'evidence').glob('*.jsonl'))
        records = [json.loads(line) for line in files[-1].read_text().splitlines()] if files else []
        return result, files, records

    def test_exact_frames_and_transport_with_private_files(self):
        frames = [
            {'jsonrpc':'2.0', 'method':'session/update', 'params':{'sessionId':'fixture',
             'update':{'sessionUpdate':'tool_call_update','toolCallId':'test-red',
                       'status':'failed','rawOutput':{'exit_code':1,'output':'2 failed, 2 passed'}}}},
            {'jsonrpc':'2.0', 'method':'session/update', 'params':{'sessionId':'fixture',
             'update':{'sessionUpdate':'tool_call_update','toolCallId':'shell-denial',
                       'status':'failed','rawOutput':{'exit_code':1,'output':'Operation not permitted'}}}},
            {'jsonrpc':'2.0', 'method':'session/update', 'params':{'sessionId':'fixture',
             'update':{'sessionUpdate':'tool_call_update','toolCallId':'terminal',
                       'status':'failed','_meta':{'terminal_exit':{'exit_code':1}}}}},
            {'jsonrpc':'2.0','method':'authenticate','params':{'token':'do-not-log'}},
        ]
        wire = ('\n'.join(json.dumps(f) for f in frames)+'\n').encode()
        source = ('const b=Buffer.from('+json.dumps(wire.hex())+',"hex");'
                  'process.stdout.write(b.subarray(0,19));'
                  'setTimeout(()=>{process.stdout.write(b.subarray(19));process.exitCode=7;},5);')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result, files, records = self.run_proxy(root, source)
            self.assertEqual(result.stdout, wire)
            self.assertEqual(result.returncode, 7)
            self.assertEqual([r['frame'] for r in records if r['type']=='server_tool_frame'], frames[:3])
            self.assertNotIn('do-not-log', files[0].read_text())
            self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
            self.assertEqual((root/'evidence').stat().st_mode & 0o777, 0o700)

    def test_bounds_explicit_gaps_and_unique_process_files(self):
        frame = {'method':'session/update','params':{'update':{
            'sessionUpdate':'tool_call_update','rawOutput':{'output':'x'*200000}}}}
        source = ('process.stdout.write("x".repeat(300000)+"\\ninvalid\\n");'
                  'const f='+json.dumps(json.dumps(frame)+'\n')+';'
                  'for(let i=0;i<100;i++)process.stdout.write(f);')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result, files, records = self.run_proxy(root, source)
            self.assertEqual(result.returncode, 0)
            self.assertGreater(len(result.stdout), 16*1024*1024)
            self.assertLess(files[0].stat().st_size, 16*1024*1024)
            self.assertIn({'type':'capture_gap','reason':'frame_limit'}, records)
            self.assertIn({'type':'capture_gap','reason':'invalid_json'}, records)
            self.assertEqual(records[-1], {'type':'capture_stopped','reason':'file_limit'})
            self.run_proxy(root, 'process.stdout.write("{}\\n");')
            self.assertEqual(len(list((root/'evidence').glob('*.jsonl'))), 2)

    def test_input_forwarding_and_capture_failure_preserve_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result, _, _ = self.run_proxy(root,
                'process.stdin.on("data",b=>process.stdout.write(b));', b'{"id":42}\n')
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b'{"id":42}\n')
            blocked = root/'blocked'; blocked.write_text('file')
            result = subprocess.run([str(node_binary()), str(PROXY), str(blocked),
                                     str(root/'adapter.mjs')], input=b'unchanged\n',
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b'unchanged\n')
            self.assertIn(b'capture unavailable', result.stderr)
