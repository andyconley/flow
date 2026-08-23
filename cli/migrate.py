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

import copy
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from flowtoml import loads as toml_loads, read_toml
from fsutil import (
    ensure_dir,
    read_json,
    rel_posix,
    remove_empty_parents,
    repo_root,
    write_atomic,
)
from paths import CAPABILITY_DIRS, FLOW_HOME, FLOW_HOME as _FLOW_HOME, SCAFFOLD_DIR
from project import (
    BUCKET_DIFFERS,
    BUCKET_IDENTICAL,
    audit_project,
    declared_sources,
    has_framework_baseline,
    overlapping_trees,
)
from sync import (
    read_managed_merge_paths,
    read_managed_paths,
    remove_managed_codex_hooks,
    remove_managed_flow_hooks,
    sync_outputs,
)

BACKUPS_DIR = _FLOW_HOME / "backups"

# The order writes happen in, and the reason the order is what it is. Each step
# names what an interruption immediately after it leaves behind.
MIGRATION_ORDER = (
    ("backup", "nothing mutated yet"),
    ("hook handlers", "handlers gone, scripts inert but present; a re-run finishes"),
    ("generated adapters", "equivalent to never having synced"),
    ("manifest", "manifest names fewer sources than exist — merely orphaned files"),
    ("framework copies", "done"),
)

# Restricted to dotted bare keys so a line inside a multi-line array —
# `["a", "b"]` — cannot be mistaken for a table header, which would
# truncate the preceding block and cut the wrong range.
_HEADER_RE = re.compile(r"^\s*(\[\[?)\s*([A-Za-z0-9_.\-]+)\s*\]\]?\s*$")
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
    # Steps 2 and 3. Carried on the plan rather than derived inside the apply
    # path, because a consent surface that omits two of the five things about
    # to happen is not a consent surface — and because a project whose overlay
    # files all landed in `differs` still has a full generated adapter tree to
    # remove, which an is_noop that only looked at `delete` called "nothing".
    adapters: list[str] = field(default_factory=list)
    settings_files: list[str] = field(default_factory=list)
    # Always populated from the `differs` bucket, whether or not they are
    # being removed, so the dry run can name them and point at the flag
    # without computing the same list twice.
    drifted: list[str] = field(default_factory=list)
    remove_drifted: bool = False
    # Drifted files whose declaring site could not be located in the manifest.
    # Refused rather than removed: an unresolved site leaves the manifest
    # pointing at a file that is gone, and unlike a framework copy a drifted
    # file cannot be re-fetched from the scaffold. The backup would be the
    # only copy left.
    drifted_blocked: list[str] = field(default_factory=list)

    def drifted_removals(self) -> list[str]:
        if not self.remove_drifted:
            return []
        blocked = set(self.drifted_blocked)
        return [rel for rel in self.drifted if rel not in blocked]

    def is_noop(self) -> bool:
        return not (
            self.delete
            or self.manifest_edits
            or self.adapters
            or self.settings_files
            or self.drifted_removals()
        )


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


def _cut_end(lines: list[str], start: int, end: int) -> int:
    """Where a block's cut actually stops.

    A block runs to the next header, but the blank lines and comments sitting
    immediately before that header introduce the *next* section, not this one.
    Cutting through them destroys section headings — the real manifest has a
    `# CLI command summaries for the flow-help...` block before
    `[[help.cli_commands]]`, and removing the last `[[codex.commands]]` entry
    took it with it. Comments *inside* the block still go: they annotate the
    entry being removed.

    One trailing blank is then reclaimed so repeated removals do not leave a
    growing run of blank lines, which would make the diff of a migration
    unreadable — and that diff is what someone reads before trusting the next
    one.
    """
    body_end = end
    while body_end > start + 1:
        stripped = lines[body_end - 1].strip()
        if stripped and not stripped.startswith("#"):
            break
        body_end -= 1
    if body_end < len(lines) and not lines[body_end].strip():
        return body_end + 1
    return body_end


