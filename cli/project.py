"""Project overlay audit: what a project carries that the framework owns.

`flow setup project` copies the whole scaffold into a repo's `.flow/`, so every
project starts life holding its own copy of every command, agent, standard, and
template. Those copies never update. A project set up months ago is running
framework files nobody has touched since, and nothing on the machine says so —
the copies are byte-identical to files the user never edited, so they read as
deliberate customization and are treated as untouchable.

This module answers the question that has to come first: **which of those files
are actually the project's, and which are stale duplicates of the framework's?**
It only reports. Deletion is a separate verb, and it consumes what this
produces.

Three properties are load-bearing, and each has a plausible-looking alternative
that is wrong:

**Only `paths.CAPABILITY_PATHS` is walked.** `PROJECT.md`, `flow.toml`,
`memory/`, and `runs/` are the project's own state and are never visited. That
is the safety property rather than a scoping convenience: a path this module
never classifies cannot be proposed for deletion by anything downstream, because
downstream reads this module's findings and nothing else. The obvious
alternative — walk `.flow/` and exclude a denylist — inverts the failure mode, so
a directory added later is included by default.

**Findings are keyed on POSIX-relative strings, never absolute paths.** The two
roots are carried once on the report and joined by the caller. An absolute path
inside a finding is the mechanism by which a later `--apply` deletes outside the
root it was pointed at. Manifest declarations that escape the overlay — absolute,
or containing `..` — are therefore returned as a *different record type* that
deliberately has no joinable field at all: `RejectedDeclaration` carries the raw
string for a human to read and nothing a caller can put after a `/`.

**Nothing here imports `setup` or `sync`.** `setup.py` imports `sync_target`, so
one convenience import would drag the whole adapter-generation graph into a
read-only command — and `setup` imports *this* module, which would be a cycle.
The traversal guard below is duplicated from `setup._safe_scaffold_rel_paths`
rather than shared for exactly that reason; the two are small and the direction
of the dependency matters more than the four lines.
"""

from dataclasses import dataclass
from pathlib import Path

# paths/fsutil/flowtoml only. See the module docstring: the absence of `setup`
# and `sync` here is a contract, not an accident, and `tests/test_flow.py`
# asserts it.


@dataclass(frozen=True)
class Declaration:
    """A manifest entry naming a source inside the project overlay.

    `rel` is a POSIX-relative string and is safe to join against a root.
    `declared_by` is the dotted site in `flow.toml` that named it, which is what
    a later manifest rewrite needs in order to know which entry to drop.
    """

    rel: str
    declared_by: str


@dataclass(frozen=True)
class RejectedDeclaration:
    """A manifest entry whose source escapes the overlay.

    Deliberately carries no `rel`. An absolute path or one containing `..` has
    no legitimate relative key, and giving it one would hand a downstream
    `--apply` the join that lets it act outside the root. The raw string is here
    to be printed and read, not resolved.
    """

    declared_value: str
    declared_by: str
    reason: str


def _site(prefix: str, entry: dict, index: int, key: str) -> str:
    """Dotted name for a manifest entry, by `name` when it has one.

    Falls back to the array index. A rewrite keyed on position breaks the moment
    someone reorders the file, so the name is preferred wherever it exists.
    """
    name = entry.get("name")
    label = name if isinstance(name, str) and name else f"[{index}]"
    return f"{prefix}.{label}.{key}"


def _classify_declaration(
    raw: str, declared_by: str
) -> Declaration | RejectedDeclaration:
    rel = Path(raw)
    if rel.is_absolute():
        return RejectedDeclaration(raw, declared_by, "absolute path")
    if ".." in rel.parts:
        return RejectedDeclaration(raw, declared_by, "escapes the overlay via ..")
    return Declaration(rel.as_posix(), declared_by)


def declared_sources(
    manifest: dict,
) -> tuple[list[Declaration], list[RejectedDeclaration]]:
    """Every project-relative source the manifest names, plus what was rejected.

    Covers all four declaration sites that carry one: `[[claude.commands]]` and
    `[[codex.commands]]` `source`, `[[agents]]` `source`, and `[standards.*]`
    `flow_standard` / `vendored_path`.

    Hooks are the deliberate omission. `[[hooks]]` entries carry `script`, which
    `sync.hook_script_source` resolves against the framework source or the user
    overlay with no project branch at all — so a hook can never be an orphaned
    project source, and adding it here would invent a finding class that cannot
    occur.

    Ordered, not a set. The previous `set[Path]` form was fine for its one
    caller, but unordered iteration makes a rendered report non-deterministic
    and its golden test flaky.
    """
    found: list[Declaration] = []
    rejected: list[RejectedDeclaration] = []
    seen: set[str] = set()

    def take(raw, declared_by: str) -> None:
        if not isinstance(raw, str) or not raw:
            return
        record = _classify_declaration(raw, declared_by)
        if isinstance(record, RejectedDeclaration):
            rejected.append(record)
            return
        if record.rel in seen:
            return
        seen.add(record.rel)
        found.append(record)

    for runtime_name in ("claude", "codex"):
        runtime = manifest.get(runtime_name, {})
        if not isinstance(runtime, dict):
            continue
        for index, entry in enumerate(runtime.get("commands", [])):
            if isinstance(entry, dict):
                take(
                    entry.get("source"),
                    _site(f"{runtime_name}.commands", entry, index, "source"),
                )

    for index, entry in enumerate(manifest.get("agents", [])):
        if isinstance(entry, dict):
            take(entry.get("source"), _site("agents", entry, index, "source"))

    for name, standard in manifest.get("standards", {}).items():
        if not isinstance(standard, dict):
            continue
        for key in ("flow_standard", "vendored_path"):
            take(standard.get(key), f"standards.{name}.{key}")

    return found, rejected
