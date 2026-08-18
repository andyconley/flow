"""Readers for Claude Code's own on-disk configuration.

Everything flow needs to know about how the local Claude install is configured
lives behind this module: the usage counters the harness maintains, which
plugins are enabled, which skills are installed, and which plugins register
hooks. Pure stdlib, no store access, no rendering.

Nothing here resolves a path on its own. Every entry point takes the path as a
parameter for the same reason `usage_store.default_store_path()` is a function
rather than a module constant: a directly-imported unit test must never end up
reading the real `~/.claude.json`.

Every reader answers a data problem with a neutral value — `None`, an empty
set, a zero — never an exception. These files belong to another program, which
rewrites them on its own schedule with no locking flow can observe, so a torn
read is an ordinary event rather than a fault. A caller that cannot distinguish
"absent" from "unreadable" would report a confident zero where the honest
answer is "no reading", so the two are kept distinguishable at every boundary:
`read_usage` returns `None` for both and reports the reason separately.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# `pluginUsage` is seeded at install, so a zero there is a real reading.
# `skillUsage` is written on first use, so it holds no zeros at all and an
# unused skill is simply absent. Both maps are read the same way; the
# asymmetry is the read model's problem, not this module's.
_USAGE_MAPS = (("pluginUsage", "plugin"), ("skillUsage", "skill"))


def read_usage(path: Path) -> tuple[list[dict], os.stat_result] | None:
    """Parse the `pluginUsage` and `skillUsage` maps out of `~/.claude.json`.

    Returns `(records, stat)` or `None` when the file is absent, unreadable,
    mid-write, or not shaped as expected. The `stat` is returned alongside
    rather than re-stat'd by the caller so the mtime recorded against an
    observation is the one belonging to the bytes actually parsed — a second
    `stat` could straddle a rewrite and stamp the row with a revision whose
    contents were never read.

    Each record is `{kind, name, usage_count, last_used_at, startups}`. `name`
    is the map key verbatim, namespace included: `security-guidance@inline` and
    `security-guidance@claude-plugins-official` are separate records here and
    are only folded together at render time. `startups` is `lastUsedNumStartups`
    where the harness supplies it (plugins only) and `None` otherwise.
    """
    try:
        stat = path.stat()
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None

    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        # A torn read of a file another process is rewriting. Not a fault.
        return None

    if not isinstance(data, dict):
        return None

    records: list[dict] = []
    for key, kind in _USAGE_MAPS:
        entries = data.get(key)
        if not isinstance(entries, dict):
            continue
        for name, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            count = entry.get("usageCount")
            if not isinstance(count, int) or isinstance(count, bool):
                # A non-integer counter is a shape flow does not understand.
                # Skipping the entry keeps the rest of the map usable; coercing
                # it would invent a reading.
                continue
            startups = entry.get("lastUsedNumStartups")
            records.append(
                {
                    "kind": kind,
                    "name": name,
                    "usage_count": count,
                    "last_used_at": _as_iso(entry.get("lastUsedAt")),
                    "startups": startups if isinstance(startups, int) else None,
                }
            )

    return records, stat


def _as_iso(value: object) -> str | None:
    """Normalize `lastUsedAt` to an ISO 8601 UTC string.

    The harness writes this as epoch **milliseconds**, not a string — a first
    version of this reader assumed ISO text, rejected every integer, and turned
    a populated field into `None` for all 127 entries without failing anything.
    Both forms are accepted now in case the harness ever changes its mind.

    Converting the format is not the same as inferring a value: the instant is
    exactly what was reported, only spelled the way the rest of the store spells
    timestamps. Anything that is neither an int nor a string reads as absent,
    because a timestamp flow cannot interpret is not one it should guess at.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        try:
            return (
                datetime.fromtimestamp(value / 1000, timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            )
        except (OSError, OverflowError, ValueError):
            return None
    return None


def read_enabled_plugins(path: Path) -> dict[str, bool]:
    """Read `enabledPlugins` from a Claude `settings.json`.

    Returns `{}` when the file is absent, unreadable, or carries no such map —
    which a caller must treat as "enablement unknown", not "nothing enabled".
    This state deliberately does not live in the observation table: it comes
    from a different file written by a different process, and on some machines
    that file is a symlink into a dotfiles repo whose contents change via
    `git pull` with the harness never involved.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    enabled = data.get("enabledPlugins")
    if not isinstance(enabled, dict):
        return {}
    return {k: bool(v) for k, v in enabled.items()}


def installed_skills(user_home: Path, project_root: Path | None = None) -> set[str]:
    """Enumerate installed skills, named as `skillUsage` keys them.

    User and project skills key on their directory name; plugin skills key as
    `plugin:skill`. Returns a set of those names.

    This enumeration is what makes "never invoked" answerable at all, because
    `skillUsage` contains no zero entries — an unused skill is absent from the
    map rather than present at zero. It is also directory-dependent once
    `project_root` is supplied, which is why callers record the scope they
    scanned alongside the result: two scans rooted in different projects
    legitimately enumerate different populations, and comparing them as one
    would turn "this scan never looked there" into "never used".
    """
    names: set[str] = set()

    for root in (user_home / ".claude" / "skills",):
        names |= _skill_dir_names(root)

    if project_root is not None:
        names |= _skill_dir_names(project_root / ".claude" / "skills")

    # cache/<marketplace>/<plugin>/<version>/skills/<skill>/SKILL.md
    cache = user_home / ".claude" / "plugins" / "cache"
    for skill_md in _glob(cache, "*/*/*/skills/*/SKILL.md"):
        parts = skill_md.parts
        if len(parts) >= 5:
            names.add(f"{parts[-5]}:{parts[-2]}")

    return names


def _skill_dir_names(root: Path) -> set[str]:
    return {p.parent.name for p in _glob(root, "*/SKILL.md")}


def _glob(root: Path, pattern: str) -> list[Path]:
    """`Path.glob` that answers an unreadable or absent root with no matches."""
    try:
        return list(root.glob(pattern))
    except OSError:
        return []


def hook_registering_plugins(user_home: Path) -> dict[str, int]:
    """Map each installed plugin's base name to how many hook entries it registers.

    This is the labeling that keeps a hook firing from being read as a use. The
    harness increments a plugin's counter once per hook firing, so a plugin's
    number scales with how many hook events it registers rather than with
    anything a person did: one plugin registering five entries across four
    events accumulates counts in the tens of thousands while a plugin invoked
    deliberately sits in single digits.

    Keyed by base name, without the `@marketplace` suffix, because the counter
    map and the install layout name plugins differently and the `@inline`
    variants have no install directory at all.
    """
    counts: dict[str, int] = {}
    cache = user_home / ".claude" / "plugins" / "cache"
    # cache/<marketplace>/<plugin>/<version>/hooks/hooks.json
    for hooks_json in _glob(cache, "*/*/*/hooks/hooks.json"):
        plugin = hooks_json.parts[-4] if len(hooks_json.parts) >= 4 else None
        if plugin is None:
            continue
        try:
            data = json.loads(hooks_json.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        hooks = data.get("hooks") if isinstance(data, dict) else None
        if not isinstance(hooks, dict):
            continue
        total = 0
        for handlers in hooks.values():
            total += len(handlers) if isinstance(handlers, list) else 1
        # Highest wins when several versions are cached: the count is used to
        # decide whether a plugin fires hooks at all, and under-reporting that
        # is the direction that misleads.
        counts[plugin] = max(counts.get(plugin, 0), total)
    return counts


def base_plugin_name(name: str) -> str:
    """Strip the `@marketplace` suffix from a plugin map key.

    `rpartition` rather than `split` so a key containing more than one `@`
    keeps everything before the last one instead of being truncated at the
    first — the map key is another program's identifier and flow does not get
    to assume its internal structure beyond the suffix it appends.
    """
    head, sep, _ = name.rpartition("@")
    return head if sep else name
