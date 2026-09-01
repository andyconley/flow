#!/usr/bin/env python3
"""Verify Flow's published tag and consumer paths without mutating the release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from release_candidate import _clean_env, _combine, _flow, _install, _run
from release_gate import (
    ContractError,
    file_sha256,
    load_evidence,
    load_plan,
    validate_release_commit_shape,
    write_canonical_json,
)


def _checked(argv: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    code, output = _run(argv, cwd=cwd, env=env)
    if code:
        raise ContractError(f"{' '.join(argv)} failed:\n{output}")
    return output.strip()


def _release_body(repository: str, tag: str, fixture: Path | None) -> tuple[str, str]:
    if fixture:
        payload = json.loads(fixture.read_text(encoding="utf-8"))
    else:
        output = _checked(
            ["gh", "api", f"repos/{repository}/releases/tags/{tag}"],
            cwd=Path.cwd(),
            env=_clean_env(),
        )
        payload = json.loads(output)
    if payload.get("tag_name") != tag:
        raise ContractError("GitHub release tag does not match the release plan")
    body = payload.get("body")
    url = payload.get("html_url") or payload.get("url")
    if not isinstance(body, str) or not body.strip():
        raise ContractError("GitHub release notes are empty")
    if not isinstance(url, str) or not url:
        raise ContractError("GitHub release URL is missing")
    return body, url


def _install_previous_from_public(remote: str, tag: str, home: Path, temp_root: Path) -> tuple[int, str]:
    clone = temp_root / "previous-source"
    code, output = _run(
        ["git", "clone", "--depth", "1", "--branch", tag, "--quiet", remote, str(clone)],
        cwd=temp_root,
        env=_clean_env(home),
    )
    if code:
        return code, output
    env = _clean_env(home)
    env["FLOW_VERSION_OVERRIDE"] = tag
    install = _run(["bash", str(clone / "install-flow.sh"), "--release"], cwd=clone, env=env)
    if install[0]:
        return install
    return _combine(install, _flow(home, "update", "--remote", remote))


def verify(
    plan_path: Path,
    evidence_path: Path,
    repository_url: str,
    github_repository: str,
    output_path: Path,
    release_fixture: Path | None,
) -> dict:
    plan = load_plan(plan_path)
    evidence = load_evidence(evidence_path, plan=plan)
    if evidence["overall_result"] != "passed":
        raise ContractError("published verification requires passing candidate evidence")
    if not plan["release_required"]:
        raise ContractError("published verification cannot run for a no-release plan")
    predicted = plan["predicted_release"]

    result: dict = {
        "schema_version": 1,
        "classification": "published-verification-failed",
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_sha": plan["source_sha"],
        "version": predicted["version"],
        "tag": predicted["tag"],
        "plan_digest": file_sha256(plan_path),
        "evidence_digest": file_sha256(evidence_path),
        "checks": [],
        "release_url": "",
        "release_commit": "",
        "overall_result": "failed",
        "recovery": "preserve published state and repair forward with a corrective commit",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.TemporaryDirectory(prefix="flow-published-verify-") as raw:
            temp_root = Path(raw)
            clone = temp_root / "repository"
            _checked(["git", "clone", "--quiet", repository_url, str(clone)], cwd=temp_root)
            _checked(["git", "fetch", "--force", "origin", "main", "tag", predicted["tag"]], cwd=clone)
            release_commit = _checked(["git", "rev-parse", f"{predicted['tag']}^{{commit}}"], cwd=clone)
            parents = _checked(["git", "show", "-s", "--format=%P", release_commit], cwd=clone).split()
            branch_tip = _checked(["git", "rev-parse", "origin/main"], cwd=clone)
            subject = _checked(["git", "show", "-s", "--format=%s", release_commit], cwd=clone)
            changed = _checked(
                ["git", "diff-tree", "--no-commit-id", "--name-status", "-r", plan["source_sha"], release_commit],
                cwd=clone,
            )
            changes = []
            for line in changed.splitlines():
                status, path = line.split("\t", 1)
                changes.append({"status": status, "path": path})
            changelog = _checked(["git", "show", f"{predicted['tag']}:CHANGELOG.md"], cwd=clone)
            shape = {
                "tag": predicted["tag"],
                "release_commit": release_commit,
                "parents": parents,
                "branch_tip": branch_tip,
                "changes": changes,
                "subject": subject,
                "changelog_has_section": f"## [{predicted['version']}]" in changelog,
            }
            validate_release_commit_shape(plan, shape)
            result["release_commit"] = release_commit
            result["checks"].append({"id": "tag-and-generated-commit", "result": "passed"})

            body, release_url = _release_body(github_repository, predicted["tag"], release_fixture)
            if hashlib.sha256(body.encode("utf-8")).hexdigest() != predicted["notes_sha256"]:
                raise ContractError("GitHub release notes digest does not match the plan")
            result["release_url"] = release_url
            result["checks"].append({"id": "github-release-and-notes", "result": "passed"})

            fresh_home = temp_root / "fresh-home"
            upgrade_home = temp_root / "upgrade-home"
            fresh_home.mkdir()
            upgrade_home.mkdir()
            fresh = _install(repository_url, fresh_home)
            if fresh[0]:
                raise ContractError(f"public fresh install failed:\n{fresh[1]}")
            result["checks"].append({"id": "public-fresh-install", "result": "passed"})

            upgrade = _install_previous_from_public(
                repository_url,
                plan["previous_release"]["tag"],
                upgrade_home,
                temp_root,
            )
            if upgrade[0]:
                raise ContractError(f"public upgrade failed:\n{upgrade[1]}")
            result["checks"].append({"id": "public-upgrade", "result": "passed"})

            installed_checks = [
                ("setup-machine", ("setup", "machine")),
                ("setup-user", ("setup", "user")),
                ("claude-sync-check", ("sync", "claude", "--user", "--check")),
                ("codex-sync-check", ("sync", "codex", "--user", "--check")),
                ("doctor-check", ("doctor", "--check")),
                ("runtime-smoke-static", ("runtime", "smoke", "--target", "all")),
                ("representative-cli", ("update", "--check", "--json", "--remote", repository_url)),
            ]
            for check_id, arguments in installed_checks:
                code, output = _flow(fresh_home, *arguments)
                if code:
                    raise ContractError(f"{check_id} failed:\n{output}")
                result["checks"].append({"id": check_id, "result": "passed"})

        result["classification"] = "published-verification-passed"
        result["overall_result"] = "passed"
        result["recovery"] = "none"
        write_canonical_json(output_path, result)
        return result
    except Exception as exc:
        result["checks"].append({"id": "failure", "result": "failed", "detail": str(exc)})
        write_canonical_json(output_path, result)
        if isinstance(exc, ContractError):
            raise
        raise ContractError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--repository-url", required=True)
    parser.add_argument("--github-repository", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--release-json", type=Path, help="test-only read-only release API fixture")
    parser.add_argument("--defer-exit", action="store_true", help="retain a failed result for upload before a later assertion fails the job")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = verify(
            args.plan,
            args.evidence,
            args.repository_url,
            args.github_repository,
            args.output,
            args.release_json,
        )
        print(f"published verification: {result['overall_result']}")
        return 0
    except ContractError as exc:
        print(f"published verification failed; preserve release and repair forward: {exc}", file=sys.stderr)
        return 0 if args.defer_exit else 1


if __name__ == "__main__":
    raise SystemExit(main())
