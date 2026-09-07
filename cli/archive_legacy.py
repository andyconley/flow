"""Reviewed-legacy observation, review publication, and generated-content repair."""
from __future__ import annotations

from datetime import datetime, timezone
import copy
import json
import os
from pathlib import Path
import uuid

from archive_legacy_model import (ACTION_DISPOSITIONS, POSITIVE_ACTIONS, effective_disposition,
    make_review, semantic_payload, validate_chain, validate_legacy_envelope, validate_review)
from archive_model import canonical_json, digest, qualified
from archive_store import (ArchiveError, atomic_write, contained, encode, envelope_path,
    file_digest, read_identity, writer_lock, write_envelope)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _path(root, work, relative):
    directory = envelope_path(root, work).parent  # validates work ID before joining
    return contained(directory / relative, root)


def _result(observation, *, state="preview", review_commit=None, replayed=False,
            abstract=None, index=None, coverage=None, action_revision=None):
    review = observation.get("review")
    return {
        "state": state, "work_id": observation.get("work_id"),
        "qualified_id": observation.get("qualified_id"),
        "fingerprint": observation.get("fingerprint"),
        "review_commit": review_commit, "replayed": replayed,
        "action_revision": action_revision if action_revision is not None else (review.get("revision_digest") if review else None),
        "current_revision": review.get("revision_digest") if review else None,
        "effective_disposition": observation.get("effective_disposition"),
        "evidence_condition": observation.get("evidence_condition"),
        "diagnostics": observation.get("diagnostics", []),
        "abstract": abstract or {"state": "not_needed"},
        "index": index or {"state": "not_needed"},
        "coverage": coverage or {"state": "not_needed"},
    }


def _file(root, path, files):
    relative = path.relative_to(Path(root)).as_posix()
    files[relative] = file_digest(path)
    return files[relative]


def _failure(work_id, error, *, unavailable=False, review_commit=None, observation=None):
    """Keep the operation contract intact when validation or storage fails."""
    result = _result(observation or {"work_id": work_id},
                     state="unavailable" if unavailable else "invalid_request",
                     review_commit=review_commit)
    result.update(reason=str(error), remedy=(
        "restore accessible local storage and retry the original request" if unavailable
        else "correct the request or preview the current evidence and base"))
    return result


def _read_history(root, work, files, current):
    """Read only the reachable chain. Orphan files can never supply authority."""
    history, seen = {}, set()
    previous = current.get("previous_revision_digest")
    while previous is not None:
        if not isinstance(previous, str) or len(previous) != 64 or any(c not in "0123456789abcdef" for c in previous):
            raise ArchiveError("invalid legacy predecessor digest")
        if previous in seen:
            raise ArchiveError("legacy review history cycle")
        seen.add(previous)
        path = _path(root, work, "abstract-history/reviews/" + previous + ".json")
        _file(root, path, files)
        value = json.loads(path.read_text())
        validate_review(value, persisted=True)
        if value["revision_digest"] != previous:
            raise ArchiveError("legacy review history filename mismatch")
        history[previous] = value
        previous = value.get("previous_revision_digest")
    return history


def _evidence_condition(root, review, files):
    if review is None:
        return "valid", []
    diagnostics = []
    from archive_extract import verify_pointer
    for evidence in review.get("evidence", []):
        source = evidence["source"]
        key = ".flow/" + source["path"]
        try:
            path = contained(Path(root) / ".flow" / source["path"], root)
            _file(root, path, files)
            verify_pointer(root, source)
        except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
            files.setdefault(key, "unreadable")
            diagnostics.append({"code": "evidence_stale", "path": source["path"], "detail": str(error),
                                "remedy": "restore exact evidence bytes or submit reapproval with current evidence"})
    return ("evidence_stale" if diagnostics else "valid"), diagnostics


