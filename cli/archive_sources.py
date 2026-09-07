"""Read-only source discovery and bounded-retry archive observation."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from archive_model import declaration_digest, digest, qualified, validate_envelope, effective_view
from archive_store import contained, read_identity
from archive_extract import verify_pointer


def discover_context(root):
    start = Path(root).resolve()
    home = (Path.home() / ".flow").resolve()
    result, physical = [], set()
    for project in [start, *start.parents]:
        overlay = project / ".flow"
        if overlay.resolve() == home or not overlay.exists():
            continue
        if not ((overlay / "PROJECT.md").exists() or (overlay / "flow.toml").exists() or (overlay / "runs").exists()):
            continue
        resolved = overlay.resolve()
        if resolved in physical:
            continue
        physical.add(resolved)
        row = {"root": str(project), "distance": len(result), "source_id": None, "state": "ready", "diagnostics": []}
        try:
            row["source_id"] = read_identity(project)
        except (OSError, ValueError, TypeError, KeyError) as error:
            row.update(state="unavailable", diagnostics=[{"code": "identity_unavailable", "detail": str(error), "remedy": "restore identity.json, or preview flow archive backfill in " + str(project)}])
        result.append(row)
    counts = {}
    for row in result:
        if row["source_id"]:
            counts[row["source_id"]] = counts.get(row["source_id"], 0) + 1
    for row in result:
        if counts.get(row["source_id"], 0) > 1:
            row.update(state="ambiguous", diagnostics=[{"code": "duplicate_source_id", "remedy": "remove duplicate logical-source checkouts from this context; do not retarget references"}])
    return result


def _observe(root, compact=False):
    root = Path(root).resolve()
    overlay = root / ".flow"
    files, diagnostics, records = {}, [], []
    def read(path):
        path = contained(path, root)
        raw = path.read_bytes()
        files[path.relative_to(root).as_posix()] = hashlib.sha256(raw).hexdigest()
        return raw
    source_id = read_identity(root)
    read(overlay / "identity.json")
    if (overlay / "components.json").exists():
        read(overlay / "components.json")
    runs = contained(overlay / "runs", root)
    inventory = sorted(p.name for p in runs.iterdir() if p.is_dir()) if runs.exists() else []
    for work in inventory:
        directory = contained(runs / work, root)
        if not (directory / "run.json").exists():
            continue
        try:
            run = json.loads(read(directory / "run.json"))
            if run.get("work_id") != work:
                raise ValueError("canonical work ID mismatch")
            if run.get("state") != "archived":
                continue
            identity = {"source_id": source_id, "work_id": work}
            row = {"work_id": work, "identity": identity, "qualified_id": qualified(identity), "run": run, "envelope": None, "declarations": {}, "declaration_status": "none", "diagnostics": []}
            events = []
            if (directory / "events.jsonl").exists():
                events = [json.loads(line) for line in read(directory / "events.jsonl").decode().splitlines() if line.strip()]
            closures = [e for e in events if e.get("event") in {"archive", "archive-scout"} and e.get("to") == "archived" and e.get("at") == run.get("gates", {}).get(e["event"])]
            row["closure_status"] = "anchored" if len(closures) == 1 else "unverified"
            row["closure_event"] = closures[0] if len(closures) == 1 else None
            path = directory / "abstract.json"
            if path.exists():
                envelope = json.loads(read(path))
                validate_envelope(envelope)
                if envelope["identity"] != identity:
                    raise ValueError("abstract identity mismatch")
                row["envelope"] = envelope
                row["declarations"] = envelope.get("declarations", {})
                edges = row["declarations"].get("supersedes", [])
                expected = closures[0].get("dispositions", {}).get("archive_declarations") if len(closures) == 1 else None
                if edges or expected:
                    row["declaration_status"] = "anchored" if expected == declaration_digest(identity, row["declarations"]) else "unverified"
                for edge in edges:
                    for pointer in edge["evidence"]:
                        try:
                            if pointer["source_id"] != source_id:
                                raise ValueError("declaration evidence is outside owning source")
                            read(overlay / pointer["path"])
                            verify_pointer(root, pointer)
                        except (OSError, ValueError, KeyError, TypeError):
                            row["declaration_status"] = "unverified"
                # Every evidence-bearing input must still match its recorded bytes.
                pointers = []
                generated = envelope.get("generated")
                if generated:
                    for field in generated["fields"].values():
                        pointers.extend(field["sources"])
                if generated and effective_view(envelope)["refinement_state"] == "applied":
                    for patch in (envelope.get("refinement") or {}).get("patches", {}).values():
                        pointers.extend(patch["sources"])
                for selection in row["declarations"].get("selections", []):
                    pointers.append(selection["source"])
                row["content_current"] = bool(generated)
                for pointer in pointers:
                    if pointer["source_id"] != source_id:
                        row["content_current"] = False
                        continue
                    try:
                        raw = read(overlay / pointer["path"])
                        if hashlib.sha256(raw).hexdigest() != pointer["digest"]:
                            row["content_current"] = False
                        else:
                            verify_pointer(root, pointer)
                    except (OSError, ValueError):
                        row["content_current"] = False
                # Inventory the complete selected artifact files even when fields are unknown.
                for path_value in run.get("artifacts", {}).values():
                    raw_path = Path(path_value)
                    if raw_path.parts and raw_path.parts[0] == ".flow":
                        raw_path = Path(*raw_path.parts[1:])
                    try:
                        read(overlay / raw_path)
                    except (OSError, ValueError):
                        pass
            else:
                row["content_current"] = False
                if closures and closures[0].get("dispositions", {}).get("archive_declarations"):
                    row["declaration_status"] = "unverified"
            if compact:
                # Retain authority graph facts, not the corpus of prose payloads.
                row.pop("envelope", None)
                row.pop("run", None)
                row.pop("closure_event", None)
                row["declarations"] = {"supersedes": [{"target": edge["target"], "whole_run": edge["whole_run"]} for edge in row["declarations"].get("supersedes", [])]}
            records.append(row)
        except (OSError, ValueError, KeyError, TypeError) as error:
            diagnostics.append({"code": "invalid_run", "work_id": work, "detail": str(error)})
    fingerprint = digest({"inventory": inventory, "files": files, "diagnostics": diagnostics})
    return {"root": str(root), "source_id": source_id, "records": records, "inventory": inventory, "files": files, "fingerprint": fingerprint, "diagnostics": diagnostics, "state": "partial" if diagnostics else "ready"}


def assess_source(root, compact=False):
    for _ in range(2):
        before = _observe(root, compact=True) if compact else _observe(root)
        after = _observe(root, compact=True) if compact else _observe(root)
        if before["fingerprint"] == after["fingerprint"]:
            return after
    after["state"] = "unstable"
    after["diagnostics"].append({"code": "source_changed_during_capture", "remedy": "retry after source writes finish"})
    return after
