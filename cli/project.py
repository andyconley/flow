"""Project overlay audit: what a project carries that the framework owns.

`flow setup project` used to copy the whole scaffold into a repo's `.flow/`, so
a project set up before that changed holds its own copy of every command,
agent, standard, and template. Those copies never update. Such a project is
running framework files nobody has touched since, and nothing on the machine
says so — the copies are byte-identical to files the user never edited, so they
read as deliberate customization and are treated as untouchable.

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

import json
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

# paths/fsutil/flowtoml only. See the module docstring: the absence of `setup`
# and `sync` here is a contract, not an accident, and `tests/test_flow.py`
# asserts it.
from flowtoml import read_toml
from fsutil import repo_root
from paths import (
    CAPABILITY_DIRS,
    CAPABILITY_PATHS,
    FLOW_HOME,
    RELEASE_EXCLUDE_DIRS,
    RELEASE_EXCLUDE_FILE_PATTERNS,
    SCAFFOLD_DIR,
)


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


def reject_relative(raw: str) -> str | None:
    """`None` if `raw` is safe to join against a root; else why it is not.

    Root-agnostic on purpose. The same three hazards apply whichever root a
    caller is about to join against — the project overlay for a declared
    source, the user overlay for a `[[replaces]]` target — and a second copy
    of this reasoning is a second place for it to drift.
    """
    rel = Path(raw)
    if rel.is_absolute():
        return "absolute path"
    if ".." in rel.parts:
        return "escapes the overlay via .."
    if rel.parts and rel.parts[0].startswith("~"):
        # pathlib does not expand `~`, so this is not absolute and carries no
        # `..` — it passes both guards above and lands as an ordinary relative
        # key. Harmless until one consumer calls expanduser, at which point it
        # is an absolute path that was never checked.
        return "home-relative path"
    return None


def _classify_declaration(
    raw: str, declared_by: str
) -> Declaration | RejectedDeclaration:
    reason = reject_relative(raw)
    if reason is not None:
        return RejectedDeclaration(raw, declared_by, reason)
    return Declaration(Path(raw).as_posix(), declared_by)


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

    **One record per declaring site, not per path.** The scaffold declares
    `commands/flow-boot.md` twice — once under `[[claude.commands]]` and once
    under `[[codex.commands]]`. Collapsing to the first site would hand a later
    manifest rewrite one entry to drop and leave the other dangling, which is
    the precise failure `declared_by` was added to prevent. Callers wanting
    unique paths take a set of `rel`, which `refresh_project` does.
    """
    found: list[Declaration] = []
    rejected: list[RejectedDeclaration] = []

    def take(raw, declared_by: str) -> None:
        if not isinstance(raw, str) or not raw:
            return
        record = _classify_declaration(raw, declared_by)
        if isinstance(record, RejectedDeclaration):
            rejected.append(record)
            return
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


# ---------------------------------------------------------------------------
# Project wiring — `[[replaces]]`
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplaceWiring:
    """One validated `[[replaces]]` entry.

    `default` names a framework file by the same relative name a role cites
    (`standards/testing.md`). `with_` names a replacement resolved under the
    user overlay — never inside the project, which is the whole point: a
    project that held the replacement would be the fork again.

    Both are safe to join. `why` is documentation, never resolved, printed
    only so a reader can see the intent without opening the manifest.
    """

    default: str
    with_: str
    why: str | None
    declared_by: str


@dataclass(frozen=True)
class RejectedReplace:
    """A `[[replaces]]` entry that could not be validated.

    Carries no joinable field, for the reason `RejectedDeclaration` does not:
    a `with` of `../../../etc/passwd` must never reach a join against the
    user overlay, so it is kept as raw text to be printed and read.
    """

    declared_by: str
    declared_value: str
    reason: str


# The only two kinds resolved by the runtime convention. Commands, agents, and
# hooks are merged at sync time instead (`merge_user_overlay` in `sync.py`), so
# a wiring naming one of those would resolve on disk, report healthy, and be
# honoured by nothing — a confident `ok` that ends the reader's investigation
# at the wrong place.
REPLACEABLE_DIRS = ("standards", "templates")


def _reject_unresolvable_kind(raw: str) -> str | None:
    parts = Path(raw).parts
    if len(parts) < 2 or parts[0] not in REPLACEABLE_DIRS:
        return f"only {' and '.join(d + '/' for d in REPLACEABLE_DIRS)} are resolved by this convention"
    return None


