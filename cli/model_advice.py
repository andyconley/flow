"""Read-only facts and mapping seams for session model advice."""

from __future__ import annotations

import json
import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import usage_store
from cost import capacity_gauge
from fsutil import repo_root
from model_policy import PROFILE_IDS, RUNTIMES, resolve_session_profile
from paths import HOME
from telemetry_freshness import usage_freshness


LANES = ("boot", "define", "solution", "plan", "resume")
POLICY_VERSION = "session-model-advice-v1"
DEFAULT_HISTORY_DAYS = 7


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_only_connection(path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(path.resolve()), safe='/')}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def history_evidence(
    *,
    runtime: str,
    project_root: Path,
    store_path: Path | None = None,
    now: datetime | None = None,
    window_days: int = DEFAULT_HISTORY_DAYS,
) -> dict:
    """Read bounded aggregate evidence without creating or changing the store."""
    path = store_path or usage_store.default_store_path(HOME)
    observed_now = now or datetime.now(timezone.utc)
    base = {
        "state": "absent",
        "window_days": window_days,
        "store": str(path),
        "runtime": runtime,
        "project": str(project_root.resolve()),
        "last_evidence_at": None,
        "models": [],
        "capacity": {"state": "unavailable", "scope": "global", "observed_at": None, "windows": []},
        "freshness": {"state": "unavailable"},
        "limitations": [],
    }
    if not path.exists():
        base["limitations"] = ["usage store is absent; absence is not zero usage"]
        return base
    try:
        conn = _read_only_connection(path)
    except (OSError, sqlite3.Error) as exc:
        return {**base, "state": "unreadable", "limitations": [f"usage store could not be read: {exc}"]}
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version != usage_store.SCHEMA_VERSION:
            return {
                **base,
                "state": "incompatible",
                "schema_version": version,
                "expected_schema_version": usage_store.SCHEMA_VERSION,
                "limitations": ["usage schema is incompatible; no consumption conclusion was drawn"],
            }
        cutoff = _iso(observed_now - timedelta(days=window_days))
        rows = conn.execute(
            """
            SELECT n.model,
                   r.is_subagent,
                   COUNT(*),
                   SUM(COALESCE(n.fresh_input_tokens, 0)
                     + COALESCE(n.cache_read_tokens, 0)
                     + COALESCE(n.cache_write_tokens, 0)
                     + COALESCE(n.output_tokens, 0)),
                   MAX(n.ts),
                   SUM(CASE WHEN n.fresh_input_tokens IS NULL
                              OR n.output_tokens IS NULL THEN 1 ELSE 0 END)
              FROM turn_norm AS n
              JOIN turn_raw AS r ON r.id = n.turn_raw_id
              JOIN session AS s ON s.id = r.session_row_id
             WHERE s.harness = ? AND s.cwd = ? AND n.ts >= ?
             GROUP BY n.model, r.is_subagent
             ORDER BY MAX(n.ts) DESC, n.model, r.is_subagent
            """,
            (runtime, str(project_root.resolve()), cutoff),
        ).fetchall()
        models = [
            {
                "model": row[0],
                "scope": "delegated" if row[1] else "parent",
                "turns": row[2],
                "reported_tokens": row[3],
                "last_evidence_at": row[4],
                "partial_turns": row[5],
            }
            for row in rows
        ]
        latest = max((row["last_evidence_at"] for row in models if row["last_evidence_at"]), default=None)
        partial = any(row["partial_turns"] for row in models)
        state = "partial" if partial or not models else "present"
        freshness = usage_freshness(conn, now=observed_now.timestamp())
        runtime_freshness = freshness.get("harnesses", {}).get(runtime)
        if runtime_freshness and runtime_freshness.get("state") == "stale":
            state = "stale"
        elif not runtime_freshness or runtime_freshness.get("state") == "error":
            state = "partial"
        limitations = [
            "history reports consumption and attribution only; it does not measure quality or latency",
            "reported token fields retain harness semantics and are not a model benchmark",
            "parent and delegated usage are labeled separately; neither proves which model should be selected",
        ]
        if not models:
            limitations.append("no attributable rows were found in the window; this is not zero usage")
        if not runtime_freshness:
            limitations.append(f"no {runtime} harvest freshness receipt was available")
        elif runtime_freshness.get("state") != "fresh":
            limitations.append(
                f"{runtime} harvest is {runtime_freshness.get('state')}; "
                "stored evidence may not describe the current session"
            )
        capacity_gauge_row = capacity_gauge(conn, cutoff, observed_now) if runtime == "codex" else None
        capacity = base["capacity"]
        if capacity_gauge_row:
            windows = []
            for name in ("primary", "secondary"):
                if capacity_gauge_row.get(f"capacity_{name}_used_pct") is not None:
                    windows.append(
                        {
                            "name": name,
                            "used_percent": capacity_gauge_row[f"capacity_{name}_used_pct"],
                            "window_minutes": capacity_gauge_row[f"capacity_{name}_window_minutes"],
                            "resets_at": capacity_gauge_row[f"capacity_{name}_resets_at"],
                            "observed_at": capacity_gauge_row[f"capacity_{name}_ts"],
                        }
                    )
            capacity = {
                "state": "present",
                "scope": "global",
                "observed_at": capacity_gauge_row["ts"],
                "stale": capacity_gauge_row["stale"],
                "windows": windows,
                "limitation": "global capacity is informative and cannot lower the quality posture by itself",
            }
        return {
            **base,
            "state": state,
            "schema_version": version,
            "last_evidence_at": latest,
            "models": models,
            "capacity": capacity,
            "freshness": {
                "state": runtime_freshness.get("state") if runtime_freshness else "unavailable",
                "last_harvested_at": (
                    runtime_freshness.get("last_harvested_at") if runtime_freshness else None
                ),
                "normalized_through": freshness.get("normalized_through"),
            },
            "limitations": limitations,
        }
    except sqlite3.Error as exc:
        return {
            **base,
            "state": "incompatible",
            "limitations": [f"compatible read model was unavailable: {exc}"],
        }
    finally:
        conn.close()


