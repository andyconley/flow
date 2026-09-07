"""Deterministic extraction from explicitly selected final artifacts only."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
from archive_model import FIELDS, EXTRACTOR_VERSION, digest, validate_field
from archive_store import contained

HEADINGS = {
    "rationale": ("rationale", "why", "decision rationale"),
    "applies_when": ("applies when", "applicability", "conditions", "constraints"),
    "work_type": ("work type",),
    "mentions": ("mentions",),
}

DECISION_HEADINGS = {
    # Do not promote a generic "Decision" heading in an archive: Work Closed is
    # the declared final outcome authority for ordinary runs.
    "archive": ("work closed",),
    # Scout summaries have two explicitly final sections, in that order.
    "scout_summary": ("scope", "handback"),
    # A handback may be used only as the documented final-outcome fallback.
    "handback": ("outcome", "work closed"),
}
ROLE_ORDER = ("archive", "scout_summary", "handback")


def unknown(reason):
    return {"state": "unknown", "value": None, "sources": [], "reason": reason}


def known(value, source):
    return {"state": "known", "value": value, "sources": [source]}


def sections(text):
    result = []
    heading, lines, count = None, [], {}
    for line in text.splitlines() + ["# __end__"]:
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            if heading is not None:
                value = "\n".join(lines).strip()
                if value:
                    result.append((heading, count[heading], value))
            heading = match.group(1).casefold()
            count[heading] = count.get(heading, 0) + 1
            lines = []
        else:
            lines.append(line)
    return result


def _selected_path(root, raw):
    # Lifecycle artifact paths are repository-relative; pointers are overlay-relative.
    raw = str(raw)
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("unsafe declared source path")
    if path.parts and path.parts[0] == ".flow":
        path = Path(*path.parts[1:])
    return contained(root / ".flow" / path, root / ".flow")


def extract(root: Path, run: dict, source_id: str, declarations=None):
    root = Path(root).resolve()
    if run.get("state") != "archived":
        raise ValueError("only canonical archived runs can be extracted")
    work = run["work_id"]
    declarations = declarations or {}
    paths = []
    artifacts = run.get("artifacts", {})
    if not isinstance(artifacts, dict):
        raise ValueError("run artifacts must be an object")
    for role in ROLE_ORDER:
        if artifacts.get(role):
            paths.append((role, _selected_path(root, artifacts[role])))
    if not paths:
        directory = root / ".flow" / "runs" / work
        paths = [(role, contained(directory / name, root)) for role, name in (
            ("archive", "archive.md"),
            ("scout_summary", "scout-summary.md"),
            ("handback", "HANDOFF.md"),
        ) if (directory / name).exists()]
    selections = declarations.get("selections", [])
    resolved_selections = []
    for selection in selections:
        source = selection["source"]
        if source["source_id"] != source_id:
            raise ValueError("cross-overlay derivation requires a local declared artifact")
        path = _selected_path(root, source["path"])
        resolved_selections.append((selection, verify_pointer(root, source)))
        if path not in {item[1] for item in paths}:
            paths.append(("explicit", path))
    if not paths:
        raise ValueError("no usable final-outcome source; declare an archive/handback artifact then backfill")
    documents = []
    for role, path in paths:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        if not text.strip():
            raise ValueError("empty final-outcome source: " + str(path))
        documents.append((role, path, hashlib.sha256(raw).hexdigest(), sections(text)))
    identity = {"source_id": source_id, "work_id": work}
    def source_for(path, content_digest, selector):
        return {**identity, "path": path.relative_to(root / ".flow").as_posix(), "selector": selector, "digest": content_digest}
    fields = {name: unknown("not stated in the selected final source") for name in FIELDS}
    decision_documents = []
    decision_headings = set()
    for role in ROLE_ORDER:
        for expected_heading in DECISION_HEADINGS[role]:
            candidates = []
            for doc_role, path, sha, parsed in documents:
                if doc_role != role:
                    continue
                for heading, occurrence, text in parsed:
                    if heading == expected_heading:
                        candidates.append((path, sha, heading, occurrence, text))
            if candidates:
                decision_documents = {candidate[0] for candidate in candidates}
                decision_headings = {(candidate[0], candidate[2]) for candidate in candidates}
                break
        if decision_documents:
            break

    for name, headings in {"decision": (), **HEADINGS}.items():
        matches = []
        explicit = [s for s in selections if s["field"] == name]
        for role, path, sha, parsed in documents:
            for heading, occurrence, text in parsed:
                selector = f"heading:{heading}:{occurrence}"
                pointer = source_for(path, sha, selector)
                if explicit:
                    if not any(s["source"] == pointer for s in explicit):
                        continue
                elif name == "decision":
                    if (path, heading) not in decision_headings:
                        continue
                elif heading not in headings or path not in decision_documents:
                    continue
                matches.append(known(text, pointer))
        values = {m["value"] for m in matches}
        if len(values) == 1:
            fields[name] = {**matches[0], "sources": [m["sources"][0] for m in matches]}
        elif len(values) > 1:
            fields[name] = {"state": "conflicted", "value": None, "sources": [m["sources"][0] for m in matches], "reason": "multiple selected passages differ; explicit source selection required", "alternatives": matches}
    # An explicit selection is an authority input, never a hint that may be
    # silently dropped because the source used JSON rather than a heading. The
    # selected value is exactly the verified selector result; a declaration
    # cannot smuggle a separately authored replacement into generated content.
    for name in FIELDS:
        if name == "component":
            continue
        selected = [(selection["source"], selected_value) for selection, selected_value in resolved_selections if selection["field"] == name]
        if not selected:
            continue
        values = {canonical_value(value) for _, value in selected}
        candidates = [known(value, pointer) for pointer, value in selected]
        if len(values) == 1:
            fields[name] = {**candidates[0], "sources": [candidate["sources"][0] for candidate in candidates]}
        else:
            fields[name] = {"state": "conflicted", "value": None, "sources": [candidate["sources"][0] for candidate in candidates], "reason": "multiple explicitly selected passages differ", "alternatives": candidates}
    if fields["decision"]["state"] == "unknown":
        raise ValueError("selected final source has no decision/outcome heading; add source-backed final outcome before backfill")
    run_path = contained(root / ".flow" / "runs" / work / "run.json", root)
    run_sha = hashlib.sha256(run_path.read_bytes()).hexdigest()
    for event in ("archive", "archive-scout"):
        if run.get("gates", {}).get(event):
            fields["closed_at"] = known(run["gates"][event], source_for(run_path, run_sha, "/gates/" + event))
            break
    for selection in selections:
        if selection["field"] == "component":
            pointer = selection["source"]
            path = _selected_path(root, pointer["path"])
            if hashlib.sha256(path.read_bytes()).hexdigest() != pointer["digest"]:
                raise ValueError("component source evidence changed")
            component = selection.get("value")
            catalog = json.loads(contained(root / ".flow" / "components.json", root).read_text())
            if catalog.get("schema_version") != 1 or not isinstance(component, dict) or component.get("source_id") != source_id:
                raise ValueError("invalid component authority")
            entries = [c for c in catalog.get("components", []) if c.get("component_id") == component.get("component_id")]
            if len(entries) != 1:
                raise ValueError("component is not declared unambiguously in components.json")
            fields["component"] = known({"source_id": source_id, **entries[0]}, pointer)
    for field in fields.values():
        validate_field(field)
    # Include actual selected file content and lifecycle closure evidence, not operational clocks.
    inputs = {"sources": [(path.relative_to(root / '.flow').as_posix(), sha) for _, path, sha, _ in documents], "closed_at": fields["closed_at"], "declarations": declarations}
    return {"extractor_version": EXTRACTOR_VERSION, "source_digest": digest(inputs), "fields": fields}


def canonical_value(value):
    """Set-friendly comparison that retains JSON's typed equality semantics."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def verify_pointer(root, pointer):
    """Resolve an evidence selector against the exact cited local file bytes."""
    from archive_model import pointer as validate_pointer
    validate_pointer(pointer)
    path = _selected_path(Path(root).resolve(), pointer["path"])
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pointer["digest"]:
        raise ValueError("evidence digest mismatch")
    selector = pointer["selector"]
    if isinstance(selector, str) and selector.startswith("heading:"):
        _, heading, occurrence = selector.rsplit(":", 2)
        matches = [text for title, number, text in sections(raw.decode("utf-8")) if title == heading and str(number) == occurrence]
        if len(matches) != 1:
            raise ValueError("evidence heading selector does not resolve")
        return matches[0]
    if isinstance(selector, str) and selector.startswith("/"):
        value = json.loads(raw)
        for part in selector[1:].split("/"):
            key = part.replace("~1", "/").replace("~0", "~")
            value = value[int(key)] if isinstance(value, list) else value[key]
        return value
    raise ValueError("unsupported evidence selector")