def declared_replaces(manifest: dict) -> tuple[list[ReplaceWiring], list[RejectedReplace]]:
    """Parse `[[replaces]]`. Pure — no filesystem, no resolution.

    Order is the manifest's, not sorted. This table is a short hand-authored
    list; re-ordering it would make doctor's report harder to read against
    the file it came from.

    Entries are keyed by index rather than by name because `[[replaces]]` has
    no name field. That is fine here in a way it would not be for
    `declared_sources`: nothing rewrites this table, so the key only has to
    identify a line for a human.
    """
    entries = manifest.get("replaces", [])
    if not isinstance(entries, list):
        return [], [RejectedReplace("replaces", str(entries), "not an array of tables")]

    found: list[ReplaceWiring] = []
    rejected: list[RejectedReplace] = []

    for index, entry in enumerate(entries):
        site = f"replaces[{index}]"
        if not isinstance(entry, dict):
            rejected.append(RejectedReplace(site, str(entry), "not a table"))
            continue

        problem = None
        for key in ("default", "with"):
            value = entry.get(key)
            if value is None:
                problem = f"missing {key}"
            elif not isinstance(value, str) or not value:
                problem = f"{key} is not a non-empty string"
            else:
                problem = reject_relative(value)
                if problem is None:
                    problem = _reject_unresolvable_kind(value)
                if problem is not None:
                    problem = f"{key}: {problem}"
            if problem is not None:
                rejected.append(RejectedReplace(site, str(entry.get(key)), problem))
                break
        if problem is not None:
            continue

        why = entry.get("why")
        found.append(
            ReplaceWiring(
                default=Path(entry["default"]).as_posix(),
                with_=Path(entry["with"]).as_posix(),
                # Dropped rather than rejected when it is the wrong type. `why`
                # is a comment with a TOML key; a bad one should not disable a
                # wiring that otherwise resolves.
                why=why if isinstance(why, str) and why else None,
                declared_by=site,
            )
        )

    # Two wirings for one `default` hand a role two instructions and no rule
    # for choosing, which is the split-brain this whole design exists to close.
    # Both are rejected rather than first-wins: picking silently would make the
    # resolution depend on manifest order, which nothing documents.
    counts: dict[str, int] = {}
    for wiring in found:
        counts[wiring.default] = counts.get(wiring.default, 0) + 1
    duplicated = {default for default, n in counts.items() if n > 1}
    if duplicated:
        rejected.extend(
            RejectedReplace(
                w.declared_by,
                w.default,
                "duplicate default — another entry already replaces this name",
            )
            for w in found
            if w.default in duplicated
        )
        found = [w for w in found if w.default not in duplicated]

    return found, rejected


REPLACE_OK = "ok"
REPLACE_ABSENT = "absent"
REPLACE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class ResolvedReplace:
    wiring: ReplaceWiring
    status: str


def resolve_replaces(
    wirings: list[ReplaceWiring], scaffold_dir: Path, user_overlay_dir: Path
) -> list[ResolvedReplace]:
    """Check each wiring against the two roots it spans.

    `unknown` is tested before `absent` deliberately. An entry can be wrong in
    both ways at once, and a `default` naming no framework file is the more
    actionable defect: it is a typo the author can fix, whereas an absent
    `with` may simply mean this machine is not the one the wiring was written
    on. Reporting the typo as a per-user gap would send the reader to fix the
    wrong thing.

    Both roots are parameters rather than module constants so this is testable
    against two temp directories, the way `classify_tree` is.
    """
    resolved: list[ResolvedReplace] = []
    for wiring in wirings:
        # A `default` is whatever name a role cites, and rule 2 lets the user
        # overlay introduce standards the framework never shipped. Checking
        # only the scaffold would call those legitimate wirings typos.
        cited_exists = (scaffold_dir / wiring.default).is_file() or (
            user_overlay_dir / wiring.default
        ).is_file()
        if not cited_exists:
            status = REPLACE_UNKNOWN
        # `is_file` follows symlinks, unlike `capability_entries`, which
        # refuses to classify them. The asymmetry is deliberate: that function
        # feeds deletion, this one only reports, and the link would have to be
        # inside the user's own overlay to matter.
        elif (user_overlay_dir / wiring.with_).is_file():
            status = REPLACE_OK
        else:
            status = REPLACE_ABSENT
        resolved.append(ResolvedReplace(wiring, status))
    return resolved


