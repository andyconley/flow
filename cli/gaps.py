"""Capability gaps: the framework's own improvement signal, made readable.

`flow-archive` has always asked what the framework was missing during a run.
Until now the answer went into a chat summary and nowhere else, so a gap
observed in one run was invisible when the next one started. One gap was
recorded, forgotten, and observed again from a different project months later —
which is the predicted behavior of a write-only signal, not a discipline
failure.

This module gives that signal a destination and a way back out. The archive
appends; `list` groups by key and counts; `promote` moves a survivor into the
flow repo's backlog.

Three design points worth stating, because each has a wrong-looking alternative:

**The ledger is append-only JSONL and promotion is a second event, not a
mutated flag.** Rewriting a line in the middle of an append log is the only
operation that can corrupt it, and a flag would discard *when* consent happened.

**The ledger lives in the user overlay, not bare `~/.flow/`.** Nothing else
holds an unpromoted gap — under the append model this file is the record, not a
cache rebuildable from run artifacts. `~/.flow/user/` is version-controlled
precisely so personal state survives a lost machine.

**Repeats are detected by an agent-supplied key, never by matching text.** The
agent reads existing keys and reuses one when a new gap is the same gap. That
puts the judgment where judgment belongs and keeps counting exact. Nothing here
enforces the discipline; a careless key silently creates a second lineage.

The CLI is strictly non-interactive. Consent for a promotion is obtained by the
agent in conversation before it runs `promote`, so this module never prompts,
never commits, and never pushes.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from paths import SOURCE_DIR, USER_OVERLAY_DIR

SCHEMA = 1
LEDGER_NAME = "capability-gaps.jsonl"

EVENT_OBSERVED = "observed"
EVENT_PROMOTED = "promoted"

BACKLOG_REL = Path("docs") / "backlog.md"

# Promoted entries land in `## Deferred / Watch`, never `## Active Priorities`.
# Active Priorities is an ordered list whose order is the maintainer's judgment;
# inserting into it — even at the end — is itself a ranking claim about an item
# that has had no triage. Deferred / Watch is the unranked holding area, and its
# entries carry no numbering, so there is no numbering to parse or corrupt.
BACKLOG_ANCHOR = "## Deferred / Watch"

_GIT_TIMEOUT_SEC = 10
_GIT_DID_NOT_RUN = -1


def default_ledger_path(overlay_dir: Path | None = None) -> Path:
    """Where the ledger lives.

    A function, not a module constant, so that importing this module resolves
    no paths. Every pure function below takes an explicit path, which is what
    lets tests exercise them without going near the real ledger.
    """
    base = USER_OVERLAY_DIR if overlay_dir is None else overlay_dir
    return base / LEDGER_NAME


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------


def read_events(path: Path) -> tuple[list[dict], int]:
    """Return (events, skipped) from the ledger.

    A missing ledger is empty, not an error — it does not exist until the first
    archive appends to it. A malformed line is skipped and counted rather than
    raised: one bad line, from a partial write or a hand edit, must not make
    every recorded gap unreadable. The count is surfaced so the damage is
    visible instead of silently swallowed.
    """
    if not path.exists():
        return [], 0
    events: list[dict] = []
    skipped = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except (ValueError, TypeError):
            skipped += 1
            continue
        if isinstance(record, dict) and record.get("event"):
            events.append(record)
        else:
            skipped += 1
    return events, skipped


def append_event(path: Path, event: dict) -> None:
    """Append one event, creating the ledger and its parent if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def add_gap(
    path: Path,
    key: str,
    summary: str,
    project: str,
    run: str,
    at: str,
) -> dict:
    """Record one observation. Returns a result dict; never raises on a repeat.

    Idempotent on `(key, run)`. A repeat is the same key from a *different*
    run — that is the signal worth counting. The same key twice within one run
    is a re-run of the archive, not a recurrence, and inflating the count there
    would make the one number this module exists to produce untrustworthy.
    """
    events, skipped = read_events(path)
    for event in events:
        if (
            event.get("event") == EVENT_OBSERVED
            and event.get("key") == key
            and event.get("run") == run
        ):
            return {"status": "duplicate", "key": key, "run": run, "skipped": skipped}

    append_event(
        path,
        {
            "schema": SCHEMA,
            "event": EVENT_OBSERVED,
            "key": key,
            "summary": summary,
            "project": project,
            "run": run,
            "at": at,
        },
    )
    seen = sum(
        1
        for event in events
        if event.get("event") == EVENT_OBSERVED and event.get("key") == key
    )
    return {
        "status": "added",
        "key": key,
        "run": run,
        "count": seen + 1,
        "skipped": skipped,
    }


