"""Retained native MAF participant. All tools are RPCs to Flow's parent."""
from __future__ import annotations
import asyncio
import hashlib
import json
import sys
import time
from typing import Any


def emit(value: dict) -> None:
    value['protocol_version'] = 1
    sys.stdout.write(json.dumps(value, default=str) + '\n')
    sys.stdout.flush()


def read() -> dict:
    line = sys.stdin.readline()
    if not line:
        raise EOFError('Flow parent disconnected')
    return json.loads(line)


def rpc(name: str, arguments: dict) -> str:
    emit({'type': 'tool', 'name': name, 'arguments': arguments})
    response = read()
    if response.get('type') != 'tool_result':
        raise RuntimeError('Unexpected parent tool response')
    return json.dumps(response.get('result'), default=str)


def read_files(paths: list[str]) -> str:
    """Read current authorized source or task artifact files."""
    return rpc('read_files', {'paths': paths})


def write_file(path: str, content: str, expected_sha256: str | None = None) -> str:
    """Create or replace an authorized source file. Read existing files first."""
    return rpc('write_file', {'path': path, 'content': content, 'expected_sha256': expected_sha256})


def run_tests() -> str:
    """Execute the Flow-authorized validation command on the actual current source."""
    return rpc('run_tests', {})


def submit_review(approved: bool, findings: str) -> str:
    """Submit independent findings bound to the source you actually read and tested."""
    return rpc('submit_review', {'approved': approved, 'findings': findings})


def submit_handoff(summary: str) -> str:
    """Persist a hash-bound source handoff for the next specialist."""
    return rpc('submit_handoff', {'summary': summary})


def read_handoff() -> str:
    """Read and validate the preceding specialist's hash-bound handoff."""
    return rpc('read_handoff', {})


async def main() -> None:
    from agent_framework import Agent
    from agent_framework.ollama import OllamaChatClient
    from ollama import AsyncClient
    config = read()
    previous = None
    request_number = 0
    last_http_bytes = 0

    class ObservedClient(AsyncClient):
        def __init__(self):
            super().__init__(host=config.get('host', 'http://127.0.0.1:11434'),
                             timeout=config.get('request_timeout', 600), trust_env=False)
            async def observe(request):
                nonlocal request_number, last_http_bytes
                if request.url.path != '/api/chat':
                    raise RuntimeError('Unexpected local provider endpoint')
                raw = request.content
                actual = json.loads(raw)
                if (actual.get('model') != config['model']
                        or actual.get('options', {}).get('num_ctx') != config['num_ctx']
                        or actual.get('options', {}).get('num_predict') != config['num_predict']):
                    raise RuntimeError('Local client did not project sealed model/context/output; no send')
                bound = (previous['prompt_tokens'] + max(0, len(raw)-previous['http_bytes'])+512
                         if previous else len(raw)+512)
                allowance = config['num_ctx']-config['num_predict']-config.get('context_reserve', 2048)
                if bound > allowance:
                    emit({'type': 'context_denied', 'bound': bound, 'allowance': allowance})
                    raise RuntimeError('Retained session exceeds conservative context reserve; no send')
                request_number += 1
                last_http_bytes = len(raw)
                emit({'type': 'model_request', 'number': request_number,
                      'request': json.loads(raw), 'http_bytes': len(raw),
                      'sha256': hashlib.sha256(raw).hexdigest(), 'conservative_bound': bound,
                      'backend_retention_proved': False})
                authorization = read()
                if authorization.get('type') != 'model_authorized' or not authorization.get('allowed'):
                    raise RuntimeError('Flow parent denied model send')
                emit({'type': 'model_send', 'number': request_number})
            self._client.event_hooks['request'].append(observe)

        async def chat(self, *args, **kwargs):
            nonlocal previous
            started = time.monotonic()
            try:
                response = await super().chat(*args, **kwargs)
                if kwargs.get('stream'):
                    chunks = [chunk async for chunk in response]
                    records = [chunk.model_dump() for chunk in chunks]
                    async def replay():
                        for chunk in chunks:
                            yield chunk
                    result = replay()
                else:
                    records = [response.model_dump()]
                    result = response
                usage = next((item for item in reversed(records) if item.get('prompt_eval_count') is not None), {})
                # Preserve the actual response and usage; no inferred success/token counts.
                emit({'type': 'model_response', 'number': request_number, 'responses': records,
                      'elapsed_seconds': time.monotonic()-started})
                if usage:
                    previous = {'prompt_tokens': usage['prompt_eval_count'], 'http_bytes': last_http_bytes}
                return result
            except BaseException as exc:
                emit({'type': 'model_error', 'number': request_number, 'error': str(exc),
                      'elapsed_seconds': time.monotonic()-started})
                raise

    transport = ObservedClient()
    options = {'num_ctx': config['num_ctx'], 'max_tokens': config['num_predict'],
               'temperature': 0, 'seed': 42, 'think': False}
    registry = {function.__name__: function for function in
                (read_files, write_file, run_tests, submit_review, submit_handoff, read_handoff)}
    tools = [registry[name] for name in config['tools']]
    client = OllamaChatClient(model=config['model'], client=transport,
        function_invocation_configuration={'allow_concurrent_invocation': False,
            'max_iterations': config.get('max_iterations') if config.get('max_iterations') is not None else sys.maxsize,
            'max_function_calls': config.get('max_function_calls', 80),
            'max_duration_seconds': config.get('turn_timeout', 2400)})
    agent = Agent(client, name=config['assignment_id'], instructions=config['instructions'],
                  tools=tools, default_options=options)
    session = agent.create_session()
    emit({'type': 'ready'})
    try:
        while True:
            command = read()
            if command.get('type') == 'close':
                break
            if command.get('type') != 'run':
                raise RuntimeError('Invalid local agent command')
            try:
                response = await agent.run(command['task'], session=session)
                emit({'type': 'result', 'text': response.text})
            except Exception as exc:
                emit({'type': 'error', 'error': f'{type(exc).__name__}: {exc}'})
    finally:
        await transport._client.aclose()


if __name__ == '__main__':
    asyncio.run(main())