LEGACY_ACTIVE_STANDARDS_HEADING = "## Active project standards"


def has_legacy_active_standards_heading(project_md_text: str) -> bool:
    """Whether a `PROJECT.md` still lists the retired project-standards section.

    Deliberately not an audit `Finding`. `PROJECT.md` is in `NOT_SCANNED`, and
    that is a safety property rather than a scoping convenience: nothing
    outside `CAPABILITY_PATHS` can be proposed for deletion by anything reading
    an `AuditReport`. This is a doctor-level flag about the *content* of a file
    the audit deliberately never opens, so it stays a separate question with a
    separate answer.
    """
    return LEGACY_ACTIVE_STANDARDS_HEADING in project_md_text


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

BUCKET_IDENTICAL = "identical"
BUCKET_DIFFERS = "differs"
BUCKET_PROJECT_ONLY = "project-only"
BUCKET_ORPHANED = "orphaned"
BUCKET_CONFLICT = "conflict"
BUCKET_UNREADABLE = "unreadable"

# Render order, and the sort key. Deliberately not alphabetical: the two buckets
# that need a decision come after the two that do not.
BUCKET_ORDER = (
    BUCKET_IDENTICAL,
    BUCKET_DIFFERS,
    BUCKET_PROJECT_ONLY,
    BUCKET_ORPHANED,
    BUCKET_CONFLICT,
    BUCKET_UNREADABLE,
)

BUCKET_GLOSS = {
    BUCKET_IDENTICAL: "byte-equal to the framework's copy",
    # Stated in the output and not only in the docs, because this count is what
    # gets pasted into a ticket and the caveat has to travel with it. Nothing
    # local can separate "the framework moved on" from "someone edited this".
    BUCKET_DIFFERS: "stale or customized — cannot be told apart locally",
    BUCKET_PROJECT_ONLY: "no framework counterpart",
    BUCKET_ORPHANED: "declared in flow.toml, absent on disk",
    BUCKET_CONFLICT: "not a file where the framework has one",
    BUCKET_UNREADABLE: "could not be read, so could not be compared",
}

NOT_SCANNED = ("PROJECT.md", "flow.toml", "memory/", "runs/")


@dataclass(frozen=True)
class Finding:
    """One classified path, keyed relative to the overlay root.

    `declared_by` is set only for orphans, which are the one bucket discovered
    through the manifest rather than by walking.
    """

    rel: str
    bucket: str
    # Every manifest site that named this path. A tuple, not one string: a
    # source declared under both `[[claude.commands]]` and `[[codex.commands]]`
    # has two entries to fix, and reporting one of them is how the other gets
    # left dangling.
    declared_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuditReport:
    """The roots are carried here, once, and nowhere inside a finding.

    `has_baseline` is false when the framework scaffold holds none of the
    capability directories. Every classification is then wrong in the same
    direction — everything looks project-only — so callers must refuse to
    report buckets rather than print a confident zero.
    """

    flow_dir: str
    scaffold_dir: str
    findings: list[Finding]
    rejected: list[RejectedDeclaration]
    symlinks: list[str]
    has_baseline: bool
    # Whether the comparison used the installed framework. `--scaffold` pointed
    # at the project's own overlay makes every file `identical`, which is the
    # bucket a later migration deletes — so the answer travels with the report
    # rather than being reconstructed by whoever consumes it.
    default_scaffold: bool

    def counts(self) -> dict[str, int]:
        counts = {bucket: 0 for bucket in BUCKET_ORDER}
        for finding in self.findings:
            counts[finding.bucket] += 1
        return counts

    def classified(self) -> int:
        """How many entries got a bucket.

        Not "entries visited": the capability directories themselves are walked
        and produce no finding, and orphans were never on disk at all. This is
        the number that reconciles against a file listing, which is the only
        reason to print it.
        """
        return sum(1 for f in self.findings if f.bucket != BUCKET_ORPHANED)


def printable(text: str) -> str:
    """Control characters escaped for display.

    A manifest source containing a newline carries no `..` and is not absolute,
    so it reaches the report as an ordinary value — and printed raw it
    fabricates rows in a report someone is about to diff by eye. ANSI escapes
    in a filename reach the terminal the same way.
    """
    return "".join(
        c if c.isprintable() else c.encode("unicode_escape").decode("ascii")
        for c in text
    )


