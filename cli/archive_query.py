"""Filter, rank and pack one transient merged corpus; never repair on reads."""
from __future__ import annotations
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import json
import itertools
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import unicodedata
from archive_graph import resolve_graph
from archive_preflight import current
from archive_model import digest, effective_view, render_lines
from archive_sources import assess_source, discover_context
from archive_store import ArchiveError, cache_dir, read_projection, projection_record, projection_rows, publish_projection, update_projection, writer_lock

TOKENIZER_VERSION = 1
VERSIONS = {"schema": 1, "extractor": 1, "tokenizer": TOKENIZER_VERSION, "ranker": "fts5-bm25-1"}
EXITS = {"complete": 0, "no_matches": 0, "invalid_request": 2, "partial": 3, "unavailable": 4, "preflight_required": 4}


def tokens(text):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return ["w" + t.encode().hex() for t in re.findall(r"[^\W_]+", normalized)] + ["c" + t.encode().hex() for t in re.findall(r"[^\W_]+(?:[-._][^\W_]+)+", normalized)]


def rank(records, query):
    terms = sorted(set(tokens(query)))
    if not terms:
        return []
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE VIRTUAL TABLE candidates USING fts5(decision, conditions, rationale, tokenize='ascii')")
        values = []
        for i, record in enumerate(records):
            fields = effective_view(record["envelope"])["fields"]
            content = []
            for field in ("decision", "applies_when", "rationale"):
                entry = fields[field]
                text = entry["value"] if entry["state"] == "known" else " ".join(str(a.get("value", "")) for a in entry.get("alternatives", []))
                content.append(" ".join(tokens(str(text))))
            values.append((i + 1, *content))
        db.executemany("INSERT INTO candidates(rowid,decision,conditions,rationale) VALUES(?,?,?,?)", values)
        match = " OR ".join('"' + term + '"' for term in terms)
        rows = db.execute("SELECT rowid,bm25(candidates,3.0,2.0,1.0) FROM candidates WHERE candidates MATCH ?", (match,)).fetchall()
    return [records[i-1] for i, score in sorted(rows, key=lambda row: (row[1], records[row[0]-1].get("distance", 0), records[row[0]-1]["qualified_id"]))]


def _fts_content(envelope):
    fields = effective_view(envelope)["fields"]
    content = []
    for field in ("decision", "applies_when", "rationale"):
        entry = fields[field]
        text = entry["value"] if entry["state"] == "known" else " ".join(str(a.get("value", "")) for a in entry.get("alternatives", []))
        content.append(" ".join(tokens(str(text))))
    return content