def group_gaps(events: list[dict]) -> list[dict]:
    """Group observations by key, most-observed first.

    This grouping is the whole point of the module: a key seen from three
    projects is a recurring framework problem, and that is invisible while the
    observations sit in three separate run artifacts.
    """
    grouped: dict[str, dict] = {}
    for event in events:
        if event.get("event") != EVENT_OBSERVED:
            continue
        key = event.get("key") or "(no key)"
        entry = grouped.setdefault(
            key,
            {
                "key": key,
                "count": 0,
                "summaries": [],
                "sightings": [],
                "promoted_at": None,
            },
        )
        entry["count"] += 1
        summary = event.get("summary") or ""
        if summary and summary not in entry["summaries"]:
            entry["summaries"].append(summary)
        entry["sightings"].append(
            {
                "project": event.get("project") or "(unknown)",
                "run": event.get("run") or "(unknown)",
                "at": event.get("at") or "",
            }
        )

    for event in events:
        if event.get("event") != EVENT_PROMOTED:
            continue
        entry = grouped.get(event.get("key") or "")
        if entry is not None:
            entry["promoted_at"] = event.get("at") or ""

    return sorted(grouped.values(), key=lambda e: (-e["count"], e["key"]))


def is_promoted(events: list[dict], key: str) -> bool:
    return any(
        event.get("event") == EVENT_PROMOTED and event.get("key") == key
        for event in events
    )


# ---------------------------------------------------------------------------
# Repo resolution
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SEC,
        )
    except (OSError, subprocess.SubprocessError):
        return _GIT_DID_NOT_RUN, ""
    return proc.returncode, proc.stdout.strip()


def resolve_checkout(source_dir: Path | None = None) -> Path | None:
    """The work tree behind `~/.flow/source`, or None if there is not one.

    Membership is asked of git, never inferred from a `.git` directory on disk:
    `~/.flow/source` is normally a symlink into a clone, and `.git` exists only
    at a work tree's root, so the filesystem test calls a perfectly good develop
    install untracked. `cli/overlay.py` documents the same rule for the overlay.

    A release install has no work tree here at all — `install.sh` copies the
    framework content in and deletes the clone — so None is the ordinary answer
    for most users, not a fault.
    """
    base = SOURCE_DIR if source_dir is None else source_dir
    if not base.exists():
        return None
    rc, out = _git(base, "rev-parse", "--show-toplevel")
    if rc != 0 or not out:
        return None
    return Path(out)


# ---------------------------------------------------------------------------
# Promotion
# ---------------------------------------------------------------------------


def backlog_entry(entry: dict) -> str:
    """The Markdown block a promoted gap becomes."""
    title = entry["key"].replace("-", " ").replace("_", " ").strip().title()
    lines = [f"### {title}", ""]
    times = "once" if entry["count"] == 1 else f"{entry['count']} times"
    lines.append(f"Status: observed {times}, promoted from the capability-gap ledger")
    lines.append("")
    for summary in entry["summaries"]:
        lines.append(summary)
        lines.append("")
    seen = ", ".join(f"{s['project']} ({s['run']})" for s in entry["sightings"])
    lines.append(f"Seen in: {seen}")
    lines.append("")
    return "\n".join(lines)


def insert_into_backlog(text: str, block: str) -> str:
    """Place `block` at the end of the Deferred / Watch section.

    Raises ValueError when the anchor is missing or ambiguous. Refusing is the
    right failure: this edits a file a human maintains, and guessing where a
    section starts in a document that has been restructured would corrupt it
    silently. The caller turns the refusal into a paste-ready block, so the
    observation is never lost to a failed write.
    """
    lines = text.splitlines()
    anchors = [i for i, line in enumerate(lines) if line.strip() == BACKLOG_ANCHOR]
    if not anchors:
        raise ValueError(f"no {BACKLOG_ANCHOR!r} section found")
    if len(anchors) > 1:
        raise ValueError(f"{BACKLOG_ANCHOR!r} appears {len(anchors)} times")

    start = anchors[0]
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break

    while end > start + 1 and not lines[end - 1].strip():
        end -= 1

    block_lines = ["", *block.rstrip("\n").splitlines()]
    return "\n".join(lines[:end] + block_lines + lines[end:]) + "\n"


