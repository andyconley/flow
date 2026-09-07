"""Pure archive schema, evidence ownership and effective rendering."""
from __future__ import annotations
import copy
import hashlib
import json
import re
import uuid

FIELDS = ("decision", "rationale", "applies_when", "component", "work_type", "closed_at", "mentions")
SELECTABLE_FIELDS = frozenset(FIELDS) - {"closed_at"}
EXTRACTOR_VERSION = 1
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def qualified(value):
    if not isinstance(value, dict):
        raise ValueError("qualified identity must be an object")
    source_id = value.get("source_id")
    try:
        valid_uuid = isinstance(source_id, str) and str(uuid.UUID(source_id)) == source_id
    except (ValueError, AttributeError, TypeError):
        valid_uuid = False
    if not valid_uuid:
        raise ValueError("invalid source UUID")
    work = value.get("work_id")
    if not isinstance(work, str) or not work or work in (".", "..") or "/" in work or "\\" in work:
        raise ValueError("invalid qualified work ID")
    return value["source_id"] + ":" + work


def pointer(value):
    from pathlib import PurePosixPath
    qualified(value)
    path = value.get("path")
    if not isinstance(path, str) or not path or PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts or "\\" in path:
        raise ValueError("invalid overlay-relative evidence path")
    selector = value.get("selector")
    digest_value = value.get("digest")
    if not isinstance(selector, str) or not selector or not isinstance(digest_value, str) or not SHA256_RE.fullmatch(digest_value):
        raise ValueError("evidence requires selector and SHA256 digest")
    if selector.startswith("heading:"):
        _, heading, occurrence = selector.rsplit(":", 2)
        if not heading or not occurrence.isdecimal() or int(occurrence) < 1:
            raise ValueError("invalid evidence heading selector")
    elif selector.startswith("/"):
        if any("~" in part and re.search(r"~(?![01])", part) for part in selector.split("/")[1:]):
            raise ValueError("invalid JSON pointer selector")
    else:
        raise ValueError("unsupported evidence selector")


def validate_field(field):
    if not isinstance(field, dict) or field.get("state") not in {"known", "unknown", "conflicted"}:
        raise ValueError("invalid generated field state")
    if not isinstance(field.get("sources"), list):
        raise ValueError("field sources must be an array")
    for source in field["sources"]:
        pointer(source)
    if field["state"] == "known":
        if field.get("value") is None or field.get("value") == "" or not field["sources"]:
            raise ValueError("known field requires a value and source evidence")
    elif field.get("value") is not None or not field.get("reason"):
        raise ValueError("unknown/conflicted field requires null and a reason")
    if field["state"] == "conflicted":
        if not isinstance(field.get("alternatives"), list) or len(field["alternatives"]) < 2:
            raise ValueError("conflict requires alternatives")
        for alternative in field["alternatives"]:
            validate_field(alternative)
            if alternative["state"] != "known":
                raise ValueError("conflict alternatives must be source-backed known values")


def validate_refinement(refinement):
    if refinement is None:
        return
    if not isinstance(refinement, dict) or not all(isinstance(refinement.get(k), str) and refinement[k] for k in ("revision", "actor", "reason", "base_generated_digest")) or not SHA256_RE.fullmatch(refinement["base_generated_digest"]):
        raise ValueError("refinement requires revision, actor, reason and base digest")
    if not isinstance(refinement.get("patches"), dict) or not refinement["patches"]:
        raise ValueError("refinement requires patches")
    for name, patch in refinement["patches"].items():
        if name not in {"decision", "rationale", "applies_when"}:
            raise ValueError("refinement cannot change control fields")
        validate_field(patch)


