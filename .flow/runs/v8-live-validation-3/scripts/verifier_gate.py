"""Timed go/no-go check of the local verifier, built the way Flow builds its call.

Usage (installed CLI's interpreter, from ~/src/flow):
    python3.12 verifier_gate.py <diff-file> <job-charter.json> [--limit 30]

System prompt: verifier_instructions(quality-reviewer effective body).
User prompt: _verifier_provider_task(charter task, diff, sha, structured=True).
Options match Flow (think false since v0.36.2, format schema, num_predict,
no num_ctx), plus keep_alive -1
so the gate does not reset the warm model's unload timer (plan review F2).
Exit 0 on go (within the limit and a schema-valid reply), 1 on no-go.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".flow" / "source" / "cli"))
from delivery_gateway import _effective_specialist_for, _verifier_provider_task  # noqa: E402
from local_worker import STRUCTURED_VERIFIER_NUM_PREDICT  # noqa: E402
from verifier_contracts import VERIFIER_OUTPUT_SCHEMA, verifier_instructions  # noqa: E402


def main(argv: list[str]) -> int:
    diff = Path(argv[0]).read_text()
    task = json.loads(Path(argv[1]).read_text())["task"]
    limit = float(argv[argv.index("--limit") + 1]) if "--limit" in argv else 30.0
    body = {"model": "gemma4:26b", "stream": False, "think": False, "keep_alive": -1,
            "format": VERIFIER_OUTPUT_SCHEMA,
            "options": {"num_predict": STRUCTURED_VERIFIER_NUM_PREDICT},
            "messages": [
                {"role": "system", "content": verifier_instructions(_effective_specialist_for("quality-reviewer"))},
                {"role": "user", "content": _verifier_provider_task(
                    task, diff, hashlib.sha256(diff.encode()).hexdigest(), structured=True)},
            ]}
    request = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=120) as response:
        reply = json.loads(response.read())
    seconds = round(time.monotonic() - started, 2)
    content = reply.get("message", {}).get("content", "")
    try:
        parsed = json.loads(content)
        valid = isinstance(parsed, dict)
    except json.JSONDecodeError:
        parsed, valid = None, False
    verdict = "go" if valid and seconds <= limit else "no-go"
    print(json.dumps({"seconds": seconds, "limit": limit, "schema_json": valid, "verdict": verdict,
                      "prompt_chars": len(body["messages"][0]["content"]) + len(body["messages"][1]["content"]),
                      "eval_count": reply.get("eval_count"), "prompt_eval_count": reply.get("prompt_eval_count"),
                      "load_duration_s": round(reply.get("load_duration", 0) / 1e9, 2),
                      "reply": parsed if valid else content[:400]}, indent=2))
    return 0 if verdict == "go" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
