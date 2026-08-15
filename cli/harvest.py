"""CLI-facing wrapper around the harness collectors.

Thin by design, matching the rest of the split: argument resolution and
printing live here; parsing and persistence logic live in each collector
module (`codex_collector.py`, `claude_collector.py`).
"""

import sqlite3
from datetime import datetime

import usage_store
from claude_collector import HARNESS as CLAUDE_HARNESS
from claude_collector import default_sessions_root as claude_sessions_root
from claude_collector import harvest_all as claude_harvest_all
from codex_collector import default_sessions_root as codex_sessions_root
from codex_collector import harvest_all as codex_harvest_all
from paths import HOME, SOURCE_DIR


def _connect(store) -> sqlite3.Connection:
    conn = sqlite3.connect(store)
    conn.execute("PRAGMA foreign_keys = ON")
    # A manual run racing a scheduled one (cron, a hook) should wait for the
    # other to finish rather than fail outright on "database is locked."
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def harvest_codex_command() -> int:
    """Harvest `~/.codex/sessions/` into the usage store.

    Ensures the store exists first — unlike `doctor`, this command writes
    data on purpose, so ensuring its own target rather than requiring
    `flow setup machine` to have run first is a real convenience, not scope
    creep on a reporting command.

    Returns 0 if every file harvested cleanly, 1 if any file hard-stopped on a
    malformed line. Files that succeeded still have their rows and watermark
    committed either way — a nonzero exit here means "look at the reported
    file," not "nothing happened."
    """
    store = usage_store.default_store_path(HOME)
    capabilities = usage_store.default_capabilities_path(SOURCE_DIR)
    usage_store.ensure_store(store, capabilities)

    sessions_root = codex_sessions_root(HOME)
    if not sessions_root.is_dir():
        print(f"no Codex sessions found at {sessions_root}")
        return 0

    conn = _connect(store)
    try:
        summary = codex_harvest_all(conn, sessions_root)
    finally:
        conn.close()

    print(
        f"codex harvest: {summary['files']} files, "
        f"{summary['turns']} turns, {summary['activity']} activity events"
    )
    if summary["skipped"]:
        print(f"  skipped {summary['skipped']} records with no resolvable session")
    for failure in summary["failures"]:
        line = failure["line"]
        where = f":{line}" if line is not None else ""
        print(f"  stopped: {failure['path']}{where} — {failure['reason']}")

    return 1 if summary["failures"] else 0


def _claude_rescan_filters(
    since: str | None = None, session: str | None = None
) -> tuple[str, list]:
    """Build the WHERE fragment and params selecting which `harvest` rows a rescan touches.

    Always scoped to `harness = 'claude'`; the two optional narrowings are
    ANDed on top.

    `since` filters `file_mtime`, not `harvested_at` — "rescan transcripts
    written since this date" is a property of the transcript, which is what
    someone rehearsing a rescan on a small slice actually means. Filtering on
    when *we* last harvested would select by our own bookkeeping and would
    include long-dead sessions that happened to be picked up recently.
    `file_mtime` is a REAL POSIX timestamp, so the date string is converted
    once here rather than compared as text.

    `session` matches `source_path` by substring rather than joining
    `session.session_id`. A Claude session's subagent files live under
    `subagents/<parent-session-uuid>/` and declare the *parent's* `sessionId`,
    so the uuid appears in every one of that session's paths — substring
    matching reaches the main transcript and its subagent files together,
    which is what "rescan this session" has to mean for the output-token fix
    to reach the subagent turns. An exact join on `session.source_path` would
    reach only whichever single file was harvested first, and for a session
    with subagents that is frequently not the main one (see
    `claude_collector`'s module docstring on `session.source_path`).
    """
    where = "harness = ?"
    params: list = [CLAUDE_HARNESS]
    if since is not None:
        # datetime.fromisoformat accepts both `2026-08-01` and a full
        # timestamp; a bare date means midnight local, matching how someone
        # typing a date reads it.
        where += " AND file_mtime IS NOT NULL AND file_mtime >= ?"
        params.append(datetime.fromisoformat(since).timestamp())
    if session is not None:
        where += " AND source_path LIKE ?"
        params.append(f"%{session}%")
    return where, params


