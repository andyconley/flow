#!/usr/bin/env python3
"""Verify Flow's published tag and consumer paths without mutating the release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from release_candidate import _clean_env, _run
from release_gate import (
    ContractError,
    file_sha256,
    load_evidence,
    load_plan,
    validate_release_commit_shape,
    write_canonical_json,
)


def _checked(argv: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    code, output = _run(argv, cwd=cwd, env=_clean_env() if env is None else env)
    if code:
        raise ContractError(f"{' '.join(argv)} failed:\n{output}")
    return output.strip()


def _release_body(repository: str, tag: str, fixture: Path | None) -> tuple[str, str]:
    if fixture:
        payload = json.loads(fixture.read_text(encoding="utf-8"))
    else:
        url = f"https://api.github.com/repos/{repository}/releases/tags/{urllib.parse.quote(tag, safe='')}"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "flow-release-verifier"}
        if token := os.environ.get("FLOW_RELEASE_READ_TOKEN"):
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(
            url,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ContractError(f"cannot read public GitHub release: {exc}") from exc
    if payload.get("tag_name") != tag:
        raise ContractError("GitHub release tag does not match the release plan")
    body = payload.get("body")
    url = payload.get("html_url") or payload.get("url")
    if not isinstance(body, str) or not body.strip():
        raise ContractError("GitHub release notes are empty")
    if not isinstance(url, str) or not url:
        raise ContractError("GitHub release URL is missing")
    return body, url



def verify_public_manifest(manifest: dict, urls: dict, expected: str | None) -> None:
    if not expected or not re.fullmatch(r'[a-f0-9]{64}', expected):
        raise ContractError('Missing exact build-job manifest identity')
    with urllib.request.urlopen(urls['release-manifest.json'], timeout=30) as response:
        raw = response.read(1024*1024+1)
    if len(raw)>1024*1024 or hashlib.sha256(raw).hexdigest()!=expected or json.loads(raw)!=manifest:
        raise ContractError('Published manifest differs from the verified build job')


def verify(
    plan_path: Path,
    evidence_path: Path,
    repository_url: str,
    github_repository: str,
    output_path: Path,
    release_fixture: Path | None,
) -> dict:
    plan = load_plan(plan_path)
    evidence = load_evidence(evidence_path, plan=plan, logs_root=evidence_path.parent)
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

            sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'v2'))
            from poc import managed
            from v2_release_checks import flow
            distribution,urls=managed.latest(github_repository,predicted['tag'])
            verify_public_manifest(distribution,urls,os.environ.get('FLOW_RELEASE_MANIFEST_SHA'))
            if distribution['source_sha']!=plan['source_sha']:
                raise ContractError('Public distribution source differs from published plan')
            assets=temp_root/'assets';managed.fetch_assets(distribution,assets,urls)
            (assets/'release-manifest.json').write_text(json.dumps(distribution,indent=2)+'\n')
            result['checks'].append({'id':'public-assets-and-provenance','result':'passed'})
            fresh_home=temp_root/'fresh-home';fresh_home.mkdir()
            managed.install_release(fresh_home,distribution,bundle=assets)
            for check_id,arguments in [
                ('public-fresh-install',('--version',)),
                ('doctor-check',('doctor','--json')),
                ('public-release-update-check',('update','--check','--json','--repository',github_repository)),
                ('public-release-update',('update','--repository',github_repository))]:
                code,text=flow(fresh_home,*arguments)
                if code:raise ContractError(check_id+' failed: '+text)
                result['checks'].append({'id':check_id,'result':'passed','output':text})
            managed.rollback(fresh_home)
            result['checks'].append({'id':'public-rollback','result':'passed'})

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
