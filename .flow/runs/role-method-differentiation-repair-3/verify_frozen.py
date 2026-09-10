#!/usr/bin/env python3
"""Verify repair-3 frozen inputs without changing them."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / ".flow/runs/role-method-differentiation-repair-3"
EVIDENCE = RUN / "evidence"
COMPOSED_ROLES = {
    "architect",
    "business-analyst",
    "lead-developer",
    "sre",
    "support-lead",
    "test-engineer",
}
BASE_ROLE_HASHES = {
    "product-manager": "db45fab8ca7a50d78d25f149f560f4076bc86002ce5627960da274c71dd3d54b",
    "quality-reviewer": "4cd2d84d7500bc240bafb5c79f7f3cf8cff738195b870aad5ed4acbe0eea3592",
}
STATE_BASELINE_SHA256 = (
    "237cf7b512e212f586e9a8d283346244e51932f8cac06bea72e3ff8572d7a8ea"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(paths: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(paths):
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(sha256(ROOT / relative).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def production_digest(records: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for item in sorted(records, key=lambda value: str(value["path"])):
        relative = str(item["path"])
        value = "ABSENT" if item["state"] == "absent" else str(item["sha256"])
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(value.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("preimplementation", "final"),
        default="preimplementation",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start = json.loads((EVIDENCE / "start-receipt.json").read_text())
    inventory = json.loads((EVIDENCE / "preservation-inventory.json").read_text())
    release_map = json.loads((EVIDENCE / "release-evidence-map.json").read_text())
    checks: list[dict[str, object]] = []

    def record(name: str, expected: object, actual: object) -> None:
        checks.append({
            "name": name,
            "expected": expected,
            "actual": actual,
            "ok": expected == actual,
        })

    if args.mode == "preimplementation":
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        diff = subprocess.check_output(["git", "diff", "--binary"], cwd=ROOT)
        record("repository.head", start["repository"]["head"], head)
        record(
            "repository.tracked_diff_sha256",
            start["repository"]["tracked_diff_sha256"],
            hashlib.sha256(diff).hexdigest(),
        )
    record(
        "protected_inventory.sha256",
        start["protected_inventory"]["sha256"],
        sha256(EVIDENCE / "preservation-inventory.json"),
    )
    record(
        "release_evidence_map.sha256",
        start["release_evidence_map"]["sha256"],
        sha256(EVIDENCE / "release-evidence-map.json"),
    )

    for relative, expected in sorted(start["files"].items()):
        path = ROOT / relative
        record(f"retained:{relative}", expected, sha256(path) if path.is_file() else None)

    inventory_paths = list(inventory["files"])
    for relative, expected in sorted(inventory["files"].items()):
        path = ROOT / relative
        record(f"protected:{relative}", expected, sha256(path) if path.is_file() else None)

    for tree in start["evidence_trees"]:
        prefix = f'{tree["path"]}/'
        paths = [path for path in inventory_paths if path.startswith(prefix)]
        record(f'tree:{tree["path"]}:file_count', tree["file_count"], len(paths))
        record(f'tree:{tree["path"]}:sha256', tree["sha256"], tree_digest(paths))

    roles = release_map["roles"]
    record(
        "release_map.roles",
        ["architect", "lead-developer", "test-engineer"],
        sorted(role["role"] for role in roles),
    )
    for role in roles:
        role_name = role["role"]
        record(f"release_map:{role_name}:gate", "pass", role.get("gate_result"))
        for label in ("role_body", "corpus", "result"):
            item = role[label]
            path = ROOT / item["path"]
            record(
                f"release_map:{role_name}:{label}",
                item["sha256"],
                sha256(path) if path.is_file() else None,
            )
        corpus = json.loads((ROOT / role["corpus"]["path"]).read_text())
        graph = corpus.get("@graph", [])
        actual_ids = sorted(item.get("@id") for item in graph)
        record(
            f"release_map:{role_name}:entry_ids",
            sorted(role["entry_ids"]),
            actual_ids,
        )
        source_entries = graph
        if role.get("behavioral_method_entry_id"):
            source_entries = [
                item for item in graph
                if item.get("@id") == role["behavioral_method_entry_id"]
            ]
        locators = sorted(
            f'{source.get("citation", {}).get("author")}, '
            f'{source.get("citation", {}).get("name")}: '
            f'{source.get("flow:locator")}'
            for item in source_entries
            for source in item.get("flow:source", [])
        )
        expected_locators = sorted(role["source_locators"])
        normalize = lambda value: re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
        checks.append({
            "name": f"release_map:{role_name}:source_locators",
            "expected": expected_locators,
            "actual": locators,
            "comparison": "case-insensitive words; punctuation ignored",
            "ok": [normalize(value) for value in expected_locators]
            == [normalize(value) for value in locators],
        })
        for record_name, pair in sorted(role["records"].items()):
            path = ROOT / pair[0]
            record(
                f"release_map:{role_name}:record:{record_name}",
                pair[1],
                sha256(path) if path.is_file() else None,
            )

    if args.mode == "final":
        manifest = tomllib.loads((ROOT / "scaffolds/default/flow.toml").read_text())
        composed = {
            agent["name"]
            for agent in manifest["agents"]
            if agent.get("generation_mode") == "composed"
        }
        record("active.composed_roles", sorted(COMPOSED_ROLES), sorted(composed))

        for role, expected in sorted(BASE_ROLE_HASHES.items()):
            body = ROOT / f"scaffolds/default/agents/{role}.md"
            corpus = ROOT / f"scaffolds/default/expertise/{role}.jsonld"
            record(f"active:{role}:base_body", expected, sha256(body))
            record(f"active:{role}:corpus_absent", False, corpus.exists())

        vocabulary = (ROOT / "scaffolds/default/expertise/competencies.md").read_text()
        terms = re.findall(r"(?m)^### (.+)$", vocabulary)
        taught_blocks = re.findall(r'(?ms)^- Taught by: (.*?)(?:\n\n|\Z)', vocabulary)
        edges = sum(len(re.findall(r'"[^"]+"', block)) for block in taught_blocks)
        record("active.vocabulary.term_count", 16, len(terms))
        record("active.vocabulary.edge_count", 21, edges)
        record(
            "active.vocabulary.product_manager_absent",
            False,
            "Roles: product-manager" in vocabulary,
        )
        record(
            "active.vocabulary.quality_reviewer_absent",
            False,
            "Roles: quality-reviewer" in vocabulary,
        )
        record(
            "excluded_worktree_baseline.sha256",
            STATE_BASELINE_SHA256,
            sha256(ROOT / ".flow/memory/STATE.md"),
        )

        surface = json.loads((EVIDENCE / "change-surface.json").read_text())
        production = surface["candidate"]["production_paths"]
        production_paths = {str(item["path"]) for item in production}
        record(
            "candidate.required_predecessor_paths",
            True,
            {
                "cli/expertise.py",
                "docs/adr/0008-author-expertise-entries-as-json-ld-per-role.md",
            }.issubset(production_paths),
        )
        for item in production:
            relative = str(item["path"])
            path = ROOT / relative
            actual_state = "present" if path.is_file() else "absent"
            actual_sha = sha256(path) if path.is_file() else None
            record(f"candidate:{relative}:state", item["state"], actual_state)
            record(f"candidate:{relative}:sha256", item["sha256"], actual_sha)
        record(
            "candidate.production_path_count",
            surface["candidate"]["production_path_count"],
            len(production),
        )
        record(
            "candidate.production_sha256",
            surface["candidate"]["sha256"],
            production_digest(production),
        )
        record("candidate.change_surface_verdict", "pass", surface["verdict"])

        command_receipt = json.loads((EVIDENCE / "logs/receipt.json").read_text())
        record(
            "command_receipt.candidate_T",
            surface["candidate"]["sha256"],
            command_receipt["candidate_T"],
        )
        record(
            "command_receipt.all_expected_exits_observed",
            True,
            command_receipt["all_expected_exits_observed"],
        )
        for item in command_receipt["commands"]:
            path = ROOT / item["log_path"]
            record(
                f'command_receipt:{item["name"]}:log_sha256',
                item["log_sha256"],
                sha256(path) if path.is_file() else None,
            )

        live = json.loads((EVIDENCE / "live-client-records.json").read_text())
        record("live.candidate_T", surface["candidate"]["sha256"], live["candidate_T"])
        record(
            "live.claude.raw_capture_sha256",
            live["role_checks"]["claude"]["raw_capture_sha256"],
            sha256(EVIDENCE / "live/claude-test-engineer.json"),
        )
        record(
            "live.codex.raw_capture_sha256",
            live["role_checks"]["codex"]["raw_capture_sha256"],
            sha256(EVIDENCE / "live/codex-test-engineer.jsonl"),
        )

    failures = [check for check in checks if not check["ok"]]
    output = {
        "schema_version": 1,
        "captured_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "validator": ".flow/runs/role-method-differentiation-repair-3/verify_frozen.py",
        "mode": args.mode,
        "ok": not failures,
        "check_count": len(checks),
        "failure_count": len(failures),
        "failures": failures,
        "excluded_worktree_baseline": {
            "path": ".flow/memory/STATE.md",
            "sha256": sha256(ROOT / ".flow/memory/STATE.md"),
            "disposition": "preserve unchanged and unstaged",
        },
        "checks": checks,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
