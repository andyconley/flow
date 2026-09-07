"""Archive command coordination; canonical closure is never enrichment's transaction."""
from __future__ import annotations
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from archive_extract import extract, verify_pointer
from archive_model import declaration_digest, digest, validate_declarations, validate_envelope
from archive_store import (ArchiveError, atomic_write, cache_dir, contained, encode, ensure_identity,
    ensure_ignore, envelope_path, file_digest, read_identity, record_coverage, cached_coverage, writer_lock, write_envelope)


def now():
    return datetime.now(timezone.utc).isoformat()


def load_run(root, work):
    path = envelope_path(root, work).parent / "run.json"
    value = json.loads(contained(path, root).read_text())
    if value.get("work_id") != work:
        raise ArchiveError("canonical work ID mismatch")
    return value


def load_envelope(root, work):
    path = envelope_path(root, work)
    return json.loads(path.read_text()) if path.exists() else None


def build_envelope(root, run, source_id, previous, origin):
    identity = {"source_id": source_id, "work_id": run["work_id"]}
    if previous:
        validate_envelope(previous)
        if previous["identity"] != identity:
            raise ArchiveError("identity mismatch; restore owning overlay identity")
    declarations = (previous or {}).get("declarations", {})
    generated = extract(root, run, source_id, declarations)
    value = copy.deepcopy(previous) if previous else {"schema_version": 1, "identity": identity, "declarations": {}, "refinement": None, "provenance": {"origin": origin, "created_at": now()}}
    if value.get("generated") != generated:
        value["generated"] = generated
        value["provenance"]["generated_at"] = now()
        value["provenance"]["last_action"] = origin
    validate_envelope(value)
    return value


def inventory(root, work_ids=None):
    directory = contained(Path(root) / ".flow" / "runs", root)
    rows = []
    if not directory.exists():
        return rows
    candidates = [envelope_path(root, work).parent for work in work_ids] if work_ids is not None else sorted(directory.iterdir())
    for path in candidates:
        if not path.is_dir():
            continue
        row = {"work_id": path.name, "eligible": False, "conditions": [], "action": "skip"}
        try:
            run = load_run(root, path.name)
        except FileNotFoundError:
            row["conditions"] = ["legacy_awaiting_review"]
            rows.append(row)
            continue
        except (OSError, ValueError, TypeError) as error:
            row["conditions"] = ["invalid_canonical"]
            row["detail"] = str(error)
            rows.append(row)
            continue
        if run.get("state") != "archived":
            row["conditions"] = ["not_archived"]
            rows.append(row)
            continue
        row["eligible"] = True
        path_abstract = envelope_path(root, path.name)
        try:
            value = load_envelope(root, path.name)
            if not value or value.get("generated") is None:
                closure_event = None
                event_path = contained(path / "events.jsonl", root)
                if event_path.exists():
                    for line in event_path.read_text().splitlines():
                        event = json.loads(line)
                        if event.get("event") in {"archive", "archive-scout"} and event.get("at") == run.get("gates", {}).get(event["event"]):
                            closure_event = event
                live = (closure_event or {}).get("dispositions", {}).get("archive_enrichment") == "1"
                row["conditions"] = ["live_regression" if live else "historical_gap"]
                row["action"] = "generate"
            else:
                if value.get("schema_version") != 1 or value.get("generated", {}).get("extractor_version") != 1:
                    row["conditions"] = ["outdated_abstract"]
                    row["action"] = "review"
                else:
                    validate_envelope(value)
                    row["conditions"] = ["backfilled"] if value.get("provenance", {}).get("origin") == "backfill" else []
        except (OSError, ValueError, KeyError, TypeError) as error:
            row["conditions"] = ["malformed_abstract"]
            row["action"] = "review"
            row["detail"] = str(error)
        row["base_digest"] = file_digest(path_abstract)
        rows.append(row)
    return rows


def refresh_coverage(root, work_id=None):
    if work_id is None:
        return record_coverage(root, inventory(root), now())
    previous = cached_coverage(root)
    rows = {row["work_id"]: row for row in previous.get("runs", [])}
    for row in inventory(root, work_ids=[work_id]):
        rows[row["work_id"]] = row
    # A single archive event cannot establish complete historical coverage.
    return record_coverage(root, [rows[key] for key in sorted(rows)], previous.get("observed_at"), inventory_complete=previous.get("inventory_complete", False))


