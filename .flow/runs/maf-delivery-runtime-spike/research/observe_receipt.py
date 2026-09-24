"""Independently inspect repo state and definition digests for a bounded receipt."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
RUN = Path(__file__).resolve().parent
FIXTURE = Path("/private/tmp/flow-maf-live-20260919")
SOURCE = json.loads((RUN / "mixed-provider-result.json").read_text())


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(FIXTURE), *args], text=True).strip()


assert SOURCE["workflow"] == "flow-maf-mixed-providers"
assert len(SOURCE["workers"]) == 3
digests = {
    role: hashlib.sha256((ROOT / "scaffolds/default/agents" / f"{role}.md").read_bytes()).hexdigest()
    for role in SOURCE["definition_sha256"]
}
assert digests == SOURCE["definition_sha256"]
head = git("rev-parse", "HEAD")
status = git("status", "--porcelain")
assert head == "f23b769cd00636f11cb06d1c7e52e8b2add9e795"
assert not status
print(json.dumps({
    "schema_version": 1,
    "source": "Flow-side observer; provider output is imported evidence, not independently attested",
    "workflow": SOURCE["workflow"],
    "charter_sha256": SOURCE["charter_sha256"],
    "definition_sha256": digests,
    "provider_sessions": [{"provider": worker["provider"], "session_id": worker.get("session_id"), "agent_id": worker.get("agent_id")} for worker in SOURCE["workers"]],
    "observed_git_head": head,
    "observed_changed_paths": [],
    "read_only_work": True,
    "provider_result_attested": False,
}, indent=2, sort_keys=True))
