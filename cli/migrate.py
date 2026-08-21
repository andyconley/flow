"""Project overlay migration: acting on what `flow project audit` reports.

`cli/project.py` classifies. This module decides what to do about it and does
it. The split is the codebase's existing rule — a diagnostic that repairs the
condition it reports can never report it (`cli/setup.py`, restated in
`cli/diagnostics.py`) — and it is also what let the classifier be reviewed and
released on its own, before anything deleted a file on the strength of it.

Four things here are load-bearing, and each has an obvious wrong version.

**The manifest is edited as text, never parsed and re-serialized.** There is no
TOML writer in this tree: `cli/flowtoml.py` reads, and its `parse_simple_toml`
fallback is lossy — comments gone, formatting gone, and `parse_toml_value`
raises on value types it does not know. A round-trip would quietly rewrite a
400-line annotated manifest into something else. So each declaration is located
in the original bytes by the dotted site the audit recorded, its line range is
cut, and the remainder is written back verbatim.

**Only `identical` is deletable.** `differs` cannot be told apart from a real
customization by anything on this machine, so it is reported and left. Nothing
here consults `differs` to decide an action.

**Writes are ordered so that every interruption lands somewhere safe.** See
`MIGRATION_ORDER`. The rule underneath it is: whenever one thing references
another, the reference is removed first. A manifest naming a deleted source is
the `path-nexus` bug; the reverse — a source nothing names — is merely untidy.

**The apply path re-derives everything.** It never consumes a dry run's
findings. The two are separate processes and the gap between them is a
time-of-check/time-of-use window on the one bucket that gets deleted.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from flowtoml import read_toml
from fsutil import repo_root
from paths import CAPABILITY_DIRS, FLOW_HOME, SCAFFOLD_DIR
from project import (
    BUCKET_IDENTICAL,
    audit_project,
    declared_sources,
    has_framework_baseline,
)

# The order writes happen in, and the reason the order is what it is. Each step
# names what an interruption immediately after it leaves behind.
MIGRATION_ORDER = (
    ("backup", "nothing mutated yet"),
    ("hook handlers", "handlers gone, scripts inert but present; a re-run finishes"),
    ("generated adapters", "equivalent to never having synced"),
    ("manifest", "manifest names fewer sources than exist — merely orphaned files"),
    ("framework copies", "done"),
)

_HEADER_RE = re.compile(r"^\s*(\[\[?)\s*([^\]\s][^\]]*?)\s*\]\]?\s*$")
_NAME_RE = re.compile(r'^\s*name\s*=\s*["\']([^"\']*)["\']\s*$')

# Sites whose owning entry is an array-of-tables element: the whole entry goes,
# because a command or agent with no source declares nothing. A `[standards.x]`
# table is different — it can carry `spec` and `upstream` that survive the
# source going away — so only the offending key line is cut.
_ARRAY_PREFIXES = ("claude.commands", "codex.commands", "agents")


@dataclass(frozen=True)
class ManifestEdit:
    """One contiguous line range to cut from the manifest, and why."""

    site: str
    start: int  # 0-based, inclusive
    end: int  # exclusive
    kind: str  # "entry" (a whole [[table]] block) or "key" (one line)


@dataclass
class MigrationPlan:
    """Everything the apply path will do, computed without doing any of it."""

    flow_dir: Path
    scaffold_dir: Path
    delete: list[str] = field(default_factory=list)
    manifest_edits: list[ManifestEdit] = field(default_factory=list)
    unresolved_sites: list[str] = field(default_factory=list)
    kept: dict[str, list[str]] = field(default_factory=dict)
    symlinks: list[str] = field(default_factory=list)

    def is_noop(self) -> bool:
        return not self.delete and not self.manifest_edits


# ---------------------------------------------------------------------------
# Manifest text surgery
# ---------------------------------------------------------------------------


def _blocks(lines: list[str]) -> list[tuple[str, bool, int, int]]:
    """Every table block as `(dotted_header, is_array, start, end)`.

    `start` is the header line; `end` is exclusive and stops before the next
    header. Preamble before the first header is not a block and is never cut.
    """
    found: list[tuple[str, bool, int, int]] = []
    for index, line in enumerate(lines):
        match = _HEADER_RE.match(line)
        if not match:
            continue
        if found:
            header, is_array, start, _ = found[-1]
            found[-1] = (header, is_array, start, index)
        found.append((match.group(2), match.group(1) == "[[", index, len(lines)))
    return found


def _trailing_blank(lines: list[str], end: int) -> int:
    """Extend a cut through one trailing blank line.

    Without it, removing entries from a blank-line-separated manifest leaves a
    growing run of blanks — cosmetic, but it makes the diff of a migration
    unreadable, which is the diff someone checks before trusting the next one.
    """
    if end < len(lines) and not lines[end].strip():
        return end + 1
    return end


def plan_manifest_edits(
    text: str, sites: list[str]
) -> tuple[list[ManifestEdit], list[str]]:
    """Locate each dotted declaration site in the manifest's own bytes.

    Returns the edits and the sites that could not be located. An unresolved
    site is reported, never guessed at: the alternative is cutting a line range
    chosen by a near-miss, in a file the user hand-annotated.
    """
    lines = text.splitlines()
    blocks = _blocks(lines)
    edits: list[ManifestEdit] = []
    unresolved: list[str] = []

    # Array entries are matched by their `name`, falling back to position for
    # entries that have none — the same two-step `project.declared_sources`
    # uses to build the site, inverted.
    for site in sites:
        parts = site.split(".")
        if len(parts) < 2:
            unresolved.append(site)
            continue
        key = parts[-1]
        label = parts[-2]
        prefix = ".".join(parts[:-2])
        edit = None

        if prefix in _ARRAY_PREFIXES:
            candidates = [b for b in blocks if b[0] == prefix and b[1]]
            for position, (_, _, start, end) in enumerate(candidates):
                names = [
                    _NAME_RE.match(line).group(1)
                    for line in lines[start:end]
                    if _NAME_RE.match(line)
                ]
                matched = (names and names[0] == label) or (
                    not names and label == f"[{position}]"
                )
                if matched:
                    edit = ManifestEdit(
                        site, start, _trailing_blank(lines, end), "entry"
                    )
                    break
        else:
            table = f"{prefix}.{label}" if prefix else label
            for header, is_array, start, end in blocks:
                if header != table or is_array:
                    continue
                for offset in range(start, end):
                    stripped = lines[offset].lstrip()
                    if stripped.startswith(key) and "=" in stripped:
                        if stripped.split("=", 1)[0].strip() == key:
                            edit = ManifestEdit(site, offset, offset + 1, "key")
                            break
                break

        if edit is None:
            unresolved.append(site)
        else:
            edits.append(edit)

    return sorted(edits, key=lambda e: e.start), unresolved


def apply_manifest_edits(text: str, edits: list[ManifestEdit]) -> str:
    """Cut the planned ranges and return the remainder verbatim.

    Overlapping ranges are refused rather than merged. Two sites resolving into
    one another's range means the resolution above went wrong, and silently
    cutting the union would delete a block nobody asked about.
    """
    if not edits:
        return text
    ordered = sorted(edits, key=lambda e: e.start)
    for earlier, later in zip(ordered, ordered[1:]):
        if later.start < earlier.end:
            raise ValueError(
                f"manifest edits overlap: {earlier.site} and {later.site}"
            )

    lines = text.splitlines(keepends=True)
    cut = set()
    for edit in ordered:
        cut.update(range(edit.start, edit.end))
    return "".join(line for index, line in enumerate(lines) if index not in cut)


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


def plan_migration(flow_dir: Path, scaffold_dir: Path) -> MigrationPlan:
    """What migration would do, derived fresh from a new audit every time."""
    report = audit_project(flow_dir, scaffold_dir)

    delete = sorted(f.rel for f in report.findings if f.bucket == BUCKET_IDENTICAL)
    delete_set = set(delete)

    manifest_path = flow_dir / "flow.toml"
    manifest = read_toml(manifest_path) if manifest_path.is_file() else {}
    declarations, _rejected = declared_sources(manifest)

    # Two reasons a declaration must go, and they need the manifest rather than
    # the findings to tell apart. An `orphaned` finding already carries its
    # sites, but a file about to be *deleted* is currently present, so its
    # finding is `identical` and carries none — the declaration that will be
    # orphaned a moment from now is only visible in the manifest.
    sites = [
        d.declared_by
        for d in declarations
        if d.rel in delete_set or not (flow_dir / d.rel).exists()
    ]

    kept = {}
    for bucket in ("differs", "project-only", "conflict", "unreadable"):
        members = sorted(f.rel for f in report.findings if f.bucket == bucket)
        if members:
            kept[bucket] = members

    edits: list[ManifestEdit] = []
    unresolved: list[str] = []
    if sites and manifest_path.is_file():
        edits, unresolved = plan_manifest_edits(
            manifest_path.read_text(), sorted(set(sites))
        )
    elif sites:
        unresolved = sorted(set(sites))

    return MigrationPlan(
        flow_dir=flow_dir,
        scaffold_dir=scaffold_dir,
        delete=delete,
        manifest_edits=edits,
        unresolved_sites=unresolved,
        kept=kept,
        symlinks=list(report.symlinks),
    )


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def render_plan(plan: MigrationPlan, *, applied: bool = False) -> str:
    """The dry run's output is the entire informed-consent surface.

    The command is non-interactive by design, so there is no second checkpoint
    between reading this and the deletion happening. Everything a person needs
    in order to decide has to be here: the exact files that go, the exact
    manifest sites that go, and — just as important — an explicit list of what
    is being left alone, so "my customization isn't mentioned" is a conclusion
    someone can actually reach rather than assume.
    """
    verb = "removed" if applied else "would remove"
    lines = [
        f"project:   {plan.flow_dir}",
        f"framework: {plan.scaffold_dir}",
        "",
    ]

    if plan.is_noop():
        lines.append("nothing to migrate: no framework copies, no stale declarations")
        if plan.kept or plan.symlinks:
            lines.append("")
        _append_kept(lines, plan)
        return "\n".join(lines)

    lines.append(f"{verb} {len(plan.delete)} framework copy(ies) from .flow/")
    for rel in plan.delete:
        lines.append(f"  {rel}")

    lines.append("")
    lines.append(
        f"{verb} {len(plan.manifest_edits)} declaration(s) from .flow/flow.toml"
    )
    for edit in plan.manifest_edits:
        span = (
            f"line {edit.start + 1}"
            if edit.end - edit.start == 1
            else f"lines {edit.start + 1}-{edit.end}"
        )
        lines.append(f"  {edit.site}   [{edit.kind}, {span}]")

    if plan.unresolved_sites:
        lines.append("")
        lines.append(
            f"could not locate {len(plan.unresolved_sites)} declaration(s) in the "
            f"manifest text — left in place rather than guessed at"
        )
        for site in plan.unresolved_sites:
            lines.append(f"  {site}")

    _append_kept(lines, plan)

    lines.append("")
    if applied:
        lines.append("done.")
    else:
        lines.append("dry run — nothing was changed.")
    return "\n".join(lines)


def _append_kept(lines: list[str], plan: MigrationPlan) -> None:
    if not plan.kept and not plan.symlinks:
        return
    lines.append("")
    lines.append("left alone, and never removed by this command:")
    for bucket, members in plan.kept.items():
        lines.append(f"  {bucket} ({len(members)})")
        for rel in members:
            lines.append(f"    {rel}")
    if plan.symlinks:
        lines.append(f"  symlinks ({len(plan.symlinks)}) — never followed")
        for rel in plan.symlinks:
            lines.append(f"    {rel}")


def plan_payload(plan: MigrationPlan) -> dict:
    return {
        "flow_dir": str(plan.flow_dir),
        "scaffold_dir": str(plan.scaffold_dir),
        "delete": list(plan.delete),
        "manifest_edits": [
            {"site": e.site, "kind": e.kind, "start": e.start, "end": e.end}
            for e in plan.manifest_edits
        ],
        "unresolved_sites": list(plan.unresolved_sites),
        "kept": {k: list(v) for k, v in plan.kept.items()},
        "symlinks": list(plan.symlinks),
        "noop": plan.is_noop(),
    }


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


def resolve_roots(args) -> tuple[Path, Path] | None:
    """Shared root resolution, including the guard against flow's own home.

    Returns None having printed the reason. Lifted out because `audit` and
    `migrate` must agree on what "this project" means — a migration that
    resolved a different root than the audit the user just read would act on a
    tree they never saw.
    """
    scaffold_dir = (
        Path(args.scaffold).expanduser()
        if getattr(args, "scaffold", None)
        else SCAFFOLD_DIR
    )
    if getattr(args, "root", None):
        flow_dir = Path(args.root).expanduser()
        if not flow_dir.is_dir():
            print(f"--root is not a directory: {flow_dir}")
            return None
    else:
        flow_dir = repo_root() / ".flow"

    if flow_dir.resolve().is_relative_to(FLOW_HOME.resolve()):
        print("that is inside flow's own home, not a project overlay")
        print("run this inside a repo, or pass --root <path-to-a-project>/.flow")
        return None
    if not flow_dir.exists():
        print("repo is missing .flow; run `flow setup project` first")
        return None
    return flow_dir, scaffold_dir


def cmd_migrate(args) -> int:
    roots = resolve_roots(args)
    if roots is None:
        return 1
    flow_dir, scaffold_dir = roots

    if not has_framework_baseline(scaffold_dir):
        print("no framework baseline: the scaffold holds none of the")
        print(f"capability directories ({', '.join(CAPABILITY_DIRS)}).")
        print("")
        print("Every file would look project-only, so nothing can be classified")
        print("as safe to remove. Refusing. Check the framework install first.")
        return 1

    plan = plan_migration(flow_dir, scaffold_dir)

    if getattr(args, "json", False):
        print(json.dumps(plan_payload(plan), indent=2, sort_keys=True))
    else:
        print(render_plan(plan))
    return 0