@contextmanager
def _stream_ranked(sources, graph, query, component, work_type, since, include_superseded, top_k):
    """Rank one disk-backed merged corpus without retaining projection payloads.

    SQLite holds token strings and ordered row locations. It yields payloads only
    as pack() asks for the display prefix, then verifies the sources it used.
    """
    fd, name = tempfile.mkstemp(prefix="flow-archive-query-", suffix=".sqlite3")
    os.close(fd)
    try:
        with sqlite3.connect(name) as db, ExitStack() as stack:
            db.execute("PRAGMA temp_store=FILE")
            db.execute("CREATE VIRTUAL TABLE eligible USING fts5(decision, conditions, rationale, tokenize='ascii')")
            db.execute("CREATE VIRTUAL TABLE uncertain USING fts5(decision, conditions, rationale, tokenize='ascii')")
            db.execute("CREATE TABLE locations (rowid INTEGER PRIMARY KEY, source_key INTEGER NOT NULL, work_id TEXT NOT NULL, qualified_id TEXT NOT NULL, distance INTEGER NOT NULL)")
            source_map = {}
            rowid = 0
            for source_key, source in enumerate(sources):
                meta, cursor = stack.enter_context(projection_rows(Path(source["root"])))
                if meta.get("fingerprint") != source["fingerprint"] or meta.get("versions") != VERSIONS:
                    raise ArchiveError("stale_index")
                source_map[source_key] = source
                for work_id, raw in cursor:
                    row = json.loads(raw)
                    status = graph["records"].get(row["qualified_id"], {"status": "unknown", "supersedes": [], "superseded_by": []})
                    fields = effective_view(row["envelope"])["fields"]
                    comp = fields["component"]["value"]
                    if component and (not isinstance(comp, dict) or component != comp["source_id"] + ":" + comp["component_id"]):
                        continue
                    if work_type and work_type != fields["work_type"]["value"]:
                        continue
                    if since:
                        try:
                            if not fields["closed_at"]["value"] or instant(fields["closed_at"]["value"]) < instant(since):
                                continue
                        except (ValueError, TypeError):
                            raise ArchiveError("invalid_closure_date:" + row["qualified_id"])
                    if status["status"] == "unknown":
                        table = "uncertain"
                    elif status["status"] == "superseded" and not include_superseded:
                        continue
                    else:
                        table = "eligible"
                    rowid += 1
                    db.execute("INSERT INTO " + table + "(rowid,decision,conditions,rationale) VALUES(?,?,?,?)", (rowid, *_fts_content(row["envelope"])))
                    if table == "eligible":
                        db.execute("INSERT INTO locations VALUES(?,?,?,?,?)", (rowid, source_key, work_id, row["qualified_id"], source["distance"]))
            match = " OR ".join('"' + term + '"' for term in sorted(set(tokens(query))))
            total = db.execute("SELECT count(*) FROM eligible WHERE eligible MATCH ?", (match,)).fetchone()[0]
            uncertain = db.execute("SELECT count(*) FROM uncertain WHERE uncertain MATCH ?", (match,)).fetchone()[0]
            chosen = db.execute("SELECT locations.source_key,locations.work_id,locations.qualified_id FROM eligible JOIN locations ON locations.rowid=eligible.rowid WHERE eligible MATCH ? ORDER BY bm25(eligible,3.0,2.0,1.0),locations.distance,locations.qualified_id LIMIT ?", (match, min(top_k, total)))
            displayed_sources = set()

            def rows():
                for source_key, work_id, qualified_id in chosen:
                    source = source_map[source_key]
                    if source_key not in displayed_sources:
                        if assess_source(Path(source["root"]), compact=True)["fingerprint"] != source["fingerprint"]:
                            raise ArchiveError("source changed while fetching ranked record")
                        displayed_sources.add(source_key)
                    row = projection_record(Path(source["root"]), work_id, source["fingerprint"], VERSIONS)
                    status = graph["records"].get(qualified_id, {"status": "unknown", "supersedes": [], "superseded_by": []})
                    yield {**row, "distance": source["distance"], **status}

            try:
                yield rows(), total, uncertain
            finally:
                for source in sources:
                    if assess_source(Path(source["root"]), compact=True)["fingerprint"] != source["fingerprint"]:
                        raise ArchiveError("source changed while verifying query counts and records")
    finally:
        if os.path.exists(name):
            os.unlink(name)


def rebuild(root, incremental=False):
    root = Path(root).resolve()
    try:
        ignore = root / ".flow" / ".gitignore"
        if not ignore.exists() or ".cache/" not in ignore.read_text().splitlines():
            raise ArchiveError("cache ignore rule missing; run an authorized flow archive backfill --apply --yes first")
        with writer_lock(root):
            source = assess_source(root)
            if source["state"] == "unstable":
                raise ArchiveError("source changed during rebuild; retry")
            records = [r for r in source["records"] if r.get("envelope") and r.get("content_current")]
            after = assess_source(root)
            if source["fingerprint"] != after["fingerprint"]:
                raise ArchiveError("source changed during rebuild; previous index retained")
            verify = lambda: assess_source(root)["fingerprint"] == source["fingerprint"]
            if incremental and (cache_dir(root) / "index.sqlite3").exists():
                update_projection(root, records, source["fingerprint"], VERSIONS, verify)
            else:
                publish_projection(root, records, source["fingerprint"], VERSIONS, verify)
            from archive_service import refresh_coverage
            try:
                refresh_coverage(root)
            except (OSError, ValueError) as error:
                return {"state": "partial", "indexed": len(records), "reason": "coverage observation not persisted: " + str(error), "remedy": "rerun flow index rebuild"}
            return {"state": "complete", "indexed": len(records), "rejected": len(source["records"]) - len(records), "diagnostics": source["diagnostics"], "fingerprint": source["fingerprint"]}
    except (OSError, ValueError, sqlite3.Error, KeyError, TypeError) as error:
        return {"state": "unavailable", "reason": str(error), "remedy": "repair sources then run flow index rebuild in " + str(root)}


def serialized(value, as_json=True):
    # Text mode deliberately uses the same canonical JSON block: one counting contract.
    for _ in range(8):
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        size = len(raw.encode("utf-8"))
        if value.get("actual_output_bytes") == size:
            return raw
        value["actual_output_bytes"] = size
    raise ValueError("response byte accounting failed to converge")


def minimum_budget():
    """Bytes needed for the mandatory bounded error envelope, including itself."""
    error = {"state": "invalid_request", "reason": "budget_too_small", "remedy": "increase budget or narrow sources", "hits": []}
    return len(serialized(error).encode("utf-8"))


