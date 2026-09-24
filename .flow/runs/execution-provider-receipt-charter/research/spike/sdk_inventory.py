"""Inspect installed public Codex SDK surfaces without constructing a client."""

from __future__ import annotations

import importlib.metadata
import inspect
import json

import openai_codex as codex


SURFACES = {
    "client_config": (codex.CodexConfig, ("cwd", "codex_bin")),
    "thread_start": (codex.Codex.thread_start, ("cwd", "sandbox", "approval_mode")),
    "thread_resume": (codex.Codex.thread_resume, ("thread_id", "cwd")),
    "thread_turn": (codex.Thread.turn, ("input", "sandbox", "approval_mode")),
    "turn_events": (codex.TurnHandle.stream, ()),
    "turn_result": (codex.TurnHandle.run, ()),
    "turn_interrupt": (codex.TurnHandle.interrupt, ()),
}


def main() -> None:
    findings = {}
    for name, (public_callable, required_parameters) in SURFACES.items():
        signature = inspect.signature(public_callable)
        found = all(parameter in signature.parameters for parameter in required_parameters)
        findings[name] = {
            "status": "observed" if found else "absent_in_version",
            "public_symbol": f"{public_callable.__module__}.{public_callable.__qualname__}",
            "signature": str(signature),
            "required_parameters": list(required_parameters),
        }
    findings["thread_identity"] = {
        "status": "observed" if "id" in codex.Thread.__annotations__ else "absent_in_version",
        "public_symbol": "openai_codex.Thread.id",
        "type_annotation": str(codex.Thread.__annotations__.get("id")),
    }
    result_fields = ("id", "status", "error", "items", "usage")
    findings["turn_result_fields"] = {
        "status": (
            "observed"
            if all(field in codex.TurnResult.__annotations__ for field in result_fields)
            else "absent_in_version"
        ),
        "public_symbol": "openai_codex.TurnResult",
        "fields": {field: str(codex.TurnResult.__annotations__.get(field)) for field in result_fields},
    }
    print(
        json.dumps(
            {
                "python_sdk_version": importlib.metadata.version("openai-codex"),
                "sdk_cli_package_version": importlib.metadata.version("openai-codex-cli-bin"),
                "inspection_only": True,
                "client_constructed": False,
                "worker_turn_started": False,
                "surfaces": findings,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
