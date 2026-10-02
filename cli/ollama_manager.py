"""Bounded Ollama adapter for Magentic manager responses."""

from __future__ import annotations

import json
from typing import Any, Callable

from execution_contracts import ContractError, canonical
from local_worker import call_local
from runner_progress import parse_progress


MAX_MANAGER_PROMPT_BYTES = 64 * 1024
MANAGER_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "is_request_satisfied",
        "is_in_loop",
        "is_progress_being_made",
        "next_speaker",
        "instruction_or_question",
    ],
    "properties": {
        "is_request_satisfied": {
            "type": "object", "additionalProperties": False,
            "required": ["answer"], "properties": {"answer": {"type": "boolean"}},
        },
        "is_in_loop": {
            "type": "object", "additionalProperties": False,
            "required": ["answer"], "properties": {"answer": {"type": "boolean"}},
        },
        "is_progress_being_made": {
            "type": "object", "additionalProperties": False,
            "required": ["answer"], "properties": {"answer": {"type": "boolean"}},
        },
        "next_speaker": {
            "type": "object", "additionalProperties": False,
            "required": ["answer", "reason"],
            "properties": {
                "answer": {"type": "string", "minLength": 1},
                "reason": {"type": "string", "minLength": 1},
            },
        },
        "instruction_or_question": {
            "type": "object", "additionalProperties": False,
            "required": ["answer"],
            "properties": {"answer": {"type": "string", "minLength": 1}},
        },
    },
}


def call_ollama_manager(messages: list[dict[str, Any]], *, model: str, attempt_id: str,
                        transport: Callable[..., Any] | None = None,
                        timeout_seconds: int = 60,
                        preserve_observed_invalid: bool = False) -> dict[str, Any]:
    if not isinstance(messages, list) or not messages:
        raise ContractError("Ollama manager messages are absent")
    serialized = canonical(messages)
    if len(serialized.encode()) > MAX_MANAGER_PROMPT_BYTES:
        raise ContractError("Ollama manager prompt exceeds size limit")
    envelope = {
        "provider": "ollama", "model": model, "attempt_id": attempt_id,
        "instructions": (
            "Return exactly one JSON object and no markdown or commentary. It must contain exactly "
            "is_request_satisfied, is_in_loop, is_progress_being_made, next_speaker, and "
            "instruction_or_question. Every value must be an object containing an answer field. "
            "next_speaker must also contain a nonempty reason. Boolean answers are JSON booleans."
        ),
        "task": serialized,
    }
    result = call_local(envelope, transport=transport, correlation_id=f"{attempt_id}-manager",
                        timeout_seconds=timeout_seconds, response_schema=MANAGER_RESPONSE_SCHEMA)
    output = result["output"]
    parsed = parse_progress(output)
    if parsed.value is None or parsed.canonical is None:
        if preserve_observed_invalid:
            return {**result, "manager_response": None, "observed_invalid": True}
        raise ContractError("Ollama manager response is not exact Magentic progress")
    return {**result, "output": parsed.canonical, "manager_response": parsed.value}
