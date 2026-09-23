"""One Flow-owned local inference call; no paid provider or MAF dependency."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from typing import Any, Callable

from execution_contracts import ContractError

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


def call_local(envelope: dict[str, Any], *, transport: Callable[..., Any] | None = None,
               correlation_id: str | None = None, timeout_seconds: int = 60,
               structured_verifier: bool = False) -> dict[str, Any]:
    """Make one local call.

    With ``structured_verifier``, a received response is always returned as a
    completed observation: empty content and a different reported model are
    facts for Flow's evaluator to judge, not transport failures.
    """
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 60:
        raise ContractError("local worker timeout is invalid")
    provider = envelope["provider"]
    if provider == "local-stub":
        if transport is None:
            raise ContractError("local-stub requires an explicit test transport")
        answer = _bounded_output(str(transport(envelope)),
                                 STRUCTURED_VERIFIER_OUTPUT_BYTES if structured_verifier else 4096)
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
        body = json.dumps({"model": envelope["model"], "stream": False, "messages": [
            {"role": "system", "content": envelope["instructions"]},
            {"role": "user", "content": envelope["task"]},
        ], "options": {"num_predict": STRUCTURED_VERIFIER_NUM_PREDICT if structured_verifier else 256}},
            sort_keys=True).encode()
        request = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json",
            "X-Flow-Correlation-Id": correlation_id or envelope["attempt_id"],
        })
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        try:
            with opener.open(request, timeout=timeout_seconds) as response:
                if response.status != 200:
                    raise RuntimeError(f"Ollama HTTP {response.status}")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise RuntimeError("Ollama response exceeds size limit")
            payload = json.loads(raw)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"local Ollama call failed: {exc}") from exc
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
    text = _bounded_output(text, STRUCTURED_VERIFIER_OUTPUT_BYTES if structured_verifier else 4096)
    return {"schema_version": 1, "status": "completed", "provider": "ollama",
            "model": reported_model if structured_verifier else envelope["model"], "physical_call": True,
            "evidence_level": "flow_observed_local_http_response",
            "output": text, "output_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "usage": usage or None, "response_created_at": payload.get("created_at")}
