"""Disposable SQLite projection for local expertise vectors."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import struct
import tempfile
import time
from typing import Callable, Iterable

from expertise_model import ExpertiseContractError, identity


SCHEMA_REVISION = "expertise-index-v1"
BUILDER_REVISION = "expertise-projection-builder-v1"


class ExpertiseProjectionError(ValueError):
    pass


def cache_root(flow_home: Path) -> Path:
    return Path(flow_home) / "cache" / "expertise"


def projection_path(flow_home: Path) -> Path:
    return cache_root(flow_home) / "index.sqlite3"


def _contained(path: Path, root: Path) -> Path:
    lexical_root = root.absolute()
    root = lexical_root.resolve()
    path = path.absolute()
    if path.is_relative_to(lexical_root):
        path = root / path.relative_to(lexical_root)
    if not path.is_relative_to(root):
        raise ExpertiseProjectionError(f"path escapes expertise cache: {path}")
    for part in [path, *path.parents]:
        if part == root:
            break
        if part.is_symlink():
            raise ExpertiseProjectionError(f"symlinked expertise cache path: {part}")
    if not path.resolve().is_relative_to(root):
        raise ExpertiseProjectionError(f"resolved path escapes expertise cache: {path}")
    return path


@contextmanager
def writer_lock(flow_home: Path, timeout: float = 2.0):
    root = _contained(cache_root(flow_home), Path(flow_home))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    lock = _contained(root / "write.lock", root)
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ExpertiseProjectionError("expertise projection is rebuilding")
                time.sleep(0.01)
        yield
    finally:
        os.close(fd)


def dense_text(entry: dict) -> str:
    competencies = "; ".join(
        str(item.get("name", "")) for item in entry.get("teaches", []) if item.get("name")
    )
    fields = (
        ("name", entry.get("name", "")),
        ("principle", entry.get("abstract", "")),
        ("trigger", entry.get("flow:trigger", "")),
        ("required behavior", entry.get("flow:requiredBehavior", "")),
        ("failure mode", entry.get("flow:failureMode", "")),
        ("competencies", competencies),
    )
    return "\n".join(f"{name}: {value}" for name, value in fields)


def _normalized_vector(values: Iterable[float]) -> tuple[float, ...]:
    vector = tuple(float(value) for value in values)
    if not vector or any(not math.isfinite(value) for value in vector):
        raise ExpertiseProjectionError("provider returned an empty or non-finite vector")
    norm = math.sqrt(sum(value * value for value in vector))
    if not math.isfinite(norm) or norm == 0.0:
        raise ExpertiseProjectionError("provider returned a zero vector")
    return tuple(value / norm for value in vector)


def encode_vector(values: Iterable[float]) -> tuple[bytes, int]:
    vector = _normalized_vector(values)
    return struct.pack(f"<{len(vector)}f", *vector), len(vector)


def decode_vector(payload: bytes, dimensions: int) -> tuple[float, ...]:
    if dimensions <= 0 or len(payload) != dimensions * 4:
        raise ExpertiseProjectionError("stored vector width is invalid")
    vector = struct.unpack(f"<{dimensions}f", payload)
    if any(not math.isfinite(value) for value in vector):
        raise ExpertiseProjectionError("stored vector is non-finite")
    return vector


def runtime_fingerprint() -> str:
    return "|".join((platform.system(), platform.release(), platform.machine(), platform.python_implementation(), platform.python_version()))


def projection_identity(snapshot: dict, provider: object) -> dict:
    return identity("projection", {
        "corpus_digest": snapshot["corpus_digest"],
        "lifecycle_revision": snapshot["lifecycle_revision"],
        "entry_serializer_revision": snapshot["entry_serializer_revision"],
        "provider_revision": str(provider.provider_revision),
        "model_artifact_digest": str(provider.model_artifact_digest),
        "embedding_runtime_revision": str(provider.runtime_revision),
        "index_schema_revision": SCHEMA_REVISION,
    })


def publish(
    flow_home: Path,
    snapshot: dict,
    provider: object,
    *,
    verify_snapshot: Callable[[], str] | None = None,
) -> dict:
    current = [entry for entry in snapshot["entries"] if entry.get("_effective_current")]
    texts = [dense_text(entry) for entry in current]
    raw_vectors = list(provider.embed(texts)) if texts else []
    if len(raw_vectors) != len(current):
        raise ExpertiseProjectionError("provider returned the wrong vector count")
    encoded = [encode_vector(vector) for vector in raw_vectors]
    dimensions = {item[1] for item in encoded}
    if len(dimensions) > 1:
        raise ExpertiseProjectionError("provider returned inconsistent vector dimensions")
    projection = projection_identity(snapshot, provider)
    target = _contained(projection_path(flow_home), Path(flow_home))
    with writer_lock(flow_home):
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(prefix=".expertise-index-", suffix=".sqlite3", dir=target.parent)
        os.close(fd)
        try:
            with sqlite3.connect(name) as database:
                database.execute("PRAGMA journal_mode=DELETE")
                database.execute("PRAGMA foreign_keys=ON")
                database.execute("CREATE TABLE index_meta (key TEXT PRIMARY KEY, value_json TEXT NOT NULL)")
                database.execute("""CREATE TABLE projection_entries (
                    entry_id TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    source_layer TEXT NOT NULL CHECK(source_layer IN ('framework','user')),
                    method_layer TEXT NOT NULL CHECK(method_layer IN ('baseline','experience')),
                    owner_id TEXT NOT NULL,
                    lifecycle_state TEXT NOT NULL CHECK(lifecycle_state='current'),
                    entry_digest BLOB NOT NULL CHECK(length(entry_digest)=32),
                    vector BLOB NOT NULL,
                    vector_dimension INTEGER NOT NULL CHECK(vector_dimension>0),
                    CHECK(length(vector)=4*vector_dimension)
                )""")
                database.execute("CREATE INDEX projection_filter ON projection_entries(role,source_layer,method_layer,lifecycle_state,entry_id)")
                metadata = {
                    "schema_revision": SCHEMA_REVISION,
                    "builder_revision": BUILDER_REVISION,
                    "projection_identity": projection,
                    "runtime_fingerprint": runtime_fingerprint(),
                    "entry_count": len(current),
                }
                database.executemany(
                    "INSERT INTO index_meta VALUES (?,?)",
                    [(key, json.dumps(value, sort_keys=True, separators=(",", ":"))) for key, value in metadata.items()],
                )
                for entry, (vector, dimension) in zip(current, encoded):
                    database.execute(
                        "INSERT INTO projection_entries VALUES (?,?,?,?,?,?,?,?,?)",
                        (
                            entry["@id"], entry["audience"]["audienceType"], entry["_source_layer"],
                            entry["_layer"], entry["_lifecycle"]["owner"], "current",
                            bytes.fromhex(entry["_entry_digest"]), vector, dimension,
                        ),
                    )
                if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ExpertiseProjectionError("projection integrity check failed")
                if database.execute("PRAGMA foreign_key_check").fetchall():
                    raise ExpertiseProjectionError("projection foreign-key check failed")
            with open(name, "rb") as stream:
                os.fsync(stream.fileno())
            if verify_snapshot is not None and verify_snapshot() != snapshot["corpus_digest"]:
                raise ExpertiseProjectionError("canonical corpus changed before projection publication")
            _contained(target, Path(flow_home))
            os.chmod(name, 0o600)
            os.replace(name, target)
            directory = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    return {"state": "complete", "indexed": len(current), "projection_identity": projection, "path": str(target)}


def inspect(flow_home: Path, expected_projection_digest: str | None = None) -> dict:
    target = _contained(projection_path(flow_home), Path(flow_home))
    if not target.is_file():
        return {"state": "unavailable", "reason": "projection_missing", "path": str(target)}
    try:
        with sqlite3.connect(target.as_uri() + "?mode=ro", uri=True) as database:
            metadata = {key: json.loads(value) for key, value in database.execute("SELECT key,value_json FROM index_meta")}
            check = database.execute("PRAGMA integrity_check").fetchone()[0]
            count = database.execute("SELECT COUNT(*) FROM projection_entries").fetchone()[0]
        if check != "ok":
            raise ExpertiseProjectionError("projection integrity check failed")
        actual_identity = metadata.get("projection_identity", {}).get("digest")
        if expected_projection_digest is not None and actual_identity != expected_projection_digest:
            return {"state": "stale", "reason": "projection_stale", "path": str(target), "entry_count": count, "metadata": metadata, "bytes": target.stat().st_size}
        return {"state": "ready", "path": str(target), "entry_count": count, "metadata": metadata, "bytes": target.stat().st_size}
    except (sqlite3.Error, json.JSONDecodeError, OSError, ExpertiseContractError) as error:
        return {"state": "unavailable", "reason": "projection_corrupt", "diagnostic": type(error).__name__, "path": str(target)}


def vectors_for_role(flow_home: Path, role: str, expected_projection_digest: str) -> list[dict]:
    target = _contained(projection_path(flow_home), Path(flow_home))
    if not target.is_file():
        raise ExpertiseProjectionError("projection_missing")
    try:
        with sqlite3.connect(target.as_uri() + "?mode=ro", uri=True) as database:
            metadata = {key: json.loads(value) for key, value in database.execute("SELECT key,value_json FROM index_meta")}
            if metadata.get("projection_identity", {}).get("digest") != expected_projection_digest:
                raise ExpertiseProjectionError("projection_stale")
            rows = database.execute(
                "SELECT entry_id,entry_digest,vector,vector_dimension FROM projection_entries WHERE role=? AND lifecycle_state='current' ORDER BY entry_id",
                (role,),
            ).fetchall()
        return [
            {"entry_id": row[0], "entry_digest": bytes(row[1]).hex(), "vector": decode_vector(bytes(row[2]), row[3])}
            for row in rows
        ]
    except sqlite3.Error as error:
        raise ExpertiseProjectionError("projection_corrupt") from error
