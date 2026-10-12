"""Real SDK routing/confirmation across fresh Flow processes; synthetic endpoint."""
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Endpoint(BaseHTTPRequestHandler):
    calls = []
    def log_message(self, *_):
        pass
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append(request)
        classifier = any('You are a model-routing classifier' in str(m.get('content')) for m in request['messages'])
        if classifier:
            message = {'role': 'assistant', 'content': '1'}
            finish = 'stop'
        elif request['model'] == 'initial':
            message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': f'route_{len(self.calls)}', 'type': 'function',
                       'function': {'name': 'route_task_to_model', 'arguments': '{}'}}]}
            finish = 'tool_calls'
        else:
            assert request['model'] == 'routed', request['model']
            outputs = [self.server.root / f'.flow/runs/routing-resume/{name}' for name in ('requirements.md', 'acceptance-criteria.md')]
            pending = next((path for path in outputs if not path.exists()), None)
            if pending:
                tool = next(t['function']['name'] for t in request['tools'] if 'editor' in t['function']['name'])
                message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': f'edit_{len(self.calls)}', 'type': 'function',
                           'function': {'name': tool, 'arguments': json.dumps({'command': 'create', 'path': str(pending), 'file_text': 'Routed profile proof.\n'})}}]}
                finish = 'tool_calls'
            else:
                message = {'role': 'assistant', 'content': 'Routed continuation complete.'}
                finish = 'stop'
        body = json.dumps({'id': f'resume_{len(self.calls)}', 'object': 'chat.completion', 'created': 1,
                           'model': request['model'], 'choices': [{'index': 0, 'message': message, 'finish_reason': finish}],
                           'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


WORKER = '''
import json, sys
from pathlib import Path
from argparse import Namespace
sys.path.insert(0, sys.argv[1])
import openhands_flow as flow
args = Namespace(project_root=Path(sys.argv[2]), work_id='routing-resume', stage='define', role=None,
                 profile=None, task_file=Path('task.md'), new_session=False, disposition=[],
                 confirm_pending=sys.argv[3]=='confirm', reject_pending=None)
if sys.argv[3]=='init':
    flow.initialize(args)
else:
    print(json.dumps(flow.execute(args)))
'''


def main():
    with tempfile.TemporaryDirectory(prefix='flow-routing-resume-') as directory:
        root = Path(directory)
        (root / '.flow').mkdir()
        (root / 'task.md').write_text('Route this coding task, then create both required stage outputs with the file editor.')
        server = ThreadingHTTPServer(('127.0.0.1', 0), Endpoint)
        server.root = root
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{server.server_port}/v1'
        (root / '.flow/runtime.toml').write_text(f'''default_profile="initial"
[profiles.initial]
kind="local"
model="openai/initial"
base_url="{url}"
max_input_tokens=65536
max_output_tokens=8192
condenser_max_tokens=57344
[profiles.routed]
kind="local"
model="openai/routed"
base_url="{url}"
max_input_tokens=32768
max_output_tokens=8192
condenser_max_tokens=24576
[roles.business-analyst]
specialists=[]
tools=["file_editor"]
[roles.business-analyst.model_routing]
classifier_profile="initial"
[[roles.business-analyst.model_routing.categories]]
description="Coding tasks"
profile="routed"
[workspace]
kind="local"
confirmation="always"
''')
        environment = {**os.environ, 'HOME': str(root / 'home'), 'OH_PERSISTENCE_DIR': str(root / 'sdk-settings'),
                       'LITELLM_LOCAL_MODEL_COST_MAP': 'True', 'OPENHANDS_SUPPRESS_BANNER': '1'}
        cli = str(Path(__file__).resolve().parents[1] / 'cli')
        def invoke(mode):
            result = subprocess.run([sys.executable, '-c', WORKER, cli, str(root), mode], env=environment,
                                    capture_output=True, text=True, timeout=45)
            assert result.returncode == 0, result.stdout + result.stderr
            return json.loads(result.stdout.splitlines()[-1]) if mode != 'init' else None
        try:
            invoke('init')
            first = invoke('run')
            assert first['session']['status'] == 'waiting_for_confirmation', first
            routed = invoke('confirm')
            assert routed['session']['status'] == 'waiting_for_confirmation', routed
            persistence = root / '.flow/runs/routing-resume/openhands'
            snapshot = next(persistence.glob('*/base_state.json'))
            state = json.loads(snapshot.read_text())
            assert state['agent']['llm']['model'] == 'openai/routed', state['agent']['llm']['model']
            before = len(Endpoint.calls)
            inspected = invoke('run')
            assert inspected['session']['status'] == 'waiting_for_confirmation'
            assert len(Endpoint.calls) == before, 'unconfirmed continuation performed inference'
            assert not (root / '.flow/runs/routing-resume/requirements.md').exists()
            for _ in range(3):
                finished = invoke('confirm')
                if finished['session']['status'] == 'finished':
                    break
            assert finished['session']['status'] == 'finished', finished
            assert all(request['model'] == 'routed' for request in Endpoint.calls[2:]), [r['model'] for r in Endpoint.calls]
            assert finished['session']['conversation_id'] == first['session']['conversation_id']
            assert json.loads(snapshot.read_text())['agent']['llm']['model'] == 'openai/routed'
            print(json.dumps({'status': 'passed', 'fresh_processes': True, 'same_conversation': True,
                              'pending_confirmation_preserved': True, 'active_model_preserved': 'openai/routed',
                              'request_models': [request['model'] for request in Endpoint.calls]}))
        finally:
            server.shutdown()
            server.server_close()

if __name__ == '__main__':
    main()
