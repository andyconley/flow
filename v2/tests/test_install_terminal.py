"""Real pipe/controlling-terminal/session boundaries; no installs or acquisition."""
import errno
import http.server
import json
import threading
import os
from pathlib import Path
import pty
import select
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallerTerminalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='flow-terminal-consent-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        release = self.folder/'release'
        (release/'v2/.venv/bin').mkdir(parents=True)
        (release/'v2/.venv/bin/python').symlink_to(sys.executable)
        (release/'v2/poc').symlink_to(ROOT/'poc', target_is_directory=True)
        (release/'knowledge').symlink_to(ROOT.parent/'knowledge', target_is_directory=True)
        self.model_present=False;self.model_pulls=[];self.remote=False
        owner=self
        class LocalOllama(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                row={'name':'fixture:local','digest':'fixture-digest','size':42}
                if owner.remote:row.update(remote_model='fixture-cloud',remote_host='https://unused.invalid')
                body=json.dumps({'models':[row] if owner.model_present else []}).encode()
                self.send_response(200);self.end_headers();self.wfile.write(body)
            def do_POST(self):
                owner.model_pulls.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                owner.model_present=True
                self.send_response(200);self.end_headers();self.wfile.write(b'{"status":"success","completed":42,"total":42}\n')
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),LocalOllama)
        self.thread=None
        self.addCleanup(self.server.server_close)
        self.addCleanup(lambda:self.server.shutdown() if self.thread else None)
        store=self.folder/'managed/state/knowledge';store.mkdir(parents=True)
        (store/'provisioned-runtime.json').write_text(json.dumps({'model':'fixture:local','ollama':'http://127.0.0.1:'+str(self.server.server_port)}))
        self.runner = self.folder/'runner.py'
        self.runner.write_text('''import json,sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from poc import managed
root=Path(sys.argv[2]);release=Path(sys.argv[3])
try:
    with managed.knowledge_transaction(root):
        result=managed.provision_knowledge(release,root,sys.argv[4],model_policy=sys.argv[5] if len(sys.argv)>5 else 'ask')
    print('CONSENT_RESULT '+json.dumps(result),flush=True)
except Exception as error:
    print('CONSENT_ERROR '+str(error),flush=True)
    raise SystemExit(1)
''')
        self.command = [sys.executable, str(self.runner), str(ROOT), str(self.folder/'managed'), str(release)]

    def start_server(self):
        if not self.thread:
            self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def pipe_with_terminal(self, mode, answer=None):
        script=self.folder/'piped-installer.sh'
        script.write_text(' '.join(shlex.quote(x) for x in [*self.command, mode])+'\n')
        pid, terminal = pty.fork()
        if pid == 0:
            # The installer script occupies stdin, just like curl | bash. Bash
            # and its managed parent still have a real controlling terminal.
            os.execv('/bin/bash', ['bash','-c','cat '+shlex.quote(str(script))+' | /bin/bash'])
        self.start_server()
        output = b'';sent = 0;answers=answer if isinstance(answer,list) else [] if answer is None else [answer];status = None;deadline = time.monotonic()+20
        try:
            while time.monotonic() < deadline:
                ready, _, _ = select.select([terminal], [], [], .1)
                if ready:
                    try:chunk = os.read(terminal, 65536)
                    except OSError as error:
                        if error.errno != errno.EIO:raise
                        chunk = b''
                    output += chunk
                    if sent<len(answers) and output.count(b'[download/defer/cancel] (default cancel):')>sent:
                        os.write(terminal, (answers[sent]+'\n').encode());sent+=1
                done, observed = os.waitpid(pid, os.WNOHANG)
                if done:
                    status=observed
                    return os.waitstatus_to_exitcode(status), output.decode(errors='replace'), sent
            self.fail('Piped installer did not terminate within 20 seconds: '+output.decode(errors='replace'))
        finally:
            os.close(terminal)
            if status is None or not os.WIFEXITED(status):
                try:os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:pass
                try:os.waitpid(pid, 0)
                except ChildProcessError:pass

    def test_piped_installer_can_receive_explicit_defer_from_controlling_terminal(self):
        code, output, sent = self.pipe_with_terminal('ask', 'defer')
        self.assertTrue(sent, output)
        self.assertEqual(0, code, output)
        self.assertIn('CONSENT_RESULT', output)
        self.assertIn('"state": "deferred"', output)
        self.assertFalse((self.folder/'managed/state/knowledge/settings.json').exists())

    def test_piped_installer_cancel_does_not_approve_acquisition(self):
        code, output, sent = self.pipe_with_terminal('ask', 'cancel')
        self.assertTrue(sent, output)
        self.assertEqual(1, code, output)
        self.assertIn('Installation canceled', output)
        self.assertFalse((self.folder/'managed/state/knowledge/settings.json').exists())

    def test_genuine_noninteractive_ask_fails_without_hanging_or_consent(self):
        self.start_server()
        result = subprocess.run([*self.command,'ask'], stdin=subprocess.DEVNULL, start_new_session=True,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(1, result.returncode, result.stdout+result.stderr)
        self.assertIn('requires consent', result.stdout+result.stderr)
        self.assertNotIn('Choose [download/defer/cancel]', result.stderr)

    def test_offline_policy_never_prompts_even_with_controlling_terminal(self):
        code, output, sent = self.pipe_with_terminal('offline')
        self.assertEqual(1, code, output)
        self.assertFalse(sent)
        self.assertNotIn('Choose [download/defer/cancel]', output)
        self.assertIn('Offline knowledge assets/configuration are incomplete', output)

    def test_explicit_noninteractive_defer_succeeds_without_terminal(self):
        self.start_server()
        result = subprocess.run([*self.command,'defer'], stdin=subprocess.DEVNULL, start_new_session=True,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(0, result.returncode, result.stdout+result.stderr)
        self.assertIn('"state": "deferred"', result.stdout)
        self.assertNotIn('Choose [download/defer/cancel]', result.stderr)

    def test_nonterminal_piped_text_cannot_supply_download_consent(self):
        self.start_server()
        result = subprocess.run([*self.command,'ask'], input='download\n', start_new_session=True,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(1, result.returncode, result.stdout+result.stderr)
        self.assertIn('requires consent', result.stdout+result.stderr)
        self.assertNotIn('Choose [download/defer/cancel]', result.stderr)
        self.assertFalse((self.folder/'managed/state/knowledge/settings.json').exists())

    def test_missing_model_offers_separate_terminal_deferral_before_acquisition(self):
        code,output,sent=self.pipe_with_terminal('ask',['download','defer'])
        self.assertEqual(0,code,output);self.assertEqual(2,sent)
        self.assertIn('Selected model: fixture:local',output)
        self.assertIn('Size unknown',output)
        self.assertIn('Extraction model [download/defer/cancel]',output)
        self.assertIn('"state": "deferred"',output)
        self.assertEqual([],self.model_pulls)

    def test_missing_model_cancel_does_not_authorize_chat_weights(self):
        code,output,sent=self.pipe_with_terminal('ask',['download','cancel'])
        self.assertEqual(1,code,output);self.assertEqual(2,sent)
        self.assertIn('Installation canceled',output);self.assertEqual([],self.model_pulls)

    def test_model_acquisition_requires_separate_policy_and_uses_fixture_only(self):
        from poc import install_knowledge as gate
        self.start_server()
        root=self.folder/'managed/state/knowledge'
        with self.assertRaisesRegex(ValueError,'prerequisite unmet'):gate.ensure_model(root,'offline')
        self.assertEqual([],self.model_pulls)
        self.assertEqual('fixture-digest',gate.ensure_model(root,'download'))
        self.assertEqual([{'model':'fixture:local','stream':True}],self.model_pulls)
        self.assertFalse((root/'settings.json').exists())

    def test_unattended_dependency_consent_does_not_include_chat_weights(self):
        self.start_server()
        result=subprocess.run([*self.command,'download','offline'],stdin=subprocess.DEVNULL,start_new_session=True,
                              capture_output=True,text=True,timeout=20)
        self.assertEqual(1,result.returncode,result.stdout+result.stderr)
        self.assertIn('--knowledge-model download',result.stdout+result.stderr)
        self.assertNotIn('[download/defer/cancel]',result.stderr)
        self.assertEqual([],self.model_pulls)

    def test_remote_model_metadata_cannot_trigger_acquisition_or_inference(self):
        from poc import install_knowledge as gate,knowledge as k
        self.start_server();self.model_present=True;self.remote=True
        with self.assertRaises(k.LocalModelRequiredError):gate.ensure_model(self.folder/'managed/state/knowledge','download')
        self.assertEqual([],self.model_pulls)
