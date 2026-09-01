#!/usr/bin/env python3
"""Capture read-only remote state after a failed publication attempt."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from release_gate import ContractError, file_sha256, load_plan, write_canonical_json


def _remote_ref(repository_url: str, ref: str) -> str | None:
    result = subprocess.run(
        ["git", "ls-remote", repository_url, ref],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise ContractError(f"cannot inspect {ref}: {result.stderr.strip()}")
    line = result.stdout.strip()
    return line.split()[0] if line else None


def _public_release(repository: str, tag: str) -> dict:
    url = f"https://api.github.com/repos/{repository}/releases/tags/{urllib.parse.quote(tag, safe='')}"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "flow-release-reconciler"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"exists": False, "url": "", "tag": "", "body_sha256": ""}
        raise ContractError(f"cannot inspect public GitHub release: {exc}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot inspect public GitHub release: {exc}") from exc
    body = payload.get("body")
    return {
        "exists": True,
        "url": payload.get("html_url") or payload.get("url") or "",
        "tag": payload.get("tag_name") or "",
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()
        if isinstance(body, str)
        else "",
    }


def reconcile(plan_path: Path, repository_url: str, github_repository: str) -> dict:
    plan = load_plan(plan_path)
    if not plan["release_required"]:
        raise ContractError("publication reconciliation requires a release plan")
    predicted = plan["predicted_release"]
    errors = []
    try:
        main_sha = _remote_ref(repository_url, "refs/heads/main")
    except ContractError as exc:
        main_sha = None
        errors.append(str(exc))
    try:
        tag_sha = _remote_ref(repository_url, f"refs/tags/{predicted['tag']}^{{}}")
        if tag_sha is None:
            tag_sha = _remote_ref(repository_url, f"refs/tags/{predicted['tag']}")
    except ContractError as exc:
        tag_sha = None
        errors.append(str(exc))
    try:
        release = _public_release(github_repository, predicted["tag"])
    except ContractError as exc:
        release = {"exists": None, "url": "", "tag": "", "body_sha256": ""}
        errors.append(str(exc))
    changed = main_sha not in {None, plan["source_sha"]} or tag_sha is not None or release["exists"] is True
    classification = "inspection-incomplete" if errors else (
        "partial-publication-observed" if changed else "publication-failed-without-observed-write"
    )
    return {
        "schema_version": 1,
        "classification": classification,
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "plan_digest": file_sha256(plan_path),
        "source_sha": plan["source_sha"],
        "expected_tag": predicted["tag"],
        "semantic_release_outcome": "failure",
        "observed": {"main_sha": main_sha, "tag_sha": tag_sha, "github_release": release},
        "inspection_errors": errors,
        "recovery": "preserve remote state; inspect the release runbook; repair forward without retry, force-push, or deletion",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--repository-url", required=True)
    parser.add_argument("--github-repository", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        write_canonical_json(
            args.output,
            reconcile(args.plan, args.repository_url, args.github_repository),
        )
        return 0
    except ContractError as exc:
        print(f"publication reconciliation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
