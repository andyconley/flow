"""Deterministic ACP peer tests; never start native adapters or models."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
from acp_permissions import CANCELLED, Terminal, options_for, relay

REQUEST = {'jsonrpc': '2.0', 'id': 7, 'method': 'session/request_permission', 'params': {
    'sessionId': 'session', 'toolCall': {'toolCallId': 'tool', 'title': 'private-request'},
    'options': [{'optionId': 'persistent', 'kind': 'allow_always', 'name': 'Always'},
                {'optionId': 'single', 'kind': 'allow_once', 'name': 'Once'},
                {'optionId': 'no', 'kind': 'reject_once', 'name': 'Deny'}]}}


class Output:
    def __init__(self):
        self.messages = asyncio.Queue()
    def write(self, line):
        self.messages.put_nowait(json.loads(line))
    async def drain(self):
        pass


class ProxyTests(unittest.IsolatedAsyncioTestCase):
    async def start_peer(self, requests, choose, timeout=.2):
        reader = asyncio.StreamReader()
        output = Output()
        script = ('import json,sys,os\n'
                  f'requests={requests!r}\n'
                  'for request in requests: print(json.dumps(request),flush=True)\n'
                  'for line in sys.stdin:\n'
                  ' print(json.dumps({"jsonrpc":"2.0","method":"peer/observed","params":json.loads(line)}),flush=True)\n')
        task = asyncio.create_task(relay([sys.executable, '-u', '-c', script], reader, output, choose, timeout=timeout))
        async def cleanup():
            reader.feed_eof()
            try:
                await asyncio.wait_for(task, 4)
            except (ValueError, asyncio.CancelledError):
                pass
        self.addAsyncCleanup(cleanup)
        return reader, output, task

    async def observation(self, output):
        message = await asyncio.wait_for(output.messages.get(), 3)
        return message['params']

    async def test_exact_choice_not_first_option_and_request_never_reaches_host(self):
        seen = []
        async def choose(message):
            seen.append(message)
            return {'outcome': {'outcome': 'selected', 'optionId': 'single'}}
        _, output, _ = await self.start_peer([REQUEST], choose)
        response = await self.observation(output)
        self.assertEqual(response, {'jsonrpc':'2.0','id':7,'result':{'outcome':{'outcome':'selected','optionId':'single'}}})
        self.assertEqual(seen, [REQUEST])

    async def test_rejection_is_preserved_exactly(self):
        async def choose(message):
            return {'outcome': {'outcome': 'selected', 'optionId': 'no'}}
        _, output, _ = await self.start_peer([REQUEST], choose)
        self.assertEqual((await self.observation(output))['result']['outcome']['optionId'], 'no')

    async def test_timeout_error_and_invalid_choice_cancel(self):
        async def timeout(message): await asyncio.sleep(20)
        async def error(message): raise OSError('private error')
        async def invalid(message): return {'outcome':{'outcome':'selected','optionId':'invented'}}
        for choose in (timeout, error, invalid):
            with self.subTest(choose=choose.__name__):
                reader, output, task = await self.start_peer([REQUEST], choose, timeout=.05)
                self.assertEqual((await self.observation(output))['result'], CANCELLED)
                reader.feed_eof()
                await task

    async def test_malformed_options_cancel_without_prompt(self):
        request = json.loads(json.dumps(REQUEST))
        request['params']['options'][1]['optionId'] = 'persistent'
        async def choose(message): self.fail('must not prompt malformed options')
        _, output, _ = await self.start_peer([request], choose)
        self.assertEqual((await self.observation(output))['result'], CANCELLED)

    async def test_concurrent_requests_keep_ids_and_session_cancel(self):
        requests = [REQUEST, {**REQUEST, 'id':'7', 'params':{**REQUEST['params'],'sessionId':'other'}}]
        started = asyncio.Event()
        async def choose(message):
            if message['id'] == 7:
                started.set()
                await asyncio.sleep(20)
            return {'outcome':{'outcome':'selected','optionId':'single'}}
        reader, output, _ = await self.start_peer(requests, choose, timeout=2)
        await asyncio.wait_for(started.wait(), 2)
        reader.feed_data(b'{"jsonrpc":"2.0","method":"session/cancel","params":{"sessionId":"session"}}\n')
        messages = [await self.observation(output) for _ in range(3)]
        responses = {type(m['id']):m for m in messages if 'id' in m}
        self.assertEqual(responses[int]['result'], CANCELLED)
        self.assertEqual(responses[str]['result']['outcome']['optionId'], 'single')

    async def test_unknown_extension_roundtrip(self):
        notification = {'jsonrpc':'2.0','method':'custom/update','params':{'_meta':{'custom':42}}}
        async def choose(message): self.fail('not permission')
        reader, output, _ = await self.start_peer([notification], choose)
        self.assertEqual(await asyncio.wait_for(output.messages.get(), 2), notification)
        reader.feed_data(json.dumps(notification).encode()+b'\n')
        self.assertEqual(await self.observation(output), notification)

    async def test_duplicate_permission_id_stops_instead_of_selecting(self):
        async def choose(message): await asyncio.sleep(20)
        _, _, task = await self.start_peer([REQUEST, REQUEST], choose)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            await asyncio.wait_for(task, 3)

    async def test_terminal_choice_and_control_character_escaping(self):
        import pty
        master, slave = pty.openpty()
        os.set_blocking(master, False)
        os.set_blocking(slave, False)
        original_open = os.open
        def open_terminal(path, flags, *args):
            return os.dup(slave) if path == '/dev/tty' else original_open(path, flags, *args)
        with patch('acp_permissions.os.open', side_effect=open_terminal), patch('acp_permissions.os.tcgetpgrp', return_value=os.getpgrp()):
            terminal = Terminal()
        try:
            request = json.loads(json.dumps(REQUEST))
            request['params']['toolCall']['title'] = '\x1b[2Jsecret'
            task = asyncio.create_task(terminal.choose(request))
            displayed = b''
            async def read_prompt():
                nonlocal displayed
                while b'Choose one number' not in displayed:
                    try: displayed += os.read(master, 4096)
                    except BlockingIOError: await asyncio.sleep(.01)
            await asyncio.wait_for(read_prompt(), 2)
            self.assertNotIn(b'\x1b', displayed)
            self.assertIn(b'\\u001b', displayed)
            os.write(master, b'2\n')
            self.assertEqual((await asyncio.wait_for(task, 2))['outcome']['optionId'], 'single')
        finally:
            terminal.close()
            os.close(master)
            os.close(slave)

    async def test_eof_terminates_adapter(self):
        async def choose(message): await asyncio.sleep(20)
        reader, _, task = await self.start_peer([REQUEST], choose)
        reader.feed_eof()
        await asyncio.wait_for(task, 3)

    async def test_proxy_cancellation_reaps_adapter_process(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory)/'pid'
            script = f'import os,time;open({str(marker)!r},"w").write(str(os.getpid()));time.sleep(60)'
            reader = asyncio.StreamReader()
            async def choose(message): self.fail('no permission request expected')
            task = asyncio.create_task(relay([sys.executable, '-c', script], reader, Output(), choose))
            async def started():
                while not marker.exists(): await asyncio.sleep(.01)
            await asyncio.wait_for(started(), 2)
            pid = int(marker.read_text())
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 4)
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)


class HeadlessTests(unittest.TestCase):
    def test_real_proxy_stdio_keeps_terminal_approval_out_of_protocol(self):
        import fcntl
        import pty
        import select
        import termios
        import time
        master, slave = pty.openpty()
        proxy = Path(__file__).resolve().parents[1]/'cli/acp_permissions.py'
        script = (f'import json,sys;print(json.dumps({REQUEST!r}),flush=True);'
                  'answer=json.loads(sys.stdin.readline());'
                  'print(json.dumps({"jsonrpc":"2.0","method":"peer/result","params":answer}),flush=True);'
                  'sys.stdin.read()')
        def controlling_terminal():
            os.setsid()
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
        check = subprocess.run([sys.executable, '-c',
            'import os,sys\ntry: os.close(os.open("/dev/tty",os.O_RDWR))\nexcept PermissionError: sys.exit(77)'],
            pass_fds=(slave,), preexec_fn=controlling_terminal, capture_output=True, timeout=5)
        if check.returncode == 77:
            os.close(master)
            os.close(slave)
            self.skipTest('outer sandbox denies /dev/tty; run this fake-peer test with terminal access')
        self.assertEqual(check.returncode, 0, check.stderr)
        os.close(master)
        os.close(slave)
        master, slave = pty.openpty()
        process = subprocess.Popen([sys.executable, str(proxy), '--', sys.executable, '-u', '-c', script],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            pass_fds=(slave,), preexec_fn=controlling_terminal)
        os.close(slave)
        slave = -1
        try:
            display = b''
            deadline = time.monotonic() + 5
            while b'Choose one number' not in display and time.monotonic() < deadline:
                if select.select([master], [], [], .1)[0]:
                    display += os.read(master, 8192)
            self.assertIn(b'Choose one number', display)
            os.write(master, b'2\n')
            self.assertTrue(select.select([process.stdout], [], [], 5)[0])
            notification = json.loads(process.stdout.readline())
            self.assertEqual(notification['method'], 'peer/result')
            self.assertEqual(notification['params']['result']['outcome']['optionId'], 'single')
            process.stdin.close()
            process.stdin = None
            # A real terminal emulator keeps draining output. On macOS a tty
            # close can wait for queued output, even after protocol EOF.
            deadline = time.monotonic() + 5
            while process.poll() is None and time.monotonic() < deadline:
                if select.select([master], [], [], .05)[0]:
                    try:
                        os.read(master, 8192)
                    except OSError:
                        break
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertNotIn(b'private-request', stdout + stderr)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    os.close(master)
                    master = -1
                    process.kill()
                    process.communicate(timeout=2)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
            if master != -1:
                os.close(master)
            if slave != -1:
                os.close(slave)

    def test_no_terminal_means_no_native_process_and_no_sensitive_logging(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory)/'started'
            proxy = Path(__file__).resolve().parents[1]/'cli/acp_permissions.py'
            result = subprocess.run([sys.executable, str(proxy), '--', sys.executable, '-c',
                f'open({str(marker)!r},"w").write("private-value")'],
                input='', capture_output=True, text=True, start_new_session=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())
            self.assertNotIn('private-value', result.stdout+result.stderr)
            self.assertEqual(result.stdout, '')