def _claude_rescan_scope(
    conn: sqlite3.Connection, since: str | None = None, session: str | None = None
) -> dict:
    """Count what a rescan with these filters would touch, changing nothing.

    Backs `--dry-run`. Reports files (matching `harvest` rows) and the
    `turn_raw` rows currently attributed to those files — the second number
    being the one that says how much stored data is in the blast radius,
    which the file count alone does not convey for a corpus whose files
    range from a handful of turns to thousands.
    """
    where, params = _claude_rescan_filters(since, session)
    files = conn.execute(f"SELECT COUNT(*) FROM harvest WHERE {where}", params).fetchone()[0]
    turns = conn.execute(
        "SELECT COUNT(*) FROM turn_raw tr JOIN session s ON s.id = tr.session_row_id"
        " WHERE s.harness = ? AND tr.source_path IN ("
        f"  SELECT source_path FROM harvest WHERE {where})",
        [CLAUDE_HARNESS, *params],
    ).fetchone()[0]
    return {"files": files, "turns": turns}


def _reset_claude_watermarks(
    conn: sqlite3.Connection, since: str | None = None, session: str | None = None
) -> None:
    """Rewind matching Claude files to the start of the file.

    Used by `--rescan` (and its retained `--backfill` alias). Replaying an
    already-harvested file from offset 0 was a free no-op back when
    `turn_raw` inserts were `INSERT OR IGNORE`; under collector v3's
    output-token upsert it is a *correction* pass, which is the point. It is
    also still the only way an already-harvested file's
    `custom-title`/`ai-title`/`cwd` lines get seen by a collector new enough
    to read them, and now the only way its `compact_boundary` records do.
    `last_size` is deliberately left alone — `harvest_file` recomputes it
    fresh from `path.stat()` on every run and never trusts the stored value
    for anything but reporting.

    Filters narrow which rows are zeroed; unfiltered, this is every recorded
    Claude file, the original behaviour. See `_claude_rescan_filters` for what
    each one selects on and why.

    Two small, accepted costs of resetting rather than a narrower scan:
    every matching file is fully re-read from byte 0 for the duration of
    this one run (each file's own future incremental runs are unaffected),
    and `WatermarkAnomaly`'s rotation check (`current_size < last_offset`)
    can't fire against a file that shrank or was replaced between harvests,
    since the offset it would have compared against is now 0. Both are
    one-run costs against files this collector has already fully harvested
    once; neither compounds across repeated runs — the upsert's max-wins
    guard is order-independent, so a correction pass cannot un-correct a row
    it already fixed.
    """
    where, params = _claude_rescan_filters(since, session)
    conn.execute(
        "UPDATE harvest SET last_offset = 0, last_line_no = 0, last_line_hash = NULL"
        f" WHERE {where}",
        params,
    )
    # Derived title state must reset alongside the watermark, or the replay
    # is not idempotent: after a full pass, last_seen_ts holds the file-wide
    # maximum, which is normally GREATER than the accepted title's
    # title_ai_ts (any timestamped activity after the last ai-title — the
    # common shape). A replay that starts from that state hands the file's
    # FIRST ai-title an effective timestamp newer than the stored
    # title_ai_ts, so it gets re-accepted and the title silently flips
    # backwards — found by review tracing, confirmed by reproduction, and
    # now pinned by a harvest→rescan→rescan test. Clearing these two
    # makes every replay a genuine first pass for title derivation. `title`
    # and `title_source` deliberately survive: the custom lockout is
    # order-independent, and keeping `title` protects sessions whose source
    # files no longer exist on disk (their rows would otherwise lose their
    # title with nothing left to re-derive it from).
    #
    # Scoped to the sessions actually being replayed, and this is load-bearing
    # once filters exist: clearing derived state for a session whose files are
    # NOT being rewound leaves it with title_ai_ts NULL and no replay coming
    # to re-derive it, so the next ordinary incremental harvest sees an
    # ai-title with nothing to compare against and can flip that title
    # backwards — the exact bug the unfiltered reset was written to prevent,
    # reintroduced by narrowing only half of it. A session is in scope if
    # either its own source_path or any of its turns' source_path is a file
    # being rewound; both are checked because session.source_path points at
    # whichever of a session's several files was harvested first, which for a
    # session with subagents is frequently not the one carrying its titles.
    conn.execute(
        "UPDATE session SET last_seen_ts = NULL, title_ai_ts = NULL"
        " WHERE harness = ?"
        f"   AND (source_path IN (SELECT source_path FROM harvest WHERE {where})"
        "        OR id IN (SELECT tr.session_row_id FROM turn_raw tr"
        f"                  WHERE tr.source_path IN (SELECT source_path FROM harvest WHERE {where})))",
        [CLAUDE_HARNESS, *params, *params],
    )