def _name_counts(lines: list[str], prefix: str) -> dict[str, int]:
    """How many array entries under `prefix` carry each `name`."""
    counts: dict[str, int] = {}
    for header, is_array, start, end in _blocks(lines):
        if header != prefix or not is_array:
            continue
        for line in lines[start:end]:
            match = _NAME_RE.match(line)
            if match:
                counts[match.group(1)] = counts.get(match.group(1), 0) + 1
                break
    return counts


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

    # Two entries sharing a `name` produce one dotted site between them, so a
    # single cut would leave the other declaring a file that is gone. There is
    # no way to tell from the site which was meant, so both are refused here
    # rather than discovered by the validating re-parse after two destructive
    # steps have already run.
    ambiguous = {
        label
        for prefix in _ARRAY_PREFIXES
        for label, count in _name_counts(lines, prefix).items()
        if count > 1
    }

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

        if prefix in _ARRAY_PREFIXES and label in ambiguous:
            unresolved.append(site)
            continue

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
                        site, start, _cut_end(lines, start, end), "entry"
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


def unremoved_sites(text: str, edits: list[ManifestEdit]) -> list[str]:
    """Which of the intended sites still parse out of the rewritten manifest.

    Runs at plan time as well as apply time. Validating only at apply time put
    the failure after two destructive steps had already run, and made it
    deterministic — every re-run crashed at the same place, leaving the repo
    permanently adapter-less with an unedited manifest. Surfacing it in the dry
    run costs one extra parse and turns a wedge into a message.

    A parse failure is itself a finding: if the edited text will not parse, the
    edit is wrong, and reporting every site as unremoved is the honest answer.
    """
    try:
        remaining = {d.declared_by for d in declared_sources(toml_loads(text))[0]}
    except Exception:
        return sorted({e.site for e in edits})
    return sorted({e.site for e in edits}.intersection(remaining))


