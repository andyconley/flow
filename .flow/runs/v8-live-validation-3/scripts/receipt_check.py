"""Read-only receipt and live-fix checks for one v8-live-validation-3 attempt (AC3-AC7, AC12).

Usage: python3.12 receipt_check.py <ledger.sqlite> <attempt_id>
Run with the installed CLI's python; imports come from ~/.flow/source/cli.
"""
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".flow/source/cli"))
from execution_contracts import validate_receipt
from execution_ledger import ExecutionLedger

ledger_path, attempt = Path(sys.argv[1]), sys.argv[2]
snap = ExecutionLedger(ledger_path, read_only=True).snapshot(attempt)
adir = ledger_path.parent / attempt
receipt_bytes = (adir / "receipt.json").read_bytes()
receipt = json.loads(receipt_bytes)
envelope = snap["envelope"]
out = {}
try:
    validate_receipt(envelope, receipt); out["validate_receipt"] = "pass"
except Exception as exc:  # report, don't hide
    out["validate_receipt"] = f"FAIL: {exc}"
file_sha = hashlib.sha256(receipt_bytes).hexdigest()
out["status"] = receipt["status"]
out["sealed_sha_matches"] = snap.get("sealed_receipt_sha256") == file_sha
out["receipt_sha256"] = file_sha
out["envelope_expansion_headroom"] = envelope.get("expansion_headroom")
out["roster"] = [(r["instance_id"] if "instance_id" in r else r.get("assignment_id"), r.get("provider"), r.get("model")) for r in envelope.get("roster", [])]
out["predecessors"] = [(p.get("attempt_id"), p.get("status"), p.get("receipt_sha256")) for p in envelope.get("predecessors", [])]
# AC3: provider evidence per row
rows = []
for a in receipt["actions"]:
    res = a.get("result") or {}
    rows.append({"action": a["action_id"][:12], "status": a["status"], "provider": (a.get("request") or {}).get("provider"),
                 "evidence_level": res.get("evidence_level") or (res.get("evidence") or {}).get("level") if isinstance(res, dict) else None})
out["actions"] = rows
out["manager_calls"] = [(m["call_id"][:12], m.get("sequence"), m["status"]) for m in receipt["manager_calls"]]
# AC3: scan the receipt, the envelope, the ledger events and every attempt file, not just the receipt.
def has_stub(text):
    return "local_stub" in text or "local-stub" in text
scanned = [f for f in adir.rglob("*") if f.is_file()]
out["local_stub_in_receipt"] = has_stub(receipt_bytes.decode())
out["local_stub_in_ledger_events"] = any(has_stub(json.dumps(e)) for e in snap["events"])
# The acceptance snapshot quotes the criterion ("No `local-stub` evidence appears"), so it is excluded.
out["local_stub_files"] = [str(f.relative_to(adir)) for f in scanned
                           if f.name != "acceptance.snapshot.md" and has_stub(f.read_text(errors="replace"))]
out["attempt_files_scanned"] = len(scanned)
# AC4-AC6: expansion and replay identity
exp = receipt.get("expansion") or {}
out["expansion_requests"] = [(r.get("request_id"), r.get("kind"), r.get("status"), (r.get("grant") or {}).get("authority")) for r in exp.get("requests", [])]
seqs = [m.get("sequence") for m in receipt["manager_calls"]]
out["manager_sequences_contiguous"] = seqs == list(range(seqs[0], seqs[0] + len(seqs))) if seqs else None
events = snap["events"]
def count(name, key=None):
    return sum(1 for e in events if e["event"] == name and (key is None or e.get("action_id") == key))
out["manager_send_started"] = count("manager_send_started")
out["manager_response_observed"] = count("manager_response_observed")
out["adapter_send_started"] = {a["action_id"][:12]: count("adapter_send_started", a["action_id"]) for a in receipt["actions"]}
out["manager_progress"] = receipt.get("manager_progress")
out["recovery_mode"] = [(r.get("mode"), r.get("status")) for r in snap.get("recoveries", [])]
# AC12 D1: event log
ev = adir / "claude-implementer.events.ndjson"
if not ev.exists():
    out["D1_event_log"] = "MISSING: check could not run"