def pack(value, ordered, top_k, limit, total_matches=None):
    if total_matches is None:
        total = len(ordered)
    else:
        total = total_matches
    value.update(hits=[], top_k=top_k, max_output_bytes=limit, total_matches=total, shown=0, withheld=total, size_limited=False, top_k_limited=total > top_k)
    if len(serialized(value).encode()) > limit:
        error = {"state": "invalid_request", "reason": "budget_too_small", "remedy": "increase budget or narrow sources", "hits": []}
        serialized(error)
        return error
    for row in itertools.islice(ordered, min(top_k, total)):
        hit = {"qualified_id": row["qualified_id"], "source_id": row["identity"]["source_id"], "work_id": row["work_id"], "status": row["status"], "supersedes": row["supersedes"], "superseded_by": row["superseded_by"], "abstract": row["envelope"], "effective": effective_view(row["envelope"]), "lines": render_lines(row["envelope"]), "rank": value["shown"] + 1, "scorer_version": VERSIONS["ranker"]}
        value["hits"].append(hit)
        value["shown"] += 1
        value["withheld"] -= 1
        if len(serialized(value).encode()) > limit:
            value["hits"].pop()
            value["shown"] -= 1
            value["withheld"] += 1
            value["size_limited"] = True
            break
    if not value["shown"] and total:
        value["reason"] = "no_hit_fits"
    serialized(value)
    # reason and cap flags also count. Remove a trailing hit if those cross a digit boundary.
    while len(serialized(value).encode()) > limit and value["hits"]:
        value["hits"].pop()
        value["shown"] -= 1
        value["withheld"] += 1
        value["size_limited"] = True
    if len(serialized(value).encode()) > limit:
        return {"state": "invalid_request", "reason": "budget_too_small", "hits": []}
    return value