def plan_migration(
    flow_dir: Path, scaffold_dir: Path, remove_drifted: bool = False
) -> MigrationPlan:
    """What migration would do, derived fresh from a new audit every time."""
    report = audit_project(flow_dir, scaffold_dir)

    delete = sorted(f.rel for f in report.findings if f.bucket == BUCKET_IDENTICAL)
    drifted = sorted(f.rel for f in report.findings if f.bucket == BUCKET_DIFFERS)
    # Kept separate from `delete` on purpose. `render_plan` labels that list
    # "framework copy(ies)", which a drifted file is not, and the two carry
    # different risk: removing an identical file is provably lossless,
    # removing a drifted one may destroy the only copy.
    delete_set = set(delete) | (set(drifted) if remove_drifted else set())

    manifest_path = flow_dir / "flow.toml"
    manifest = read_toml(manifest_path) if manifest_path.is_file() else {}
    declarations, _rejected = declared_sources(manifest)
    root = flow_dir.parent
    runtimes = runtime_managed_paths(root, manifest)
    adapters = sorted(
        rel_posix(p, root)
        for info in runtimes.values()
        for p in info["managed"]
        if p.is_file() and p not in info["merge_protected"]
    )
    settings_files = sorted(
        rel_posix(p, root)
        for info in runtimes.values()
        for p in info["merge_protected"]
        if p.is_file()
    )

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

    def _plan_edits(site_list: list[str]) -> tuple[list[ManifestEdit], list[str]]:
        if site_list and manifest_path.is_file():
            return plan_manifest_edits(
                manifest_path.read_text(), sorted(set(site_list))
            )
        return [], sorted(set(site_list))

    edits, unresolved = _plan_edits(sites)

    # An unresolved site is tolerable for a framework copy: the file is
    # byte-identical to the scaffold's and can be fetched back. For a drifted
    # file it means the manifest would point at a customization that is gone
    # and reconstructible from nothing but the backup. Refuse those
    # individually rather than aborting the run, so the removable ones still
    # go.
    drifted_blocked: list[str] = []
    if remove_drifted and unresolved:
        unresolved_set = set(unresolved)
        by_rel: dict[str, set[str]] = {}
        for d in declarations:
            by_rel.setdefault(d.rel, set()).add(d.declared_by)
        drifted_blocked = sorted(
            rel
            for rel in drifted
            if by_rel.get(rel, set()) & unresolved_set
        )

        # Second pass, and the reason there are two. A file with more than one
        # declaring site can have one resolve and another not: it is blocked
        # from deletion by the loop above, but its *resolvable* site is still
        # in `sites` and step 4 would cut it. That leaves a file on disk the
        # manifest no longer declares — the same inconsistency this guard
        # exists to prevent, arrived at from the other side. Blocking has to
        # be known before the edits are planned, and it cannot be known until
        # after, so the edits are planned twice.
        if drifted_blocked:
            blocked_sites = {
                site for rel in drifted_blocked for site in by_rel.get(rel, set())
            }
            sites = [s for s in sites if s not in blocked_sites]
            edits, unresolved = _plan_edits(sites)

    return MigrationPlan(
        flow_dir=flow_dir,
        scaffold_dir=scaffold_dir,
        delete=delete,
        manifest_edits=edits,
        unresolved_sites=unresolved,
        kept=kept,
        drifted=drifted,
        remove_drifted=remove_drifted,
        drifted_blocked=drifted_blocked,
        symlinks=list(report.symlinks),
        adapters=adapters,
        settings_files=settings_files,
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
        # The headline has to survive its own body. A drifted-only overlay
        # used to print "nothing to migrate" directly above a list of the
        # files it was declining to migrate, and a reader who stopped at the
        # first line got the wrong answer.
        if plan.drifted:
            lines.append(
                "nothing removable: no framework copies, no stale declarations, "
                "no generated adapters"
            )
        else:
            lines.append(
                "nothing to migrate: no framework copies, no stale declarations, "
                "no generated adapters"
            )
        _append_unresolved(lines, plan)
        _append_drifted(lines, plan, applied)
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

    if plan.adapters:
        lines.append("")
        lines.append(
            f"{verb} {len(plan.adapters)} generated adapter file(s) — project-level "
            f"sync no longer regenerates these"
        )
        for rel in plan.adapters:
            lines.append(f"  {rel}")

    if plan.settings_files:
        lines.append("")
        lines.append(
            f"{'stripped' if applied else 'would strip'} flow's hook handlers from "
            f"{len(plan.settings_files)} settings file(s), preserving everything else"
        )
        for rel in plan.settings_files:
            lines.append(f"  {rel}")

    _append_unresolved(lines, plan)
    _append_drifted(lines, plan, applied)
    _append_kept(lines, plan)

    lines.append("")
    if applied:
        lines.append("done.")
    else:
        # The backup destination belongs in the consent surface, not only in
        # the report afterwards. Once a drifted file can be removed and
        # nothing restores anything from the scaffold, this is the only route
        # back, and it has to be visible before the decision rather than
        # after it.
        if plan.delete or plan.drifted_removals():
            lines.append(f"a backup is taken first, under {BACKUPS_DIR}/")
            lines.append("")
        lines.append("dry run — nothing was changed.")
    return "\n".join(lines)


def _append_unresolved(lines: list[str], plan: MigrationPlan) -> None:
    if not plan.unresolved_sites:
        return
    lines.append("")
    lines.append(
        f"could not locate {len(plan.unresolved_sites)} declaration(s) in the "
        f"manifest text — left in place rather than guessed at"
    )
    for site in plan.unresolved_sites:
        lines.append(f"  {site}")


def _append_drifted(lines: list[str], plan: MigrationPlan, applied: bool) -> None:
    """The drifted block, in whichever of its two shapes applies.

    Kept out of `_append_kept` and out of the "framework copy(ies)" list: a
    file must never appear in both the removal paragraph and the paragraph
    headed "never removed by this command", or the output stops functioning
    as a consent surface.
    """
    if not plan.drifted:
        return
    removals = plan.drifted_removals()
    lines.append("")
    if not plan.remove_drifted:
        lines.append(
            f"{len(plan.drifted)} file(s) differ from the framework and are left alone"
        )
        for rel in plan.drifted:
            lines.append(f"  {rel}")
        lines.append("")
        lines.append("  customized or stale — nothing local can tell which, so none")
        lines.append("  of these is provably safe to remove. To remove them anyway,")
        lines.append("  re-run with --drifted after reading the list.")
        return

    verb = "removed" if applied else "would remove"
    lines.append(f"{verb} {len(removals)} drifted file(s) from .flow/")
    for rel in removals:
        lines.append(f"  {rel}")
    lines.append("")
    lines.append("  these DIFFER from the framework. Any one of them may be a")
    lines.append("  customization, and the backup is the only copy afterwards.")
    if plan.drifted_blocked:
        lines.append("")
        lines.append(
            f"  refused ({len(plan.drifted_blocked)}) — declaring site not found in "
            f"flow.toml,"
        )
        lines.append("  so removing the file would leave the manifest pointing at it")
        for rel in plan.drifted_blocked:
            lines.append(f"    {rel}")


def _append_kept(lines: list[str], plan: MigrationPlan) -> None:
    # Drifted files always get their own block, in one of its two shapes, so
    # they never belong here as well. Listing the same path under two headings
    # is what stops the output working as a consent surface.
    kept = {
        bucket: members
        for bucket, members in plan.kept.items()
        if bucket != "differs"
    }
    if not kept and not plan.symlinks:
        return
    lines.append("")
    lines.append("left alone, and never removed by this command:")
    for bucket, members in kept.items():
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
        # Additive. `kept["differs"]` stays populated in both modes, so a
        # consumer reading it keeps getting the right answer rather than an
        # empty list that reads as "no drifted files".
        "drifted": list(plan.drifted),
        "remove_drifted": plan.remove_drifted,
        "drifted_blocked": list(plan.drifted_blocked),
        "manifest_edits": [
            {"site": e.site, "kind": e.kind, "start": e.start, "end": e.end}
            for e in plan.manifest_edits
        ],
        "unresolved_sites": list(plan.unresolved_sites),
        "adapters": list(plan.adapters),
        "settings_files": list(plan.settings_files),
        "kept": {k: list(v) for k, v in plan.kept.items()},
        "symlinks": list(plan.symlinks),
        "noop": plan.is_noop(),
    }


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


