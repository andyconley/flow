#!/usr/bin/env python3
"""Fail-closed contracts used by Flow's release workflow.

Semantic-release remains responsible for deciding whether and what to release.
This module only validates its structured Action outputs, binds candidate
evidence to that decision, and exposes pure guards before a publisher is called.
Release notes are always handled as data; this module never builds shell text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence


PLAN_SCHEMA_VERSION = 1
EVIDENCE_SCHEMA_VERSION = 1
PUBLICATION_SCHEMA_VERSION = 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[-0-9A-Za-z.]+)?(?:\+[-0-9A-Za-z.]+)?$")
RELEASE_TYPES = frozenset({"major", "minor", "patch"})
STABLE_CHECK_IDS = (
    "python-test-suite",
    "generated-help",
    "release-staging",
    "clean-tracked-tree",
    "candidate-fresh-install",
    "candidate-upgrade",
    "setup-machine",
    "setup-user",
    "claude-sync-check",
    "codex-sync-check",
    "doctor-check",
    "runtime-smoke-static",
    "representative-cli",
)

POLICY_VERSIONS = {
    "semantic-release": "25.0.9",
    "@semantic-release/changelog": "7.0.0",
    "@semantic-release/git": "11.0.1",
    "conventional-changelog-conventionalcommits": "9.3.1",
}


class ContractError(ValueError):
    """A release artifact failed its fail-closed contract."""


def canonical_json_bytes(data: Any) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def canonical_digest(data: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(data)).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_canonical_json(path: str | Path, data: Any) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(data)
    target.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _require_exact_keys(data: Mapping[str, Any], required: set[str], context: str) -> None:
    actual = set(data)
    missing = sorted(required - actual)
    extra = sorted(actual - required)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if extra:
            details.append(f"unknown {', '.join(extra)}")
        raise ContractError(f"{context}: {'; '.join(details)}")


def _string(value: Any, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ContractError(f"{name} must be a{' possibly empty' if allow_empty else ' non-empty'} string")
    if "\x00" in value:
        raise ContractError(f"{name} contains a NUL byte")
    return value


def _sha(value: Any, name: str) -> str:
    value = _string(value, name)
    if not GIT_SHA_RE.fullmatch(value):
        raise ContractError(f"{name} must be a lowercase 40-character Git SHA")
    return value


def _semver(value: Any, name: str) -> str:
    value = _string(value, name)
    if not SEMVER_RE.fullmatch(value):
        raise ContractError(f"{name} must be a semantic version")
    return value


def _release_type(previous: str, next_version: str) -> str:
    """Classify semantic-release's already-selected stable version transition."""
    previous_parts = tuple(int(part) for part in previous.split("."))
    next_parts = tuple(int(part) for part in next_version.split("."))
    if next_parts[0] == previous_parts[0] + 1 and next_parts[1:] == (0, 0):
        return "major"
    if next_parts[0] == previous_parts[0] and next_parts[1] == previous_parts[1] + 1 and next_parts[2] == 0:
        return "minor"
    if next_parts[:2] == previous_parts[:2] and next_parts[2] == previous_parts[2] + 1:
        return "patch"
    raise ContractError(f"cannot classify release transition {previous} -> {next_version}")


def _tag(value: Any, version: str, name: str) -> str:
    value = _string(value, name)
    if value != f"v{version}" or any(ch.isspace() for ch in value):
        raise ContractError(f"{name} must equal v{version}")
    return value


def _safe_relative_path(value: Any, name: str) -> str:
    value = _string(value, name)
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value.startswith("~") or "\\" in value:
        raise ContractError(f"{name} must be a safe relative POSIX path")
    return value


def _policy_identity(versions: Mapping[str, str]) -> str:
    return canonical_digest({"versions": dict(versions), "config": "release.config.cjs", "revision": 1})


