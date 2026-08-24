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
import telemetry_freshness

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

# ...and enough elapsed time for those snapshots to mean something. The hook
# fires on every session start, so five can accumulate within an hour; a
# count-only gate would call a same-day store mature. Roughly a week, because
# plugins are used irregularly and a shorter window reports "unused" for
# anything simply not reached yet.
MIN_HISTORY_DAYS = 7

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
        # MAX rather than assignment: two writers race, and the loser finishing
        # last would otherwise rewind the watermark to the older revision it
        # saw. Dedup keeps the data correct either way, but the rewind costs a
        # redundant parse of a 150 KB file on the next run.
        " ON CONFLICT(harness, host_id, source_path, scope) DO UPDATE SET"
        "   last_mtime = MAX(last_mtime, excluded.last_mtime),"
        "   scanned_at = excluded.scanned_at",
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

    # `stat` before read, and the order is the whole point. An earlier version
    # read first and compared afterwards, which suppressed the insert but not
    # the parse — so every session still paid to load and decode a 150 KB
    # document, which is the entire cost this guard exists to avoid.
    try:
        probe = claude_json_path.stat()
    except OSError:
        result["error"] = "unreadable"
        return result

    known = scan_state if scan_state is not None else _scan_mtime(
        conn, harness, host_id, str(claude_json_path)
    )
    if known is not None and probe.st_mtime <= known:
        result["skipped_unchanged"] = True
        return result

    read = claude_config.read_usage(claude_json_path)
    if read is None:
        result["error"] = "unreadable"
        return result
    # The mtime stored is the one `read_usage` took alongside the bytes it
    # parsed, not the probe above: the file can be rewritten between the two,
    # and stamping a row with a revision whose contents were never read is how
    # a later delta gets attributed to the wrong change.
    records, stat = read
    mtime = stat.st_mtime

    # The application-level guard: store only counters that actually moved.
    # Without it every observation writes a full copy of all ~127 entries
    # because `source_mtime` is part of the identity, so the table would grow
    # with how often the harness rewrites its config rather than with how often
    # anything was used — and the maturity gate would count file churn as
    # evidence. The UNIQUE key is not a substitute for this; it is what makes
    # this guard's inherent read-then-write race harmless rather than
    # corrupting, since a racing writer can only ever insert a row identical to
    # one this guard would have skipped.
    latest = {
        (r[0], r[1]): r[2]
        for r in conn.execute(
            "SELECT kind, name, usage_count FROM plugin_usage_observation o"
            " WHERE harness = ? AND host_id = ? AND source_mtime = ("
            "   SELECT MAX(source_mtime) FROM plugin_usage_observation i"
            "   WHERE i.harness = o.harness AND i.host_id = o.host_id"
            "     AND i.kind = o.kind AND i.name = o.name)",
            (harness, host_id),
        )
    }

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
        if latest.get((r["kind"], r["name"])) != r["usage_count"]
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
    # Only when something was actually recorded. Writing the scope
    # unconditionally took a write lock and committed on every session start
    # even when the observation was skipped, which is the cost the stat guard
    # exists to avoid, one function up.
    if result["changed"]:
        record_inventory_scope(conn, project_root, harness=harness, host_id=host_id)
    return result


# ---------------------------------------------------------------------------
# read model
# ---------------------------------------------------------------------------

