"""Compose role expertise entries into an agent body at sync time.

Entries are authored as JSON-LD (ADR 0008) and owned per role. Two layers
merge here: the `baseline` corpus that ships with flow, and an `experience`
corpus the user owns under `~/.flow/user/expertise/`. The merge is a **union**,
unlike the `[[agents]]` overlay in sync.py, which replaces an entry by name —
replacement is right for a role body and wrong for a corpus, because it would
silently drop baseline entries the user never meant to remove.

Experience entries render first, so they are read first, but they do not
suppress baseline entries covering the same ground. Nothing here ranks or
selects: the whole merged corpus reaches the agent, which is what the pilot
validation measured.
"""
from __future__ import annotations

import json
from pathlib import Path

SECTION = "## Expertise"
BULLETS = (
    ("Source", None),
    ("Principle", "abstract"),
    ("Use when", "flow:trigger"),
    ("Required behavior", "flow:requiredBehavior"),
    ("Avoid", "flow:failureMode"),
)
WRAP = 78


class ExpertiseError(ValueError):
    """An authored corpus is unusable. Sync fails rather than dropping entries.

    Silently skipping a malformed corpus would ship an agent quietly missing
    its expertise, which is the one failure mode the composed agent cannot
    show on its face.
    """

    def __init__(self, rule: str, detail: str, *, source: str, remediation: str) -> None:
        self.rule = rule
        self.source = source
        self.remediation = remediation
        super().__init__(f"{rule}: {detail} (source={source}) — {remediation}")


def _read(path: Path, layer: str) -> list[dict]:
    try:
        document = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise ExpertiseError(
            "invalid-expertise-json",
            f"expertise corpus is not valid JSON: {error}",
            source=str(path),
            remediation="fix the JSON syntax; sync will not skip a corpus it cannot read",
        ) from error
    graph = document.get("@graph")
    if not isinstance(graph, list):
        raise ExpertiseError(
            "missing-expertise-graph",
            "expertise corpus has no @graph array",
            source=str(path),
            remediation='wrap the entries in {"@context": {...}, "@graph": [...]}',
        )
    entries = []
    for entry in graph:
        if not isinstance(entry, dict):
            raise ExpertiseError(
                "invalid-expertise-entry",
                "every @graph member must be an object",
                source=str(path),
                remediation="remove the non-object member",
            )
        missing = [
            key
            for key in ("name", "abstract", "flow:trigger", "flow:requiredBehavior", "flow:failureMode")
            if not entry.get(key)
        ]
        if missing:
            raise ExpertiseError(
                "incomplete-expertise-entry",
                f'entry {entry.get("name") or entry.get("@id") or "<unnamed>"} is missing {", ".join(missing)}',
                source=str(path),
                remediation="an entry carries all five authored parts or it is not an entry",
            )
        entry = dict(entry)
        entry["_layer"] = layer
        entries.append(entry)
    return entries


def corpus_for(role: str, framework_dir: Path, user_dir: Path | None) -> list[dict]:
    """Merged corpus for one role: experience entries first, then baseline."""
    baseline_path = framework_dir / "expertise" / f"{role}.jsonld"
    baseline = _read(baseline_path, "baseline") if baseline_path.exists() else []
    experience: list[dict] = []
    if user_dir is not None:
        user_path = user_dir / "expertise" / f"{role}.jsonld"
        if user_path.exists():
            experience = _read(user_path, "experience")
    return experience + baseline


def _cite(source: dict) -> str:
    citation = source.get("citation") or {}
    author = str(citation.get("author", "")).split()
    surname = author[-1] if author else "Unattributed"
    name = citation.get("name", "")
    title = f"*{name}*" if citation.get("@type") == "Book" else f'"{name}"'
    published = []
    if citation.get("isPartOf"):
        published.append(f'*{citation["isPartOf"]}*')
    if citation.get("datePublished"):
        published.append(str(citation["datePublished"]))
    if citation.get("version"):
        published.append(str(citation["version"]))
    parenthetical = f' ({", ".join(str(p) for p in published)})' if published else ""
    locator = source.get("flow:locator")
    tail = f" — {locator}" if locator else ""
    return f"{surname}, {title}{parenthetical}{tail}"


def _source_line(entry: dict) -> str:
    sources = entry.get("flow:source") or []
    if not sources:
        return "unattributed"
    return "; ".join(_cite(source) for source in sources) + "."


def _wrap(label: str, text: str) -> list[str]:
    import textwrap

    return textwrap.wrap(
        f"- {label}: {text}", width=WRAP, subsequent_indent="  ", break_long_words=False,
        break_on_hyphens=False,
    ) or [f"- {label}:"]


def render_entry(entry: dict) -> list[str]:
    lines = [f'### {entry["name"]}', ""]
    for label, key in BULLETS:
        text = _source_line(entry) if key is None else entry[key]
        lines.extend(_wrap(label, text))
    teaches = [t.get("name") for t in entry.get("teaches") or [] if t.get("name")]
    if teaches:
        lines.extend(_wrap("Teaches", "; ".join(f'"{name}"' for name in teaches)))
    if entry.get("_layer") == "experience":
        lines.extend(_wrap("Layer", "experience — yours, not shipped with flow"))
    return lines


def render_section(entries: list[dict]) -> str:
    blocks = [SECTION, ""]
    for entry in entries:
        blocks.extend(render_entry(entry))
        blocks.append("")
    return "\n".join(blocks)


def compose(body: str, entries: list[dict]) -> str:
    """Insert the rendered section into an agent body.

    Placed before `## Composition` when that heading exists, matching where the
    pilot authored it by hand, and appended otherwise. An agent with no corpus
    is returned unchanged, so marking a role composed before writing its
    entries is a no-op rather than a failure.
    """
    if not entries:
        return body
    if SECTION in body:
        raise ExpertiseError(
            "duplicate-expertise-section",
            "agent body already carries an ## Expertise section",
            source="<agent body>",
            remediation="remove the hand-authored section; composition owns it now",
        )
    section = render_section(entries)
    marker = "\n## Composition"
    if marker in body:
        head, _, tail = body.partition(marker)
        return f"{head.rstrip()}\n\n{section}\n{marker.lstrip(chr(10))}{tail}"
    return f"{body.rstrip()}\n\n{section}"