def validate_declarations(declarations, identity):
    if not isinstance(declarations, dict):
        raise ValueError("declarations must be an object")
    supersedes = declarations.get("supersedes", [])
    if not isinstance(supersedes, list):
        raise ValueError("supersedes must be an array")
    for edge in supersedes:
        if not isinstance(edge, dict) or edge.get("whole_run") is not True:
            raise ValueError("supersession requires explicit whole_run true")
        if qualified(edge.get("target")) == qualified(identity):
            raise ValueError("self supersession is invalid")
        if not isinstance(edge.get("rationale"), str) or not edge["rationale"] or not isinstance(edge.get("actor"), str) or not edge["actor"] or not isinstance(edge.get("evidence"), list) or not edge["evidence"]:
            raise ValueError("supersession requires rationale, actor and evidence")
        for source in edge["evidence"]:
            pointer(source)
    selections = declarations.get("selections", [])
    if not isinstance(selections, list):
        raise ValueError("selections must be an array")
    for selection in selections:
        if not isinstance(selection, dict) or selection.get("field") not in SELECTABLE_FIELDS or not isinstance(selection.get("actor"), str) or not selection["actor"] or not isinstance(selection.get("reason"), str) or not selection["reason"]:
            raise ValueError("invalid explicit source selection")
        pointer(selection.get("source", {}))


def declaration_digest(identity, declarations):
    validate_declarations(declarations, identity)
    edges = sorted(declarations.get("supersedes", []), key=canonical_json)
    return digest({"schema_version": 1, "identity": identity, "supersedes": edges})


def validate_envelope(value):
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int:
        raise ValueError("unsupported abstract schema; do not downgrade")
    if value["schema_version"] == 2:
        from archive_legacy_model import validate_legacy_envelope
        return validate_legacy_envelope(value)
    if value["schema_version"] != 1:
        raise ValueError("unsupported abstract schema; do not downgrade")
    if "legacy_review" in value:
        raise ValueError("legacy review requires reviewed-legacy schema 2")
    qualified(value.get("identity"))
    validate_declarations(value.get("declarations", {}), value["identity"])
    generated = value.get("generated")
    if generated is not None:
        if not isinstance(generated, dict) or type(generated.get("extractor_version")) is not int or generated.get("extractor_version") != EXTRACTOR_VERSION or not isinstance(generated.get("source_digest"), str) or not SHA256_RE.fullmatch(generated["source_digest"]):
            raise ValueError("unsupported extractor version or missing source digest")
        fields = generated.get("fields", {})
        if not isinstance(fields, dict) or set(fields) != set(FIELDS):
            raise ValueError("incomplete generated field set")
        for field in fields.values():
            validate_field(field)
    validate_refinement(value.get("refinement"))
    if not isinstance(value.get("provenance"), dict):
        raise ValueError("missing provenance")
    canonical_json(value)
    return value


def effective_view(value):
    validate_envelope(value)
    generated = value.get("generated")
    if generated is None:
        raise ValueError("abstract has controls but no generated content")
    fields = copy.deepcopy(generated["fields"])
    refinement = value.get("refinement")
    warnings = []
    state = "none"
    if refinement:
        state = "applied" if refinement["base_generated_digest"] == digest(generated) else "stale"
        if state == "applied":
            fields.update(copy.deepcopy(refinement["patches"]))
        else:
            warnings.append({"code": "stale_refinement", "old_digest": refinement["base_generated_digest"], "new_digest": digest(generated), "revision": refinement["revision"], "remedy": "preview and revalidate refinement against current generated content"})
    return {"fields": fields, "refinement_state": state, "warnings": warnings}


def render_lines(value):
    view = effective_view(value)
    labels = [("Decision", "decision"), ("Why", "rationale"), ("Applies when", "applies_when"), ("Component", "component"), ("Work type", "work_type"), ("Closed", "closed_at")]
    lines = []
    for label, name in labels:
        field = view["fields"][name]
        text = field["value"] if field["state"] == "known" else field["state"] + ": " + field["reason"]
        lines.append(label + ": " + (text if isinstance(text, str) else canonical_json(text)))
    edges = value.get("declarations", {}).get("supersedes", [])
    lines.append("Supersedes: " + (", ".join(qualified(e["target"]) for e in edges) if edges else "none declared"))
    return lines
