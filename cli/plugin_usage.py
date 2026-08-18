"""`flow doctor`'s usage section: which installed plugins and skills earn their keep.

Every other flow surface measures what a session cost. This one measures whether
the configuration that cost it is being used at all. The evidence is counters the
harness maintains itself in `~/.claude.json` — not something flow derives, and
not something it can re-create — so this module samples them into the store and
reports movement over time.

It exists because a configuration prune was once decided on a number that was
accurate and misleading at the same time. A plugin was cut for "0 invocations"
when its counter actually read 3,552; those were Stop-hook firings, and the
harness increments a plugin's counter once per hook firing. The decision held and
the reasoning did not. So the governing rule here is not "report the counters" —
it is **never let a hook firing be read as a use**, which is why hook-registering
plugins render in their own block and never share a column with deliberate calls.

Three properties of the data drive nearly every decision below:

  Opposite zero-semantics. `pluginUsage` is seeded at install, so a plugin at
  zero is a real reading of "never used". `skillUsage` is written on first use,
  so it holds no zeros at all and an unused skill is simply absent. The same
  looking row means opposite things, and the two are worded differently on
  purpose.

  Doubled keys. `security-guidance@claude-plugins-official` and
  `security-guidance@inline` are one plugin under two map keys. They are stored
  verbatim and folded only for display, never summed: whether the two counters
  double-count the same invocations or count disjoint ones is unverified, and a
  total this store cannot back up is exactly the kind of confident number that
  caused the original error.

  No backfill. The harness keeps no history, so this reports only what flow has
  observed since it started looking. A snapshot's absolute counts are unreliable
  archaeology — key names have drifted across renames and uninstalls — but every
  delta between two observations flow made itself is trustworthy, because it saw
  both endpoints.

Claude-only, gated on the `plugin_usage_counters` capability. Codex maintains no
equivalent, and the section says so rather than rendering an empty table that
implies there was nothing to find.

Import direction is one-way: this module imports `usage_store`, `claude_config`
and `paths`, and nothing in `cost.py`'s tree imports it or is imported by it.
`harness_supports` is duplicated from `baseline.py` rather than imported for that
reason — six lines is a cheaper price than putting this module on the live
`verdict`/`warn` hook paths.
"""

import json
import sqlite3
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path

import claude_config
import usage_store

CAPABILITY = "plugin_usage_counters"

# `plugin_usage_scan.source_path` for the installed-skill walk. Not a real path:
# the row records that an enumeration happened and how wide it reached, which is
# a different kind of watermark from "we read this file".
INVENTORY_SOURCE = "skill-inventory"

# Snapshots required before a "never invoked" plugin rollup renders at all.
# Borrowed from `baseline`'s min_n rather than introduced as a new tunable. A
# plugin at zero after two days is evidence of a short window, not of disuse,
# and a list that looks identical to the mature one while meaning something
# weaker is worse than no list.
MIN_SNAPSHOTS = 5

STATE_UNSUPPORTED = "unsupported"
STATE_STALE = "stale"
STATE_EMPTY = "empty"
STATE_THIN = "thin"
STATE_OK = "ok"


def default_claude_config_path(home: Path) -> Path:
    return home / ".claude.json"


def default_settings_path(home: Path) -> Path:
    return home / ".claude" / "settings.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def harness_supports(conn: sqlite3.Connection, harness: str, field: str) -> bool:
    """Whether `harness` can report `field` at all, per `harness_capability`.

    Duplicated from `baseline.py` on purpose — see the module docstring. Absent
    rows read as unsupported, so a harness the seed has never heard of degrades
    to "cannot report" rather than silently behaving as though it could.
    """
    row = conn.execute(
        "SELECT supported FROM harness_capability WHERE harness = ? AND field = ?",
        (harness, field),
    ).fetchone()
    return bool(row and row[0])


# ---------------------------------------------------------------------------
# write path
# ---------------------------------------------------------------------------


def _scan_mtime(
    conn: sqlite3.Connection, harness: str, host_id: str, source_path: str, scope: str = ""
) -> float | None:
    row = conn.execute(
        "SELECT last_mtime FROM plugin_usage_scan"
        " WHERE harness = ? AND host_id = ? AND source_path = ? AND scope = ?",
        (harness, host_id, source_path, scope),
    ).fetchone()
    return float(row[0]) if row else None


