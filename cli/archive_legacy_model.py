"""Pure schema and state rules for reviewed legacy archive authority."""
from __future__ import annotations

from datetime import datetime
import copy
import re
import uuid

from archive_model import (EXTRACTOR_VERSION, FIELDS, SELECTABLE_FIELDS, SHA256_RE,
    canonical_json, digest, pointer, qualified, validate_declarations, validate_field, validate_refinement)

ACTION_DISPOSITIONS = {
    "approve": "approved", "reapprove": "approved", "reject": "rejected",
    "unresolved": "unresolved", "withdraw": "withdrawn",
}
POSITIVE_ACTIONS = frozenset(("approve", "reapprove"))
NEGATIVE_ACTIONS = frozenset(("reject", "unresolved", "withdraw"))


def _time(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value):
        raise ValueError(label + " requires an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(label + " requires an RFC3339 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(label + " requires a timezone")


def _uuid(value, label):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("invalid " + label) from error


def _action_id(value):
    if not isinstance(value, str) or not value:
        raise ValueError("invalid legacy action ID")


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " is required")


def _bound_pointer(value, identity):
    pointer(value)
    if value.get("source_id") != identity["source_id"] or value.get("work_id") != identity["work_id"]:
        raise ValueError("legacy evidence must bind the reviewed candidate")


def _evidence(value, identity):
    if not isinstance(value, dict):
        raise ValueError("legacy evidence must be an object")
    if not isinstance(value.get("kind"), str) or value["kind"] not in {"local", "external_capture"}:
        raise ValueError("legacy evidence kind is invalid")
    if not isinstance(value.get("role"), str) or value["role"] not in {"final_outcome", "closure_evidence"}:
        raise ValueError("legacy evidence role is invalid")
    _bound_pointer(value.get("source", {}), identity)
    _text(value.get("explanation"), "legacy evidence explanation")
    if value["kind"] == "external_capture":
        _text(value.get("url"), "external capture URL")
        _time(value.get("captured_at"), "external capture")
        if "source_identifier" in value and (not isinstance(value["source_identifier"], str) or not value["source_identifier"]):
            raise ValueError("external capture source identifier must be a nonempty string")
    elif any(key in value for key in ("url", "captured_at", "source_identifier")):
        raise ValueError("local evidence cannot carry external capture metadata")
    if set(value) - {"kind", "role", "source", "explanation", "url", "captured_at", "source_identifier"}:
        raise ValueError("unknown legacy evidence field")


def _closed_at(value, identity, closure_sources):
    if not isinstance(value, dict) or not isinstance(value.get("state"), str) or value["state"] not in {"known", "unknown"}:
        raise ValueError("historical closed_at must be known or unknown")
    if value["state"] == "known":
        _time(value.get("value"), "historical closed_at")
        _bound_pointer(value.get("source", {}), identity)
        if canonical_json(value["source"]) not in closure_sources:
            raise ValueError("historical closed_at source must be closure evidence")
    elif value.get("value") is not None or "source" in value:
        raise ValueError("unknown historical closed_at cannot carry a value or source")


def _review_fields(value, *, persisted):
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise ValueError("unsupported legacy review schema")
    identity = value.get("identity")
    qualified(identity)
    _action_id(value.get("action_id"))
    action = value.get("action")
    if not isinstance(action, str) or action not in ACTION_DISPOSITIONS:
        raise ValueError("unsupported legacy review action")
    _text(value.get("reviewer"), "reviewer")
    author_relationship = value.get("reviewer_is_author")
    if not (type(author_relationship) is bool or author_relationship == "unknown"):
        raise ValueError("reviewer_is_author must be true, false or unknown")
    _text(value.get("reason"), "review reason")
    base = value.get("expected_base_fingerprint")
    if not isinstance(base, str) or not SHA256_RE.fullmatch(base):
        raise ValueError("review requires expected base fingerprint")
    evidence = value.get("evidence", [])
    if not isinstance(evidence, list):
        raise ValueError("review evidence must be an array")
    for item in evidence:
        _evidence(item, identity)
    closure_sources = {canonical_json(item["source"]) for item in evidence if item["role"] == "closure_evidence"}
    _closed_at(value.get("closed_at"), identity, closure_sources)
    selected = value.get("selected_final_outcome_sources", [])
    if not isinstance(selected, list):
        raise ValueError("selected final outcome sources must be an array")
    for source in selected:
        _bound_pointer(source, identity)
    encoded = {canonical_json(item) for item in selected}
    if len(encoded) != len(selected):
        raise ValueError("selected final outcome sources must be unique")
    final_sources = {canonical_json(item["source"]) for item in evidence if item["role"] == "final_outcome"}
    if any(canonical_json(source) not in final_sources for source in selected):
        raise ValueError("selected final outcome source lacks final-outcome evidence")
    if action in POSITIVE_ACTIONS:
        _text(value.get("closure_assertion"), "closure assertion")
        if not selected or not final_sources or not any(item["role"] == "closure_evidence" for item in evidence):
            raise ValueError("approval requires selected final outcome and closure evidence")
    elif value.get("closure_assertion") is not None and value.get("closure_assertion") != "":
        raise ValueError("negative review action cannot assert closure")
    if persisted and action == "withdraw" and value.get("previous_revision_digest") in {None, ""}:
        raise ValueError("withdraw requires a previous approved review")
    selections = value.get("field_selections", [])
    if not isinstance(selections, list):
        raise ValueError("field selections must be an array")
    for selection in selections:
        if not isinstance(selection, dict) or not isinstance(selection.get("field"), str) or selection["field"] not in SELECTABLE_FIELDS:
            raise ValueError("invalid legacy field selection")
        _bound_pointer(selection.get("source", {}), identity)
        if canonical_json(selection["source"]) not in final_sources:
            raise ValueError("legacy field selection must use final-outcome evidence")
        _text(selection.get("reason"), "legacy field selection reason")
    allowed = {"schema_version", "identity", "action_id", "action", "reviewer", "reviewer_is_author", "reason", "expected_base_fingerprint", "closed_at", "evidence", "selected_final_outcome_sources", "field_selections", "closure_assertion", "previous_revision_digest"}
    if persisted:
        allowed |= {"recorded_at", "review_id", "semantic_payload_digest", "revision_digest"}
        _time(value.get("recorded_at"), "review recorded_at")
        _uuid(value.get("review_id"), "legacy review ID")
        for name in ("semantic_payload_digest", "revision_digest"):
            if not isinstance(value.get(name), str) or not SHA256_RE.fullmatch(value[name]):
                raise ValueError("review requires " + name)
    if set(value) - allowed:
        raise ValueError("unknown legacy review field")
    return identity


