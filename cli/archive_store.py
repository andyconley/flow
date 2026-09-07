"""Archive-owned publication and disposable SQLite projections.

No lifecycle writes belong here. Paths are project roots, never overlay roots.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import uuid


class ArchiveError(ValueError):
    pass


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else "absent"


def contained(path, root):
    path, lexical_root = Path(path).absolute(), Path(root).absolute()
    root = lexical_root.resolve()
    if path.is_relative_to(lexical_root):
        path = root / path.relative_to(lexical_root)
    if not path.is_relative_to(root):
        raise ArchiveError(f"path escapes archive root: {path}")
    for part in [path, *path.parents]:
        if part == root:
            break
        if part.is_symlink():
            raise ArchiveError(f"symlinked archive path: {part}")
    if not path.resolve().is_relative_to(root):
        raise ArchiveError(f"resolved path escapes archive root: {path}")
    return path


def atomic_write(path, data, root):
    path = contained(path, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    contained(path, root)
    fd, name = tempfile.mkstemp(prefix=".archive-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        contained(path, root)
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def cache_dir(root):
    return Path(root) / ".flow" / ".cache" / "archive"


@contextmanager
def writer_lock(root, timeout=1.0):
    root = Path(root).resolve()
    directory = contained(cache_dir(root), root)
    directory.mkdir(parents=True, exist_ok=True)
    lock = contained(directory / "write.lock", root)
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ArchiveError("archive writer busy; retry after the current writer finishes")
                time.sleep(0.01)
        yield
    finally:
        os.close(fd)


def ensure_ignore(root):
    path = contained(Path(root) / ".flow" / ".gitignore", root)
    old = path.read_text() if path.exists() else ""
    if ".cache/" not in old.splitlines():
        atomic_write(path, (old + ("\n" if old and not old.endswith("\n") else "") + ".cache/\n").encode(), root)


def read_identity(root):
    path = contained(Path(root) / ".flow" / "identity.json", root)
    value = json.loads(path.read_text())
    valid = (isinstance(value, dict) and type(value.get("schema_version")) is int
             and value["schema_version"] == 1 and isinstance(value.get("source_id"), str))
    if valid:
        try:
            valid = str(uuid.UUID(value["source_id"])) == value["source_id"]
        except ValueError:
            valid = False
    if not valid:
        raise ArchiveError("invalid overlay identity; restore identity.json from version control or backup")
    return value["source_id"]


def ensure_identity(root):
    """Caller must hold writer_lock. Never retarget retained qualified evidence."""
    root = Path(root).resolve()
    path = contained(root / ".flow" / "identity.json", root)
    if path.exists():
        return read_identity(root)
    runs = root / ".flow" / "runs"
    if runs.exists():
        for run in runs.iterdir():
            for name in ("abstract.json", "events.jsonl"):
                source = contained(run / name, root)
                if source.exists() and ('"source_id"' in source.read_text() or "archive_declarations" in source.read_text()):
                    raise ArchiveError("identity missing with retained qualified evidence; restore identity.json from backup or version control")
    source_id = str(uuid.uuid4())
    atomic_write(path, encode({"schema_version": 1, "source_id": source_id}), root)
    return read_identity(root)


def envelope_path(root, work_id):
    if not isinstance(work_id, str) or not work_id or work_id in {".", ".."} or "/" in work_id or "\\" in work_id:
        raise ArchiveError("invalid work ID")
    return contained(Path(root) / ".flow" / "runs" / work_id / "abstract.json", root)


def write_envelope(root, work_id, envelope, expected_digest):
    """Publish under the caller's writer lock, with immutable refinement retention."""
    from archive_model import validate_envelope
    validate_envelope(envelope)
    path = envelope_path(root, work_id)
    if file_digest(path) != expected_digest:
        raise ArchiveError("archive base changed; preview again before applying")
    data = encode(envelope)
    if path.exists() and path.read_bytes() == data:
        return False
    previous = json.loads(path.read_text()) if path.exists() else {}
    refinement = previous.get("refinement")
    if refinement and refinement != envelope.get("refinement"):
        revision = hashlib.sha256(encode(refinement)).hexdigest()
        history = path.parent / "abstract-history" / (revision + ".json")
        if history.exists():
            if history.read_bytes() != encode(refinement):
                raise ArchiveError("immutable refinement history mismatch")
        else:
            atomic_write(history, encode(refinement), root)
    if file_digest(path) != expected_digest:
        raise ArchiveError("archive base changed during preservation; preview again")
    atomic_write(path, data, root)
    return True


def cached_coverage(root):
    try:
        path = contained(cache_dir(root) / "coverage.json", root)
        value = json.loads(path.read_text())
        if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("runs"), list):
            raise ValueError("invalid coverage observation")
        value["freshness"] = "last_observed"
        return value
    except (OSError, ValueError):
        return {"state": "unknown", "observed_at": None, "counts": None, "runs": []}