def promote(
    ledger_path: Path,
    key: str,
    at: str,
    source_dir: Path | None = None,
) -> dict:
    """Write one gap into the backlog and record that it happened.

    Never commits and never pushes. Publishing is the engineer's decision and
    is made separately from the decision to promote — the tool stops at a dirty
    working tree on purpose.
    """
    events, skipped = read_events(ledger_path)
    grouped = {entry["key"]: entry for entry in group_gaps(events)}
    entry = grouped.get(key)
    if entry is None:
        return {"status": "unknown-key", "key": key, "skipped": skipped}
    if is_promoted(events, key):
        return {"status": "already-promoted", "key": key, "skipped": skipped}

    block = backlog_entry(entry)
    checkout = resolve_checkout(source_dir)
    if checkout is None:
        return {"status": "no-checkout", "key": key, "block": block, "skipped": skipped}

    backlog = checkout / BACKLOG_REL
    if not backlog.exists():
        return {
            "status": "no-backlog",
            "key": key,
            "block": block,
            "path": str(backlog),
            "skipped": skipped,
        }

    try:
        updated = insert_into_backlog(backlog.read_text(encoding="utf-8"), block)
    except ValueError as exc:
        return {
            "status": "unparsable-backlog",
            "key": key,
            "block": block,
            "path": str(backlog),
            "reason": str(exc),
            "skipped": skipped,
        }

    # Write the backlog first, then record the promotion. The reverse order
    # loses the observation if the write fails: the ledger would say promoted
    # while the backlog never received it, and nothing would ever surface the
    # gap again.
    tmp = backlog.with_suffix(backlog.suffix + ".tmp")
    tmp.write_text(updated, encoding="utf-8")
    tmp.replace(backlog)

    append_event(
        ledger_path,
        {
            "schema": SCHEMA,
            "event": EVENT_PROMOTED,
            "key": key,
            "at": at,
            "promoted_to": str(BACKLOG_REL),
        },
    )
    return {"status": "promoted", "key": key, "path": str(backlog), "skipped": skipped}


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def render_list(entries: list[dict], skipped: int, ledger_path: Path) -> str:
    lines: list[str] = []
    if not entries:
        lines.append("no capability gaps recorded yet")
        lines.append(f"ledger: {ledger_path}")
        if skipped:
            lines.append(f"warning: {skipped} unreadable line(s) skipped")
        return "\n".join(lines)

    width = max(max(len(e["key"]) for e in entries), 3)
    lines.append(f"{'KEY'.ljust(width)}  SEEN  STATUS")
    for entry in entries:
        status = "promoted" if entry["promoted_at"] else "open"
        lines.append(
            f"{entry['key'].ljust(width)}  {str(entry['count']).rjust(4)}  {status}"
        )
        for sighting in entry["sightings"]:
            lines.append(
                f"{' ' * width}        {sighting['project']} ({sighting['run']})"
            )
    lines.append("")
    lines.append(f"ledger: {ledger_path}")
    if skipped:
        lines.append(f"warning: {skipped} unreadable line(s) skipped")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_add(args) -> int:
    path = Path(args.ledger) if args.ledger else default_ledger_path()
    result = add_gap(
        path,
        key=args.key,
        summary=args.summary,
        project=args.project,
        run=args.run,
        at=args.at or _now(),
    )
    if result["status"] == "duplicate":
        print(f"already recorded for this run: {result['key']}")
        return 0
    count = result["count"]
    if count > 1:
        print(f"recorded: {result['key']} — seen {count} times now")
    else:
        print(f"recorded: {result['key']}")
    return 0


def cmd_list(args) -> int:
    path = Path(args.ledger) if args.ledger else default_ledger_path()
    events, skipped = read_events(path)
    entries = group_gaps(events)
    if getattr(args, "json", False):
        print(
            json.dumps(
                {"entries": entries, "skipped": skipped}, indent=2, sort_keys=True
            )
        )
        return 0
    print(render_list(entries, skipped, path))
    return 0


def cmd_promote(args) -> int:
    path = Path(args.ledger) if args.ledger else default_ledger_path()
    result = promote(path, key=args.key, at=args.at or _now())
    status = result["status"]

    if status == "promoted":
        print(f"promoted {result['key']} into {result['path']}")
        print("not committed and not pushed — both are yours to make")
        return 0
    if status == "unknown-key":
        print(f"no gap recorded under key: {result['key']}")
        return 1
    if status == "already-promoted":
        print(f"already promoted: {result['key']}")
        return 0
    if status == "no-checkout":
        print("~/.flow/source is not a git work tree, so there is no backlog to write.")
        print("This is normal for a release install. Paste this in yourself:")
        print("")
        print(result["block"])
        return 0

    print(f"cannot write the backlog: {result.get('reason', status)}")
    print("Paste this in yourself:")
    print("")
    print(result["block"])
    return 1