def semantic_payload(value):
    copied = copy.deepcopy(value)
    copied.setdefault("evidence", [])
    copied.setdefault("selected_final_outcome_sources", [])
    copied.setdefault("field_selections", [])
    for name in ("recorded_at", "review_id", "previous_revision_digest", "semantic_payload_digest", "revision_digest"):
        copied.pop(name, None)
    return copied


def validate_review(value, *, persisted=False):
    _review_fields(value, persisted=persisted)
    if persisted:
        if value["semantic_payload_digest"] != digest(semantic_payload(value)):
            raise ValueError("legacy review semantic payload digest mismatch")
        copied = copy.deepcopy(value)
        supplied = copied.pop("revision_digest")
        if supplied != digest(copied):
            raise ValueError("legacy review revision digest mismatch")
    return value


def make_review(request, *, review_id, previous_revision_digest, recorded_at):
    value = copy.deepcopy(request)
    value.setdefault("evidence", [])
    value.setdefault("selected_final_outcome_sources", [])
    value.setdefault("field_selections", [])
    value.update({"recorded_at": recorded_at, "review_id": review_id,
                  "previous_revision_digest": previous_revision_digest})
    value["semantic_payload_digest"] = digest(semantic_payload(value))
    value["revision_digest"] = digest(value)
    validate_review(value, persisted=True)
    return value


def validate_chain(current, history):
    """Validate current to genesis and return oldest-first immutable revisions."""
    validate_review(current, persisted=True)
    if not isinstance(history, dict):
        raise ValueError("legacy review history must be a mapping")
    chain, seen, review_id = [], set(), current["review_id"]
    value = current
    while True:
        revision = value["revision_digest"]
        if revision in seen:
            raise ValueError("legacy review history cycle")
        seen.add(revision)
        if value["review_id"] != review_id:
            raise ValueError("legacy review history changed review ID")
        if value["identity"] != current["identity"]:
            raise ValueError("legacy review history changed identity")
        chain.append(value)
        previous = value.get("previous_revision_digest")
        if previous is None:
            break
        if not isinstance(previous, str) or not SHA256_RE.fullmatch(previous) or previous not in history:
            raise ValueError("legacy review history is incomplete")
        value = history[previous]
        validate_review(value, persisted=True)
        if value["revision_digest"] != previous:
            raise ValueError("legacy review history digest mismatch")
    actions = [item["action_id"] for item in chain]
    if len(actions) != len(set(actions)):
        raise ValueError("legacy review action IDs must be unique")
    ordered = list(reversed(chain))
    previous_action = None
    for item in ordered:
        action = item["action"]
        if previous_action is None and action not in {"approve", "reject", "unresolved"}:
            raise ValueError("invalid genesis review action")
        if previous_action is not None and action == "approve":
            raise ValueError("approve is genesis only")
        if action == "withdraw" and previous_action not in POSITIVE_ACTIONS:
            raise ValueError("withdraw requires a prior approved review")
        previous_action = action
    return ordered


def effective_disposition(review, evidence_condition="valid"):
    validate_review(review, persisted=True)
    return ACTION_DISPOSITIONS[review["action"]]


def validate_legacy_envelope(value, *, validate_generated=True):
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 2:
        raise ValueError("unsupported reviewed legacy envelope schema")
    identity = value.get("identity")
    qualified(identity)
    provenance = value.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("origin") != "reviewed_legacy":
        raise ValueError("schema 2 envelope requires reviewed_legacy provenance")
    declarations = value.get("declarations", {})
    validate_declarations(declarations, identity)
    if declarations.get("supersedes"):
        raise ValueError("reviewed legacy cannot declare outgoing supersession")
    review = value.get("legacy_review")
    validate_review(review, persisted=True)
    if review["identity"] != identity:
        raise ValueError("legacy review identity mismatch")
    generated = value.get("generated")
    if generated is not None and validate_generated:
        if not isinstance(generated, dict) or generated.get("extractor_version") != EXTRACTOR_VERSION or not isinstance(generated.get("source_digest"), str) or not SHA256_RE.fullmatch(generated["source_digest"]):
            raise ValueError("unsupported extractor version or missing source digest")
        if not isinstance(generated.get("fields"), dict) or set(generated["fields"]) != set(FIELDS):
            raise ValueError("incomplete generated field set")
        for field in generated["fields"].values():
            validate_field(field)
    if validate_generated:
        validate_refinement(value.get("refinement"))
    if set(value) - {"schema_version", "identity", "declarations", "legacy_review", "generated", "refinement", "provenance"}:
        raise ValueError("unknown reviewed legacy envelope field")
    canonical_json(value)
    return value
