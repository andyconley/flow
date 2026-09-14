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

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from expertise_json import BoundedJSONError, read_json

SECTION = "## Expertise"
VOCABULARY = "competencies.md"
COMPETENCY_PREFIX = "flow:competency/"
BULLETS = (
    ("Source", None),
    ("Principle", "abstract"),
    ("Use when", "flow:trigger"),
    ("Required behavior", "flow:requiredBehavior"),
    ("Avoid", "flow:failureMode"),
)
WRAP = 78
LIFECYCLE_STATES = frozenset({"current", "withdrawn", "superseded", "unknown"})
FRAMEWORK_OWNER_PREFIX = "flow:owner/"


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
        document = read_json(path, maximum_bytes=1024 * 1024, maximum_nodes=10000)
    except BoundedJSONError as error:
        raise ExpertiseError(
            "invalid-expertise-json",
            f"expertise corpus cannot be parsed within limits: {error}",
            source=str(path),
            remediation="fix the JSON or reduce the corpus; sync will not skip unusable expertise",
        ) from error
    if not isinstance(document, dict):
        raise ExpertiseError("invalid-expertise-json", "expertise corpus must be an object",
                             source=str(path), remediation="wrap entries in a JSON-LD object")
    graph = document.get("@graph")
    if not isinstance(graph, list) or len(graph) > 512:
        raise ExpertiseError(
            "missing-expertise-graph",
            "expertise corpus needs an @graph array of at most 512 entries",
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
            key for key in (
                "@id", "name", "audience", "flow:layer", "abstract", "flow:trigger",
                "flow:requiredBehavior", "flow:failureMode",
            )
            if not entry.get(key)
        ]
        if missing:
            raise ExpertiseError(
                "incomplete-expertise-entry",
                f'entry {entry.get("name") or entry.get("@id") or "<unnamed>"} is missing {", ".join(missing)}',
                source=str(path),
                remediation="an entry carries all five authored parts or it is not an entry",
            )
        audience = entry.get("audience")
        if not isinstance(audience, dict) or not isinstance(audience.get("audienceType"), str):
            raise ExpertiseError(
                "invalid-expertise-audience",
                f'entry {entry.get("@id") or "<unnamed>"} has no audienceType',
                source=str(path),
                remediation="set audience.audienceType to the owning role name",
            )
        if entry.get("flow:layer") != layer:
            raise ExpertiseError(
                "unauthorized-expertise-layer",
                f'entry {entry["@id"]} declares {entry.get("flow:layer")!r} in the {layer} corpus',
                source=str(path),
                remediation=f'set flow:layer to "{layer}" or move the entry to its authorized corpus',
            )
        entry = dict(entry)
        entry["_layer"] = layer
        entry["_source_layer"] = "framework" if layer == "baseline" else "user"
        entry["_canonical_path"] = str(path)
        entry["_lifecycle"] = _lifecycle(entry, path)
        entry["_entry_digest"] = _entry_digest(entry)
        entries.append(entry)
    return entries


