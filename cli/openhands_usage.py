"""Import SDK-owned usage into the existing raw/normalized reporting store.

Each persisted conversation contributes only its own LLM buckets. `task:`
rollups are excluded: descendants have their own snapshots and response history.
No agent prompts, tool output, secrets, or credentials are imported.
"""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

COLLECTOR_VERSION = 1


def _stamp(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def harvest_project(conn, root):
    root = Path(root).resolve()
    result = {"sessions": 0, "turns": 0, "failures": [], "notes": []}
    for run_path in sorted((root / ".flow/runs").glob("*/run.json")):
        try:
            if run_path.is_symlink() or not run_path.resolve().is_relative_to(root):
                raise ValueError("run projection escapes project")
            run = json.loads(run_path.read_text())
            if run.get("runtime") != "openhands":
                continue
            references = [*run.get("sessions", {}).values(), *run.get("prior_sessions", [])]
            refs = {str(UUID(ref["conversation_id"])): ref for ref in references}
            persistence = run_path.parent / "openhands"
            if not persistence.resolve().is_relative_to(run_path.parent.resolve()):
                raise ValueError("SDK persistence escapes run")
            snapshots = {}
            for path in sorted(persistence.rglob("base_state.json")):
                if path.is_symlink() or not path.resolve().is_relative_to(persistence.resolve()):
                    raise ValueError("SDK snapshot escapes run persistence")
                state = json.loads(path.read_text())
                session_id = str(UUID(state["id"]))
                snapshots[path.parent] = (path, state, session_id)
            # Root references can project remote usage, or retain usage if a
            # snapshot is temporarily unavailable. Never import outcome.json
            # alongside run.json: it is the same projection.
            seen = set()
            for directory, (path, state, session_id) in snapshots.items():
                ancestor = next((parent for parent in directory.parents if parent in snapshots), None)
                parent_id = snapshots[ancestor][2] if ancestor else None
                top_id = session_id
                current = ancestor
                while current:
                    top_id = snapshots[current][2]
                    current = next((parent for parent in current.parents if parent in snapshots), None)
                reference = refs.get(top_id)
                if reference is None:
                    result["notes"].append(f"{run['work_id']}: unreferenced SDK session {session_id}; not imported")
                    continue
                agent = state.get("agent", {})
                server = agent.get("acp_server")
                provider = {"claude-code": "claude", "codex": "codex"}.get(server, "local")
                own_ref = refs.get(session_id, {})
                metrics = own_ref.get("metrics_by_usage", state.get("stats", {}).get("usage_to_metrics", {}))
                _import(conn, root, run, session_id, parent_id, path, metrics,
                        {**reference, **own_ref, "provider": provider, "model": agent.get("acp_model") or own_ref.get("model")}, result, child=bool(parent_id))
                seen.add(session_id)
            for session_id, ref in refs.items():
                if session_id not in seen and isinstance(ref.get("metrics_by_usage"), dict):
                    _import(conn, root, run, session_id, None, run_path, ref["metrics_by_usage"], ref, result)
                elif session_id not in seen and ref.get("metrics"):
                    result["notes"].append(f"{run['work_id']}: combined-only projection {session_id}; cannot safely attribute child usage")
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            result["failures"].append({"path": str(run_path), "reason": str(exc)})
    return result


def _import(conn, root, run, session_id, parent_id, path, metrics, ref, result, child=False):
    provider = ref.get("provider", "local")
    observed = ref.get("metrics_observed_at") or _stamp(path.stat().st_mtime)
    roles = [key.removeprefix("flow-").removesuffix("-condenser") for key in metrics
             if key.startswith("flow-")]
    role = roles[0] if len(set(roles)) == 1 else (None if child else ref.get("role"))
    with conn:
        conn.execute("INSERT INTO sdk_session(session_id,parent_session_id,cwd,title,source_path,work_id,stage,role,provider,profile)"
                     " VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET role=excluded.role,provider=excluded.provider",
                     (session_id, parent_id, str(root), f"{run['work_id']} {ref.get('stage', '')} {role or 'delegate'}",
                      str(path), run["work_id"], ref.get("stage"), role, provider, None if child else ref.get("profile")))
        row_id = conn.execute("SELECT id FROM sdk_session WHERE session_id=?", (session_id,)).fetchone()[0]
        result["sessions"] += 1
        for usage_id, metric in metrics.items():
            if usage_id.startswith("task:"):
                continue
            usages = metric.get("token_usages", [])
            cumulative = not usages
            aggregate = metric.get("accumulated_token_usage") or {}
            if cumulative:
                if not any(aggregate.get(key, 0) for key in ("prompt_tokens", "completion_tokens", "cache_read_tokens", "cache_write_tokens")):
                    continue
                if conn.execute("SELECT 1 FROM sdk_turn_raw WHERE session_row_id=? AND json_extract(payload,'$.usage_id')=? AND json_extract(payload,'$.record_kind')='call' LIMIT 1", (row_id, usage_id)).fetchone():
                    result["notes"].append(f"{session_id}/{usage_id}: cumulative snapshot cannot replace existing per-call history; retained existing calls")
                    continue
                usages = [aggregate]
                result["notes"].append(f"{session_id}/{usage_id}: cumulative snapshot; call count/context and execution dates unavailable")
            costs = metric.get("costs", [])
            aligned = len(costs) == len(usages)
            for index, usage in enumerate(usages):
                native_id = usage.get("response_id") if provider in {"claude", "codex"} else None
                if provider in {"claude", "codex"} and not native_id:
                    result["notes"].append(f"{session_id}: native response without session identity; omitted to prevent duplication")
                    continue
                cost = metric.get("accumulated_cost") if cumulative else costs[index].get("cost") if aligned else None
                # A zero emitted after LiteLLM failed pricing is not a measured
                # free call. Positive estimates are still not subscription bills.
                pricing = "subscription_not_measured" if native_id else "sdk_estimate" if cost and cost > 0 else "unknown_pricing"
                reported = cost
                ts = _stamp(costs[index]["timestamp"]) if not cumulative and aligned and costs[index].get("timestamp") else observed
                basis = "sdk_cost_timestamp" if not cumulative and aligned and costs[index].get("timestamp") else "observation"
                model = usage.get("model") or metric.get("model_name")
                if model in {"default", "acp-managed"} and ref.get("model"):
                    model = ref["model"]
                raw = json.dumps({"usage": usage, "provider": provider, "usage_id": usage_id, "sdk_reported_cost": cost, "configured_model": ref.get("model"), "record_kind": "cumulative" if cumulative else "call"}, sort_keys=True)
                identity = f"{usage_id}:aggregate" if cumulative else f"{usage_id}:{index}"
                existing = conn.execute("SELECT id,payload,ts,timestamp_basis FROM sdk_turn_raw WHERE session_row_id=? AND natural_turn_id=?", (row_id,identity)).fetchone()
                if existing and (existing[1] != raw or basis == "sdk_cost_timestamp" and (existing[2] != ts or existing[3] != basis)):
                    conn.execute("DELETE FROM sdk_turn_norm WHERE turn_raw_id=?", (existing[0],))
                conn.execute("INSERT INTO sdk_turn_raw(session_row_id,natural_turn_id,turn_seq,is_subagent,ts,model,payload,source_path,source_line_no,collector_version,native_session_id,reported_cost,pricing_status,timestamp_basis)"
                             " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(session_row_id,natural_turn_id) DO UPDATE SET payload=excluded.payload,model=excluded.model,native_session_id=excluded.native_session_id,reported_cost=excluded.reported_cost,pricing_status=excluded.pricing_status,ts=CASE WHEN excluded.timestamp_basis='sdk_cost_timestamp' OR (json_extract(excluded.payload,'$.record_kind')='cumulative' AND sdk_turn_raw.payload != excluded.payload) THEN excluded.ts ELSE sdk_turn_raw.ts END,timestamp_basis=CASE WHEN excluded.timestamp_basis='sdk_cost_timestamp' THEN excluded.timestamp_basis ELSE sdk_turn_raw.timestamp_basis END",
                             (row_id, identity, index, int(child), ts, model, raw,
                              str(path), index, COLLECTOR_VERSION, native_id, reported, pricing, basis))
                result["turns"] += int(existing is None)


def harvest_command(root):
    import usage_store
    from normalize import normalize_all
    from paths import HOME, SOURCE_DIR
    store = usage_store.default_store_path(HOME)
    usage_store.ensure_store(store, usage_store.default_capabilities_path(SOURCE_DIR))
    with sqlite3.connect(store) as conn:
        result = harvest_project(conn, root)
        result["normalize"] = normalize_all(conn)
    print(json.dumps(result, indent=2))
    return int(bool(result["failures"] or result["normalize"]["failures"]))


def reporting_rows(conn, since=None):
    """Attribution and pricing provenance alongside the existing token reports."""
    where = "WHERE NOT (json_extract(r.payload, '$.record_kind')='cumulative' AND EXISTS (SELECT 1 FROM sdk_turn_raw calls WHERE calls.session_row_id=r.session_row_id AND json_extract(calls.payload, '$.usage_id')=json_extract(r.payload, '$.usage_id') AND json_extract(calls.payload, '$.record_kind')='call'))"
    if since:
        where += " AND r.ts >= ?"
    return [dict(row) for row in conn.execute(f"""
        SELECT ss.session_id, ss.parent_session_id, ss.work_id, ss.stage, ss.role,
               ss.profile, ss.provider, r.model, r.pricing_status, r.timestamp_basis, json_extract(r.payload, '$.record_kind') AS record_kind,
               CASE WHEN json_extract(r.payload, '$.record_kind')='cumulative' THEN NULL ELSE COUNT(*) END AS sdk_calls,
               SUM(r.reported_cost) AS sdk_reported_cost,
               SUM(CASE WHEN r.pricing_status='sdk_estimate' THEN r.reported_cost END) AS sdk_estimated_cost,
               NULL AS actual_billed_cost,
               CASE WHEN EXISTS (SELECT 1 FROM session ns JOIN turn_raw nt ON nt.session_row_id=ns.id
                    WHERE ns.harness=ss.provider AND ns.session_id=r.native_session_id)
                    THEN 'native_transcript' ELSE 'sdk' END AS token_source
        FROM sdk_turn_raw r JOIN sdk_session ss ON ss.id=r.session_row_id
        {where}
        GROUP BY ss.id, r.model, r.pricing_status, r.timestamp_basis, record_kind, token_source
        ORDER BY ss.work_id, ss.session_id, r.model
    """, (since,) if since else ()).fetchall()]