def normalize_parent_context(runtime: str, value: dict | None) -> dict:
    """Keep active-parent evidence separate from configured recommendations."""
    if not value or not value.get("model"):
        return {
            "state": "unknown",
            "runtime": runtime,
            "model": None,
            "effort": None,
            "source": None,
            "observed_at": None,
            "session_binding": None,
            "limitations": ["no verified same-session parent identity was supplied"],
        }
    if value.get("runtime") not in (None, runtime):
        return {
            "state": "unknown",
            "runtime": runtime,
            "model": None,
            "effort": None,
            "source": value.get("source"),
            "observed_at": value.get("observed_at"),
            "session_binding": None,
            "limitations": ["parent declaration belongs to a different runtime"],
        }
    source = value.get("source") or "user"
    requested = value.get("provenance")
    state = "declared"
    limitations = []
    if requested == "observed":
        limitations.append(
            "CLI input cannot prove source freshness or same-session binding and remains declared"
        )
    return {
        "state": state,
        "runtime": runtime,
        "model": value.get("model"),
        "effort": value.get("effort"),
        "source": source,
        "observed_at": value.get("observed_at"),
        "session_binding": "present" if value.get("session_binding") else None,
        "limitations": limitations,
    }


def context_payload(
    manifest: dict,
    *,
    runtime: str,
    lane: str,
    project_root: Path,
    store_path: Path | None = None,
    parent_context: dict | None = None,
    now: datetime | None = None,
) -> dict:
    if runtime not in RUNTIMES:
        raise ValueError(f"unsupported runtime: {runtime}")
    if lane not in LANES:
        raise ValueError(f"unsupported advice lane: {lane}")
    mappings = {
        profile: {
            **resolve_session_profile(manifest, runtime, profile),
            "availability": {"state": "unverified", "source": None},
        }
        for profile in PROFILE_IDS
    }
    return {
        "schema_version": 1,
        "policy_version": POLICY_VERSION,
        "configuration": {
            "identity": hashlib.sha256(
                json.dumps(
                    manifest.get("session_model_profiles", {}),
                    sort_keys=True,
                    default=str,
                ).encode()
            ).hexdigest(),
            "source": "effective merged session_model_profiles",
        },
        "lane": lane,
        "runtime": {"name": runtime, "provenance": "command_argument"},
        "profiles": mappings,
        "parent": normalize_parent_context(runtime, parent_context),
        "history": history_evidence(
            runtime=runtime,
            project_root=project_root,
            store_path=store_path,
            now=now,
        ),
        "limitations": [
            "task characteristics require agent judgment under the shared rubric",
            "configured suitability is not proof of availability, quality, or speed",
            "this command does not select a profile, call a model, switch a session, or configure delegation",
        ],
    }


def _load_manifest():
    from paths import SCAFFOLD_DIR
    from sync import merge_user_overlay

    return merge_user_overlay(SCAFFOLD_DIR)[1]


def context_command(args) -> int:
    parent = None
    if args.parent_model:
        parent = {
            "runtime": args.runtime,
            "model": args.parent_model,
            "effort": args.parent_effort,
            "source": args.parent_source or "user",
            "provenance": "declared",
        }
    payload = context_payload(
        _load_manifest(),
        runtime=args.runtime,
        lane=args.lane,
        project_root=repo_root(),
        parent_context=parent,
    )
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"session model context: {args.runtime} / {args.lane}")
        print(f"parent: {payload['parent']['state']}")
        print(f"history: {payload['history']['state']}")
        for profile, mapping in payload["profiles"].items():
            suffix = (
                f"{mapping['model']} ({mapping['effort']})"
                if mapping["status"] == "resolved"
                else mapping["status"]
            )
            print(f"{profile}: {suffix}; availability unverified")
        print("advisory only: assess the task with the shared rubric; no model was switched")
    return 0


def resolve_command(args) -> int:
    payload = resolve_session_profile(_load_manifest(), args.runtime, args.profile)
    payload["availability"] = {"state": "unverified", "source": None}
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"{payload['profile']} for {payload['runtime']}: {payload['status']}")
        if payload["status"] == "resolved":
            print(f"model: {payload['model']}")
            print(f"effort: {payload['effort']}")
            print("availability: unverified")
        print("advisory only: no model or delegated-agent configuration was changed")
    return 0 if payload["status"] != "invalid" else 1
