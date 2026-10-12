"""Exercise stock TaskManager native execution, permission transport and resume.

Default uses a disposable ACP peer. --live uses existing native auth and Ollama;
no installation, credential copying, or native configuration writes are performed.
"""
import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
os.environ.setdefault('OPENHANDS_SUPPRESS_BANNER', '1')
os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
_sdk_settings = tempfile.TemporaryDirectory(prefix='flow-sdk-settings-')
os.environ['OH_PERSISTENCE_DIR'] = _sdk_settings.name
os.environ.setdefault('ACP_NPX_CACHE_WARM_TIMEOUT', '15')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
from openhands_config import select
from openhands_runtime import build_agent
from openhands.sdk import Conversation
from openhands.tools.task.manager import TaskManager


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--orchestrated', action='store_true', help='Run real local-parent selection through stock Conversation.run')
    parser.add_argument('--provider', choices=('local-coder', 'claude-reader', 'codex-reader'))
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--local-api', choices=('ollama', 'openai'), default='ollama')
    args = parser.parse_args()
    fixture = Path(__file__).resolve().parent / 'fixtures/openhands_acp_server.py'
    spec = SimpleNamespace(npx_command=lambda: (sys.executable, str(fixture)))
    catalog = patch('openhands.sdk.settings.acp_install_catalog.ACP_INSTALL_CATALOG',
                    {'codex': spec, 'claude-code': spec}) if not args.live else __import__('contextlib').nullcontext()
    results = []
    directory_context = __import__('contextlib').nullcontext(str(args.output_dir.resolve())) if args.output_dir else tempfile.TemporaryDirectory(prefix='flow-specialists-')
    with catalog, directory_context as directory:
        root = Path(directory)
        (root / '.flow/agents').mkdir(parents=True, exist_ok=True)
        for name in ('coordinator', 'local-coder', 'claude-reader', 'codex-reader'):
            (root / f'.flow/agents/{name}.md').write_text(f'# {name}\nWork only on the supplied benign fixture. Do not edit native configuration.\n')
        (root / 'numbers.txt').write_text('2 3 5\n')
        os.environ['npm_config_cache'] = str(root / 'npm-cache')
        (root / '.flow/runtime.toml').write_text('''default_profile="local"
[profiles.local]
kind="local"
model="ollama_chat/gemma4-26b-dev:latest"
base_url="http://localhost:11434"
max_input_tokens=65536
max_output_tokens=8192
[profiles.claude]
kind="claude"
permission_requests="stock-openhands"
session_mode="plan"
[profiles.codex]
kind="codex"
permission_requests="stock-openhands"
session_mode="read-only"
model="gpt-6-astra"
[roles.coordinator]
specialists=["local-coder", "claude-reader", "codex-reader"]
[roles.local-coder]
specialists=[]
tools=["terminal", "file_editor"]
[roles.claude-reader]
profile="claude"
[roles.codex-reader]
profile="codex"
''')
        if args.local_api == 'openai':
            runtime_path = root / '.flow/runtime.toml'
            runtime_path.write_text(runtime_path.read_text().replace('ollama_chat/gemma4-26b-dev:latest', 'openai/gemma4-26b-dev:latest').replace('http://localhost:11434', 'http://localhost:11434/v1'))
        agent = build_agent(select(root, 'implement', 'coordinator'), root)
        keys = dict(re.findall(r'([\w-]+): use task subagent_type=(\S+)', agent.agent_context.system_message_suffix))
        parent = Conversation(agent=agent, workspace=root, persistence_dir=root / '.flow/history', visualizer=None, max_iteration_per_run=12 if args.orchestrated else 8)
        try:
            if args.orchestrated:
                if not args.live:
                    parser.error('--orchestrated requires --live')
                parent.send_message(
                    f"Complete this benign fixture by delegating with the stock task tool. "
                    f"First use subagent_type={keys['local-coder']} to read {root / 'numbers.txt'} "
                    f"and create {root / 'sum.txt'} containing the sum 10. "
                    f"Then use subagent_type={keys['codex-reader']} to read those files and verify the sum. "
                    f"Continue that same Codex child once using the task ID returned by task and the resume parameter. "
                    "Native instructions: read only; do not edit configuration or request new permissions. "
                    "Do not perform the child tasks yourself. Finish with the verified sum and delegation result.")
                parent.run()
                from openhands.sdk.conversation.response_utils import get_agent_final_response
                child_paths = list((root / '.flow/history').glob('*/subagents/*/base_state.json'))
                child_states = [json.loads(path.read_text()) for path in child_paths]
                native_turns = [sum(1 for event_path in path.parent.glob('events/*.json')
                                    if (event := json.loads(event_path.read_text())).get('kind') == 'MessageEvent' and event.get('source') == 'user')
                                for path, state in zip(child_paths, child_states) if state['agent'].get('acp_server') == 'codex']
                verified = (root / 'sum.txt').is_file() and (root / 'sum.txt').read_text().strip() == '10'
                verified = verified and any(turns >= 2 for turns in native_turns)
                verified = verified and any(state['agent'].get('llm', {}).get('model', '').startswith('ollama_chat/') for state in child_states)
                report = {'live': True, 'orchestrated': True, 'outcome_verified': bool(verified),
                          'parent_status': parent.state.execution_status.value,
                          'response': get_agent_final_response(parent.state.events),
                          'child_count': len(child_states), 'native_child_user_turns': native_turns, 'sum_file': (root / 'sum.txt').read_text() if (root / 'sum.txt').is_file() else None}
                print(json.dumps(report, indent=2))
                if args.output_dir:
                    (root / 'result.json').write_text(json.dumps(report, indent=2))
                if not verified or parent.state.execution_status.value != 'finished':
                    raise SystemExit(1)
                return
            manager = TaskManager()
            manager.attach_parent(parent)
            names = ('local-coder', 'claude-reader', 'codex-reader') if args.live else ('claude-reader', 'codex-reader')
            if args.provider:
                names = (args.provider,)
            for name in names:
                prompt = ('Read numbers.txt using your available tools and report its sum. Do not write files, alter configuration or request new permissions.' if name != 'local-coder' else f'Use file_editor to view {root / "numbers.txt"}, then create {root / "sum.txt"} containing 10. Terminal is available for verification. Use absolute paths for file_editor and call finish when done.') if args.live else 'Perform the disposable fixture proof operation.'
                try:
                    first = manager.start_task(prompt, subagent_type=keys[name])
                    second = manager.start_task('Continue the same task and report the sum again.' if args.live else prompt, subagent_type=keys[name], resume=first.id) if not first.error else None
                    results.append({'role': name, 'status': str(first.status), 'error': first.error, 'result': first.result,
                                    'resume_status': str(second.status) if second else None,
                                    'resume_error': second.error if second else None,
                                    'same_conversation': second.conversation_id == first.conversation_id if second else False})
                except Exception as exc:
                    results.append({'role': name, 'error': f'{type(exc).__name__}: {exc}'})
        finally:
            parent.close()
        if not args.live:
            fresh = TaskManager()
            fresh.attach_parent(parent)
            try:
                fresh._resume_task(first.id, keys[name])
            except ValueError as exc:
                assert 'not found' in str(exc), exc
            else:
                raise AssertionError('SDK task map unexpectedly survived a fresh manager')
            assert (root / 'native-fixture-proof.txt').read_text() == '4', results
            assert all(r.get('same_conversation') and not r.get('resume_error') for r in results), results
        verified = all(not r.get('error') and not r.get('resume_error') and r.get('same_conversation') for r in results)
        if args.live:
            verified = verified and all('10' in str(r.get('result', '')) for r in results if r['role'] != 'local-coder')
            if 'local-coder' in names:
                verified = verified and (root / 'sum.txt').is_file() and (root / 'sum.txt').read_text().strip() == '10'
        report = {'live': args.live, 'outcome_verified': bool(verified), 'results': results, 'sum_file': (root / 'sum.txt').read_text() if (root / 'sum.txt').is_file() else None}
        print(json.dumps(report, indent=2))
        if args.output_dir:
            (root / 'result.json').write_text(json.dumps(report, indent=2))
        if not verified:
            raise SystemExit(1)

if __name__ == '__main__':
    main()
