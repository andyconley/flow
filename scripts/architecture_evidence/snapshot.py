"""Snapshot collection and immutable local artifact transactions."""

from __future__ import annotations
from contextlib import contextmanager
import fnmatch
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from .model import (
    EvidenceError,
    canonical,
    contained,
    digest,
    load_snapshot,
    normalize_graph,
    read_json,
    validate_snapshot,
    value_digest,
    write_json,
)


@contextmanager
def output_directory(path):
    path = Path(path).resolve()
    if path.exists():
        raise EvidenceError("output already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".evidence-", dir=path.parent))
    try:
        yield temp
        if path.exists():
            raise EvidenceError("output appeared during collection")
        temp.rename(path)
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def source_files(root, config):
    root = Path(root).resolve()
    files = []
    for name in config.get("identity_roots", config["source_roots"]):
        base = contained(root, name)
        if not base.is_dir():
            raise EvidenceError("source root missing: " + name)
        for p in sorted(base.rglob("*")):
            rel = p.relative_to(root).as_posix()
            if any(
                fnmatch.fnmatch(rel, pattern)
                for pattern in config.get("identity_excludes", [])
            ):
                continue
            safe = contained(root, rel)
            if p.is_symlink():
                raise EvidenceError("symlink source not supported: " + rel)
            if safe.is_file():
                files.append({"path": rel, "sha256": digest(safe.read_bytes())})
    if len({f["path"] for f in files}) != len(files):
        raise EvidenceError("overlapping identity roots")
    return sorted(files, key=lambda f: f["path"])


def file_artifacts(root):
    return [
        {"path": p.relative_to(root).as_posix(), "sha256": digest(p.read_bytes())}
        for p in sorted(Path(root).rglob("*"))
        if p.is_file()
    ]


def collect(source, config, out):
    from .adapters.tach import collect_graph

    root = Path(source).resolve()
    if Path(out).resolve().is_relative_to(root):
        raise EvidenceError("evidence output must be outside source checkout")
    files = source_files(root, config)
    with output_directory(out) as work:
        raw = work / "raw"
        raw.mkdir()
        graph, tools, gaps = collect_graph(root, config, raw)
        implementation = Path(__file__).parent
        producer_files = sorted(implementation.rglob("*.py")) + [
            implementation / "requirements.lock"
        ]
        tools["entrypoint_digest"] = digest(
            (implementation.parent / "architecture_evidence_pilot.py").read_bytes()
        )
        tools["collector_digest"] = value_digest(
            [
                {
                    "path": p.relative_to(implementation).as_posix(),
                    "sha256": digest(p.read_bytes()),
                }
                for p in producer_files
            ]
        )
        quality = {
            "status": "unsupported",
            "records": [],
            "gaps": ["quality collection disabled"],
        }
        if config.get("quality", {}).get("enabled"):
            from .adapters.coverage_json import collect_quality

            quality = collect_quality(root, config, raw)
        if source_files(root, config) != files:
            raise EvidenceError("source changed during collection")
        sources = {}
        for f in files:
            if any(Path(f["path"]).is_relative_to(p) for p in config["source_roots"]):
                try:
                    text = contained(root, f["path"]).read_bytes().decode("utf-8")
                    sources[f["path"]] = {
                        "sha256": f["sha256"],
                        "text": text,
                        "lines": text.splitlines(),
                    }
                except UnicodeError:
                    gaps.append("non UTF-8 source: " + f["path"])
        rev = (
            subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            or None
        )
        s = {
            "schema_version": 1,
            "kind": "snapshot",
            "source": {"revision": rev, "digest": value_digest(files), "files": files},
            "config": config,
            "config_digest": value_digest(config),
            "graph": normalize_graph(graph),
            "quality": quality,
            "tools": tools,
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
            "gaps": sorted(set(gaps)),
            "artifacts": file_artifacts(work),
            "sources": sources,
        }
        write_json(work / "graph.json", s["graph"])
        s["artifacts"] = file_artifacts(work)
        validate_snapshot(s)
        write_json(work / "snapshot.json", s)
    return s


def compare(baseline, candidate, policy_path, out):
    from .delta import compare_graphs
    from .policy import evaluate

    b = load_snapshot(baseline)
    c = load_snapshot(candidate)
    policy = read_json(policy_path)
    approval_path = Path(policy_path).parent / "policy-approval.json"
    approval = read_json(approval_path) if approval_path.exists() else {}
    if approval:
        try:
            plan = contained(approval_path.parent, approval["plan_file"]).read_text()
            events = contained(
                approval_path.parent, approval["events_file"]
            ).read_text()
            if plan != approval["plan_text"] or events != approval["events_text"]:
                raise EvidenceError("approval source mismatch")
        except (KeyError, OSError) as e:
            raise EvidenceError("approval source artifacts missing") from e
    delta = compare_graphs(b["graph"], c["graph"])
    result = evaluate(b, c, delta, policy, approval)
    with output_directory(out) as work:
        for name, root in [("baseline", baseline), ("candidate", candidate)]:
            # Copy verified evidence files only, never follow undeclared files/symlinks.
            s = b if name == "baseline" else c
            (work / name).mkdir()
            for rel in ["snapshot.json"] + [a["path"] for a in s["artifacts"]]:
                target = contained(work / name, rel)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(contained(root, rel), target)
        write_json(work / "policy.json", policy)
        write_json(work / "policy-approval.json", approval)
        if approval:
            for key in ("plan_file", "events_file"):
                target = contained(work, approval[key])
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(contained(approval_path.parent, approval[key]), target)
        p = {
            "schema_version": 1,
            "kind": "packet",
            "baseline": b,
            "candidate": c,
            "delta": delta,
            "policy": policy,
            "approval": approval,
            **result,
            "artifacts": file_artifacts(work),
        }
        write_json(work / "packet.json", p)
    return p
