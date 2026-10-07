"""One Flow-owned local inference call; no paid provider or MAF dependency."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import socket
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from typing import Any, Callable

from delivery_cancel import interruptible, run_interruptibly
from execution_contracts import ContractError
from verifier_contracts import VERIFIER_OUTPUT_SCHEMA
from runner_limits import resolve_local_agent_budget

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MAX_RESPONSE_BYTES = 131072
# Structured verifier output is judged by Flow's evaluator, which owns the
# size limit. The adapter retains up to the ledger's response ceiling.
STRUCTURED_VERIFIER_OUTPUT_BYTES = 64 * 1024
STRUCTURED_VERIFIER_NUM_PREDICT = 1024


def _bounded_output(value: str, limit: int = 4096) -> str:
    return value.encode("utf-8")[:limit].decode("utf-8", errors="ignore")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        raise RuntimeError("Ollama redirect refused")


class _TrackedHTTPHandler(urllib.request.HTTPHandler):
    """Keeps the request's connection so that a cancel can shut its socket."""

    def __init__(self) -> None:
        super().__init__()
        self.connection: http.client.HTTPConnection | None = None

    def http_open(self, req):
        def connect(host, **kwargs):
            self.connection = http.client.HTTPConnection(host, **kwargs)
            return self.connection
        return self.do_open(connect, req)

    def abort(self) -> None:
        sock = self.connection.sock if self.connection is not None else None
        if sock is not None:
            sock.shutdown(socket.SHUT_RDWR)


