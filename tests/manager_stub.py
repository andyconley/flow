"""Stub stock-manager replies that carry the provider identity a v8 observation requires (ADR 0020)."""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from execution_contracts import ContractError, canonical  # noqa: E402
from manager_requests import render_manager_prompt  # noqa: E402


def prompt_sha256(messages):
    """The Claude ``input_sha256`` for these messages, as the real adapter sends them."""
    try:
        text = render_manager_prompt(messages)
    except ContractError:
        text = canonical(messages)  # test-only message shapes that no real adapter renders
    return hashlib.sha256(text.encode()).hexdigest()


def manager_reply(message, output, *, usage=None, provider="claude"):
    """A manager adapter reply with the session identity of ``provider``."""
    reply = {"output": output, "usage": usage}
    if provider == "claude":
        reply.update({"session_id": "stub-session-" + str(message.get("call_id", ""))[:16],
                      "input_sha256": prompt_sha256(message.get("messages")), "num_turns": 1})
    elif provider == "codex":
        reply["thread_id"] = "stub-thread-" + str(message.get("call_id", ""))[:16]
    return reply