def validate_plan(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ContractError("release plan must be an object")
    _require_exact_keys(data, {
        "schema_version", "workflow", "source_sha", "previous_release",
        "release_required", "predicted_release", "policy", "created_at",
    }, "release plan")
    if data["schema_version"] != PLAN_SCHEMA_VERSION:
        raise ContractError(f"unsupported release plan schema_version {data['schema_version']!r}")
    _sha(data["source_sha"], "source_sha")
    _string(data["created_at"], "created_at")
    if not isinstance(data["release_required"], bool):
        raise ContractError("release_required must be a boolean")

    workflow = data["workflow"]
    if not isinstance(workflow, dict):
        raise ContractError("workflow must be an object")
    _require_exact_keys(workflow, {"repository", "workflow", "run_id", "run_attempt"}, "workflow")
    for key in workflow:
        _string(workflow[key], f"workflow.{key}")

    previous = data["previous_release"]
    if not isinstance(previous, dict):
        raise ContractError("previous_release must be an object")
    _require_exact_keys(previous, {"version", "tag", "commit"}, "previous_release")
    previous_version = _semver(previous["version"], "previous_release.version")
    _tag(previous["tag"], previous_version, "previous_release.tag")
    _sha(previous["commit"], "previous_release.commit")

    policy = data["policy"]
    if not isinstance(policy, dict):
        raise ContractError("policy must be an object")
    _require_exact_keys(policy, {"identity", "versions"}, "policy")
    if policy["versions"] != POLICY_VERSIONS:
        raise ContractError("policy.versions does not match the pinned release policy")
    expected_policy = _policy_identity(POLICY_VERSIONS)
    if policy["identity"] != expected_policy:
        raise ContractError("policy.identity does not match the release policy")

    predicted = data["predicted_release"]
    if not data["release_required"]:
        if predicted is not None:
            raise ContractError("predicted_release must be null when no release is required")
        return data
    if not isinstance(predicted, dict):
        raise ContractError("predicted_release must be an object when a release is required")
    _require_exact_keys(predicted, {"type", "version", "tag", "notes", "notes_sha256", "rendered_entry_count"}, "predicted_release")
    release_type = _string(predicted["type"], "predicted_release.type")
    if release_type not in RELEASE_TYPES:
        raise ContractError(f"unsupported predicted_release.type {release_type!r}")
    version = _semver(predicted["version"], "predicted_release.version")
    _tag(predicted["tag"], version, "predicted_release.tag")
    notes = _string(predicted["notes"], "predicted_release.notes")
    if not notes.strip():
        raise ContractError("predicted_release.notes must contain non-whitespace text")
    if predicted["notes_sha256"] != hashlib.sha256(notes.encode("utf-8")).hexdigest():
        raise ContractError("predicted_release.notes_sha256 does not match notes")
    if not isinstance(predicted["rendered_entry_count"], int) or isinstance(predicted["rendered_entry_count"], bool) or predicted["rendered_entry_count"] < 1:
        raise ContractError("predicted_release.rendered_entry_count must be a positive integer")
    return data


def load_plan(path: str | Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read release plan: {exc}") from exc
    return validate_plan(data)


def write_plan(path: str | Path, data: Any) -> str:
    return write_canonical_json(path, validate_plan(data))


def validate_evidence(data: Any, *, plan: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ContractError("release evidence must be an object")
    _require_exact_keys(data, {
        "schema_version", "plan_digest", "source_sha", "candidate_version",
        "candidate_tag", "candidate_repository", "runner_sha", "checks", "overall_result",
    }, "release evidence")
    if data["schema_version"] != EVIDENCE_SCHEMA_VERSION:
        raise ContractError(f"unsupported release evidence schema_version {data['schema_version']!r}")
    if not SHA256_RE.fullmatch(_string(data["plan_digest"], "plan_digest")):
        raise ContractError("plan_digest must be a lowercase SHA-256 digest")
    _sha(data["source_sha"], "source_sha")
    version = _semver(data["candidate_version"], "candidate_version")
    _tag(data["candidate_tag"], version, "candidate_tag")
    _sha(data["runner_sha"], "runner_sha")
    repository = data["candidate_repository"]
    if not isinstance(repository, dict):
        raise ContractError("candidate_repository must be an object")
    _require_exact_keys(repository, {"url", "main_sha", "tag_sha"}, "candidate_repository")
    url = _string(repository["url"], "candidate_repository.url")
    if not url.startswith("file://"):
        raise ContractError("candidate_repository.url must identify an isolated file:// repository")
    if _sha(repository["main_sha"], "candidate_repository.main_sha") != data["source_sha"]:
        raise ContractError("candidate repository main does not match source_sha")
    if _sha(repository["tag_sha"], "candidate_repository.tag_sha") != data["source_sha"]:
        raise ContractError("candidate repository tag does not match source_sha")

    checks = data["checks"]
    if not isinstance(checks, list):
        raise ContractError("checks must be an array")
    observed_ids = []
    all_passed = True
    stopped = False
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            raise ContractError(f"checks[{index}] must be an object")
        _require_exact_keys(check, {"id", "result", "exit_code", "duration_ms", "log_path", "log_sha256"}, f"checks[{index}]")
        check_id = _string(check["id"], f"checks[{index}].id")
        observed_ids.append(check_id)
        if check["result"] not in {"passed", "failed", "not_run"}:
            raise ContractError(f"checks[{index}].result must be passed, failed, or not_run")
        if not isinstance(check["duration_ms"], int) or isinstance(check["duration_ms"], bool) or check["duration_ms"] < 0:
            raise ContractError(f"checks[{index}].duration_ms must be a non-negative integer")
        _safe_relative_path(check["log_path"], f"checks[{index}].log_path")
        if not SHA256_RE.fullmatch(_string(check["log_sha256"], f"checks[{index}].log_sha256")):
            raise ContractError(f"checks[{index}].log_sha256 must be a lowercase SHA-256 digest")
        passed = check["result"] == "passed"
        if check["result"] == "not_run":
            if check["exit_code"] is not None or check["duration_ms"] != 0:
                raise ContractError(f"checks[{index}] not_run result requires null exit_code and zero duration")
            stopped = True
        else:
            if not isinstance(check["exit_code"], int) or isinstance(check["exit_code"], bool):
                raise ContractError(f"checks[{index}].exit_code must be an integer")
            if passed != (check["exit_code"] == 0):
                raise ContractError(f"checks[{index}] result and exit_code disagree")
            if stopped:
                raise ContractError(f"checks[{index}] cannot run after a failed or not_run check")
            if check["result"] == "failed":
                stopped = True
        all_passed = all_passed and passed
    if tuple(observed_ids) != STABLE_CHECK_IDS:
        raise ContractError("checks must contain every stable check ID exactly once and in order")
    expected_overall = "passed" if all_passed else "failed"
    if data["overall_result"] != expected_overall:
        raise ContractError(f"overall_result must be {expected_overall}")

    if plan is not None:
        validate_plan(plan)
        if not plan["release_required"]:
            raise ContractError("candidate evidence cannot authorize a no-release plan")
        predicted = plan["predicted_release"]
        comparisons = {
            "plan_digest": canonical_digest(plan),
            "source_sha": plan["source_sha"],
            "candidate_version": predicted["version"],
            "candidate_tag": predicted["tag"],
        }
        for field, expected in comparisons.items():
            if data[field] != expected:
                raise ContractError(f"evidence {field} does not match release plan")
    return data


def load_evidence(path: str | Path, *, plan: Mapping[str, Any] | None = None) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read release evidence: {exc}") from exc
    return validate_evidence(data, plan=plan)


def write_evidence(path: str | Path, data: Any, *, plan: Mapping[str, Any] | None = None) -> str:
    return write_canonical_json(path, validate_evidence(data, plan=plan))


def compare_analysis(plan: Mapping[str, Any], repeated: Mapping[str, Any]) -> None:
    validate_plan(plan)
    validate_plan(repeated)
    protected = ("source_sha", "previous_release", "release_required", "predicted_release", "policy")
    drift = [field for field in protected if plan[field] != repeated[field]]
    if drift:
        raise ContractError(f"repeated release analysis drifted: {', '.join(drift)}")


def authorize_publication(
    plan: Mapping[str, Any],
    evidence: Mapping[str, Any],
    repeated: Mapping[str, Any],
    publisher: Callable[[], Any],
) -> Any:
    """Call publisher exactly once, but only after all contracts pass."""
    validate_plan(plan)
    validate_evidence(evidence, plan=plan)
    compare_analysis(plan, repeated)
    if evidence["overall_result"] != "passed":
        raise ContractError("candidate evidence did not pass")
    return publisher()


def validate_release_commit_shape(plan: Mapping[str, Any], shape: Mapping[str, Any]) -> None:
    """Validate the exact changelog-only commit semantic-release is allowed to add."""
    validate_plan(plan)
    if not plan["release_required"]:
        raise ContractError("a no-release plan cannot have a generated release commit")
    required = {"tag", "release_commit", "parents", "branch_tip", "changes", "subject", "changelog_has_section"}
    if not isinstance(shape, dict):
        raise ContractError("release commit shape must be an object")
    _require_exact_keys(shape, required, "release commit shape")
    predicted = plan["predicted_release"]
    if shape["tag"] != predicted["tag"]:
        raise ContractError("published tag does not match the release plan")
    release_commit = _sha(shape["release_commit"], "release_commit")
    if shape["branch_tip"] != release_commit:
        raise ContractError("origin/main must resolve to the generated release commit")
    if shape["parents"] != [plan["source_sha"]]:
        raise ContractError("generated release commit must have exactly the planned source as its parent")
    if shape["changes"] != [{"status": "M", "path": "CHANGELOG.md"}]:
        raise ContractError("generated release commit may modify only CHANGELOG.md")
    expected_subject = f"chore(release): {predicted['version']} [skip ci]"
    if shape["subject"] != expected_subject:
        raise ContractError("generated release commit subject does not match policy")
    if shape["changelog_has_section"] is not True:
        raise ContractError("CHANGELOG.md does not contain the predicted version section")


def validate_publication_result(data: Any, *, plan: Mapping[str, Any]) -> dict[str, Any]:
    """Validate semantic-release's structured publication result against its plan."""
    validate_plan(plan)
    if not plan["release_required"]:
        raise ContractError("a no-release plan cannot have a publication result")
    if not isinstance(data, dict):
        raise ContractError("publication result must be an object")
    _require_exact_keys(data, {
        "schema_version", "source_sha", "version", "tag", "release_commit", "notes_sha256",
    }, "publication result")
    if data["schema_version"] != PUBLICATION_SCHEMA_VERSION:
        raise ContractError(f"unsupported publication result schema_version {data['schema_version']!r}")
    predicted = plan["predicted_release"]
    expected = {
        "source_sha": plan["source_sha"],
        "version": predicted["version"],
        "tag": predicted["tag"],
        "notes_sha256": predicted["notes_sha256"],
    }
    for field, value in expected.items():
        if data[field] != value:
            raise ContractError(f"publication {field} does not match release plan")
    _sha(data["release_commit"], "publication release_commit")
    return data


def publication_from_environment(plan: Mapping[str, Any], env: Mapping[str, str] = os.environ) -> dict[str, Any]:
    """Normalize publish-mode Action outputs without executing or parsing notes."""
    validate_plan(plan)
    published = _parse_bool(
        _env_value(env, "FLOW_RELEASE_NEW_RELEASE_PUBLISHED", "FLOW_RELEASE_PUBLISHED"),
        "FLOW_RELEASE_NEW_RELEASE_PUBLISHED",
    )
    if not published:
        raise ContractError("semantic-release did not report a published release")
    notes = _env_value(env, "FLOW_RELEASE_NEW_RELEASE_NOTES", "FLOW_RELEASE_NOTES")
    result = {
        "schema_version": PUBLICATION_SCHEMA_VERSION,
        "source_sha": plan["source_sha"],
        "version": _env_value(env, "FLOW_RELEASE_NEW_RELEASE_VERSION", "FLOW_RELEASE_VERSION"),
        "tag": _env_value(env, "FLOW_RELEASE_NEW_RELEASE_GIT_TAG", "FLOW_RELEASE_TAG"),
        "release_commit": _env_value(env, "FLOW_RELEASE_NEW_RELEASE_GIT_HEAD"),
        "notes_sha256": hashlib.sha256(notes.encode("utf-8")).hexdigest(),
    }
    return validate_publication_result(result, plan=plan)


def verify_remote_baseline(plan: Mapping[str, Any], repository: str | Path, remote: str) -> dict[str, Any]:
    """Refresh and compare the live branch/tag baseline immediately before write."""
    validate_plan(plan)
    cwd = Path(repository)

    def git(*arguments: str) -> str:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if completed.returncode:
            raise ContractError(f"git {' '.join(arguments)} failed: {completed.stderr.strip()}")
        return completed.stdout.strip()

    git("fetch", "--force", remote, "refs/heads/main:refs/remotes/origin/main")
    git("fetch", "--force", "--tags", remote)
    main_sha = git("rev-parse", "refs/remotes/origin/main")
    tags = [
        value
        for value in git("tag", "--list", "--sort=-version:refname").splitlines()
        if re.fullmatch(r"v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", value)
    ]
    latest_tag = tags[0] if tags else ""
    latest_commit = git("rev-parse", f"{latest_tag}^{{commit}}") if latest_tag else ""
    previous = plan["previous_release"]
    if main_sha != plan["source_sha"]:
        raise ContractError("remote main moved after release analysis")
    if latest_tag != previous["tag"] or latest_commit != previous["commit"]:
        raise ContractError("latest remote release tag moved after release analysis")
    candidate_tag = plan["predicted_release"]["tag"] if plan["release_required"] else ""
    if candidate_tag and candidate_tag in tags:
        raise ContractError("predicted release tag already exists remotely")
    return {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "remote": remote,
        "main_sha": main_sha,
        "latest_tag": latest_tag,
        "latest_tag_commit": latest_commit,
        "candidate_tag_absent": bool(candidate_tag),
    }


def _env_value(env: Mapping[str, str], name: str, *aliases: str, required: bool = True) -> str:
    for candidate in (name, *aliases):
        if candidate in env:
            return env[candidate]
    if required:
        raise ContractError(f"missing environment value {name}")
    return ""


def _parse_bool(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ContractError(f"{name} must be true or false")
    return normalized == "true"


def plan_from_environment(env: Mapping[str, str] = os.environ) -> dict[str, Any]:
    """Normalize semantic-release Action outputs plus immutable workflow identity."""
    required = _parse_bool(
        _env_value(env, "FLOW_RELEASE_REQUIRED", "FLOW_RELEASE_PUBLISHED", "FLOW_RELEASE_NEW_RELEASE_PUBLISHED"),
        "FLOW_RELEASE_REQUIRED",
    )
    previous_version = _env_value(env, "FLOW_RELEASE_PREVIOUS_VERSION", "FLOW_RELEASE_LAST_RELEASE_VERSION")
    previous_tag = _env_value(env, "FLOW_RELEASE_PREVIOUS_TAG", "FLOW_RELEASE_LAST_RELEASE_GIT_TAG")
    previous_commit = _env_value(env, "FLOW_RELEASE_PREVIOUS_COMMIT", "FLOW_RELEASE_LAST_RELEASE_GIT_HEAD")
    predicted = None
    if required:
        notes = _env_value(env, "FLOW_RELEASE_NOTES", "FLOW_RELEASE_NEW_RELEASE_NOTES")
        version = _env_value(env, "FLOW_RELEASE_VERSION", "FLOW_RELEASE_NEW_RELEASE_VERSION")
        count = len(re.findall(r"(?m)^[*-] ", notes))
        supplied_count = _env_value(env, "FLOW_RELEASE_ENTRY_COUNT", required=False)
        if supplied_count:
            try:
                parsed_count = int(supplied_count)
            except ValueError as exc:
                raise ContractError("FLOW_RELEASE_ENTRY_COUNT must be an integer") from exc
            if parsed_count != count:
                raise ContractError("FLOW_RELEASE_ENTRY_COUNT does not match rendered notes")
        release_type = _env_value(env, "FLOW_RELEASE_TYPE", "FLOW_RELEASE_NEW_RELEASE_TYPE", required=False)
        derived_type = _release_type(_semver(previous_version, "previous release version"), _semver(version, "release version"))
        if release_type and release_type != derived_type:
            raise ContractError("FLOW_RELEASE_TYPE disagrees with the semantic-release version transition")
        new_head = _env_value(env, "FLOW_RELEASE_NEW_RELEASE_GIT_HEAD", required=False)
        source_sha = _env_value(env, "FLOW_RELEASE_SOURCE_SHA", "GITHUB_SHA")
        if new_head and new_head != source_sha:
            raise ContractError("semantic-release new_release_git_head does not match the analyzed source SHA")
        predicted = {
            "type": derived_type,
            "version": version,
            "tag": _env_value(env, "FLOW_RELEASE_TAG", "FLOW_RELEASE_NEW_RELEASE_GIT_TAG"),
            "notes": notes,
            "notes_sha256": hashlib.sha256(notes.encode("utf-8")).hexdigest(),
            "rendered_entry_count": count,
        }
    else:
        unexpected = [
            name for name in (
                "FLOW_RELEASE_VERSION", "FLOW_RELEASE_NEW_RELEASE_VERSION",
                "FLOW_RELEASE_TAG", "FLOW_RELEASE_NEW_RELEASE_GIT_TAG",
                "FLOW_RELEASE_NOTES", "FLOW_RELEASE_NEW_RELEASE_NOTES",
                "FLOW_RELEASE_NEW_RELEASE_GIT_HEAD",
            ) if env.get(name)
        ]
        if unexpected:
            raise ContractError(f"no-release analysis included release outputs: {', '.join(unexpected)}")

    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "workflow": {
            "repository": _env_value(env, "FLOW_RELEASE_REPOSITORY", "GITHUB_REPOSITORY"),
            "workflow": _env_value(env, "FLOW_RELEASE_WORKFLOW", "GITHUB_WORKFLOW"),
            "run_id": _env_value(env, "FLOW_RELEASE_RUN_ID", "GITHUB_RUN_ID"),
            "run_attempt": _env_value(env, "FLOW_RELEASE_RUN_ATTEMPT", "GITHUB_RUN_ATTEMPT"),
        },
        "source_sha": _env_value(env, "FLOW_RELEASE_SOURCE_SHA", "GITHUB_SHA"),
        "previous_release": {
            "version": previous_version,
            "tag": previous_tag,
            "commit": previous_commit,
        },
        "release_required": required,
        "predicted_release": predicted,
        "policy": {"identity": _policy_identity(POLICY_VERSIONS), "versions": dict(POLICY_VERSIONS)},
        "created_at": _env_value(env, "FLOW_RELEASE_CREATED_AT"),
    }
    return validate_plan(plan)


def _append_github_outputs(path: str | Path, values: Mapping[str, str]) -> None:
    with Path(path).open("a", encoding="utf-8") as stream:
        for key, value in values.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]*", key) or "\n" in value or "\r" in value:
                raise ContractError("GitHub output keys and values must be single-line controlled scalars")
            stream.write(f"{key}={value}\n")


def _plan_outputs(plan: Mapping[str, Any], digest: str) -> dict[str, str]:
    predicted = plan["predicted_release"] or {}
    return {
        "release_required": str(plan["release_required"]).lower(),
        "plan_digest": digest,
        "source_sha": plan["source_sha"],
        "version": predicted.get("version", ""),
        "tag": predicted.get("tag", ""),
        "release_type": predicted.get("type", ""),
        "previous_tag": plan["previous_release"]["tag"],
    }


def _assert_digest(actual: str, expected: str, name: str) -> None:
    if not SHA256_RE.fullmatch(expected) or actual != expected:
        raise ContractError(f"{name} digest mismatch")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="normalize environment values into a release plan")
    plan.add_argument("--output", required=True)
    plan.add_argument("--github-output")
    check_plan = sub.add_parser("validate-plan")
    check_plan.add_argument("--plan", required=True)
    check_plan.add_argument("--expected-digest")
    check_plan.add_argument("--expected-source-sha")
    check_plan.add_argument("--github-output")
    check_evidence = sub.add_parser("validate-evidence")
    check_evidence.add_argument("--plan", required=True)
    check_evidence.add_argument("--evidence", required=True)
    check_evidence.add_argument("--expected-digest")
    check_evidence.add_argument("--github-output")
    compare = sub.add_parser("compare-analysis")
    compare.add_argument("--plan", required=True)
    compare.add_argument("--github-output")
    publication = sub.add_parser("validate-publication")
    publication.add_argument("--plan", required=True)
    publication.add_argument("--output", required=True)
    publication.add_argument("--github-output")
    baseline = sub.add_parser("verify-remote-baseline")
    baseline.add_argument("--plan", required=True)
    baseline.add_argument("--repository", default=".")
    baseline.add_argument("--remote", default="origin")
    baseline.add_argument("--output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "plan":
            plan = plan_from_environment()
            digest = write_plan(args.output, plan)
            if args.github_output:
                _append_github_outputs(args.github_output, _plan_outputs(plan, digest))
        elif args.command == "validate-plan":
            plan = load_plan(args.plan)
            digest = file_sha256(args.plan)
            if args.expected_digest:
                _assert_digest(digest, args.expected_digest, "release plan")
            if args.expected_source_sha and plan["source_sha"] != args.expected_source_sha:
                raise ContractError("release plan source_sha mismatch")
            if args.github_output:
                _append_github_outputs(args.github_output, _plan_outputs(plan, digest))
        elif args.command == "validate-evidence":
            plan = load_plan(args.plan)
            evidence = load_evidence(args.evidence, plan=plan)
            digest = file_sha256(args.evidence)
            if args.expected_digest:
                _assert_digest(digest, args.expected_digest, "release evidence")
            if evidence["overall_result"] != "passed":
                raise ContractError("candidate evidence did not pass")
            if args.github_output:
                _append_github_outputs(args.github_output, {"evidence_digest": digest, "candidate_passed": "true"})
        elif args.command == "compare-analysis":
            plan = load_plan(args.plan)
            repeated = plan_from_environment()
            compare_analysis(plan, repeated)
            if args.github_output:
                _append_github_outputs(args.github_output, {"analysis_matches": "true"})
        elif args.command == "validate-publication":
            plan = load_plan(args.plan)
            publication = publication_from_environment(plan)
            digest = write_canonical_json(args.output, publication)
            if args.github_output:
                _append_github_outputs(args.github_output, {
                    "publication_digest": digest,
                    "release_commit": publication["release_commit"],
                    "published": "true",
                })
        elif args.command == "verify-remote-baseline":
            plan = load_plan(args.plan)
            baseline = verify_remote_baseline(plan, args.repository, args.remote)
            write_canonical_json(args.output, baseline)
        return 0
    except ContractError as exc:
        print(f"release gate: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
