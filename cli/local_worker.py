"""One Flow-owned local inference call; no paid provider or MAF dependency."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable

from execution_contracts import ContractError

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MAX_RESPONSE_BYTES = 131072


def _bounded_output(value: str) -> str:
    return value.encode("utf-8")[:4096].decode("utf-8", errors="ignore")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        raise RuntimeError("Ollama redirect refused")


def call_local(envelope: dict[str, Any], *, transport: Callable[..., Any] | None = None) -> dict[str, Any]:
    provider = envelope["provider"]
    if provider == "local-stub":
        if transport is None:
            raise ContractError("local-stub requires an explicit test transport")
        answer = _bounded_output(str(transport(envelope)))
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
            raise ContractError("Ollama endpoint override is not allowed in this slice")
        body = json.dumps({"model": envelope["model"], "stream": False, "messages": [
            {"role": "system", "content": envelope["instructions"]},
            {"role": "user", "content": envelope["task"]},
        ], "options": {"num_predict": 256}}, sort_keys=True).encode()
        request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        try:
            with opener.open(request, timeout=60) as response:
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
    if not isinstance(text, str) or not text:
        raise RuntimeError("Ollama returned empty response")
    if payload.get("model") != envelope["model"]:
        raise RuntimeError("Ollama reported a different model than the approved model")
    usage = {}
    for key in ("prompt_eval_count", "eval_count"):
        value = payload.get(key)
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RuntimeError("Ollama returned invalid usage")
            usage[key] = value
    text = _bounded_output(text)
    return {"schema_version": 1, "status": "completed", "provider": "ollama", "model": envelope["model"], "physical_call": True,
            "evidence_level": "flow_observed_local_http_response",
            "output": text, "output_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "usage": usage or None, "response_created_at": payload.get("created_at")}
