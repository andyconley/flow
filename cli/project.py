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
from fnmatch import fnmatch
from pathlib import Path

# paths/fsutil/flowtoml only. See the module docstring: the absence of `setup`
# and `sync` here is a contract, not an accident, and `tests/test_flow.py`
# asserts it.
from flowtoml import read_toml
from paths import (
    CAPABILITY_DIRS,
    CAPABILITY_PATHS,
    RELEASE_EXCLUDE_DIRS,
    RELEASE_EXCLUDE_FILE_PATTERNS,
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


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

BUCKET_IDENTICAL = "identical"
BUCKET_DIFFERS = "differs"
BUCKET_PROJECT_ONLY = "project-only"
BUCKET_ORPHANED = "orphaned"
BUCKET_CONFLICT = "conflict"

# Render order, and the sort key. Deliberately not alphabetical: the two buckets
# that need a decision come after the two that do not.
BUCKET_ORDER = (
    BUCKET_IDENTICAL,
    BUCKET_DIFFERS,
    BUCKET_PROJECT_ONLY,
    BUCKET_ORPHANED,
    BUCKET_CONFLICT,
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
    declared_by: str | None = None


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
    has_baseline: bool

    def counts(self) -> dict[str, int]:
        counts = {bucket: 0 for bucket in BUCKET_ORDER}
        for finding in self.findings:
            counts[finding.bucket] += 1
        return counts

    def scanned(self) -> int:
        """Entries visited on disk. Orphans were never on disk, so they are not
        part of this total — a scanned count that included them could not be
        reconciled against a file listing."""
        return sum(1 for f in self.findings if f.bucket != BUCKET_ORPHANED)


def _is_noise(name: str) -> bool:
    return any(fnmatch(name, pattern) for pattern in RELEASE_EXCLUDE_FILE_PATTERNS)


def capability_entries(flow_dir: Path) -> list[tuple[str, bool]]:
    """Every entry under the capability paths, as `(posix_rel, is_dir)`.

    An allowlist walk, never a denylist over `.flow/`: a directory added to the
    overlay in some future version is excluded by default rather than swept in.
    """
    entries: set[tuple[str, bool]] = set()
    for name in CAPABILITY_PATHS:
        top = flow_dir / name
        if not top.exists():
            continue
        entries.add((name, top.is_dir()))
        if not top.is_dir():
            continue
        for child in top.rglob("*"):
            rel = child.relative_to(flow_dir)
            if any(part in RELEASE_EXCLUDE_DIRS for part in rel.parts):
                continue
            is_dir = child.is_dir()
            if not is_dir and _is_noise(child.name):
                continue
            entries.add((rel.as_posix(), is_dir))
    return sorted(entries)


def classify_tree(flow_dir: Path, scaffold_dir: Path) -> list[Finding]:
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
    for rel, is_dir in capability_entries(flow_dir):
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
        elif (flow_dir / rel).read_bytes() == src.read_bytes():
            findings.append(Finding(rel, BUCKET_IDENTICAL))
        else:
            findings.append(Finding(rel, BUCKET_DIFFERS))
    return findings


def find_orphans(declarations: list[Declaration], flow_dir: Path) -> list[Finding]:
    """Declarations naming a file that is not there.

    Existence is checked first and wins: a declared file that *is* present has
    already been classified by `classify_tree`, and reporting it as orphaned as
    well would tell a later manifest rewrite to drop an entry that resolves.
    """
    orphans = [
        Finding(d.rel, BUCKET_ORPHANED, d.declared_by)
        for d in declarations
        if not (flow_dir / d.rel).exists()
    ]
    return sorted(orphans, key=lambda f: (f.rel, f.declared_by or ""))


def has_framework_baseline(scaffold_dir: Path) -> bool:
    return any((scaffold_dir / name).is_dir() for name in CAPABILITY_DIRS)


def audit_project(flow_dir: Path, scaffold_dir: Path) -> AuditReport:
    manifest_path = flow_dir / "flow.toml"
    manifest = read_toml(manifest_path) if manifest_path.is_file() else {}
    declarations, rejected = declared_sources(manifest)

    findings = classify_tree(flow_dir, scaffold_dir)
    findings.extend(find_orphans(declarations, flow_dir))
    findings.sort(key=lambda f: (BUCKET_ORDER.index(f.bucket), f.rel))

    return AuditReport(
        flow_dir=str(flow_dir),
        scaffold_dir=str(scaffold_dir),
        findings=findings,
        rejected=rejected,
        has_baseline=has_framework_baseline(scaffold_dir),
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
        "has_baseline": report.has_baseline,
        "scanned": report.scanned(),
        "counts": report.counts(),
        "findings": [
            {"rel": f.rel, "bucket": f.bucket, "declared_by": f.declared_by}
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
    scanned = report.scanned()
    lines.append(
        f"scanned {scanned} entr{'y' if scanned == 1 else 'ies'} under: "
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
                f"   [declared by {finding.declared_by}]" if finding.declared_by else ""
            )
            lines.append(f"  {finding.rel}{suffix}")

    if report.rejected:
        lines.append("")
        lines.append(
            f"unusable declarations ({len(report.rejected)}) — flow.toml names a "
            f"source outside the overlay"
        )
        for record in report.rejected:
            lines.append(
                f"  {record.declared_value}   [{record.declared_by}: {record.reason}]"
            )

    return "\n".join(lines)
