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


def _classify_declaration(
    raw: str, declared_by: str
) -> Declaration | RejectedDeclaration:
    rel = Path(raw)
    if rel.is_absolute():
        return RejectedDeclaration(raw, declared_by, "absolute path")
    if ".." in rel.parts:
        return RejectedDeclaration(raw, declared_by, "escapes the overlay via ..")
    if rel.parts and rel.parts[0].startswith("~"):
        # pathlib does not expand `~`, so this is not absolute and carries no
        # `..` — it passes both guards above and lands as an ordinary relative
        # key. Harmless until one consumer calls expanduser, at which point it
        # is an absolute path that was never checked.
        return RejectedDeclaration(raw, declared_by, "home-relative path")
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


def _printable(text: str) -> str:
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
            lines.append(f"  {_printable(finding.rel)}{suffix}")

    if report.symlinks:
        lines.append("")
        lines.append(
            f"not followed ({len(report.symlinks)}) — symlinks, which resolve "
            f"outside the overlay and are never classified"
        )
        for rel in report.symlinks:
            lines.append(f"  {_printable(rel)}")

    if report.rejected:
        lines.append("")
        lines.append(
            f"unusable declarations ({len(report.rejected)}) — flow.toml names a "
            f"source outside the overlay"
        )
        for record in report.rejected:
            lines.append(
                f"  {_printable(record.declared_value)}   "
                f"[{_printable(record.declared_by)}: {record.reason}]"
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