def _record_scan(
    conn: sqlite3.Connection,
    harness: str,
    host_id: str,
    source_path: str,
    mtime: float,
    scope: str = "",
) -> None:
    conn.execute(
        "INSERT INTO plugin_usage_scan"
        " (harness, host_id, source_path, scope, last_mtime, scanned_at)"
        " VALUES (?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(harness, host_id, source_path, scope) DO UPDATE SET"
        "   last_mtime = excluded.last_mtime, scanned_at = excluded.scanned_at",
        (harness, host_id, source_path, scope, mtime, _now()),
    )


def observe_usage(
    claude_json_path: Path,
    conn: sqlite3.Connection,
    scan_state: float | None = None,
    harness: str = "claude",
    host_id: str = "",
) -> dict:
    """Read the counters and store any state not already recorded.

    The guarded write path in order: `stat` the file, compare its mtime against
    the recorded watermark, and only then parse and insert. That order is the
    real guard — the file is 150 KB and larger, so parsing it on every call
    would be the whole cost of the feature.

    `scan_state` overrides the watermark read, so a test can simulate "another
    writer already recorded this revision" without seeding rows through SQL.
    Pass `None` to read the table normally.

    Never raises for a missing or unreadable file: both callers — a hook and a
    CLI command — need "nothing to do" and "could not read" to be handled the
    same way, so both come back as a result dict.

    `INSERT OR IGNORE` against a UNIQUE over observed state is what makes this
    safe to run concurrently with the harvest backstop. Two writers that saw the
    same revision write identical rows and the second is a no-op; neither can
    compute a delta against a row the other just wrote, because no delta is
    stored at all.
    """
    result = {"changed": False, "inserted": 0, "skipped_unchanged": False, "error": None}

    read = claude_config.read_usage(claude_json_path)
    if read is None:
        result["error"] = "unreadable"
        return result
    records, stat = read
    mtime = stat.st_mtime

    known = scan_state if scan_state is not None else _scan_mtime(
        conn, harness, host_id, str(claude_json_path)
    )
    if known is not None and mtime <= known:
        result["skipped_unchanged"] = True
        return result

    observed_at = _now()
    rows = [
        (
            harness,
            host_id,
            r["kind"],
            r["name"],
            r["usage_count"],
            r["last_used_at"],
            mtime,
            observed_at,
        )
        for r in records
    ]
    with conn:
        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO plugin_usage_observation"
            " (harness, host_id, kind, name, usage_count, last_used_at,"
            "  source_mtime, observed_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        inserted = conn.total_changes - before
        _record_scan(conn, harness, host_id, str(claude_json_path), mtime)

    result["inserted"] = inserted
    result["changed"] = inserted > 0
    return result


def record_inventory_scope(
    conn: sqlite3.Connection,
    scope: Path | None,
    harness: str = "claude",
    host_id: str = "",
) -> None:
    """Record that a skill inventory was enumerated, and how wide it reached.

    Stored because `skillUsage` holds no zeros, so "which skills are unused"
    depends on enumerating installed skills — and once project-local skills
    count, that enumeration depends on where it ran. Without the scope, a later
    read cannot tell "absent because never invoked" from "absent because this
    scan never looked where it lives".
    """
    with conn:
        _record_scan(
            conn,
            harness,
            host_id,
            INVENTORY_SOURCE,
            time.time(),
            scope=str(scope) if scope is not None else "",
        )


def snapshot(
    conn: sqlite3.Connection,
    home: Path | None = None,
    project_root: Path | None = None,
    harness: str = "claude",
    host_id: str = "",
) -> dict:
    """Observe the counters and record the inventory scope. The whole write path."""
    base = home if home is not None else Path.home()
    result = observe_usage(
        default_claude_config_path(base), conn, harness=harness, host_id=host_id
    )
    record_inventory_scope(conn, project_root, harness=harness, host_id=host_id)
    return result


# ---------------------------------------------------------------------------
# read model
# ---------------------------------------------------------------------------

_LATEST_SQL = """
WITH ordered AS (
  SELECT
    kind, name, usage_count, last_used_at, source_mtime, observed_at,
    LAG(usage_count) OVER (
      PARTITION BY kind, name ORDER BY source_mtime, rowid
    ) AS prev_usage_count,
    ROW_NUMBER() OVER (
      PARTITION BY kind, name ORDER BY source_mtime DESC, rowid DESC
    ) AS rn
  FROM plugin_usage_observation
  WHERE harness = ? AND host_id = ?
)
SELECT
  kind, name, usage_count, last_used_at, source_mtime, observed_at,
  prev_usage_count,
  CASE
    WHEN prev_usage_count IS NULL THEN NULL
    WHEN usage_count < prev_usage_count THEN NULL
    ELSE usage_count - prev_usage_count
  END AS delta,
  (prev_usage_count IS NOT NULL AND usage_count < prev_usage_count) AS is_reset
FROM ordered
WHERE rn = 1
ORDER BY kind, name
"""