def resolve_roots(args) -> tuple[Path, Path] | None:
    """Migrate's root resolution, including the guard against flow's own home.

    Returns None having printed the reason.

    This is migrate's only, despite the name. `cmd_audit` resolves its own
    roots (`project.py`) and never calls this, and the two now differ
    deliberately: the `--scaffold` overlap refusal below belongs here and not
    there, because audit deletes nothing and comparing a tree against itself is
    a reasonable thing to ask it for. That divergence is the reason a
    migration can refuse a comparison the audit will still perform, so the
    audit's report is not always the plan migrate would act on.
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
    # Last, so the flow-home guard above keeps its more specific message.
    # Pointed at a home directory or a repo root, the walk and the backup
    # would both be nonsense; cheap to require it looks like what it claims.
    if flow_dir.name != ".flow" and not (flow_dir / "flow.toml").is_file():
        print(f"--root does not look like a .flow overlay: {flow_dir}")
        print("expected a directory named .flow, or one containing flow.toml")
        return None
    # Compared against the project's own tree, every file is byte-equal to
    # itself. That reclassifies the whole `differs` bucket — the files this
    # command exists to protect — as `identical`, which is the bucket `--apply`
    # deletes, and it sweeps up `project-only` files the contract says are
    # never removed. Refused at planning time so the dry run and `--json`
    # cannot describe a plan the command would decline to run.
    #
    # Deliberately not `AuditReport.default_scaffold`, which asks "is this the
    # installed framework" and is false for every override — including the
    # legitimate ones the flag exists for.
    if overlapping_trees(scaffold_dir.resolve(), flow_dir.resolve()):
        print("--scaffold names this project's own overlay, or part of it")
        print(f"  scaffold: {scaffold_dir}")
        print(f"  project:  {flow_dir}")
        print("")
        print("Every file would be byte-equal to itself, so the whole overlay")
        print("would classify as removable. Refusing. Pass a framework scaffold,")
        print("or omit --scaffold to compare against the installed one.")
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

    remove_drifted = getattr(args, "drifted", False)
    plan = plan_migration(flow_dir, scaffold_dir, remove_drifted=remove_drifted)
    apply = getattr(args, "apply", False)

    if apply and not getattr(args, "yes", False):
        print("`--apply` deletes files. Re-run with `--apply --yes` to confirm.")
        print("Run without `--apply` first to see exactly what would go.")
        return 1

    if not apply:
        if getattr(args, "json", False):
            print(json.dumps(plan_payload(plan), indent=2, sort_keys=True))
        else:
            print(render_plan(plan))
        return 0

    if plan.is_noop():
        print(render_plan(plan))
        return 0

    root = flow_dir.parent
    stamp = (args.at or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")).strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", stamp):
        # It becomes a directory name under ~/.flow/backups; `../../x` would
        # put the backup somewhere the restore instructions do not describe.
        print(f"--at must be 1-64 characters of [A-Za-z0-9_.-]: {stamp!r}")
        return 1
    try:
        outcome = apply_migration(
            root, flow_dir, scaffold_dir, plan, BACKUPS_DIR, stamp
        )
    except MigrationAborted as err:
        print(f"migration aborted: {err}")
        return 1

    if getattr(args, "json", False):
        print(json.dumps({**plan_payload(plan), "applied": outcome}, indent=2, sort_keys=True))
        return 0

    print(render_plan(plan, applied=True))
    print("")
    print(f"backup: {outcome['backup']} ({outcome['backed_up']} file(s))")
    for rel in outcome["handlers_stripped"]:
        print(f"stripped flow handlers from {rel}")
    if outcome["adapters_removed"]:
        print(f"removed {len(outcome['adapters_removed'])} generated adapter file(s)")
    return 0


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


class MigrationAborted(Exception):
    """Raised before anything irreversible, never during.

    Every raise site is upstream of the first deletion. A migration that stops
    halfway is recoverable from the backup; a migration that stops halfway
    *without* one is the failure this whole module is arranged to avoid.
    """


def runtime_managed_paths(root: Path, manifest: dict) -> dict[str, dict]:
    """Per runtime: the managed paths, the merge-protected subset, and the
    settings file flow writes into.

    Read from each runtime's own managed manifest, which is the record of what
    project-level sync generated. That record is also what disappears when
    project sync is retired, which is why migration has to run before anyone
    can rely on it not existing.
    """
    found: dict[str, dict] = {}
    for target in ("claude", "codex"):
        runtime = manifest.get(target)
        if not isinstance(runtime, dict) or "managed_manifest" not in runtime:
            continue
        managed_manifest = root / runtime["managed_manifest"]
        found[target] = {
            "managed_manifest": managed_manifest,
            "managed": read_managed_paths(root, managed_manifest),
            "merge_protected": read_managed_merge_paths(root, managed_manifest),
        }
    return found


def backup_set(
    root: Path, flow_dir: Path, plan: MigrationPlan, runtimes: dict[str, dict]
) -> list[Path]:
    """Everything about to be deleted or mutated, and nothing else.

    Deliberately includes the settings files whole. Project-level sync is
    retired in the same change that adds this, so there is no `flow sync` left
    to regenerate an adapter with — the backup is the only route back, and a
    partial one is worse than none because it looks like a route.
    """
    paths = {flow_dir / rel for rel in plan.delete}
    # The one class that cannot be reconstructed from the scaffold must not be
    # the one class left unbacked.
    paths.update(flow_dir / rel for rel in plan.drifted_removals())
    if plan.manifest_edits:
        paths.add(flow_dir / "flow.toml")
    for info in runtimes.values():
        paths.update(info["managed"])
        paths.update(info["merge_protected"])
    return sorted(p for p in paths if p.is_file())


def perform_backup(root: Path, destination: Path, paths: list[Path]) -> int:
    """Copy each path into `destination`, mirroring its path relative to root.

    Returns the count, which the caller checks against what it asked for. A
    migration that cannot prove it backed up does not delete: the check is the
    difference between "the backup step ran" and "the backup exists".
    """
    # Files are mirrored under `files/` rather than at the top of the backup
    # so the listing can never collide with something being backed up. A repo
    # with its own top-level MANIFEST.txt would otherwise have it saved and
    # then immediately overwritten by the listing — destroyed, not saved, and
    # invisible to any count.
    tree = destination / "files"
    ensure_dir(tree)
    listed = []
    for path in paths:
        rel = path.relative_to(root)
        target = tree / rel
        ensure_dir(target.parent)
        shutil.copy2(path, target)
        listed.append(rel.as_posix())
    (destination / "MANIFEST.txt").write_text(
        "\n".join(
            [
                f"# flow project migrate backup of {root}",
                "# restore a file by copying it from files/<path> back to <path>",
                "",
                *listed,
                "",
            ]
        )
    )
    # Counted off the filesystem, not off the loop. Incrementing a counter per
    # iteration only restates that the loop ran; it cannot notice two source
    # paths mirroring onto one destination.
    return sum(1 for p in tree.rglob("*") if p.is_file())


def strip_managed_handlers(path: Path, remover) -> bool:
    """Remove flow's hook handlers from a settings/hooks file, in place.

    R4's guarantee is enforced here, at write time, rather than trusted to a
    restore: the stripped document is compared to the original with `hooks`
    removed from both, and anything else differing aborts. A remover that
    dropped an unmanaged top-level key, or reordered a nested structure, would
    otherwise be indistinguishable from one that behaved.
    """
    if not path.is_file():
        return False
    original = read_json(path)
    # Deep-copied because `remove_managed_flow_hooks` mutates its argument and
    # returns the same object. Without this, `original` and `stripped` are one
    # dict, every comparison below is a dict against itself, and the function
    # concludes nothing changed and writes nothing — silently leaving flow's
    # handlers pointing at scripts the next step deletes.
    original = copy.deepcopy(original)
    stripped = remover(copy.deepcopy(original))

    without_hooks = {k: v for k, v in original.items() if k != "hooks"}
    stripped_without_hooks = {k: v for k, v in stripped.items() if k != "hooks"}
    if without_hooks != stripped_without_hooks:
        raise MigrationAborted(
            f"refusing to write {path}: stripping flow's handlers would have "
            f"changed unmanaged content"
        )
    if stripped == original:
        return False
    write_atomic(path, json.dumps(stripped, indent=2, sort_keys=True) + "\n")
    return True


def apply_migration(
    root: Path,
    flow_dir: Path,
    scaffold_dir: Path,
    plan: MigrationPlan,
    backups_root: Path,
    stamp: str,
) -> dict:
    """The five ordered writes. See MIGRATION_ORDER for what each interruption
    leaves behind.

    Whenever one thing references another, the reference goes first: handlers
    before the scripts they invoke, adapters before the `.flow` sources they
    were generated from, and the manifest before the files it declares. The
    reverse of any of those pairs is a live breakage; this direction leaves
    only files nothing points at.
    """
    manifest_path = flow_dir / "flow.toml"
    manifest = read_toml(manifest_path) if manifest_path.is_file() else {}
    runtimes = runtime_managed_paths(root, manifest)

    # 1 — backup, and verify it before anything else happens.
    destination = backups_root / f"migrate-{root.name}-{stamp}"
    if destination.exists():
        raise MigrationAborted(f"backup destination already exists: {destination}")
    wanted = backup_set(root, flow_dir, plan, runtimes)
    written = perform_backup(root, destination, wanted)
    if written != len(wanted):
        raise MigrationAborted(
            f"backup incomplete: {written} of {len(wanted)} files copied"
        )

    result = {
        "backup": str(destination),
        "backed_up": written,
        "handlers_stripped": [],
        "adapters_removed": [],
        "manifest_edits": 0,
        "deleted": [],
    }

    # 2 — hook handlers, before the scripts they invoke are removed.
    for target, remover in (
        ("claude", remove_managed_flow_hooks),
        ("codex", remove_managed_codex_hooks),
    ):
        if target not in runtimes:
            continue
        for path in sorted(runtimes[target]["merge_protected"]):
            if strip_managed_handlers(path, remover):
                result["handlers_stripped"].append(rel_posix(path, root))

    # 3 — generated adapters, before the `.flow` sources they came from.
    for target, info in runtimes.items():
        before = {p for p in info["managed"] if p.exists()}
        sync_outputs(
            root,
            target,
            {},
            info["managed"],
            set(),
            check=False,
            merge_protected=info["merge_protected"],
        )
        gone = sorted(rel_posix(p, root) for p in before if not p.exists())
        result["adapters_removed"].extend(gone)

    # 4 — the manifest, before the sources it declares.
    if plan.manifest_edits:
        edited = apply_manifest_edits(manifest_path.read_text(), plan.manifest_edits)
        # The one place a validating round-trip belongs. `plan_migration` has
        # already run exactly this check, so reaching a failure here means the
        # tree changed under us between the two — worth aborting rather than
        # assuming, but no longer the first time anyone looked.
        still_there = unremoved_sites(edited, plan.manifest_edits)
        if still_there:
            raise MigrationAborted(
                f"manifest rewrite did not remove: {', '.join(still_there)}"
            )
        write_atomic(manifest_path, edited)
        result["manifest_edits"] = len(plan.manifest_edits)

    # 5 — the framework copies themselves, and any drifted files the run
    # explicitly opted into removing.
    for rel in list(plan.delete) + plan.drifted_removals():
        path = flow_dir / rel
        if path.is_file():
            path.unlink()
            remove_empty_parents(path, flow_dir)
            result["deleted"].append(rel)

    return result