def instant(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        # Date-only filter means UTC midnight; naive timestamps are ambiguous.
        if len(value) == 10:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def sqlite_storage_failure(error):
    """Recognize storage failures without mistaking them for missing FTS5.

    Python 3.11 exposes SQLite result codes; 3.10 needs the engine's messages.
    Extended result codes preserve the primary code in their low byte.
    """
    code = getattr(error, "sqlite_errorcode", None)
    if isinstance(code, int):
        # SQLITE_READONLY, SQLITE_IOERR, SQLITE_FULL, SQLITE_CANTOPEN.
        return (code & 0xff) in {8, 10, 13, 14}
    return str(error).casefold() in {
        "attempt to write a readonly database", "disk i/o error",
        "database or disk is full", "unable to open database file",
    }


def search(root, query, lane="define", sources=None, current_only=False, component=None, work_type=None, since=None, include_superseded=False, top_k=None, max_output_bytes=None):
    from archive_preflight import current
    k = top_k if top_k is not None else (8 if lane == "solution" else 5)
    limit = max_output_bytes if max_output_bytes is not None else (32768 if lane == "solution" else 16384)
    if not isinstance(query, str) or not tokens(query) or len(query.encode()) > 8192 or lane not in {"define", "solution"} or not isinstance(k, int) or k < 1 or not isinstance(limit, int) or limit < minimum_budget():
        return {"state": "invalid_request", "reason": "invalid_query_or_budget", "remedy": f"use plain query text, positive top-k and at least {minimum_budget()} bytes", "hits": []}
    try:
        from archive_model import qualified
        if since:
            instant(since)
        if component is not None:
            source_id, separator, component_id = component.partition(":")
            if not separator or ":" in component_id:
                raise ValueError("component requires UUID:ID")
            qualified({"source_id": source_id, "work_id": component_id})
        if sources:
            for source_id in sources:
                qualified({"source_id": source_id, "work_id": "validation"})
            sources = sorted(set(sources))
        if sources and current_only:
            raise ValueError("source and current-only are mutually exclusive")
    except ValueError as error:
        return {"state": "invalid_request", "reason": str(error), "hits": []}
    preflight = current()
    if preflight["state"] != "available":
        return pack({"state": preflight["state"], "reason": "fts5_preflight", "diagnostics": [preflight]}, [], k, limit)
    context = discover_context(root)
    if not context:
        return pack({"state": "unavailable", "reason": "no_project_overlay", "remedy": "run from a project overlay"}, [], k, limit)
    known_sources = {s["source_id"] for s in context}
    if sources and set(sources) - known_sources:
        return {"state": "invalid_request", "reason": "source is not in current context", "hits": []}
    selected = {context[0]["source_id"]} if current_only else set(sources or known_sources)
    searched, unavailable, ready_sources = [], [], []
    for source in context:
        if source["state"] != "ready":
            if source["source_id"] in selected:
                unavailable.append({k: v for k, v in source.items() if k != "records"})
            continue
        try:
            observation = assess_source(Path(source["root"]), compact=True)
            source.update(observation)
            if source["state"] != "ready" and source["source_id"] in selected:
                unavailable.append({"source_id": source["source_id"], "reason": source["state"], "diagnostics": source["diagnostics"]})
            if source["source_id"] not in selected:
                continue
            if source["state"] == "unstable":
                raise ArchiveError("source unstable")
            with projection_rows(Path(source["root"])) as (meta, _):
                if meta.get("fingerprint") != source["fingerprint"] or meta.get("versions") != VERSIONS:
                    raise ArchiveError("stale_index")
            if assess_source(Path(source["root"]), compact=True)["fingerprint"] != source["fingerprint"]:
                raise ArchiveError("source changed while reading index")
            ready_sources.append(source)
            searched.append(source["source_id"])
        except (OSError, ValueError, sqlite3.Error, KeyError, TypeError) as error:
            if "records" not in source:
                source["state"] = "unavailable"
            if source["source_id"] in selected:
                unavailable.append({"source_id": source["source_id"], "reason": str(error), "remedy": "run flow index rebuild in " + source["root"]})
    graph = resolve_graph(context)
    selected_uncertainty = any(row["identity"]["source_id"] in selected and graph["records"].get(row["qualified_id"], {}).get("status") == "unknown" for source in context for row in source.get("records", []))
    content_gaps = any(row["identity"]["source_id"] in selected
                       and any(item.get("code") == "invalid_abstract_content" for item in row.get("diagnostics", []))
                       for source in context for row in source.get("records", []))
    try:
        with _stream_ranked(ready_sources, graph, query, component, work_type, since, include_superseded, k) as (ordered, total_matches, uncertain_matches):
            state = "partial" if unavailable or uncertain_matches or selected_uncertainty or content_gaps else "complete" if total_matches else "no_matches"
            if not searched:
                state = "unavailable"
            value = {"state": state, "context_sources": [{"source_id": s["source_id"], "root": s["root"], "state": s["state"], "fingerprint": s.get("fingerprint")} for s in context], "searched_sources": searched, "unavailable_sources": unavailable, "uncertain_matches": uncertain_matches, "diagnostics": graph["diagnostics"], "count_scope": "verified_selected_sources", "selection_id": digest({"query": query, "sources": [(s["source_id"], s.get("fingerprint")) for s in context], "filters": [sources, current_only, component, work_type, since, include_superseded], "caps": [k, limit]})}
            result = pack(value, ordered, k, limit, total_matches=total_matches)
        # Excluded candidate sources can still own supersession controls.
        for source in context:
            if source["source_id"] not in selected and source.get("fingerprint"):
                if assess_source(Path(source["root"]), compact=True)["fingerprint"] != source["fingerprint"]:
                    raise ArchiveError("supersession context changed during query")
    except OSError as error:
        return pack({"state": "unavailable", "reason": "temporary_storage_unavailable", "remedy": "provide a writable temporary directory via TMPDIR and sufficient free space; retry retrieval", "detail": str(error)}, [], k, limit)
    except ArchiveError as error:
        if str(error).startswith("invalid_closure_date:"):
            return pack({"state": "unavailable", "reason": "invalid_closure_date", "remedy": "inspect the named run's canonical closure date and regenerate its abstract after correcting evidence", "detail": str(error)}, [], k, limit)
        return pack({"state": "unavailable", "reason": "source_changed_during_query", "remedy": "retry after source writes finish; rebuild the owning index if stale", "detail": str(error)}, [], k, limit)
    except sqlite3.Error as error:
        if sqlite_storage_failure(error):
            return pack({"state": "unavailable", "reason": "temporary_storage_unavailable", "remedy": "provide a writable temporary directory via TMPDIR and sufficient free space; check archive database storage if the I/O error persists; retry retrieval", "detail": str(error)}, [], k, limit)
        return pack({"state": "unavailable", "reason": "fts5_failed_after_preflight", "remedy": "run flow doctor and select an FTS5-enabled interpreter", "detail": str(error)}, [], k, limit)
    except (ValueError, KeyError, TypeError) as error:
        return pack({"state": "unavailable", "reason": "fts5_failed_after_preflight", "remedy": "run flow doctor and select an FTS5-enabled interpreter", "detail": str(error)}, [], k, limit)
    return result