def usage_payload(
    conn: sqlite3.Connection,
    harness: str = "claude",
    home: Path | None = None,
    project_root: Path | None = None,
    host_id: str = "",
) -> dict:
    """Everything the section renders, as data.

    Catches the missing-table case rather than propagating it: `flow doctor` is
    read-only and never migrates, so on the first run after an upgrade the store
    is still at the previous version. A traceback there would break doctor for
    every existing user at exactly the moment they most need it to work.
    """
    base = home if home is not None else Path.home()

    # Absent and unsupported are different answers and must not collapse.
    # `harness_capability` has existed since v1, so a *missing* row means this
    # store predates the feature and has not been re-seeded — not that the
    # harness cannot report. Collapsing the two told every existing user on an
    # unmigrated store "no usage counters exist to sample", which is false about
    # Claude and is exactly the confident-wrong statement this surface exists to
    # prevent. Only an explicit 0 means unsupported.
    row = conn.execute(
        "SELECT supported FROM harness_capability WHERE harness = ? AND field = ?",
        (harness, CAPABILITY),
    ).fetchone()
    if row is None:
        return {"state": STATE_STALE, "harness": harness}
    if not row[0]:
        return {"state": STATE_UNSUPPORTED, "harness": harness}

    try:
        rows = conn.execute(_LATEST_SQL, (harness, host_id)).fetchall()
        snapshots = conn.execute(
            "SELECT COUNT(DISTINCT source_mtime) FROM plugin_usage_observation"
            " WHERE harness = ? AND host_id = ?",
            (harness, host_id),
        ).fetchone()[0]
        span = conn.execute(
            "SELECT MIN(source_mtime), MAX(source_mtime) FROM plugin_usage_observation"
            " WHERE harness = ? AND host_id = ?",
            (harness, host_id),
        ).fetchone()
        scope_row = conn.execute(
            "SELECT scope, scanned_at FROM plugin_usage_scan"
            " WHERE harness = ? AND host_id = ? AND source_path = ?",
            (harness, host_id, INVENTORY_SOURCE),
        ).fetchone()
    except sqlite3.OperationalError:
        return {"state": STATE_STALE, "harness": harness}

    if not rows:
        return {"state": STATE_EMPTY, "harness": harness}

    enabled = claude_config.read_enabled_plugins(default_settings_path(base))
    # Enablement belongs to the plugin, not to the map key. `security-guidance`
    # appears in the counters under two keys but only once in `enabledPlugins`,
    # so an exact-key lookup leaves the `@inline` twin reading "unknown" beside
    # its own marketplace row saying "disabled" — two answers for one plugin.
    enabled_by_base: dict[str, bool] = {}
    for key, value in enabled.items():
        enabled_by_base.setdefault(claude_config.base_plugin_name(key), value)
    hook_counts = claude_config.hook_registering_plugins(base)
    installed = claude_config.installed_skills(base, project_root)

    skills: list[dict] = []
    plugins: list[dict] = []
    hooked: list[dict] = []
    resets: list[dict] = []

    for row in rows:
        kind, name, count, last_used, mtime, observed, _prev, delta, is_reset = row
        entry = {
            "name": name,
            "usage_count": count,
            "last_used_at": last_used,
            "delta": delta,
            "is_reset": bool(is_reset),
            "observed_at": observed,
        }
        if is_reset:
            resets.append({"name": name, "kind": kind})
        if kind == "skill":
            skills.append(entry)
            continue

        base_name = claude_config.base_plugin_name(name)
        entry["base_name"] = base_name
        entry["namespace"] = name[len(base_name) + 1 :] if name != base_name else None
        entry["enabled"] = (
            enabled[name] if name in enabled else enabled_by_base.get(base_name)
        )
        entry["hook_entries"] = hook_counts.get(base_name, 0)
        # The load-bearing split. A hook-registering plugin's counter measures
        # how many hook events it declares, not anything a person did, so it
        # never shares a lane with deliberate invocations.
        (hooked if entry["hook_entries"] else plugins).append(entry)

    seen_skills = {s["name"] for s in skills}
    never_invoked_skills = sorted(installed - seen_skills)
    # Map keys matching no installed skill. Surfaced rather than dropped: on the
    # machine this was built against 40 of 73 keys no longer resolved, and 55%
    # of the evidence vanishing silently would leave output that looks clean.
    unresolved_skills = sorted(seen_skills - installed)

    zero_plugins = sorted(p["name"] for p in plugins if p["usage_count"] == 0)
    used_plugins = [p for p in plugins if p["usage_count"] > 0]

    state = STATE_OK if snapshots >= MIN_SNAPSHOTS else STATE_THIN
    return {
        "state": state,
        "harness": harness,
        "snapshots": snapshots,
        "first_seen": span[0],
        "last_seen": span[1],
        "inventory_scope": scope_row[0] if scope_row else None,
        "inventory_scanned_at": scope_row[1] if scope_row else None,
        "skills_used": sorted(skills, key=lambda s: -s["usage_count"]),
        "skills_never_invoked": never_invoked_skills,
        "skills_unresolved": unresolved_skills,
        "plugins_used": sorted(used_plugins, key=lambda p: -p["usage_count"]),
        "plugins_never_invoked": zero_plugins,
        "plugins_hook_driven": sorted(hooked, key=lambda p: -p["usage_count"]),
        "resets": resets,
    }


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------


