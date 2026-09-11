"""Portable evidence values and integrity checks; no language analyzers."""

from __future__ import annotations
import math
import hashlib
import json
from pathlib import Path


class EvidenceError(ValueError):
    """Required evidence is missing, incompatible or inconsistent."""


def canonicalize(value, key=None):
    if isinstance(value, dict):
        return {k: canonicalize(v, k) for k, v in value.items()}
    if isinstance(value, list):
        items = [canonicalize(v) for v in value]
        if key in (
            "nodes",
            "edges",
            "rules",
            "exceptions",
            "records",
            "inventory",
            "files",
            "artifacts",
            "sources",
            "approved_rules",
        ):
            items.sort(
                key=lambda x: (
                    str(x.get("id", x.get("path", ""))),
                    x.get("start_line", 0),
                    x.get("end_line", 0),
                    json.dumps(x, sort_keys=True, ensure_ascii=False),
                )
                if isinstance(x, dict)
                else (str(x), 0, 0, "")
            )
        return items
    return value


def canonical(value):
    return (
        json.dumps(
            canonicalize(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def value_digest(value):
    return digest(canonical(value))


def contained(root, relative):
    p = Path(relative)
    if p.is_absolute() or ".." in p.parts or not p.parts or "\\" in str(relative):
        raise EvidenceError(f"unsafe relative path: {relative}")
    target = (Path(root) / p).resolve()
    if not target.is_relative_to(Path(root).resolve()):
        raise EvidenceError(f"path escapes root: {relative}")
    return target


def read_json(path):
    try:
        return json.loads(
            Path(path).read_text(),
            parse_constant=lambda x: (_ for _ in ()).throw(
                EvidenceError("nonfinite JSON")
            ),
        )
    except (OSError, ValueError) as e:
        raise EvidenceError(f"invalid evidence {Path(path).name}: {e}") from e


def write_json(path, value):
    Path(path).write_bytes(canonical(value))


def normalize_graph(graph):
    g = json.loads(json.dumps(graph))
    for e in g["edges"]:
        e["sources"] = sorted(
            e.get("sources", []),
            key=lambda s: (s["path"], s["start_line"], s["end_line"]),
        )
    for key in ("nodes", "edges"):
        g[key] = sorted(g[key], key=lambda x: x["id"])
    g["inventory"] = sorted(g.get("inventory", []), key=lambda x: x["path"])
    g["unresolved"] = sorted(g.get("unresolved", []), key=canonical)
    return g


def validate_snapshot(s):
    if not isinstance(s, dict):
        raise EvidenceError("snapshot must be object")
    if s.get("schema_version") != 1 or s.get("kind") != "snapshot":
        raise EvidenceError("unsupported snapshot schema")
    for key in (
        "source",
        "config",
        "config_digest",
        "graph",
        "quality",
        "gaps",
        "artifacts",
        "sources",
    ):
        if key not in s:
            raise EvidenceError(f"missing {key}")
    if value_digest(s["config"]) != s["config_digest"]:
        raise EvidenceError("config digest mismatch")
    files = s["source"]["files"]
    if value_digest(files) != s["source"]["digest"]:
        raise EvidenceError("source digest mismatch")
    if len({f["path"] for f in files}) != len(files):
        raise EvidenceError("duplicate source path")
    paths = {f["path"]: f["sha256"] for f in files}
    for p, src in s["sources"].items():
        contained(Path("/tmp"), p)
        if (
            digest(src["text"].encode("utf-8")) != src["sha256"]
            or paths.get(p) != src["sha256"]
        ):
            raise EvidenceError("source excerpt identity mismatch")
        if src["text"].splitlines() != src["lines"]:
            raise EvidenceError("source lines mismatch")
    g = s["graph"]
    nodes = g["nodes"]
    ids = {n["id"] for n in nodes}
    if len(ids) != len(nodes):
        raise EvidenceError("duplicate node identity")
    if len({e["id"] for e in g["edges"]}) != len(g["edges"]):
        raise EvidenceError("duplicate edge identity")
    for n in nodes:
        if n.get("path") and (
            paths.get(n["path"]) != n.get("sha256") or n["path"] not in s["sources"]
        ):
            raise EvidenceError("node source mismatch or missing excerpt")
    inventory = g.get("inventory", [])
    if len({i["path"] for i in inventory}) != len(inventory):
        raise EvidenceError("duplicate inventory record")
    for i in inventory:
        if i["status"] not in ("processed", "excluded", "failed"):
            raise EvidenceError("invalid inventory status")
    expected = {
        p
        for p in paths
        if any(Path(p).is_relative_to(root) for root in s["config"]["source_roots"])
    }
    if expected != {i["path"] for i in inventory}:
        raise EvidenceError("inventory does not account for source files")
    for e in g["edges"]:
        if e["from"] not in ids or e["to"] not in ids:
            raise EvidenceError("dangling edge")
        if e["kind"] != "direct-import":
            raise EvidenceError("unsupported pilot edge kind")
        for span in e.get("sources", []):
            src = s["sources"].get(span["path"])
            a = span["start_line"]
            b = span["end_line"]
            if (
                not src
                or not isinstance(a, int)
                or not isinstance(b, int)
                or not 1 <= a <= b <= len(src["lines"])
            ):
                raise EvidenceError("invalid source span")
    for q in s["quality"].get("records", []):
        if q.get("path") and q.get("source_sha256") != paths.get(q["path"]):
            raise EvidenceError("quality source mismatch")
    quality = s["quality"]
    if quality.get("status") == "available":
        if not quality.get("records"):
            raise EvidenceError("available quality has no records")
        for q in quality["records"]:
            c = q["complexity"]["value"]
            cov = q["coverage"]
            covered, total = cov["covered"], cov["total"]
            if not isinstance(c, (int, float)) or not math.isfinite(c) or c < 0:
                raise EvidenceError("invalid complexity")
            if (
                cov.get("unit") != "statements"
                or not isinstance(total, int)
                or total <= 0
                or not isinstance(covered, int)
                or not 0 <= covered <= total
            ):
                raise EvidenceError("invalid coverage denominator")
            expected = c * c * (1 - covered / total) ** 3 + c
            if q["crap"].get("coverage_basis") != "statements" or not math.isclose(
                q["crap"]["value"], expected, rel_tol=1e-12
            ):
                raise EvidenceError("CRAP calculation mismatch")
            if not q.get("mutation", {}).get("records"):
                raise EvidenceError("available quality lacks mutation outcomes")
    return s


def verify_artifacts(root, artifacts):
    seen = set()
    for a in artifacts:
        if a["path"] in seen:
            raise EvidenceError("duplicate artifact path")
        seen.add(a["path"])
        p = contained(root, a["path"])
        if not p.is_file() or digest(p.read_bytes()) != a["sha256"]:
            raise EvidenceError("artifact mismatch: " + a["path"])


def load_snapshot(root):
    root = Path(root)
    s = validate_snapshot(read_json(root / "snapshot.json"))
    verify_artifacts(root, s["artifacts"])
    if (root / "graph.json").exists() and read_json(root / "graph.json") != s["graph"]:
        raise EvidenceError("normalized graph mismatch")
    return s


def validate_packet(p):
    if not isinstance(p, dict):
        raise EvidenceError("packet must be object")
    if p.get("schema_version") != 1 or p.get("kind") != "packet":
        raise EvidenceError("unsupported packet schema")
    validate_snapshot(p["baseline"])
    validate_snapshot(p["candidate"])
    for k in ("policy_result", "overall_result"):
        if p.get(k) not in ("pass", "fail", "inconclusive"):
            raise EvidenceError("invalid result")
    return p


def load_packet(root):
    root = Path(root)
    p = validate_packet(read_json(root / "packet.json"))
    verify_artifacts(root, p["artifacts"])
    if (
        read_json(root / "policy.json") != p["policy"]
        or read_json(root / "policy-approval.json") != p["approval"]
    ):
        raise EvidenceError("embedded policy/approval mismatch")
    for side in ("baseline", "candidate"):
        if load_snapshot(root / side) != p[side]:
            raise EvidenceError("embedded snapshot mismatch")
    if p["approval"]:
        for key, textkey in [
            ("plan_file", "plan_text"),
            ("events_file", "events_text"),
        ]:
            if (
                contained(root, p["approval"][key]).read_text()
                != p["approval"][textkey]
            ):
                raise EvidenceError("approval artifact mismatch")
    from .policy import evaluate
    from .delta import compare_graphs

    d = compare_graphs(p["baseline"]["graph"], p["candidate"]["graph"])
    if d != p["delta"]:
        raise EvidenceError("delta mismatch")
    result = evaluate(p["baseline"], p["candidate"], d, p["policy"], p["approval"])
    for key in ("policy_result", "overall_result", "findings", "gaps"):
        if p[key] != result[key]:
            raise EvidenceError(f"{key} mismatch")
    return p
