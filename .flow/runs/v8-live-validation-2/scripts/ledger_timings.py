"""Per-call timings for one v8 attempt, read-only from Flow's execution ledger.

Usage (installed CLI's interpreter):
    python3.12 ledger_timings.py <ledger.sqlite> <attempt_id> [--json]

A call starts at its send event and ends at the next event recorded for the
same id (observed, evaluated, unknown, ...). Timestamps are the ledger's own
microsecond UTC values; nothing is inferred. A call with no end event is
reported with `end: null`.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".flow" / "source" / "cli"))
from execution_ledger import ExecutionLedger  # noqa: E402

STARTS = {"manager_send_started": "manager", "adapter_send_started": "producer",
          "verifier_send_claimed": "verifier"}
NOT_AN_END = {"policy_allowed", "manager_policy_allowed", "magentic_checkpoint_bound",
              "worker_dispatched", "verifier_input_recorded", *STARTS}


def timings(snapshot: dict) -> dict:
    events = snapshot["events"]
    # A verifier send writes both adapter_send_started and verifier_send_claimed
    # for one action; count it once, as the verifier.
    verifier_ids = {event["action_id"] for event in events if event["event"] == "verifier_send_claimed"}
    calls = []
    for index, event in enumerate(events):
        kind = STARTS.get(event["event"])
        if kind is None or (kind == "producer" and event["action_id"] in verifier_ids):
            continue
        end = next((later for later in events[index + 1:]
                    if later["action_id"] == event["action_id"] and later["event"] not in NOT_AN_END), None)
        evaluated = next((later["at"] for later in events[index + 1:] if kind == "verifier"
                          and later["action_id"] == event["action_id"] and later["event"] == "verifier_evaluated"), None)
        seconds = None
        if end is not None:
            seconds = round((datetime.fromisoformat(end["at"]) - datetime.fromisoformat(event["at"])).total_seconds(), 3)
        calls.append({"kind": kind, "id": event["action_id"], "start": event["at"],
                      "end": end["at"] if end else None, "end_event": end["event"] if end else None,
                      "seconds": seconds, "evaluated_at": evaluated})
    expansions = []
    for item in snapshot.get("expansions", []):
        grant = item.get("grant") or {}
        decided = grant.get("decided_at")
        wait = None
        if decided:
            wait = round((datetime.fromisoformat(decided) - datetime.fromisoformat(item["created_at"])).total_seconds(), 3)
        expansions.append({"request_id": item["request_id"], "kind": item["kind"], "status": item["status"],
                           "created_at": item["created_at"], "authority": grant.get("authority"),
                           "decision": grant.get("decision"), "decided_at": decided, "decision_wait_seconds": wait})
    return {"attempt_id": snapshot["attempt_id"], "calls": calls, "expansions": expansions,
            "first_event": events[0]["at"] if events else None,
            "last_event": events[-1]["at"] if events else None}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    ledger = ExecutionLedger(Path(argv[0]), read_only=True)
    result = timings(ledger.snapshot(argv[1]))
    if "--json" in argv:
        print(json.dumps(result, indent=2))
        return 0
    print(f"attempt {result['attempt_id']}  {result['first_event']} .. {result['last_event']}")
    for number, call in enumerate(result["calls"], 1):
        print(f"{number:>2} {call['kind']:<9} {call['id'][:12]}  {call['start']}  "
              f"{call['seconds'] if call['seconds'] is not None else '-':>8}s  {call['end_event'] or 'no end event'}")
    for item in result["expansions"]:
        print(f"   expansion {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