def _fmt_date(mtime: float | None) -> str:
    if not mtime:
        return "?"
    return datetime.fromtimestamp(mtime, timezone.utc).date().isoformat()


def _fmt_last_used(value: str | None) -> str:
    return (value or "")[:10] or "—"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


# Doctor output is read in a terminal, so a line that runs past the window wraps
# somewhere arbitrary and stops being a table. Rollup prose is wrapped to this;
# columns are sized from the data instead, so nothing is truncated away.
_WRAP = 92


def _wrap(prefix: str, body: str, indent: str = "    ") -> list[str]:
    return textwrap.wrap(
        body,
        width=_WRAP,
        initial_indent=prefix,
        subsequent_indent=indent,
        break_long_words=False,
        break_on_hyphens=False,
    ) or [prefix.rstrip()]


def _labeller(entries: list[dict]):
    """Build a display-name function that shows a namespace only where it disambiguates.

    The namespace has to survive into the output wherever one plugin appears
    under more than one map key — two rows reading `security-guidance` with
    different numbers and no way to tell them apart reads as a rendering bug
    rather than as the two distinct counters it is. But most plugins appear
    once, and spending a third of the line on `claude-plugins-official` for
    every one of them pushes the real columns off the edge.

    So the suffix is added exactly where it carries information: base names with
    more than one variant present. Truncating it is not an option — a namespace
    trimmed to `claude-plu…` disambiguates nothing, which is the one job it has
    — so the column is sized to fit whatever is actually there.
    """
    seen: dict[str, int] = {}
    for e in entries:
        seen[e["base_name"]] = seen.get(e["base_name"], 0) + 1

    def label(entry: dict) -> str:
        ns = entry.get("namespace")
        if ns and seen.get(entry["base_name"], 0) > 1:
            return f"{entry['base_name']} ({ns})"
        return entry["base_name"]

    return label


def _col_width(values: list[str], floor: int = 18) -> int:
    return max([floor, *(len(v) for v in values)]) if values else floor