def record_coverage(root, records, observed_at, inventory_complete=True):
    counts = {}
    for row in records:
        for condition in row.get("conditions", []):
            counts[condition] = counts.get(condition, 0) + 1
    value = {"schema_version": 1, "state": "observed" if inventory_complete else "partial", "scope": str(Path(root).resolve()), "observed_at": observed_at, "inventory_complete": inventory_complete, "counts": counts if inventory_complete else None, "runs": records}
    atomic_write(cache_dir(root) / "coverage.json", encode(value), root)
    return value


def projection_path(root):
    return contained(cache_dir(root) / "index.sqlite3", root)


def read_projection(root):
    path = projection_path(root)
    if not path.is_file():
        raise ArchiveError("no_index; run flow index rebuild in " + str(root))
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        metadata = {key: json.loads(value) for key, value in db.execute("SELECT key,value FROM metadata")}
        records = [json.loads(row[0]) for row in db.execute("SELECT payload FROM records ORDER BY work_id")]
    return metadata, records


@contextmanager
def projection_rows(root):
    """Yield projection metadata and an ordered, one-payload-at-a-time cursor."""
    path = projection_path(root)
    if not path.is_file():
        raise ArchiveError("no_index; run flow index rebuild in " + str(root))
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        metadata = {key: json.loads(value) for key, value in db.execute("SELECT key,value FROM metadata")}
        yield metadata, db.execute("SELECT work_id,payload FROM records ORDER BY work_id")


def projection_record(root, work_id, expected_fingerprint=None, expected_versions=None):
    """Load one ranked payload after the transient query has chosen its prefix."""
    path = projection_path(root)
    if not path.is_file():
        raise ArchiveError("no_index; run flow index rebuild in " + str(root))
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        metadata = {key: json.loads(value) for key, value in db.execute("SELECT key,value FROM metadata")}
        if expected_fingerprint is not None and metadata.get("fingerprint") != expected_fingerprint:
            raise ArchiveError("projection changed while fetching ranked record")
        if expected_versions is not None and metadata.get("versions") != expected_versions:
            raise ArchiveError("projection version changed while fetching ranked record")
        row = db.execute("SELECT payload FROM records WHERE work_id=?", (work_id,)).fetchone()
    if row is None:
        raise ArchiveError("projection changed while fetching ranked record")
    return json.loads(row[0])


def publish_projection(root, records, fingerprint, versions, verify=None):
    """Caller holds lock and rechecks source snapshot before this publication."""
    path = projection_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".index-", suffix=".sqlite3", dir=path.parent)
    os.close(fd)
    try:
        with sqlite3.connect(name) as db:
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("CREATE TABLE records (work_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            metadata = {"schema_version": 1, "fingerprint": fingerprint, "versions": versions}
            db.executemany("INSERT INTO metadata VALUES (?,?)", [(k, json.dumps(v, sort_keys=True)) for k, v in metadata.items()])
            db.executemany("INSERT INTO records VALUES (?,?)", [(row["work_id"], json.dumps(row, ensure_ascii=False, sort_keys=True)) for row in records])
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ArchiveError("rebuilt projection integrity check failed")
        with open(name, "rb") as stream:
            os.fsync(stream.fileno())
        contained(path, root)
        if verify is not None and not verify():
            raise ArchiveError("source changed before projection publication; previous index retained")
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def update_projection(root, records, fingerprint, versions, verify):
    """Transactional incremental replacement of changed rows; no-op leaves bytes alone."""
    path = projection_path(root)
    old_meta, old_rows = read_projection(root)
    if old_meta.get("schema_version") != 1:
        raise ArchiveError("unsupported projection schema; run flow index rebuild")
    if old_meta.get("fingerprint") == fingerprint and old_meta.get("versions") == versions and old_rows == sorted(records, key=lambda r: r["work_id"]):
        return
    desired = {r["work_id"]: json.dumps(r, ensure_ascii=False, sort_keys=True) for r in records}
    with sqlite3.connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        existing = dict(db.execute("SELECT work_id,payload FROM records"))
        for work, payload in desired.items():
            if existing.get(work) != payload:
                db.execute("INSERT OR REPLACE INTO records VALUES (?,?)", (work, payload))
        for work in existing.keys() - desired.keys():
            db.execute("DELETE FROM records WHERE work_id=?", (work,))
        for key, value in {"fingerprint": fingerprint, "versions": versions}.items():
            db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, json.dumps(value, sort_keys=True)))
        if not verify():
            raise ArchiveError("source changed before projection commit; previous transaction retained")