def harvest_claude_command(
    rescan: bool = False,
    since: str | None = None,
    session: str | None = None,
    dry_run: bool = False,
) -> int:
    """Harvest `~/.claude/projects/` into the usage store. Same contract as `harvest_codex_command`.

    `rescan=True` rewinds matching already-recorded Claude files' watermarks
    first (see `_reset_claude_watermarks`) and then harvests normally, so
    already-harvested files are re-read from byte 0. That recovers three
    things a plain incremental run cannot: the full `output_tokens` of any
    turn stored before collector v3's upsert, `compact_boundary` records
    dropped before v3 read them, and title/`cwd`/provenance for sessions
    harvested before those existed.

    `since` / `session` narrow which files are rewound; `dry_run` reports the
    scope and writes nothing. A rescan of the whole corpus re-reads every
    recorded transcript, so rehearsing the filters first is the intended
    workflow rather than a nicety.

    `dry_run` returns 0 without harvesting at all — not even the ordinary
    incremental pass. A dry run that harvested would be a dry run that writes,
    which is worse than having no dry run: it would look like a rehearsal and
    behave like a commit.
    """
    store = usage_store.default_store_path(HOME)
    capabilities = usage_store.default_capabilities_path(SOURCE_DIR)
    usage_store.ensure_store(store, capabilities)

    sessions_root = claude_sessions_root(HOME)
    if not sessions_root.is_dir():
        print(f"no Claude Code sessions found at {sessions_root}")
        return 0

    conn = _connect(store)
    try:
        if dry_run:
            scope = _claude_rescan_scope(conn, since=since, session=session)
            scope_desc = _describe_rescan_scope(since, session)
            print(
                f"claude rescan (dry run): would rewind {scope['files']} files"
                f" covering {scope['turns']} stored turns{scope_desc}"
            )
            print("  nothing written — drop --dry-run to run it")
            return 0
        if rescan:
            _reset_claude_watermarks(conn, since=since, session=session)
            conn.commit()
        summary = claude_harvest_all(conn, sessions_root)
    finally:
        conn.close()

    print(
        f"claude harvest: {summary['files']} files, {summary['turns']} turns,"
        f" {summary['activity']} compaction events"
    )
    if summary["skipped"]:
        print(f"  skipped {summary['skipped']} records with no resolvable session")
    for failure in summary["failures"]:
        line = failure["line"]
        where = f":{line}" if line is not None else ""
        print(f"  stopped: {failure['path']}{where} — {failure['reason']}")

    return 1 if summary["failures"] else 0


def _describe_rescan_scope(since: str | None, session: str | None) -> str:
    """Echo the active filters back in the dry-run line.

    A dry run that reports only counts leaves the reader to trust that the
    filter they typed was parsed the way they meant — which is most of what
    the rehearsal is for.
    """
    parts = []
    if since is not None:
        parts.append(f"modified since {since}")
    if session is not None:
        parts.append(f"matching session {session}")
    return f" ({', '.join(parts)})" if parts else " (whole corpus)"