def backfill(root, rescan=False, apply=False, yes=False, work_ids=None):
    root = Path(root).resolve()
    rows = inventory(root)
    selected = set(work_ids or [])
    for row in rows:
        if row["eligible"] and (not selected or row["work_id"] in selected) and rescan and row["action"] == "skip":
            row["action"] = "rescan"
        if selected and row["work_id"] not in selected:
            row["action"] = "skip"
    result = {"state": "preview", "identity_needed": not (root / ".flow" / "identity.json").exists(), "runs": rows, "errors": []}
    if not apply:
        return result
    if not yes:
        return {**result, "state": "invalid_request", "errors": ["writes require --apply --yes"]}
    try:
        with writer_lock(root):
            ensure_ignore(root)
            source_id = ensure_identity(root)
    except (OSError, ValueError) as error:
        return {**result, "state": "failed", "errors": [str(error)]}
    for row in rows:
        if row["action"] not in {"generate", "rescan"}:
            continue
        try:
            work = row["work_id"]
            run = load_run(root, work)
            previous = load_envelope(root, work)
            value = build_envelope(root, run, source_id, previous, "backfill")
            with writer_lock(root):
                if load_run(root, work) != run:
                    raise ArchiveError("run changed during generation; preview again")
                # Re-extract after acquiring lock to reject external source races.
                if extract(root, run, source_id, value["declarations"]) != value["generated"]:
                    raise ArchiveError("sources changed during generation; preview again")
                row["changed"] = write_envelope(root, work, value, row["base_digest"])
                row["result"] = "repaired"
        except (OSError, ValueError, KeyError, TypeError) as error:
            row["result"] = "failed"
            result["errors"].append(f"{row['work_id']}: abstract: {error}; repair source and rerun backfill")
    try:
        with writer_lock(root):
            refresh_coverage(root)
    except (OSError, ValueError) as error:
        result["errors"].append("coverage: " + str(error) + "; observation not persisted; rerun backfill")
    # Refresh an already-established projection; first projection remains explicit rebuild.
    if (cache_dir(root) / "index.sqlite3").exists():
        try:
            from archive_query import rebuild
            index_result = rebuild(root, incremental=True)
            if index_result["state"] != "complete":
                result["errors"].append("index: " + str(index_result))
        except (OSError, ValueError) as error:
            result["errors"].append("index: " + str(error) + "; run flow index rebuild")
    result["state"] = "partial" if result["errors"] else "complete"
    return result


