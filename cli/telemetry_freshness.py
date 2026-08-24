"""Freshness summaries for local telemetry read surfaces."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from diagnostic_model import (
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    STATUS_FAILED,
    STATUS_NOT_APPLICABLE,
    STATUS_OK,
    STATUS_WARNING,
    diagnostic,
)

FRESH_WINDOW_SECONDS = 60 * 60


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def _iso_from_ts(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_iso(value: str | None) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        return None


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone() is not None


def usage_freshness(conn: sqlite3.Connection, *, now: float | None = None) -> dict:
    """Classify transcript harvest and normalization freshness from store metadata."""
    clock = _now_ts() if now is None else now
    status: dict = {"state": "empty", "harnesses": {}, "notes": []}
    try:
        if not _table_exists(conn, "harvest"):
            return {"state": "error", "harnesses": {}, "notes": ["usage store is not migrated"]}
        rows = conn.execute(
            "SELECT harness, COUNT(*) AS sources, MAX(harvested_at) AS harvested_at"
            " FROM harvest GROUP BY harness ORDER BY harness"
        ).fetchall()
        norm = conn.execute("SELECT MAX(ts) FROM turn_norm").fetchone()[0]
    except sqlite3.Error as exc:
        return {"state": "error", "harnesses": {}, "notes": [str(exc)]}

    if not rows:
        return {
            "state": "empty",
            "harnesses": {},
            "normalized_through": norm,
            "notes": ["no transcript harvests recorded"],
        }

    states = []
    for row in rows:
        harness = row["harness"] if isinstance(row, sqlite3.Row) else row[0]
        sources = row["sources"] if isinstance(row, sqlite3.Row) else row[1]
        harvested_at = row["harvested_at"] if isinstance(row, sqlite3.Row) else row[2]
        harvested_ts = _parse_iso(harvested_at)
        age_seconds = None if harvested_ts is None else max(0, int(clock - harvested_ts))
        state = "error" if harvested_ts is None else "fresh" if age_seconds <= FRESH_WINDOW_SECONDS else "stale"
        states.append(state)
        status["harnesses"][harness] = {
            "state": state,
            "sources": sources,
            "last_harvested_at": harvested_at,
            "age_seconds": age_seconds,
            "next_action": None if state == "fresh" else f"flow harvest {harness} && flow normalize",
        }

    if "error" in states:
        status["state"] = "error"
    elif "stale" in states and "fresh" in states:
        status["state"] = "partial"
    elif "stale" in states:
        status["state"] = "stale"
    else:
        status["state"] = "fresh"
    status["normalized_through"] = norm
    return status


def plugin_freshness(plugin_payload: dict) -> dict:
    """Classify plugin-usage freshness from the existing read model."""
    state = plugin_payload.get("state")
    if state == "unsupported":
        return {
            "state": "unsupported",
            "harness": plugin_payload.get("harness"),
            "summary": "plugin usage counters are not supported by this harness",
            "next_action": None,
        }
    if state == "stale":
        return {
            "state": "stale",
            "harness": plugin_payload.get("harness"),
            "summary": "plugin usage store predates this feature",
            "next_action": "flow setup machine",
        }
    if state == "empty":
        return {
            "state": "empty",
            "harness": plugin_payload.get("harness"),
            "summary": "no plugin usage snapshots recorded",
            "next_action": "flow plugin-usage snapshot",
        }
    return {
        "state": "fresh" if state == "ok" else "partial",
        "harness": plugin_payload.get("harness"),
        "summary": (
            f"{plugin_payload.get('snapshots', 0)} plugin usage snapshot(s), "
            f"last seen {_iso_from_ts(plugin_payload.get('last_seen')) or '?'}"
        ),
        "last_seen": _iso_from_ts(plugin_payload.get("last_seen")),
        "snapshots": plugin_payload.get("snapshots"),
        "next_action": None if state == "ok" else "flow plugin-usage snapshot",
    }


def freshness_notes(freshness: dict, *, read_only: bool) -> list[str]:
    state = freshness.get("state")
    if state == "fresh":
        return []
    if state == "empty":
        return ["freshness: no usage harvests recorded yet; run `flow harvest claude`, `flow harvest codex`, then `flow normalize`."]
    if state == "error":
        return ["freshness: could not determine usage freshness."]
    if state == "partial":
        notes = ["freshness: partial; one or more harnesses are stale or unreadable."]
    else:
        notes = ["freshness: stale; this view reads stored telemetry."]
    if read_only:
        notes.append("refresh manually with `flow harvest claude`, `flow harvest codex`, then `flow normalize`.")
    return notes


def usage_diagnostics(freshness: dict) -> list:
    state = freshness.get("state")
    if state == "empty":
        return [
            diagnostic(
                "telemetry.usage.empty",
                STATUS_WARNING,
                SEVERITY_WARNING,
                "missing",
                "no usage harvests recorded",
                next_action="flow harvest claude && flow harvest codex && flow normalize",
            )
        ]
    if state == "error":
        return [
            diagnostic(
                "telemetry.usage.status",
                STATUS_FAILED,
                SEVERITY_ERROR,
                "parse_error",
                "usage freshness could not be determined",
                detail="; ".join(freshness.get("notes", [])) or None,
            )
        ]
    items = []
    for harness, info in freshness.get("harnesses", {}).items():
        h_state = info["state"]
        ok = h_state == "fresh"
        items.append(
            diagnostic(
                f"telemetry.{harness}.harvest",
                STATUS_OK if ok else STATUS_WARNING,
                SEVERITY_INFO if ok else SEVERITY_WARNING,
                "ok" if ok else "stale",
                f"{harness} usage harvest is {h_state}",
                target=harness,
                detail=f"last harvested at {info.get('last_harvested_at')}" if info.get("last_harvested_at") else None,
                next_action=None if ok else info.get("next_action"),
            )
        )
    if not items:
        items.append(
            diagnostic(
                "telemetry.usage",
                STATUS_NOT_APPLICABLE,
                SEVERITY_INFO,
                "missing",
                "usage freshness is unavailable",
            )
        )
    return items


def plugin_diagnostic(freshness: dict):
    state = freshness.get("state")
    if state == "fresh":
        return diagnostic(
            "telemetry.plugin_usage",
            STATUS_OK,
            SEVERITY_INFO,
            "ok",
            freshness.get("summary", "plugin usage freshness is ok"),
            target=freshness.get("harness"),
        )
    if state == "unsupported":
        return diagnostic(
            "telemetry.plugin_usage",
            STATUS_NOT_APPLICABLE,
            SEVERITY_INFO,
            "manual_required",
            freshness.get("summary", "plugin usage is unsupported"),
            target=freshness.get("harness"),
        )
    return diagnostic(
        "telemetry.plugin_usage",
        STATUS_WARNING,
        SEVERITY_WARNING,
        "stale" if state == "stale" else "missing",
        freshness.get("summary", "plugin usage freshness needs attention"),
        target=freshness.get("harness"),
        next_action=freshness.get("next_action"),
    )