def _selected_field(root, pointers):
    """Build a field from verified selections without synthesizing source text."""
    matches = [known(verify_pointer(root, source), source) for source in pointers]
    if not matches:
        return unknown("not stated in the selected final source")
    if len({canonical_value(match["value"]) for match in matches}) == 1:
        return {**matches[0], "sources": [match["sources"][0] for match in matches]}
    return {"state": "conflicted", "value": None, "sources": [match["sources"][0] for match in matches],
            "reason": "multiple selected passages differ; explicit source selection required", "alternatives": matches}


def extract_legacy(root, review, source_id):
    """Extract from reviewer-selected final evidence, without a canonical run.

    Eligibility is the review adapter's responsibility. Source resolution, text
    section parsing, field validation and deterministic encoding are shared with
    canonical extraction. No fabricated lifecycle object enters extract().
    """
    root = Path(root).resolve()
    if review["identity"]["source_id"] != source_id:
        raise ValueError("legacy review is outside owning source")
    pointers = review["selected_final_outcome_sources"]
    fields = {name: unknown("not stated in the selected final source") for name in FIELDS}
    fields["decision"] = _selected_field(root, pointers)
    documents = {}
    for source in pointers:
        path = _selected_path(root, source["path"])
        raw = path.read_bytes()
        documents[source["path"]] = (hashlib.sha256(raw).hexdigest(), sections(raw.decode("utf-8")))
    for name, headings in HEADINGS.items():
        selected = []
        for path, (sha, parsed) in documents.items():
            for heading, occurrence, text in parsed:
                if heading in headings:
                    selected.append({**review["identity"], "path": path, "digest": sha,
                                     "selector": f"heading:{heading}:{occurrence}"})
        fields[name] = _selected_field(root, selected)
    selections = review.get("field_selections", [])
    for name in FIELDS:
        selected = [s for s in selections if s["field"] == name]
        if not selected:
            continue
        if name == "component":
            if len(selected) != 1:
                raise ValueError("component requires one explicit selection")
            selection = selected[0]
            verify_pointer(root, selection["source"])
            value = selection.get("value")
            catalog = json.loads(contained(root / ".flow" / "components.json", root).read_text())
            if catalog.get("schema_version") != 1 or not isinstance(value, dict) or value.get("source_id") != source_id:
                raise ValueError("invalid component authority")
            entries = [entry for entry in catalog.get("components", []) if entry.get("component_id") == value.get("component_id")]
            if len(entries) != 1:
                raise ValueError("component is not declared unambiguously in components.json")
            fields[name] = known({"source_id": source_id, **entries[0]}, selection["source"])
        else:
            fields[name] = _selected_field(root, [s["source"] for s in selected])
    closed = review.get("closed_at", {"state": "unknown"})
    if closed["state"] == "known":
        verify_pointer(root, closed["source"])
        fields["closed_at"] = known(closed["value"], closed["source"])
    else:
        fields["closed_at"] = unknown("historical closure date was not established by the review; review time is not closure time")
    for field in fields.values():
        validate_field(field)
    return {"extractor_version": EXTRACTOR_VERSION,
            "source_digest": digest({"identity": review["identity"], "documents": documents,
                                     "selections": selections, "closed_at": closed, "final_sources": pointers}),
            "fields": fields}