def render_usage_section(payload: dict) -> str:
    """The `flow doctor` section body.

    Two lines in every degraded state, and it grows only with what was actually
    used. The caveats print here rather than only in the docs because a
    limitation someone has to go and find does not protect the number they are
    reading right now.
    """
    head = "-- usage: skills & plugins --"
    state = payload.get("state")

    if state == STATE_UNSUPPORTED:
        return (
            f"{head}\n"
            f"  not reported by {payload.get('harness', 'this harness')} —"
            " no usage counters exist to sample"
        )
    if state == STATE_STALE:
        return f"{head}\n  store predates this feature — run `flow setup machine` to migrate"
    if state == STATE_EMPTY:
        return f"{head}\n  no snapshots yet — history starts recording from the next session"

    lines = [
        f"{head}  ({_plural(payload['snapshots'], 'snapshot')}"
        f" since {_fmt_date(payload['first_seen'])})",
        "",
    ]

    used_skills = payload["skills_used"]
    if used_skills:
        shown = used_skills[:5]
        width = _col_width([s["name"] for s in shown])
        lines.append("skills, by counter")
        for s in shown:
            delta = "" if s["delta"] is None else f"  +{s['delta']} since last"
            lines.append(
                f"  {s['name']:<{width}}  {_fmt_last_used(s['last_used_at']):>10}"
                f"  {s['usage_count']:>6}{delta}"
            )
        if len(used_skills) > 5:
            lines.append(f"  ... and {len(used_skills) - 5} more with a counter")

    never = payload["skills_never_invoked"]
    if never:
        # `~` because this is the one inferred figure on the surface: it comes
        # from diffing an installed-skill walk against the counters, not from
        # anything the harness reported.
        lines += _wrap(
            f"  ~{len(never)} installed skills never invoked: ",
            ", ".join(never[:4]) + (", ..." if len(never) > 4 else ""),
        )

    unresolved = payload["skills_unresolved"]
    if unresolved:
        lines += _wrap(
            f"  {len(unresolved)} counter keys match no installed skill: ",
            "renamed or uninstalled, so their history is not comparable to anything"
            " currently on disk",
        )

    used_plugins = payload["plugins_used"]
    if used_plugins:
        lines.append("")
        lines.append("plugins, deliberate invocations")
        shown = used_plugins[:5]
        label = _labeller(shown)
        width = _col_width([label(p) for p in shown])
        for p in shown:
            lines.append(
                f"  {label(p):<{width}}  {_fmt_last_used(p['last_used_at']):>10}"
                f"  {p['usage_count']:>6}"
            )

    if payload["state"] == STATE_THIN:
        lines += _wrap(
            f"  {_plural(payload['snapshots'], 'snapshot')} so far: ",
            "too few to say which plugins are unused rather than simply not reached yet",
        )
    elif payload["plugins_never_invoked"]:
        zero = payload["plugins_never_invoked"]
        lines += _wrap(
            f"  {len(zero)} plugins at zero invocations: ",
            ", ".join(zero[:4]) + (", ..." if len(zero) > 4 else ""),
        )

    hooked = payload["plugins_hook_driven"]
    if hooked:
        lines.append("")
        lines.append(
            "plugins, hook-driven firings"
            " (not a usage signal — counts hook events, not deliberate calls)"
        )
        label = _labeller(hooked)
        width = _col_width([label(p) for p in hooked])
        for p in hooked:
            enabled = p.get("enabled")
            mark = "enabled" if enabled else ("disabled" if enabled is False else "unknown")
            lines.append(
                f"  {label(p):<{width}}  {p['usage_count']:>9,} firings"
                f"  {_plural(p['hook_entries'], 'hook'):<8}  {mark}"
            )

    if payload["resets"]:
        lines.append("")
        for r in payload["resets"]:
            lines += _wrap(
                f"  counter reset: {r['name']} ",
                "reads lower than its predecessor, so history across that point is not"
                " comparable",
            )

    lines.append("")
    lines.append(
        "counters are maintained by the harness, not by flow;"
        " deltas cover only what flow has observed"
    )
    lines.append("~ marks a value inferred by diffing installed skills against the counters")
    if payload.get("inventory_scope"):
        lines.append(f"skill inventory scanned from {payload['inventory_scope']}")
    lines.append("measured on this machine only")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def _open_store(busy_timeout: int) -> sqlite3.Connection:
    path = usage_store.default_store_path()
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA busy_timeout = {busy_timeout}")
    return conn


def plugin_usage_snapshot_command(hook: bool = False) -> int:
    """`flow plugin-usage snapshot [--hook]`.

    The hook path uses a deliberately short `busy_timeout` — below the verdict
    hook's — so this observer yields rather than making a live hook wait on it.
    Nothing here is worth delaying a session for.
    """
    conn = _open_store(2000 if hook else 5000)
    try:
        result = snapshot(conn, project_root=Path.cwd())
    finally:
        conn.close()
    if hook:
        return 0
    if result.get("error"):
        print("usage snapshot: could not read the harness config")
        return 0
    if result["skipped_unchanged"]:
        print("usage snapshot: no change since the last observation")
        return 0
    print(f"usage snapshot: {result['inserted']} observations recorded")
    return 0


def plugin_usage_show_command(as_json: bool = False) -> int:
    """`flow plugin-usage show [--json]` — the same payload doctor renders."""
    conn = _open_store(5000)
    try:
        payload = usage_payload(conn, project_root=Path.cwd())
    finally:
        conn.close()
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print(render_usage_section(payload))
    return 0