def _is_noise(name: str) -> bool:
    return any(fnmatch(name, pattern) for pattern in RELEASE_EXCLUDE_FILE_PATTERNS)


def capability_entries(flow_dir: Path) -> tuple[list[tuple[str, bool]], list[str]]:
    """Every entry under the capability paths, plus the symlinks that were not
    followed. Entries are `(posix_rel, is_dir)`.

    An allowlist walk, never a denylist over `.flow/`: a directory added to the
    overlay in some future version is excluded by default rather than swept in.

    **Symlinks are never classified.** This module's central safety claim is
    that a finding's relative key is safe to join against the overlay root, and
    a symlink breaks it: with `.flow/agents` symlinked elsewhere, `agents/x.md`
    is a perfectly innocent-looking key that resolves outside the overlay, and
    the consumer of these findings deletes what they name. `rglob` already
    declines to descend into a symlinked directory, but the capability path
    itself can be one, which it does follow.

    They are returned rather than dropped. A silently skipped file is the same
    output as a file that is not there, and the two want different responses.
    """
    entries: set[tuple[str, bool]] = set()
    symlinks: set[str] = set()
    for name in CAPABILITY_PATHS:
        top = flow_dir / name
        # Checked before `exists`, which is False for a broken symlink and
        # would drop it from both lists.
        if top.is_symlink():
            symlinks.add(name)
            continue
        if not top.exists():
            continue
        entries.add((name, top.is_dir()))
        if not top.is_dir():
            continue
        for child in top.rglob("*"):
            rel = child.relative_to(flow_dir)
            if any(part in RELEASE_EXCLUDE_DIRS for part in rel.parts):
                continue
            if child.is_symlink():
                symlinks.add(rel.as_posix())
                continue
            is_dir = child.is_dir()
            if not is_dir and _is_noise(child.name):
                continue
            entries.add((rel.as_posix(), is_dir))
    return sorted(entries), sorted(symlinks)


def classify_tree(
    flow_dir: Path, scaffold_dir: Path
) -> tuple[list[Finding], list[str]]:
    """Classify a project's capability files against a framework scaffold.

    Both roots are parameters and neither is read from a module global. That is
    the whole reason this is unit-testable against two temporary directories
    instead of a subprocess with a fabricated HOME — `_refresh_scaffold_files`
    in setup.py reads `SCAFFOLD_DIR` directly, and every test of it pays for it.

    Comparison is raw bytes. Anything more forgiving — normalizing line endings,
    ignoring trailing whitespace — would classify a real edit as `identical`,
    and `identical` is the bucket a later migration deletes.
    """
    findings: list[Finding] = []
    entries, symlinks = capability_entries(flow_dir)
    for rel, is_dir in entries:
        src = scaffold_dir / rel
        if is_dir:
            # A directory where the framework has a file. setup.py already
            # carries this branch; without it the byte comparison below raises
            # IsADirectoryError and the whole audit dies on one odd path.
            if src.is_file():
                findings.append(Finding(rel, BUCKET_CONFLICT))
            continue
        if not src.exists():
            findings.append(Finding(rel, BUCKET_PROJECT_ONLY))
        elif not src.is_file():
            findings.append(Finding(rel, BUCKET_CONFLICT))
        else:
            # A file `rglob` listed but cannot be read — mode 000 is the
            # ordinary cause. Reported as its own bucket rather than skipped:
            # a path that silently gets no bucket is indistinguishable from a
            # path that is not there, and the consumer of these findings must
            # not inherit a file nobody classified.
            try:
                same = (flow_dir / rel).read_bytes() == src.read_bytes()
            except OSError:
                findings.append(Finding(rel, BUCKET_UNREADABLE))
                continue
            findings.append(
                Finding(rel, BUCKET_IDENTICAL if same else BUCKET_DIFFERS)
            )
    return findings, symlinks


def find_orphans(declarations: list[Declaration], flow_dir: Path) -> list[Finding]:
    """Declarations naming a file that is not there.

    Existence is checked first and wins: a declared file that *is* present has
    already been classified by `classify_tree`, and reporting it as orphaned as
    well would tell a later manifest rewrite to drop an entry that resolves.
    """
    sites: dict[str, list[str]] = {}
    for declaration in declarations:
        if (flow_dir / declaration.rel).exists():
            continue
        sites.setdefault(declaration.rel, []).append(declaration.declared_by)
    return [
        Finding(rel, BUCKET_ORPHANED, tuple(sorted(sites[rel])))
        for rel in sorted(sites)
    ]