def observe(root, work, record=None):
    """Read every authority input without creating identity, cache, or lock files."""
    root = Path(root).resolve()
    files, diagnostics = {}, []
    directory = _path(root, work, "")
    if not directory.exists() or not directory.is_dir():
        return {"work_id": work, "candidate_state": "missing", "eligible": False, "files": files,
                "diagnostics": [{"code": "candidate_missing", "remedy": "select an existing run folder"}]}
    run_path = _path(root, work, "run.json")
    _file(root, run_path, files)
    if run_path.exists():
        return {"work_id": work, "candidate_state": "canonical_collision", "eligible": False, "files": files,
                "diagnostics": [{"code": "canonical_collision", "remedy": "repair or reconcile canonical lifecycle evidence; legacy import is unavailable"}]}
    try:
        source_id = read_identity(root)
    except (OSError, ValueError) as error:
        return {"work_id": work, "candidate_state": "identity_unavailable", "eligible": False, "files": files,
                "diagnostics": [{"code": "identity_unavailable", "detail": str(error), "remedy": "restore overlay identity before import"}]}
    identity = {"source_id": source_id, "work_id": work}
    _file(root, contained(root / ".flow" / "identity.json", root), files)
    path = envelope_path(root, work)
    _file(root, path, files)
    envelope = review = None
    chain = []
    try:
        if path.exists():
            envelope = json.loads(path.read_text())
            validate_legacy_envelope(envelope, validate_generated=False)
            if envelope["identity"] != identity:
                raise ArchiveError("reviewed legacy envelope identity mismatch")
            review = envelope["legacy_review"]
            history = _read_history(root, work, files, review)
            chain = validate_chain(review, history)
        else:
            history = {}
        evidence_condition, evidence_diagnostics = _evidence_condition(root, review, files)
        diagnostics.extend(evidence_diagnostics)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {"work_id": work, "qualified_id": qualified(identity), "identity": identity,
                "candidate_state": "invalid_review", "eligible": False, "files": files,
                "diagnostics": [{"code": "invalid_review", "detail": str(error), "remedy": "restore current control and complete history before review or rescan"}]}
    value = {"identity": identity, "current": review, "history": [item["revision_digest"] for item in chain],
             "files": files}
    fingerprint = digest(value)
    return {"work_id": work, "qualified_id": qualified(identity), "identity": identity,
            "candidate_state": "reviewed" if review else "legacy_awaiting_review",
            "envelope": envelope, "review": review, "chain": chain, "history": history,
            "files": files, "fingerprint": fingerprint, "evidence_condition": evidence_condition,
            "action_disposition": ACTION_DISPOSITIONS[review["action"]] if review else "awaiting_review",
            "effective_disposition": effective_disposition(review, evidence_condition) if review else "awaiting_review",
            "eligible": bool(review and effective_disposition(review, evidence_condition) == "approved" and evidence_condition == "valid"),
            "diagnostics": diagnostics}


def _preview_row(root, work):
    observation = observe(root, work)
    available, diagnostics = [], []
    directory = envelope_path(root, work).parent
    if directory.exists() and observation.get("candidate_state") not in {"canonical_collision", "identity_unavailable"}:
        from archive_extract import sections
        for candidate in sorted(directory.rglob("*")):
            if "abstract-history" in candidate.relative_to(directory).parts:
                continue
            if candidate.name in {"abstract.json", "run.json", "events.jsonl"} or candidate.suffix.lower() not in {".md", ".txt", ".json"}:
                continue
            try:
                candidate = contained(candidate, root)
                if not candidate.is_file():
                    continue
                raw = candidate.read_bytes()
                import hashlib
                available.append({"path": candidate.relative_to(Path(root) / ".flow").as_posix(),
                                  "digest": hashlib.sha256(raw).hexdigest(),
                                  "selectors": [f"heading:{title}:{number}" for title, number, _ in sections(raw.decode("utf-8"))],
                                  "status": "available_unreviewed_source"})
            except (OSError, ValueError, UnicodeError) as error:
                diagnostics.append({"code": "candidate_source_unreadable", "path": candidate.name, "detail": str(error)})
    roles = {e["role"] for e in (observation.get("review") or {}).get("evidence", [])}
    observation.update(available_evidence=available, missing_evidence_roles=sorted({"final_outcome", "closure_evidence"} - roles))
    observation["diagnostics"] = observation.get("diagnostics", []) + diagnostics
    return observation