# `usage_count` sits between `source_mtime` and `rowid` in both orderings as a
# tiebreak. Two revisions can land under one `source_mtime` on a filesystem with
# coarse timestamps, and breaking that tie by insertion order alone lets a
# 105-then-100 arrival read as a decrease and print a counter-reset line about
# data that never reset. Counters are monotonic within an install, so ordering
# by the counter is the correct tiebreak; a genuine reset moves the mtime far
# enough that it never lands in the same tie.
#
# The `harness`/`host_id` filter is applied in the CTE, before the window
# functions, which is what makes partitioning on `(kind, name)` alone safe. A
# future caller that drops that filter would silently merge hosts into one
# series.
_LATEST_SQL = """
WITH ordered AS (
  SELECT
    kind, name, usage_count, last_used_at, source_mtime, observed_at,
    LAG(usage_count) OVER (
      PARTITION BY kind, name ORDER BY source_mtime, usage_count, rowid
    ) AS prev_usage_count,
    ROW_NUMBER() OVER (
      PARTITION BY kind, name ORDER BY source_mtime DESC, usage_count DESC, rowid DESC
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
    #
    # Inside the try with everything else: a store with no `harness_capability`
    # table at all (0-byte file, or one this feature created by connecting to a
    # path that was never set up) would otherwise raise straight past this
    # function and be swallowed by doctor's catch-all as "unavailable", which
    # is the absent-vs-unsupported collapse again in a different costume.
    try:
        row = conn.execute(
            "SELECT supported FROM harness_capability WHERE harness = ? AND field = ?",
            (harness, CAPABILITY),
        ).fetchone()
        if row is None:
            return {"state": STATE_STALE, "harness": harness}
        if not row[0]:
            return {"state": STATE_UNSUPPORTED, "harness": harness}

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
    installed_plugin_names = claude_config.installed_plugins(base)
    installed = claude_config.installed_skills(base, project_root)

    skills: list[dict] = []
    plugins: list[dict] = []
    hooked: list[dict] = []
    departed: list[dict] = []
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
        # Tri-state, and the third state is what keeps this honest. Hook
        # detection reads the plugin's install directory, so a plugin whose
        # counter outlived its install answers "no hooks" for the same reason it
        # answers nothing else: it is gone. Routing that absence into the
        # deliberate-invocation lane is precisely the original error — an
        # uninstalled ralph-loop would render 3,552 hook firings as calls, with
        # no caveat, at the moment someone re-checks a prune.
        entry["installed"] = base_name in installed_plugin_names
        entry["hook_entries"] = hook_counts.get(base_name, 0) if entry["installed"] else None

        if not entry["installed"]:
            departed.append(entry)
        elif entry["hook_entries"]:
            hooked.append(entry)
        else:
            plugins.append(entry)

    seen_skills = {s["name"] for s in skills}
    never_invoked_skills = sorted(installed - seen_skills)
    # Map keys matching no installed skill. Surfaced rather than dropped: on the
    # machine this was built against 40 of 73 keys no longer resolved, and 55%
    # of the evidence vanishing silently would leave output that looks clean.
    unresolved_skills = sorted(seen_skills - installed)

    # A reset is not a zero. It satisfies `usage_count == 0` but its history
    # stopped being comparable at the reset, so listing it beside genuinely
    # never-used plugins puts a plugin someone may use daily into the list they
    # prune from. Excluded here and reported as a reset instead.
    reset_names = {r["name"] for r in resets}
    zero_plugins = sorted(
        p["name"] for p in plugins if p["usage_count"] == 0 and p["name"] not in reset_names
    )
    used_plugins = [p for p in plugins if p["usage_count"] > 0]

    # Maturity is elapsed time *and* sample count, not sample count alone. Five
    # snapshots can land in an hour — the hook fires on every session start —
    # and a count-only gate would release the "never invoked" prune list on a
    # same-day store, which is the exact reading the gate exists to withhold.
    elapsed_days = ((span[1] - span[0]) / 86400) if span[0] and span[1] else 0
    mature = snapshots >= MIN_SNAPSHOTS and elapsed_days >= MIN_HISTORY_DAYS

    return {
        "state": STATE_OK if mature else STATE_THIN,
        "harness": harness,
        "snapshots": snapshots,
        "elapsed_days": round(elapsed_days, 1),
        "first_seen": span[0],
        "last_seen": span[1],
        # The scope the *number* was computed from, not whichever row the scan
        # table happened to return. `installed` above is enumerated live from
        # this run's project_root, and every distinct cwd a session ever started
        # in has its own scan row — so reporting one of those would caption this
        # run's figure with an unrelated run's provenance.
        "inventory_scope": str(project_root) if project_root is not None else None,
        "skills_used": sorted(skills, key=lambda s: -s["usage_count"]),
        "skills_never_invoked": never_invoked_skills,
        "skills_unresolved": unresolved_skills,
        "plugins_used": sorted(used_plugins, key=lambda p: -p["usage_count"]),
        "plugins_never_invoked": zero_plugins,
        "plugins_hook_driven": sorted(hooked, key=lambda p: -p["usage_count"]),
        "plugins_departed": sorted(departed, key=lambda p: -p["usage_count"]),
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


def _safe(name: str) -> str:
    """Strip control characters from a name before it reaches a terminal.

    Skill names are directory basenames, and once project-local skills are in
    scope those directories can come from a cloned repository. A POSIX
    directory name may contain ESC and CR, so a repo could ship a skill whose
    name repositions the cursor or overwrites lines in `flow doctor` output —
    a diagnostic someone is reading in order to make a decision.

    Applied at render only. The stored name stays verbatim, because the column
    means "the map key exactly as the harness wrote it".
    """
    return "".join(c for c in name if c.isprintable())


def _display_path(value: str) -> str:
    """Render a path home-relative.

    `flow doctor` output gets pasted into issues, and an absolute project path
    carries the OS username plus whatever the directory is named — client,
    employer, or product. The absolute value stays in the store, where it is
    what makes two scans comparable.
    """
    home = str(Path.home())
    return f"~{value[len(home):]}" if value.startswith(home) else value


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
            return _safe(f"{entry['base_name']} ({ns})")
        return _safe(entry["base_name"])

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
    freshness = payload.get("freshness")

    def degraded(line: str) -> str:
        lines = [head, f"  {line}"]
        if freshness and freshness.get("state") != "fresh":
            action = freshness.get("next_action")
            suffix = f" — run `{action}`" if action else ""
            lines.append(f"  freshness: {freshness.get('state')}{suffix}")
        return "\n".join(lines)

    if state == STATE_UNSUPPORTED:
        return degraded(
            f"not reported by {payload.get('harness', 'this harness')} —"
            " no usage counters exist to sample"
        )
    if state == STATE_STALE:
        return degraded("store predates this feature — run `flow setup machine` to migrate")
    if state == STATE_EMPTY:
        return degraded("no snapshots yet — history starts recording from the next session")

    lines = [
        f"{head}  ({_plural(payload['snapshots'], 'snapshot')}"
        f" since {_fmt_date(payload['first_seen'])})",
        "",
    ]

    used_skills = payload["skills_used"]
    if used_skills:
        shown = used_skills[:5]
        width = _col_width([_safe(s["name"]) for s in shown])
        lines.append("skills, by counter")
        for s in shown:
            # "at last change", not "since last snapshot": rows are only written
            # when a counter moves, so consecutive rows always differ and the
            # delta is the size of the most recent movement.
            delta = "" if s["delta"] is None else f"  +{s['delta']} at last change"
            lines.append(
                f"  {_safe(s['name']):<{width}}  {_fmt_last_used(s['last_used_at']):>10}"
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
            ", ".join(_safe(n) for n in never[:4]) + (", ..." if len(never) > 4 else ""),
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
        # Never truncate silently in the block a prune decision reads. Showing 5
        # of 22 with no counterpart line invites the reader to infer the
        # population from what is on screen.
        if len(used_plugins) > 5:
            lines.append(f"  ... and {len(used_plugins) - 5} more with invocations")

    if payload["state"] == STATE_THIN:
        lines += _wrap(
            f"  {_plural(payload['snapshots'], 'snapshot')}"
            f" over {payload['elapsed_days']} days: ",
            "too little history to say which plugins are unused rather than simply not"
            " reached yet",
        )
    elif payload["plugins_never_invoked"]:
        zero = payload["plugins_never_invoked"]
        lines += _wrap(
            f"  {len(zero)} plugins at zero invocations: ",
            ", ".join(_safe(n) for n in zero[:4]) + (", ..." if len(zero) > 4 else ""),
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

    departed = payload.get("plugins_departed") or []
    if departed:
        lines.append("")
        label = _labeller(departed)
        width = _col_width([label(p) for p in departed])
        lines.append(
            "plugins with counters but no install"
            " (uninstalled or renamed — cannot tell whether these fired hooks)"
        )
        for p in departed[:5]:
            lines.append(
                f"  {label(p):<{width}}  {_fmt_last_used(p['last_used_at']):>10}"
                f"  {p['usage_count']:>6}"
            )
        if len(departed) > 5:
            lines.append(f"  ... and {len(departed) - 5} more")

    if payload["resets"]:
        lines.append("")
        for r in payload["resets"]:
            lines += _wrap(
                f"  counter reset: {_safe(r['name'])} ",
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
        lines.append(
            f"skill inventory scanned from"
            f" {_display_path(payload['inventory_scope'])}"
        )
    lines.append("measured on this machine only")
    if freshness and freshness.get("state") != "fresh":
        action = freshness.get("next_action")
        suffix = f" — run `{action}`" if action else ""
        lines.append(f"freshness: {freshness.get('state')}{suffix}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def _open_store(busy_timeout: int) -> sqlite3.Connection | None:
    """Open the store, or return None when there is nothing to open.

    The existence check has to precede `connect`, because `connect` creates the
    file. Without it, running this on a machine that never ran `flow setup
    machine` left a 0-byte `usage.db` behind and then tracebacked on the first
    missing table — and that empty file went on to make every later run report
    a store that could not be read.
    """
    path = usage_store.default_store_path()
    if not path.exists():
        return None
    try:
        conn = sqlite3.connect(path)
    except sqlite3.Error:
        return None
    conn.execute(f"PRAGMA busy_timeout = {busy_timeout}")
    return conn


def plugin_usage_snapshot_command(hook: bool = False) -> int:
    """`flow plugin-usage snapshot [--hook]`.

    The hook path uses a deliberately short `busy_timeout` — below the verdict
    hook's — so this observer yields rather than making a live hook wait on it.
    Nothing here is worth delaying a session for.
    """
    conn = _open_store(2000 if hook else 5000)
    if conn is None:
        if not hook:
            print("usage snapshot: no usage store — run `flow setup machine`")
        return 0
    try:
        result = snapshot(conn, project_root=Path.cwd())
    except sqlite3.Error as exc:
        # Both writers can hold a write transaction at once, so the loser sees
        # "database is locked" after its busy timeout. A missed sample costs
        # change-timing resolution, never a total, so this is worth nothing more
        # than a line.
        if not hook:
            print(f"usage snapshot: skipped — {exc}")
        return 0
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
    if conn is None:
        payload = {"state": STATE_STALE, "harness": "claude"}
        payload["freshness"] = telemetry_freshness.plugin_freshness(payload)
        print(json.dumps(payload, indent=2, sort_keys=True) if as_json else render_usage_section(payload))
        return 0
    try:
        payload = usage_payload(conn, project_root=Path.cwd())
    except sqlite3.Error as exc:
        if as_json:
            payload = {
                "state": STATE_STALE,
                "harness": "claude",
                "error": str(exc),
            }
            payload["freshness"] = telemetry_freshness.plugin_freshness(payload)
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        print(f"usage: store unavailable — {exc}")
        return 0
    finally:
        conn.close()
    payload["freshness"] = telemetry_freshness.plugin_freshness(payload)
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print(render_usage_section(payload))
    return 0