def overlapping_trees(a: Path, b: Path) -> bool:
    """True when two resolved paths are the same directory or one contains
    the other.

    Containment rather than equality, because a subdirectory of the overlay is
    still the project's own tree and still compares byte-equal to itself.
    `samefile` covers the gap `resolve()` leaves on a case-insensitive
    filesystem for the *equality* leg only: `is_relative_to` is a lexical
    comparison, so a case-differing subdirectory is caught by none of the
    three. Unreachable in practice, since the baseline gate rejects it a
    moment later, but the limit is real and worth stating.

    Path-shaped, not content-shaped. A copy of the overlay somewhere else is
    a different tree by every test here, and migrating against it deletes
    everything — no guard sees that, and none is proposed: the flag has to
    stay usable for real scaffolds.
    """
    if a == b:
        return True
    try:
        if a.samefile(b):
            return True
    except OSError:
        # Either side missing. Not the same tree by any reading, and a
        # nonexistent scaffold is caught by the baseline gate anyway.
        pass
    return a.is_relative_to(b) or b.is_relative_to(a)


def has_framework_baseline(scaffold_dir: Path) -> bool:
    return any((scaffold_dir / name).is_dir() for name in CAPABILITY_DIRS)


def audit_project(flow_dir: Path, scaffold_dir: Path) -> AuditReport:
    manifest_path = flow_dir / "flow.toml"
    manifest = read_toml(manifest_path) if manifest_path.is_file() else {}
    declarations, rejected = declared_sources(manifest)

    # Classification is skipped entirely without a baseline rather than
    # computed and then withheld by the renderer: a JSON consumer reading
    # `findings` would otherwise get the buckets the table refuses to print.
    baseline = has_framework_baseline(scaffold_dir)
    findings: list[Finding] = []
    symlinks: list[str] = []
    if baseline:
        findings, symlinks = classify_tree(flow_dir, scaffold_dir)
        findings.extend(find_orphans(declarations, flow_dir))
        findings.sort(key=lambda f: (BUCKET_ORDER.index(f.bucket), f.rel))

    return AuditReport(
        flow_dir=str(flow_dir),
        scaffold_dir=str(scaffold_dir),
        findings=findings,
        rejected=rejected,
        symlinks=symlinks,
        has_baseline=baseline,
        default_scaffold=scaffold_dir.resolve() == SCAFFOLD_DIR.resolve(),
    )


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def audit_payload(report: AuditReport) -> dict:
    """The machine form. Roots appear once, at the top; findings carry only a
    relative key, so nothing in the array can be joined against the wrong root."""
    return {
        "flow_dir": report.flow_dir,
        "scaffold_dir": report.scaffold_dir,
        "default_scaffold": report.default_scaffold,
        "has_baseline": report.has_baseline,
        "symlinks": list(report.symlinks),
        "classified": report.classified(),
        "counts": report.counts(),
        "findings": [
            {"rel": f.rel, "bucket": f.bucket, "declared_by": list(f.declared_by)}
            for f in report.findings
        ],
        "rejected": [
            {
                "declared_value": r.declared_value,
                "declared_by": r.declared_by,
                "reason": r.reason,
            }
            for r in report.rejected
        ],
    }