else:
    text = ev.read_text(errors="replace")
    out["D1_event_log_bytes"] = ev.stat().st_size
    out["D1_event_log_vs_1MiB"] = round(ev.stat().st_size / (1 << 20), 3)
    out["D1_stream_event_records"] = text.count('"type":"stream_event"') + text.count('"type": "stream_event"')
    out["D1_terminal_result_event"] = '"type":"result"' in text or '"type": "result"' in text
out["D1_limit_errors"] = [e["detail"] for e in events if "exceeds limit" in (e.get("detail") or "") or "trace limit" in (e.get("detail") or "")]
# AC12 D7: the ledger stores manager request digests only; the manager's
# conversation (with the chartered facts) is in the bound Magentic checkpoints.
facts = "The approved editors get one call in total"
# Live and recovery-quarantined checkpoints; the initial one carries the task
# inside a base64 pickled message, so decode base64 runs before searching.
import base64, re
def contains_facts(text):
    if facts in text:
        return True
    for run in re.findall(r"[A-Za-z0-9+/=]{200,}", text):
        try:
            if facts.encode() in base64.b64decode(run + "=" * (-len(run) % 4)):
                return True
        except Exception:
            pass
    return False
live = sorted((adir / "checkpoints").glob("*.json"))
quarantined = sorted((adir / "checkpoints-quarantine").glob("*/*.json"))
if not live and not quarantined:
    out["D7_checkpoints_with_facts_line"] = "NO CHECKPOINTS: check could not run"
else:
    out["D7_checkpoints_with_facts_line"] = {
        "live": f"{sum(contains_facts(c.read_text()) for c in live)}/{len(live)}",
        "quarantined": f"{sum(contains_facts(c.read_text()) for c in quarantined)}/{len(quarantined)}"}
# AC5/AC6: the escalated call is the one later completed, and no manager send
# happened between the pause and the engineer decision.
decided = [r for r in exp.get("requests", []) if (r.get("grant") or {}).get("authority") == "engineer"]
checks = []
for r in decided:
    row = r.get("denied_row_id")
    completed = [m for m in receipt["manager_calls"] if m["call_id"] == row and m["status"] == "completed"]
    ledger_row = next((x for x in snap.get("expansions", []) if x.get("request_id") == r["request_id"]), {})
    paused_at, decided_at = ledger_row.get("created_at"), (ledger_row.get("grant") or {}).get("decided_at")
    if not paused_at or not decided_at:
        checks.append({"request_id": r["request_id"], "error": "pause or decision time missing: check could not run"})
        continue
    sends = [e["at"] for e in snap["events"] if e["event"] == "manager_send_started"]
    checks.append({"request_id": r["request_id"], "denied_row_id": row, "completed_once": len(completed) == 1,
                   "paused_at": paused_at, "decided_at": decided_at,
                   "manager_sends_before_pause": sum(t < paused_at for t in sends),
                   "manager_sends_between_pause_and_decision": sum(paused_at <= t < decided_at for t in sends),
                   "manager_sends_after_decision": sum(t >= decided_at for t in sends)})
out["AC5_AC6_escalated_call_identity"] = checks
auto = [r for r in exp.get("requests", []) if (r.get("grant") or {}).get("authority") == "charter_headroom"]
out["AC4_auto_grant_consumed_by"] = [((r.get("grant") or {}).get("consumed_by"), r.get("denied_row_id")) for r in auto]
# D3: verifier content non-empty
out["D3_verifier_evaluations"] = [(v.get("outcome"), v.get("reason")) for v in snap.get("verifier_evaluations", [])]
print(json.dumps(out, indent=1, default=str))