def preview(root, work_id=None):
    root = Path(root).resolve()
    if work_id is not None:
        return {"state": "preview", "runs": [_preview_row(root, work_id)]}
    directory = contained(root / ".flow" / "runs", root)
    runs = [] if not directory.exists() else [_preview_row(root, path.name) for path in sorted(directory.iterdir()) if path.is_dir()]
    return {"state": "preview", "runs": runs}


def _load_record(record):
    if isinstance(record, dict):
        return copy.deepcopy(record)
    return json.loads(Path(record).read_text())


def _verify_positive_evidence(root, request):
    if request["action"] not in POSITIVE_ACTIONS:
        return
    from archive_extract import verify_pointer
    for evidence in request["evidence"]:
        verify_pointer(root, evidence["source"])


def _confirm_current(root, work_id, expected_revision):
    """Confirm file and containing directory durability for an explicit replay."""
    path = envelope_path(root, work_id)
    for target in (path, path.parent):
        descriptor = os.open(target, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    observed = observe(root, work_id)
    if (observed.get("review") or {}).get("revision_digest") != expected_revision:
        raise ArchiveError("current review changed while confirming durability; retry")
    return observed


def _new_envelope(observation, review):
    prior = observation.get("envelope") or {}
    selections = []
    for selection in review.get("field_selections", []):
        selections.append({"field": selection["field"], "source": selection["source"],
                           "actor": review["reviewer"], "reason": selection["reason"]})
    return {"schema_version": 2, "identity": observation["identity"],
            "declarations": {"supersedes": [], "selections": selections},
            "legacy_review": review, "generated": prior.get("generated"),
            "refinement": prior.get("refinement"),
            "provenance": {"origin": "reviewed_legacy", "created_at": prior.get("provenance", {}).get("created_at", _now()),
                           "last_action": review["action"], "generated_at": prior.get("provenance", {}).get("generated_at")}}


def _action_allowed(current, action):
    if current is None:
        if action not in {"approve", "reject", "unresolved"}:
            raise ArchiveError("first legacy review must approve, reject, or unresolved")
        return
    current_disposition = ACTION_DISPOSITIONS[current["action"]]
    if action == "approve":
        raise ArchiveError("approve is genesis only; use reapprove after a prior decision")
    if action == "reapprove" and current_disposition not in {"approved", "rejected", "unresolved", "withdrawn"}:
        raise ArchiveError("reapprove requires a prior decision")
    if action == "withdraw" and current_disposition != "approved":
        raise ArchiveError("withdraw requires a prior approved review")


def _find_action(chain, action_id):
    return next((item for item in chain if item["action_id"] == action_id), None)


def _publish_review(root, observation, updated):
    work = observation["work_id"]
    current = observation.get("review")
    if current:
        history_path = _path(root, work, "abstract-history/reviews/" + current["revision_digest"] + ".json")
        if history_path.exists() and history_path.read_bytes() != encode(current):
            raise ArchiveError("immutable legacy review history mismatch")
        if not history_path.exists():
            atomic_write(history_path, encode(current), root)
    path = envelope_path(root, work)
    current_observation = observe(root, work)
    if current_observation.get("fingerprint") != observation["fingerprint"]:
        raise ArchiveError("archive inputs changed during preservation; preview again")
    _verify_positive_evidence(root, updated["legacy_review"])
    atomic_write(path, encode(updated), root)


def _derived_outcomes(root, work):
    coverage = {"state": "skipped", "reason": "legacy coverage integration unavailable"}
    index = {"state": "skipped", "reason": "legacy projection integration unavailable"}
    try:
        from archive_service import refresh_coverage
        from archive_store import ensure_ignore
        with writer_lock(root):
            ensure_ignore(root)
            refresh_coverage(root, work)
        coverage = {"state": "completed"}
    except ImportError:
        pass
    except Exception as error:  # post-commit derived work never rolls back authority
        coverage = {"state": "failed", "reason": str(error), "remedy": "rerun flow archive import rescan"}
    try:
        from archive_query import rebuild
        from archive_store import cache_dir
        if not (cache_dir(root) / "index.sqlite3").exists():
            index = {"state": "skipped", "reason": "no established projection; run flow index rebuild"}
        else:
            index_result = rebuild(root, incremental=True, coverage_work_id=work)
            index = {"state": "completed" if index_result.get("state") == "complete" else "failed", "detail": index_result}
    except ImportError:
        pass
    except Exception as error:
        index = {"state": "failed", "reason": str(error), "remedy": "run flow index rebuild"}
    return index, coverage


def _usable(observation):
    return observation.get("candidate_state") not in {"canonical_collision", "identity_unavailable", "invalid_review", "missing"}


def _replayed(observation, request):
    prior = _find_action(observation.get("chain", []), request["action_id"])
    if prior and prior["semantic_payload_digest"] != digest(semantic_payload(request)):
        raise ArchiveError("legacy action ID was reused with a different semantic payload")
    return prior


def review(root, work_id, record_path, apply=False, yes=False):
    root = Path(root).resolve()
    try:
        request = _load_record(record_path)
        validate_review(request, persisted=False)
        observation = observe(root, work_id)
        if not _usable(observation):
            return _result(observation, state="unavailable", review_commit="not_committed" if apply else None)
        if request["identity"] != observation["identity"]:
            raise ArchiveError("review record identity does not match candidate")
        replay = _replayed(observation, request)
        if not apply:
            if not replay:
                if request["expected_base_fingerprint"] != observation["fingerprint"]:
                    raise ArchiveError("stale consent; preview the current base")
                _action_allowed(observation.get("review"), request["action"])
                _verify_positive_evidence(root, request)
            return _result(observation, replayed=bool(replay), action_revision=replay["revision_digest"] if replay else None)
        if not yes:
            raise ArchiveError("writes require --apply --yes")
        with writer_lock(root):
            locked_request = _load_record(record_path)
            validate_review(locked_request, persisted=False)
            if semantic_payload(locked_request) != semantic_payload(request):
                raise ArchiveError("stale consent; review record changed while acquiring the writer lock; validate the current request again")
            request = locked_request
            locked = observe(root, work_id)
            if not _usable(locked) or locked.get("identity") != request["identity"]:
                return _result(locked, state="unavailable", review_commit="not_committed")
            replay = _replayed(locked, request)
            if replay:
                try:
                    confirmed = _confirm_current(root, work_id, locked["review"]["revision_digest"])
                except (OSError, ValueError) as error:
                    return _result(locked, state="unavailable", review_commit="uncertain", replayed=True,
                                   action_revision=replay["revision_digest"], abstract={"state": "not_needed"},
                                   index={"state": "skipped", "reason": str(error), "remedy": "retry the same action ID to confirm current directory durability"})
                return _result(confirmed, state="complete", review_commit="committed", replayed=True,
                               action_revision=replay["revision_digest"])
            if locked.get("fingerprint") != request["expected_base_fingerprint"]:
                raise ArchiveError("stale consent; preview the current base")
            _action_allowed(locked.get("review"), request["action"])
            _verify_positive_evidence(root, request)
            updated_review = make_review(request, review_id=(locked["review"] or {}).get("review_id", str(uuid.uuid4())),
                                         previous_revision_digest=(locked["review"] or {}).get("revision_digest"), recorded_at=_now())
            updated = _new_envelope(locked, updated_review)
            generation_error = None
            if updated_review["action"] in POSITIVE_ACTIONS:
                try:
                    from archive_extract import extract_legacy
                    updated["generated"] = extract_legacy(root, updated_review, locked["identity"]["source_id"])
                    updated["provenance"]["generated_at"] = _now()
                except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
                    generation_error = str(error)
                    updated["generated"] = None  # never reuse earlier prose for a new review
            validate_legacy_envelope(updated, validate_generated=False)
            try:
                _publish_review(root, locked, updated)
            except OSError as error:
                try:
                    after = observe(root, work_id)
                except (OSError, ValueError):
                    return _result({"work_id": work_id, "diagnostics": [{
                        "code": "publication_readback_unavailable", "detail": str(error),
                        "remedy": "retain the original action ID and retry; publication could not be confirmed"}]},
                        state="unavailable", review_commit="uncertain",
                        action_revision=updated_review["revision_digest"],
                        abstract={"state": "uncertain"})
                if after.get("fingerprint") != locked["fingerprint"]:
                    return _result(after, state="unavailable", review_commit="uncertain",
                                   action_revision=updated_review["revision_digest"],
                                   abstract={"state": "uncertain", "reason": str(error), "remedy": "retry the same action ID; do not roll back"})
                raise
        try:
            after = observe(root, work_id)
        except (OSError, ValueError) as error:
            return _result({"work_id": work_id, "diagnostics": [{
                "code": "post_commit_read_unavailable", "detail": str(error),
                "remedy": "inspect current authority and retry the original action"}]},
                state="unavailable", review_commit="committed",
                action_revision=updated_review["revision_digest"],
                abstract={"state": "failed" if generation_error else "committed"},
                index={"state": "skipped", "reason": "current authority unavailable"},
                coverage={"state": "skipped", "reason": "current authority unavailable"})
        index, coverage = _derived_outcomes(root, work_id)
        abstract = {"state": "failed", "reason": generation_error, "remedy": "run flow archive import rescan " + work_id} if generation_error else {"state": "committed"}
        partial = generation_error is not None or any(item.get("state") == "failed" for item in (index, coverage))
        return _result(after, state="partial" if partial else "complete", review_commit="committed",
                       action_revision=updated_review["revision_digest"],
                       abstract=abstract, index=index, coverage=coverage)
    except OSError as error:
        return _failure(work_id, error, unavailable=True, review_commit="not_committed" if apply else None)
    except (ValueError, KeyError, TypeError, IndexError) as error:
        return _failure(work_id, error, review_commit="not_committed" if apply else None)


def _rescan_preview(root, observation):
    """Describe proposed work separately from outcomes; never create derived files."""
    from archive_store import cache_dir
    abstract = {"action": "not_needed", "reason": "only approved valid reviews can regenerate content"}
    index = {"action": "skipped", "reason": "only approved valid reviews refresh the projection"}
    if observation.get("eligible"):
        from archive_extract import extract_legacy
        generated = extract_legacy(root, observation["review"], observation["identity"]["source_id"])
        changed = observation["envelope"].get("generated") != generated
        abstract = {"action": "regenerate" if changed else "not_needed",
                    "reason": "generated content differs" if changed else "generated content is unchanged"}
        path = contained(cache_dir(root) / "index.sqlite3", root)
        index = ({"action": "refresh"} if path.exists() else {
            "action": "skipped", "reason": "no established projection",
            "remedy": "run flow index rebuild to create the first index"})
    result = _result(observation)
    result["proposed_operations"] = {
        "abstract": abstract, "index": index,
        "coverage": {"action": "refresh", "qualified_id": observation["qualified_id"]},
    }
    return result


def _rescan_unavailable(work_id, qualified_id, error, publication, observation=None):
    remedy = "preview current content and retry explicit rescan; review authority is unchanged"
    current = observation or {"work_id": work_id, "qualified_id": qualified_id}
    result = _result(current, state="unavailable",
                     abstract={"state": publication, "reason": str(error), "remedy": remedy},
                     index={"state": "skipped", "reason": "content publication or readback unavailable", "remedy": remedy},
                     coverage={"state": "skipped", "reason": "content publication or readback unavailable", "remedy": remedy})
    result.update(reason=str(error), remedy=remedy)
    return result


def rescan(root, work_id, base_fingerprint=None, apply=False, yes=False):
    root = Path(root).resolve()
    try:
        observation = observe(root, work_id)
        if not _usable(observation):
            return _result(observation, state="unavailable")
        if apply and (not yes or not base_fingerprint):
            raise ArchiveError("rescan writes require current --base-fingerprint, --apply and --yes")
        if apply and base_fingerprint != observation["fingerprint"]:
            raise ArchiveError("stale consent; preview the current base")
        if not apply:
            return _rescan_preview(root, observation)
        if not observation.get("eligible"):
            with writer_lock(root):
                if observe(root, work_id).get("fingerprint") != base_fingerprint:
                    raise ArchiveError("stale consent; preview the current base")
                from archive_service import refresh_coverage
                try:
                    refresh_coverage(root, work_id)
                    coverage = {"state": "completed"}
                except (OSError, ValueError) as error:
                    return _result(observation, state="unavailable", coverage={
                        "state": "failed", "reason": str(error),
                        "remedy": "restore derived storage and retry the targeted rescan"})
            return _result(observation, state="complete",
                           abstract={"state": "not_needed", "reason": "only approved valid reviews can regenerate content"},
                           coverage=coverage)
        with writer_lock(root):
            locked = observe(root, work_id)
            if locked.get("fingerprint") != base_fingerprint or not locked.get("eligible"):
                raise ArchiveError("stale consent; preview the current base")
            from archive_extract import extract_legacy
            generated = extract_legacy(root, locked["review"], locked["identity"]["source_id"])
            updated = dict(locked["envelope"])
            changed = updated.get("generated") != generated
            if changed:
                updated["generated"] = generated
                updated["provenance"] = {**updated["provenance"], "generated_at": _now(), "last_action": "legacy_rescan"}
                validate_legacy_envelope(updated)
                if observe(root, work_id).get("fingerprint") != base_fingerprint:
                    raise ArchiveError("source changed during generation; preview again")
                path = envelope_path(root, work_id)
                previous_bytes = path.read_bytes()
                try:
                    write_envelope(root, work_id, updated, file_digest(path))
                except OSError as error:
                    # Readback is optional evidence, not a prerequisite for reporting
                    # an attempted publication. Changed or unreadable bytes cannot
                    # prove that replacement did not happen.
                    publication, after = "uncertain", None
                    try:
                        if path.read_bytes() == previous_bytes:
                            publication = "not_committed"
                        observed = observe(root, work_id)
                        if _usable(observed):
                            after = observed
                    except (OSError, ValueError):
                        pass
                    return _rescan_unavailable(work_id, locked["qualified_id"], error, publication, after)
        try:
            after = observe(root, work_id)
        except (OSError, ValueError) as error:
            return _rescan_unavailable(work_id, locked["qualified_id"], error,
                                       "committed" if changed else "not_needed")
        if not _usable(after):
            return _rescan_unavailable(work_id, locked["qualified_id"], "current authority readback unavailable",
                                       "committed" if changed else "not_needed", after)
        index, coverage = _derived_outcomes(root, work_id)
        partial = any(item.get("state") == "failed" for item in (index, coverage))
        return _result(after, state="partial" if partial else "complete",
                       abstract={"state": "committed" if changed else "not_needed"}, index=index, coverage=coverage)
    except OSError as error:
        return _failure(work_id, error, unavailable=True)
    except (ValueError, KeyError, TypeError, IndexError) as error:
        return _failure(work_id, error)