def render_audit(report: AuditReport) -> str:
    """Bucket-major, with the paths listed under every bucket including
    `identical`.

    Per-file rows with a bucket column would be shorter, but the buckets carry
    different actions and the counts belong at the section head where a hand
    audit can be diffed against them. The paths are listed because the list is
    what a diff actually compares — two audits agreeing on six integers while
    disagreeing on which files they counted is the failure this format exists
    to make visible.
    """
    lines = [
        f"project:   {report.flow_dir}",
        f"framework: {report.scaffold_dir}",
        "",
    ]

    if not report.has_baseline:
        lines.append("no framework baseline: the scaffold holds none of the")
        lines.append(f"capability directories ({', '.join(CAPABILITY_DIRS)}).")
        lines.append("")
        lines.append(
            "Every file would classify as project-only, which would be wrong "
            "rather than clean."
        )
        lines.append("Nothing is reported. Check the framework install first.")
        return "\n".join(lines)

    counts = report.counts()
    classified = report.classified()
    lines.append(
        f"classified {classified} entr{'y' if classified == 1 else 'ies'} under: "
        f"{', '.join(CAPABILITY_PATHS)}"
    )
    lines.append(
        f"not scanned: {', '.join(NOT_SCANNED)} — project state, never framework "
        f"capability"
    )
    lines.append("this command only reads; it never writes, moves, or deletes.")

    # The one reading of this report that is actively misleading. Compared
    # against the project's own tree every file is byte-equal to itself, so
    # `identical` fills up and the report reads as an invitation to migrate —
    # while `flow project migrate` refuses this exact comparison. Audit is
    # still allowed to make it: it deletes nothing, and comparing a tree
    # against itself is a reasonable thing to ask for. It just has to say what
    # it is looking at.
    if not report.default_scaffold and overlapping_trees(
        Path(report.scaffold_dir).resolve(), Path(report.flow_dir).resolve()
    ):
        lines.append("")
        lines.append("NOTE: --scaffold names this project's own tree, so every file is")
        lines.append("being compared against itself and `identical` below means only")
        lines.append("that. `flow project migrate` refuses this comparison.")

    for bucket in BUCKET_ORDER:
        members = [f for f in report.findings if f.bucket == bucket]
        lines.append("")
        lines.append(f"{bucket} ({counts[bucket]}) — {BUCKET_GLOSS[bucket]}")
        if not members:
            lines.append("  (none)")
            continue
        for finding in members:
            suffix = (
                f"   [declared by {', '.join(finding.declared_by)}]"
                if finding.declared_by
                else ""
            )
            lines.append(f"  {printable(finding.rel)}{suffix}")

    if report.symlinks:
        lines.append("")
        lines.append(
            f"not followed ({len(report.symlinks)}) — symlinks, which resolve "
            f"outside the overlay and are never classified"
        )
        for rel in report.symlinks:
            lines.append(f"  {printable(rel)}")

    if report.rejected:
        lines.append("")
        lines.append(
            f"unusable declarations ({len(report.rejected)}) — flow.toml names a "
            f"source outside the overlay"
        )
        for record in report.rejected:
            lines.append(
                f"  {printable(record.declared_value)}   "
                f"[{printable(record.declared_by)}: {record.reason}]"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_audit(args) -> int:
    """Resolve the two roots, print, and return.

    The exit code reports whether an audit could be produced, never what it
    found. Contamination is the normal state of every project set up before
    the overlay was thinned, so a non-zero exit on `differs` would make the
    command useless in a pipeline and train everyone to ignore it — this is
    the deliberate divergence from `flow sync --check`, which exits 1 on drift
    because drift there is a repairable fault.

    The two cases that do exit 1 are the ones where a clean-looking report
    would be a lie: there is no project here, or there is no framework to
    compare against.
    """
    scaffold_dir = (
        Path(args.scaffold).expanduser() if getattr(args, "scaffold", None)
        else SCAFFOLD_DIR
    )

    if getattr(args, "root", None):
        flow_dir = Path(args.root).expanduser()
        if not flow_dir.is_dir():
            print(f"--root is not a directory: {flow_dir}")
            return 1
    else:
        flow_dir = repo_root() / ".flow"

    # `repo_root` falls back to the working directory when nothing above it
    # looks like a project, so from $HOME this resolves to flow's own home.
    # `bootstrap` guards the same confusion with an equality check; containment
    # is used here because `--root` accepts a path directly, and
    # `~/.flow/user` or `~/.flow/source/scaffolds/default` would otherwise be
    # audited as if the framework's own files were some project's overlay.
    if flow_dir.resolve().is_relative_to(FLOW_HOME.resolve()):
        print("that is inside flow's own home, not a project overlay")
        print("run this inside a repo, or pass --root <path-to-a-project>/.flow")
        return 1
    if not flow_dir.exists():
        print("repo is missing .flow; run `flow setup project` first")
        return 1

    report = audit_project(flow_dir, scaffold_dir)

    if getattr(args, "json", False):
        print(json.dumps(audit_payload(report), indent=2, sort_keys=True))
    else:
        print(render_audit(report))

    return 0 if report.has_baseline else 1