def call_local(envelope: dict[str, Any], *, transport: Callable[..., Any] | None = None,
               correlation_id: str | None = None, timeout_seconds: int | None = None,
               structured_verifier: bool = False,
               response_schema: dict[str, Any] | None = None,
               local_agent_profile: dict[str, Any] | None = None,
               observer: Callable[[dict[str, Any]], Any] | None = None,
               resource_monitor_factory: Callable | None = None,
               chat_messages: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Make one local call.

    With ``structured_verifier``, a received response is always returned as a
    completed observation: empty content and a different reported model are
    facts for Flow's evaluator to judge, not transport failures.
    """
    profile = (resolve_local_agent_budget(local_agent_profile)
               if local_agent_profile is not None else None)
    if profile and timeout_seconds is None:
        timeout_seconds = profile['request_timeout_seconds']
    output_limit = (profile['output_tokens'] * 8 if profile else
                    STRUCTURED_VERIFIER_OUTPUT_BYTES if structured_verifier else 4096)
    response_limit = max(MAX_RESPONSE_BYTES, output_limit * 2)
    started = time.monotonic()
    def observed(event):
        if observer is not None:
            observer(event)
    messages = [
        {'role': 'system', 'content': envelope['instructions']},
        {'role': 'user', 'content': envelope['task']}]
    if chat_messages is not None:
        if profile is None:
            raise ContractError('native chat messages require a retained local profile')
        if not isinstance(chat_messages, list) or not chat_messages:
            raise ContractError('native chat messages are absent')
        native = []
        for message in chat_messages:
            if (not isinstance(message, dict)
                    or message.get('role') not in {'system', 'user', 'assistant', 'tool'}
                    or not isinstance(message.get('content'), str)):
                raise ContractError('native chat message role/content is invalid')
            native.append({'role': message['role'], 'content': message['content']})
        messages = [{'role': 'system', 'content': envelope['instructions']}, *native]
    request_body = {'model': envelope['model'], 'stream': False, 'think': False,
                    'messages': messages, 'options': {
                        'num_predict': STRUCTURED_VERIFIER_NUM_PREDICT if structured_verifier else 256}}
    if profile:
        request_body['options'] = {'num_ctx': profile['context_tokens'],
            'num_predict': profile['output_tokens'], 'temperature': 0, 'seed': 42}
    if structured_verifier or response_schema is not None:
        request_body['format'] = VERIFIER_OUTPUT_SCHEMA if structured_verifier else response_schema
    if profile:
        request_preview = json.dumps(request_body, sort_keys=True).encode()
        # UTF-8 bytes are a conservative token upper bound across arbitrary
        # source languages; no optimistic characters-per-token assumption.
        bound = len(request_preview) + 512
        allowance = profile['context_tokens']-profile['output_tokens']-profile['context_reserve']
        if bound > allowance:
            observed({'type': 'context_denied', 'bound': bound, 'allowance': allowance})
            raise ContractError('local worker exceeds conservative context reserve; no send')
    if timeout_seconds is not None and (type(timeout_seconds) is not int or timeout_seconds < 1):
        raise ContractError("local worker timeout is invalid")
    provider = envelope["provider"]
    if provider == "local-stub":
        if transport is None:
            raise ContractError("local-stub requires an explicit test transport")
        answer = _bounded_output(str(transport(envelope)),
                                 output_limit)
        return {"schema_version": 1, "status": "completed", "provider": "local-stub", "model": envelope["model"], "physical_call": False,
                "evidence_level": "local_stub",
                "output": answer, "output_sha256": hashlib.sha256(answer.encode()).hexdigest(), "usage": None}
    if provider != "ollama":
        raise ContractError("paid or unknown provider is not dispatchable")
    if transport is not None:
        payload = transport(envelope)
        if not isinstance(payload, dict) or "message" not in payload:
            raise ContractError("test Ollama transport returned invalid payload")
    else:
        url = os.environ.get("FLOW_OLLAMA_URL", OLLAMA_URL)
        if url != OLLAMA_URL:
            parsed = urlsplit(url)
            if (os.environ.get("FLOW_OLLAMA_OBSERVER") != "1" or parsed.scheme != "http"
                    or parsed.hostname != "127.0.0.1" or parsed.path != "/api/chat"
                    or parsed.username or parsed.password or parsed.query or parsed.fragment
                    or parsed.port is None):
                raise ContractError("Ollama endpoint override requires an explicit loopback observer")
        # "think": false keeps a reasoning model's hidden trace from spending
        # the num_predict budget: gemma4 otherwise returns empty content for a
        # real diff. Models without a thinking mode accept and ignore it.
        if structured_verifier and response_schema is not None:
            raise ContractError("local worker response schema conflicts with structured verifier")
        if structured_verifier or response_schema is not None:
            request_body["format"] = VERIFIER_OUTPUT_SCHEMA if structured_verifier else response_schema
        body = json.dumps(request_body, sort_keys=True).encode()
        request = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json",
            "X-Flow-Correlation-Id": correlation_id or envelope["attempt_id"],
        })
        tracked = _TrackedHTTPHandler()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect(), tracked)

        monitor = None
        def resource_observation(sample, decision):
            observed({'type': 'resource_sample', 'sample': sample, 'decision': decision})
            if decision.get('action') == 'stop':
                try:
                    tracked.abort()
                except OSError:
                    pass
        def exchange() -> bytes:
            if monitor is not None:
                monitor.check()
            observed({'type': 'model_send', 'number': 1})
            with opener.open(request, timeout=timeout_seconds) as response:
                if response.status != 200:
                    raise RuntimeError(f"Ollama HTTP {response.status}")
                return response.read(response_limit + 1)

        try:
            if resource_monitor_factory is not None:
                monitor = resource_monitor_factory(callback=resource_observation)
                monitor.start()
                monitor.check()
            observed({'type': 'model_request', 'number': 1, 'request': request_body,
                      'http_bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
                      'backend_retention_proved': False})
            # A cancel breaks the request once and shuts its socket. The
            # exchange runs on a helper thread under a live parent, because a
            # socket read cannot watch the cancel wakeup pipe.
            with interruptible():
                raw = run_interruptibly(exchange, abort=tracked.abort)
            if monitor is not None:
                monitor.check()
            if len(raw) > response_limit:
                raise RuntimeError("Ollama response exceeds size limit")
            payload = json.loads(raw)
            observed({'type': 'model_response', 'number': 1, 'responses': [payload],
                      'elapsed_seconds': time.monotonic()-started})
        except BaseException as exc:
            observed({'type': 'model_error', 'number': 1, 'error': str(exc),
                      'elapsed_seconds': time.monotonic()-started})
            if monitor is not None:
                monitor.record_error(exc)
                monitor.check()
            if isinstance(exc, (urllib.error.URLError, TimeoutError, json.JSONDecodeError)):
                raise RuntimeError(f"local Ollama call failed: {exc}") from exc
            raise
        finally:
            if monitor is not None:
                monitor.stop()
    if not isinstance(payload.get("message"), dict):
        raise RuntimeError("Ollama response has no message object")
    text = payload["message"].get("content")
    reported_model = payload.get("model")
    if structured_verifier:
        if text is None:
            text = ""
        if not isinstance(text, str):
            raise RuntimeError("Ollama response content is not text")
        if not isinstance(reported_model, str) or not reported_model:
            reported_model = "unreported"
    else:
        if not isinstance(text, str) or not text:
            raise RuntimeError("Ollama returned empty response")
        if reported_model != envelope["model"]:
            raise RuntimeError("Ollama reported a different model than the approved model")
    usage = {}
    for key in ("prompt_eval_count", "eval_count"):
        value = payload.get(key)
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RuntimeError("Ollama returned invalid usage")
            usage[key] = value
    text = _bounded_output(text, output_limit)
    return {"schema_version": 1, "status": "completed", "provider": "ollama",
            "model": reported_model if structured_verifier else envelope["model"], "physical_call": True,
            "evidence_level": "flow_observed_local_http_response",
            "output": text, "output_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "usage": usage or None, "response_created_at": payload.get("created_at")}