def _entry_digest(entry: dict) -> str:
    authored = {key: value for key, value in entry.items() if not key.startswith("_")}
    encoded = json.dumps(
        authored, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc_instant(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed)


def _lifecycle(entry: dict, path: Path) -> dict:
    raw = entry.get("flow:lifecycle")
    if raw is None:
        return {"state": "unknown", "owner": None, "attestedAt": None, "evidence": [], "supersedes": []}
    if not isinstance(raw, dict):
        raise ExpertiseError(
            "invalid-expertise-lifecycle", f'entry {entry["@id"]} lifecycle is not an object',
            source=str(path), remediation="use the documented flow:lifecycle object",
        )
    allowed = {"state", "owner", "attestedAt", "evidence", "supersedes"}
    extras = set(raw) - allowed
    state = raw.get("state")
    owner = raw.get("owner")
    evidence = raw.get("evidence")
    supersedes = raw.get("supersedes", [])
    invalid = (
        bool(extras) or state not in LIFECYCLE_STATES
        or not isinstance(supersedes, list)
        or any(not isinstance(value, str) or not value for value in supersedes)
        or len(supersedes) != len(set(supersedes))
    )
    if state != "unknown":
        invalid = invalid or not isinstance(owner, str) or not owner.strip()
        invalid = invalid or not _utc_instant(raw.get("attestedAt"))
        invalid = invalid or not isinstance(evidence, list) or not evidence
        if isinstance(evidence, list):
            invalid = invalid or any(
                not isinstance(item, dict)
                or set(item) != {"kind", "ref"}
                or not isinstance(item.get("kind"), str) or not item["kind"].strip()
                or not isinstance(item.get("ref"), str) or not item["ref"].strip()
                for item in evidence
            )
    elif any(raw.get(field) not in (None, [], "") for field in ("owner", "attestedAt", "evidence", "supersedes")):
        invalid = True
    if invalid:
        raise ExpertiseError(
            "invalid-expertise-lifecycle", f'entry {entry["@id"]} has malformed lifecycle metadata',
            source=str(path), remediation="supply a closed state/owner/UTC-attestation/evidence/supersession record",
        )
    return {
        "state": state,
        "owner": owner if state != "unknown" else None,
        "attestedAt": raw.get("attestedAt") if state != "unknown" else None,
        "evidence": evidence if state != "unknown" else [],
        "supersedes": supersedes,
    }


def _validate_lifecycle_graph(entries: list[dict], role: str) -> None:
    by_id: dict[str, dict] = {}
    for entry in entries:
        entry_id = entry["@id"]
        if entry_id in by_id:
            raise ExpertiseError(
                "duplicate-expertise-id", f"duplicate effective entry id {entry_id}",
                source=entry["_canonical_path"], remediation="give every merged role entry a distinct @id",
            )
        if entry["audience"]["audienceType"] != role:
            raise ExpertiseError(
                "wrong-expertise-role", f"entry {entry_id} belongs to {entry['audience']['audienceType']}, not {role}",
                source=entry["_canonical_path"], remediation=f'move the entry to {role}.jsonld or correct its audience',
            )
        if entry["_source_layer"] == "framework" and not str(entry["_lifecycle"].get("owner") or "").startswith(FRAMEWORK_OWNER_PREFIX):
            if entry["_lifecycle"]["state"] != "unknown":
                raise ExpertiseError(
                    "unauthorized-expertise-owner", f"framework entry {entry_id} has a non-framework owner",
                    source=entry["_canonical_path"], remediation=f"use a {FRAMEWORK_OWNER_PREFIX} owner identifier",
                )
        by_id[entry_id] = entry

    graph: dict[str, list[str]] = {entry_id: [] for entry_id in by_id}
    incoming: set[str] = set()
    for entry_id, entry in by_id.items():
        for target_id in entry["_lifecycle"]["supersedes"]:
            target = by_id.get(target_id)
            if target is None:
                raise ExpertiseError(
                    "unknown-supersession-target", f"entry {entry_id} supersedes missing {target_id}",
                    source=entry["_canonical_path"], remediation="add the target or remove the supersession edge",
                )
            if target_id == entry_id:
                raise ExpertiseError(
                    "self-supersession", f"entry {entry_id} supersedes itself", source=entry["_canonical_path"],
                    remediation="remove the self edge",
                )
            if (
                target["_layer"] != entry["_layer"]
                or target["_source_layer"] != entry["_source_layer"]
                or target["_lifecycle"].get("owner") != entry["_lifecycle"].get("owner")
            ):
                raise ExpertiseError(
                    "unauthorized-supersession", f"entry {entry_id} crosses an owner or layer boundary",
                    source=entry["_canonical_path"], remediation="supersede only an entry with the same owner and layer",
                )
            graph[entry_id].append(target_id)
            incoming.add(target_id)

    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(entry_id: str) -> None:
        if entry_id in visiting:
            raise ExpertiseError(
                "cyclic-supersession", f"supersession cycle includes {entry_id}",
                source=by_id[entry_id]["_canonical_path"], remediation="remove a supersession edge to make the graph acyclic",
            )
        if entry_id in visited:
            return
        visiting.add(entry_id)
        for target_id in graph[entry_id]:
            visit(target_id)
        visiting.remove(entry_id)
        visited.add(entry_id)
    for entry_id in graph:
        visit(entry_id)
    for entry_id, entry in by_id.items():
        entry["_effective_current"] = entry["_lifecycle"]["state"] == "current" and entry_id not in incoming


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _terms(path: Path) -> dict[str, str]:
    """Term id -> term name, read from a `competencies.md` DefinedTermSet.

    Headings are the terms. `## Open`-style prose sections are skipped by
    reading `###` only, which is the level every term uses.
    """
    if not path.exists():
        return {}
    names = re.findall(r"(?m)^### (.+)$", path.read_text())
    return {_slug(" ".join(name.split())): " ".join(name.split()) for name in names}


def vocabulary(framework_dir: Path, user_dir: Path | None) -> dict[str, str]:
    """The competency terms entries may teach: framework terms plus the user's.

    Unioned for the same reason the corpus is: a user writing their own
    experience entries may need a term flow does not ship, and validating
    their entries against flow's vocabulary alone would make that impossible
    without editing framework files.
    """
    terms = _terms(framework_dir / "expertise" / VOCABULARY)
    if user_dir is not None:
        user_path = user_dir / "expertise" / VOCABULARY
        for key, name in _terms(user_path).items():
            if key in terms and terms[key] != name:
                raise ExpertiseError(
                    "conflicting-competency-name",
                    f'user vocabulary names "{key}" as "{name}" but the framework defines "{terms[key]}"',
                    source=str(user_path),
                    remediation="use the framework term name, or choose a distinct term name",
                )
            terms[key] = name
    return terms


def _validate_teaches(entries: list[dict], terms: dict[str, str], source: Path) -> None:
    """Every `teaches` edge resolves to a defined term, by id and by name.

    Checking the name as well as the id catches the case the id alone cannot:
    a term renamed in the vocabulary leaves entries pointing at a live id with
    stale text, which then renders a competency that no longer exists under
    that wording.
    """
    for entry in entries:
        taught = entry.get("teaches", [])
        if taught is None:
            taught = []
        if not isinstance(taught, list):
            raise ExpertiseError(
                "invalid-teaches-list",
                f'entry {entry["name"]} has a non-list teaches value',
                source=str(source),
                remediation="set teaches to a list of DefinedTerm objects",
            )
        for term in taught:
            if not isinstance(term, dict):
                raise ExpertiseError(
                    "invalid-competency-reference",
                    f'entry {entry["name"]} has a non-object teaches value',
                    source=str(source),
                    remediation="make each teaches value a DefinedTerm object",
                )
            if term.get("@type") != "DefinedTerm":
                raise ExpertiseError(
                    "invalid-competency-reference",
                    f'entry {entry["name"]} teaches a value whose @type is not DefinedTerm',
                    source=str(source),
                    remediation='set each teaches value @type to "DefinedTerm"',
                )
            raw = str(term.get("@id", ""))
            if not raw.startswith(COMPETENCY_PREFIX):
                raise ExpertiseError(
                    "unqualified-competency-reference",
                    f'entry {entry["name"]} teaches {raw or "<no @id>"}, which is not a {COMPETENCY_PREFIX} id',
                    source=str(source),
                    remediation=f'reference the term as "{COMPETENCY_PREFIX}<slug-of-term-name>"',
                )
            key = raw[len(COMPETENCY_PREFIX):]
            if key not in terms:
                raise ExpertiseError(
                    "unknown-competency",
                    f'entry {entry["name"]} teaches "{key}", which no competency defines',
                    source=str(source),
                    remediation=f"add the term to expertise/{VOCABULARY}, or correct the reference",
                )
            declared = " ".join(str(term.get("name", "")).split())
            if not declared:
                raise ExpertiseError(
                    "missing-competency-name",
                    f'entry {entry["name"]} teaches "{key}" without the vocabulary display name',
                    source=str(source),
                    remediation="set teaches name to the exact competency vocabulary heading",
                )
            if declared != terms[key]:
                raise ExpertiseError(
                    "stale-competency-name",
                    f'entry {entry["name"]} names its term "{declared}" but the vocabulary defines "{terms[key]}"',
                    source=str(source),
                    remediation="update the entry's teaches name to match the vocabulary heading",
                )


def corpus_for(role: str, framework_dir: Path, user_dir: Path | None) -> list[dict]:
    """Merged corpus for one role: experience entries first, then baseline."""
    terms = vocabulary(framework_dir, user_dir)
    baseline_path = framework_dir / "expertise" / f"{role}.jsonld"
    baseline = _read(baseline_path, "baseline") if baseline_path.exists() else []
    _validate_teaches(baseline, terms, baseline_path)
    experience: list[dict] = []
    if user_dir is not None:
        user_path = user_dir / "expertise" / f"{role}.jsonld"
        if user_path.exists():
            experience = _read(user_path, "experience")
            _validate_teaches(experience, terms, user_path)
    entries = experience + baseline
    _validate_lifecycle_graph(entries, role)
    return entries


def eligible_corpus_for(role: str, framework_dir: Path, user_dir: Path | None) -> list[dict]:
    """Return only authorized effective-current entries for automatic retrieval."""
    return [entry for entry in corpus_for(role, framework_dir, user_dir) if entry["_effective_current"]]


def canonical_snapshot(
    roles: list[str] | tuple[str, ...], framework_dir: Path, user_dir: Path | None
) -> dict:
    """Return a digest-bound canonical view for projection and inspection."""
    entries: list[dict] = []
    tuples: list[dict] = []
    for role in sorted(set(roles)):
        for entry in corpus_for(role, framework_dir, user_dir):
            entries.append(entry)
            if len(entries) > 1024:
                raise ExpertiseError(
                    "expertise-corpus-too-large", "merged expertise exceeds 1024 entries",
                    source=str(framework_dir), remediation="reduce the authored expertise corpus",
                )
            tuples.append({
                "role": role,
                "source_layer": entry["_source_layer"],
                "method_layer": entry["_layer"],
                "entry_id": entry["@id"],
                "entry_digest": entry["_entry_digest"],
                "lifecycle": entry["_lifecycle"],
                "effective_current": entry["_effective_current"],
            })
    encoded = json.dumps(tuples, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema_version": 1,
        "roles": sorted(set(roles)),
        "entries": entries,
        "corpus_digest": hashlib.sha256(encoded).hexdigest(),
        "lifecycle_revision": "expertise-lifecycle-v1",
        "entry_serializer_revision": "expertise-dense-unit-v1",
    }


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

def reverse_join_problems(framework_dir: Path, roles: tuple[str, ...]) -> list[str]:
    """Disagreements between a vocabulary's `Taught by:` lists and the corpora.

    Reported rather than raised, and deliberately not wired into sync. The
    reverse listing is framework-authored prose that a user cannot break, so
    failing their sync over it would spend their time on our bookkeeping. The
    shipped corpus is checked by test instead, before release. Under ADR 0008
    this listing becomes derived, at which point the disagreement it guards
    against stops being possible.
    """
    terms = _terms(framework_dir / "expertise" / VOCABULARY)
    text = (framework_dir / "expertise" / VOCABULARY).read_text()
    taught: dict[str, list[str]] = {}
    for match in re.finditer(r"(?m)^### (.+)$", text):
        name = " ".join(match.group(1).split())
        body = text[match.end():]
        following = re.search(r"(?m)^#{2,3} ", body)
        body = body[: following.start()] if following else body
        listed = re.search(r"- Taught by:(.*?)(?=\n- |\n#|\Z)", body, re.S)
        taught[name] = [
            " ".join(title.split()) for title in re.findall(r'"([^"]+)"', listed.group(1))
        ] if listed else []
    authored: dict[str, list[str]] = {}
    for role in roles:
        for entry in corpus_for(role, framework_dir, None):
            for term in entry.get("teaches") or []:
                key = str(term.get("@id", ""))[len(COMPETENCY_PREFIX):]
                authored.setdefault(terms.get(key, key), []).append(entry["name"])
    problems = []
    for name, titles in taught.items():
        if not titles:
            problems.append(f'term "{name}" lists no entry that teaches it')
        for title in titles:
            if title not in authored.get(name, []):
                problems.append(f'term "{name}" claims entry "{title}", which does not teach it')
    for name, titles in authored.items():
        for title in titles:
            if title not in taught.get(name, []):
                problems.append(f'entry "{title}" teaches "{name}", which does not list it')
    return problems
