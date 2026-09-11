"""Explicit policy over validated data, never inferred from observed imports."""

import json
from .model import value_digest, digest, canonical


def approval_gaps(policy, approval):
    try:
        if policy.get("schema_version") != 1:
            return ["unsupported policy schema"]
        if policy.get("exceptions"):
            return ["exceptions are not implemented in pilot v1"]
        rules = policy["rules"]
        if len({r["id"] for r in rules}) != len(rules):
            return ["duplicate policy rule"]
        if any(r.get("kind") != "direct-import" for r in rules):
            return ["unsupported rule semantics"]
        if approval["policy_digest"] != value_digest(policy):
            return ["policy approval digest mismatch"]
        if approval["plan_digest"] != digest(approval["plan_text"].encode()):
            return ["approved plan digest mismatch"]
        ev = approval["event"]
        if ev not in [
            json.loads(line)
            for line in approval["events_text"].splitlines()
            if line.strip()
        ]:
            return ["approval event absent from event artifact"]
        if (
            ev["event"] != "approve-plan"
            or ev["to"] != "plan_approved"
            or not ev["at"]
            or not approval["approver"]
        ):
            return ["missing approval event"]
        if not ev["artifacts"].get("plan", "").endswith("/plan.md"):
            return ["approval event missing plan reference"]
        if canonical({"rules": approval["approved_rules"]}) != canonical(
            {"rules": rules}
        ):
            return ["approved rules mismatch"]
        # Receipt includes the exact plan text and its approval event for human inspection.
        if (
            "watermark must not import either collector or harvest"
            not in approval["plan_text"]
        ):
            return ["approval plan does not declare pilot rule semantics"]
        expected = {
            ("python:jsonl_watermark", "python:" + t)
            for t in ("codex_collector", "claude_collector", "harvest")
        }
        expected |= {
            ("python:" + t, "python:harvest")
            for t in ("codex_collector", "claude_collector")
        }
        if {(r["from"], r["to"]) for r in rules} != expected:
            return ["rules differ from approved pilot semantics"]
        return []
    except (KeyError, TypeError, ValueError):
        return ["missing approval reference"]


def graph_gaps(s):
    gaps = list(s.get("gaps", []))
    gaps.extend(
        "unresolved: " + str(u.get("reason", "dependency"))
        for u in s["graph"].get("unresolved", [])
    )
    gaps.extend(
        "failed inventory: " + i["path"]
        for i in s["graph"]["inventory"]
        if i["status"] == "failed"
    )
    gaps.extend(
        "missing edge source: " + e["id"]
        for e in s["graph"]["edges"]
        if not e.get("sources")
    )
    return gaps


def evaluate(b, c, d, policy, approval):
    gaps = approval_gaps(policy, approval) + graph_gaps(b) + graph_gaps(c)
    if b["config_digest"] != c["config_digest"]:
        gaps.append("baseline/candidate configuration differs")
    if b.get("tools") != c.get("tools"):
        gaps.append("baseline/candidate tools differ")
    findings = []
    old = {e["id"] for e in b["graph"]["edges"]}
    for r in policy.get("rules", []):
        for e in c["graph"]["edges"]:
            if (e["from"], e["to"], e["kind"]) == (
                r.get("from"),
                r.get("to"),
                r.get("kind"),
            ):
                prior = e["id"] in old
                changed = next(
                    (n for n in c["graph"]["nodes"] if n["id"] == e["from"]), {}
                ).get("sha256") != next(
                    (n for n in b["graph"]["nodes"] if n["id"] == e["from"]), {}
                ).get("sha256")
                findings.append(
                    {
                        "id": r["id"] + ":" + e["id"],
                        "kind": "baseline-violation" if prior else "forbidden-edge",
                        "message": r["id"],
                        "edges": [e["id"]],
                        "touched": prior and changed,
                    }
                )
    for i, cycle in enumerate(d["new_cycles"]):
        findings.append(
            {
                "id": "cycle:" + str(i),
                "kind": "new-cycle",
                "message": "New cyclic dependency",
                "edges": cycle["edges"],
                "members": cycle["members"],
            }
        )
    findings.sort(key=lambda f: f["id"])
    violated = any(f["kind"] in ("forbidden-edge", "new-cycle") for f in findings)
    policy_result = "inconclusive" if gaps else ("fail" if violated else "pass")
    gaps.extend(
        "review disposition required: " + f["id"] for f in findings if f.get("touched")
    )
    quality = c["quality"]
    required = c["config"].get("quality", {}).get("required", True)
    if required and quality.get("status") != "available":
        gaps.extend(quality.get("gaps") or ["required quality unavailable"])
    return {
        "policy_result": policy_result,
        "overall_result": "inconclusive" if gaps else ("fail" if violated else "pass"),
        "findings": findings,
        "gaps": sorted(set(gaps)),
    }
