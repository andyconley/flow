"""Stock SDK delegation to three choices for one role, using disposable peers."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault('OPENHANDS_SUPPRESS_BANNER', '1')
os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))


def main():
    with tempfile.TemporaryDirectory(prefix='flow-provider-choices-') as temporary:
        root = Path(temporary)
        os.environ['HOME'] = str(root / 'home')
        os.environ['OH_PERSISTENCE_DIR'] = str(root / 'sdk-settings')
        os.environ['npm_config_cache'] = str(root / 'npm-cache')
        from openhands_config import select
        from openhands_runtime import conversation
        from openhands.sdk import Message, TextContent
        from openhands.sdk.tool import resolve_tool
        from openhands.sdk.llm.llm_response import LLMResponse
        from openhands.sdk.llm.utils.metrics import MetricsSnapshot
        from litellm.types.utils import ModelResponse
        user = root / 'home/.flow/user'
        user.mkdir(parents=True)
        (user / 'flow.toml').write_text('[local_machine]\nmodel="fixture"\ncontext_tokens=16384\n')
        (root / '.flow').mkdir()
        (root / '.flow/runtime.toml').write_text('[roles.lead-developer]\nspecialists=["test-engineer"]\n[roles.test-engineer]\ntools=[]\n')
        fixture = Path(__file__).resolve().parent / 'fixtures/openhands_acp_server.py'
        spec = SimpleNamespace(npx_command=lambda: (sys.executable, str(fixture)))
        response = LLMResponse(message=Message(role='assistant', content=[TextContent(text='Local fixture completed.')]),
                               metrics=MetricsSnapshot(), raw_response=ModelResponse(id='fixture-response'))
        selected = select(root, 'implement')
        with patch('openhands.sdk.settings.acp_install_catalog.ACP_INSTALL_CATALOG', {'codex': spec, 'claude-code': spec}), \
                patch('openhands.sdk.llm.LLM.completion', return_value=response):
            with conversation(selected, root, root / 'history', uuid4(), lambda _: None) as parent:
                assert parent.state.confirmation_policy.__class__.__name__ == 'NeverConfirm'
                tool = resolve_tool(parent.agent.tools[0], parent.state)[0]
                outcomes = []
                for candidate in ('ollama-local', 'codex-hosted', 'claude-hosted'):
                    target = f'test-engineer--{candidate}'
                    result = tool.executor(tool.action_type(prompt='Perform the disposable fixture proof operation.', subagent_type=target), parent)
                    assert not result.is_error, result
                    assert target in result.text, result
                    outcomes.append({'target': target, 'task_id': result.task_id, 'status': result.status})
                rejected = tool.executor(tool.action_type(prompt='Cross-provider resume must fail.',
                    subagent_type='test-engineer--codex-hosted', resume=outcomes[0]['task_id']), parent)
                assert rejected.is_error
                assert (root / 'native-fixture-proof.txt').read_text() == '2'
        print(json.dumps({'status': 'passed', 'providers': outcomes, 'automatic_sdk_dispatch': True,
                          'native_permission_transport': 'stock allow-once, disposable ACP peers',
                          'cross_provider_resume_rejected': True, 'live_providers': False}))


if __name__ == '__main__':
    main()