def archive_transition(args):
    import runstate
    from fsutil import repo_root
    root = repo_root().resolve()
    errors = []
    try:
        artifacts = runstate.parse_assignments(args.artifact, "--artifact")
        dispositions = runstate.parse_assignments(args.disposition, "--disposition")
    except ValueError as error:
        print(str(error))
        return 1
    dispositions["archive_enrichment"] = "1"
    try:
        with writer_lock(root):
            ensure_ignore(root)
            source_id = ensure_identity(root)
            previous = load_envelope(root, args.work_id)
            if previous:
                validate_envelope(previous)
                if previous["identity"] != {"source_id": source_id, "work_id": args.work_id}:
                    raise ArchiveError("archive identity mismatch")
                if previous.get("declarations", {}).get("supersedes"):
                    for edge in previous["declarations"]["supersedes"]:
                        for pointer in edge["evidence"]:
                            if pointer["source_id"] != source_id:
                                raise ArchiveError("supersession evidence must belong to the declaring overlay")
                            verify_pointer(root, pointer)
                    dispositions["archive_declarations"] = declaration_digest(previous["identity"], previous["declarations"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors.append(f"{args.work_id}: prepare: {error}; restore identity/control evidence then backfill")
        dispositions.pop("archive_declarations", None)
    # Do not wrap lifecycle persistence exceptions as enrichment success.
    ok, payload, refused = runstate.apply_transition(args.work_id, args.event, artifacts=artifacts, dispositions=dispositions, note=args.note, root=root)
    if ok:
        try:
            source_id = read_identity(root)
            # Parse and hash one byte snapshot, never a second read of a newer base.
            with writer_lock(root):
                if load_run(root, args.work_id) != payload:
                    raise ArchiveError("canonical run changed after closure; regenerate through backfill")
                path = envelope_path(root, args.work_id)
                raw = path.read_bytes() if path.exists() else None
                previous = json.loads(raw) if raw is not None else None
                import hashlib
                base = hashlib.sha256(raw).hexdigest() if raw is not None else "absent"
            value = build_envelope(root, payload, source_id, previous, "archive")
            with writer_lock(root):
                if load_run(root, args.work_id) != payload:
                    raise ArchiveError("canonical run changed during archive generation")
                if extract(root, payload, source_id, value["declarations"]) != value["generated"]:
                    raise ArchiveError("source changed during archive generation")
                write_envelope(root, args.work_id, value, base)
        except Exception as error:
            errors.append(f"{args.work_id}: abstract: {error}; repair source and run flow archive backfill")
        if (cache_dir(root) / "index.sqlite3").exists():
            try:
                from archive_query import rebuild
                result = rebuild(root, incremental=True)
                if result["state"] != "complete":
                    errors.append(f"{args.work_id}: index: {result}; run flow index rebuild")
            except Exception as error:
                errors.append(f"{args.work_id}: index: {error}; run flow index rebuild")
        try:
            with writer_lock(root):
                refresh_coverage(root, args.work_id)
        except Exception as error:
            errors.append(f"{args.work_id}: coverage: {error}; observation not persisted; run flow archive backfill")
    coverage = cached_coverage(root)
    if args.json:
        print(json.dumps({"ok": ok, "run": payload, "errors": refused, "enrichment_diagnostics": errors, "archive_coverage": coverage}, sort_keys=True))
    else:
        print(f"transition {'accepted' if ok else 'refused'}: {args.event}")
        if ok:
            print("state: " + payload["state"])
        for error in refused + errors:
            print("- " + error)
    return 0 if ok else 1


def mutate(root, work, operation, data, base_digest, apply=False, yes=False):
    root = Path(root).resolve()
    path = envelope_path(root, work)
    if file_digest(path) != base_digest:
        raise ArchiveError("stale consent; preview the current base")
    try:
        run = load_run(root, work)
    except FileNotFoundError:
        if operation != "declare":
            raise
        run = {"work_id": work, "state": None}
    old = load_envelope(root, work)
    source_id = read_identity(root)
    value = copy.deepcopy(old) if old else {"schema_version": 1, "identity": {"source_id": source_id, "work_id": work}, "generated": None, "declarations": {}, "refinement": None, "provenance": {"origin": "declaration", "created_at": now()}}
    if data.get("schema_version") != 1 or not data.get("actor") or not data.get("reason"):
        raise ArchiveError("input requires schema_version=1, actor and reason")
    if operation == "declare":
        proposed = data.get("declarations", {})
        unknown = set(proposed) - {"supersedes", "selections"}
        if unknown:
            raise ArchiveError("unsupported declaration mutation fields")
        if run.get("state") == "archived" and "supersedes" in proposed and proposed["supersedes"] != value["declarations"].get("supersedes", []):
            raise ArchiveError("historical supersession intent is immutable; use a new decision run")
        value["declarations"].update(proposed)
        validate_declarations(value["declarations"], value["identity"])
    else:
        if not value.get("generated") or data.get("base_generated_digest") != digest(value["generated"]):
            raise ArchiveError("refinement generated base changed")
        value["refinement"] = {"revision": digest(data), "actor": data["actor"], "reason": data["reason"], "base_generated_digest": data["base_generated_digest"], "patches": data.get("patches", {})}
    validate_envelope(value)
    # Verify evidence bytes before accepting authority. Never dereference URLs.
    pointers = [p for e in value["declarations"].get("supersedes", []) for p in e["evidence"]]
    pointers += [s["source"] for s in value["declarations"].get("selections", [])]
    pointers += [p for patch in (value.get("refinement") or {}).get("patches", {}).values() for p in patch["sources"]]
    for pointer in pointers:
        if pointer["source_id"] != source_id:
            raise ArchiveError("mutation evidence must be in the owning overlay")
        verify_pointer(root, pointer)
    if apply and not yes:
        raise ArchiveError("writes require --apply --yes")
    if apply:
        with writer_lock(root):
            for pointer in pointers:
                verify_pointer(root, pointer)
            write_envelope(root, work, value, base_digest)
    return {"state": "complete" if apply else "preview", "base_digest": base_digest, "envelope": value}
