#!/usr/bin/env python3
"""Run Flow's deterministic release-candidate gate against a local-only tag."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path
from typing import Callable, Mapping

from release_gate import (
    EVIDENCE_SCHEMA_VERSION,
    STABLE_CHECK_IDS,
    ContractError,
    canonical_digest,
    file_sha256,
    load_plan,
    write_evidence,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
Result = tuple[int, str]


def _run(
    argv: list[str], *, cwd: Path = REPO_ROOT, env: dict[str, str] | None = None
) -> Result:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return completed.returncode, completed.stdout


def _git(*args: str, cwd: Path = REPO_ROOT) -> str:
    code, output = _run(["git", *args], cwd=cwd)
    if code:
        raise ContractError(f"git {' '.join(args)} failed:\n{output}")
    return output.strip()


def _clean_env(home: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    for name in (
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "FLOW_RELEASE_READ_TOKEN",
        "GIT_ASKPASS",
        "SSH_ASKPASS",
        "GIT_DIR",
        "GIT_WORK_TREE",
    ):
        env.pop(name, None)
    env["NO_COLOR"] = "1"
    if home is not None:
        env["HOME"] = str(home)
        env["PATH"] = f"{home / '.local' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env


def create_candidate_remote(plan: dict, destination: Path) -> str:
    _git("init", "--bare", str(destination))
    source_sha = plan["source_sha"]
    _git("push", str(destination), f"{source_sha}:refs/heads/main")
    candidate_tag = plan["predicted_release"]["tag"]
    # Copy historical tags, but construct the predicted candidate tag only in
    # the isolated remote. A checkout may already contain that public tag at a
    # prior commit while testing the next unreleased candidate.
    historical = _git("for-each-ref", "--format=%(refname)", "refs/tags").splitlines()
    for ref in historical:
        if ref != f"refs/tags/{candidate_tag}":
            _git("push", str(destination), f"{ref}:{ref}")
    _git(f"--git-dir={destination}", "update-ref", f"refs/tags/{candidate_tag}", source_sha)
    _git(f"--git-dir={destination}", "symbolic-ref", "HEAD", "refs/heads/main")
    main_sha = _git(f"--git-dir={destination}", "rev-parse", "refs/heads/main")
    tag_sha = _git(f"--git-dir={destination}", "rev-parse", f"refs/tags/{candidate_tag}^{{commit}}")
    if main_sha != source_sha or tag_sha != source_sha:
        raise ContractError("local candidate repository identity does not match the release plan")
    return f"file://{destination.resolve()}"


def _tag_exists(tag: str) -> bool:
    completed = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/tags/{tag}"],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


def create_previous_remote(plan: dict, destination: Path) -> str:
    _git("init", "--bare", str(destination))
    previous = plan["previous_release"]
    _git("push", str(destination), f"{previous['commit']}:refs/heads/main")
    _git("push", str(destination), f"refs/tags/{previous['tag']}:refs/tags/{previous['tag']}")
    _git(f"--git-dir={destination}", "symbolic-ref", "HEAD", "refs/heads/main")
    return f"file://{destination.resolve()}"


def _release_staging() -> Result:
    cli_dir = str(REPO_ROOT / "cli")
    sys.path.insert(0, cli_dir)
    try:
        from lifecycle import _populate_release_dir, _validate_staging

        with tempfile.TemporaryDirectory(prefix="flow-release-stage-") as raw:
            staging = Path(raw) / "source"
            _populate_release_dir(REPO_ROOT, staging)
            invalid = _validate_staging(staging)
        return (1, invalid + "\n") if invalid else (0, "release staging and transitive imports are valid\n")
    except Exception as exc:  # evidence must retain unexpected validation failures
        return 1, f"release staging raised {type(exc).__name__}: {exc}\n"
    finally:
        sys.path.remove(cli_dir)


def _tracked_tree_clean() -> Result:
    code, diff = _run(["git", "diff", "--check"])
    if code:
        return code, diff
    code, status = _run(["git", "status", "--porcelain", "--untracked-files=no"])
    if code:
        return code, status
    if status.strip():
        return 1, "tracked tree changed during candidate checks:\n" + status
    return 0, "tracked tree is clean\n"


def _install(remote: str, home: Path) -> Result:
    env = _clean_env(home)
    env["FLOW_REPO_URL"] = remote
    return _run(["bash", str(REPO_ROOT / "install.sh")], cwd=home, env=env)


def _flow(home: Path, *args: str) -> Result:
    return _run([str(home / ".local" / "bin" / "flow"), *args], cwd=home, env=_clean_env(home))


def _upgrade_previous(remote: str, home: Path, previous_tag: str) -> Result:
    """Keep the v0.40.16 cached-checker failure distinct from bootstrap recovery.

    The old updater cannot load a new runtime checker while its process remains
    alive. Only its exact known failure after a verified rollback may use the
    supported remote bootstrap path; all other upgrade failures block release.
    """
    config = home / ".flow" / "config.toml"
    pointer = home / ".flow" / "runtimes" / "maf" / "current.json"
    source = home / ".flow" / "source"
    def snapshot():
        return {str(path.relative_to(home)): file_sha256(path)
                for path in [config, pointer, *source.rglob('*')]
                if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc'}
    before = snapshot()
    installed = tomllib.loads(config.read_text()).get('install', {}).get('version') if config.is_file() else None
    legacy = previous_tag == installed == 'v0.40.16'
    if legacy:
        code, expected = _run(['git', 'show', f'{previous_tag}:cli/maf_runtime.py'])
        legacy = code == 0 and (source / 'cli' / 'maf_runtime.py').read_text() == expected
    update = _flow(home, 'update', '--remote', remote)
    if update[0] == 0:
        return update
    if (not legacy or update[0] != 1
            or 'managed MAF runtime provisioning failed: version_mismatch:' not in update[1]
            or snapshot() != before):
        return update
    bootstrap = _install(remote, home)
    output = update[1] + '\nLegacy updater exit=1; exact prior source/config/runtime rollback verified.\n'
    output += 'Recovery method: supported remote release bootstrap over the existing install.\n' + bootstrap[1]
    if bootstrap[0]:
        return bootstrap[0], output
    ready = _flow(home, 'runtime', 'readiness', '--json')
    return ready[0], output + ready[1]


def _doctor_check(home: Path) -> Result:
    code, output = _flow(home, "doctor", "--check", "--json")
    if code == 0:
        return code, output
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return code, output
    allowed_warnings = {
        "user.claude.runtime_smoke",
        "user.codex.runtime_smoke",
        "telemetry.usage.empty",
        "telemetry.plugin_usage",
    }
    observed_warnings = {
        item.get("id")
        for item in payload.get("diagnostics", [])
        if item.get("severity") == "warning"
    }
    model_warnings = [
        item for item in payload.get("diagnostics", [])
        if item.get("id") == "expertise.model" and item.get("severity") == "warning"
    ]
    if len(model_warnings) == 1 and model_warnings[0].get("category") in {
        "model_missing", "unsupported_runtime",
    }:
        # Fresh release homes have no separately installed local model. The
        # runner's Python build may also be outside the optional model matrix.
        observed_warnings.discard("expertise.model")
    if (
        payload.get("ok") is True
        and payload.get("errors") == 0
        and observed_warnings.issubset(allowed_warnings)
    ):
        explanation = (
            "doctor --check reported only isolated-run warnings accepted by the release contract: "
            + ", ".join(sorted(observed_warnings))
            + "\n"
        )
        return 0, explanation + output
    return code, output


def _setup_user(home: Path) -> Result:
    setup = _flow(home, "setup", "user")
    if setup[0]:
        return setup
    overlay = home / ".flow" / "user"
    overlay.mkdir(parents=True, exist_ok=True)
    manifest = overlay / "flow.toml"
    if not manifest.exists():
        manifest.write_text("# Empty candidate overlay; release checks require clean VCS state.\n", encoding="utf-8")
    env = _clean_env(home)
    env.update({
        "GIT_AUTHOR_NAME": "Flow Release Gate",
        "GIT_AUTHOR_EMAIL": "release-gate@example.invalid",
        "GIT_COMMITTER_NAME": "Flow Release Gate",
        "GIT_COMMITTER_EMAIL": "release-gate@example.invalid",
    })
    overlay_remote = home / ".flow" / "candidate-user-overlay.git"
    return _combine(
        setup,
        _run(["git", "init", "--bare", "-b", "main", str(overlay_remote)], cwd=home, env=env),
        _run(["git", "init", "-b", "main"], cwd=overlay, env=env),
        _run(["git", "add", "flow.toml"], cwd=overlay, env=env),
        _run(["git", "commit", "-m", "test: seed isolated release overlay"], cwd=overlay, env=env),
        _run(["git", "remote", "add", "origin", str(overlay_remote)], cwd=overlay, env=env),
        _run(["git", "push", "-u", "origin", "main"], cwd=overlay, env=env),
    )


def _combine(*results: Result) -> Result:
    output: list[str] = []
    for code, text in results:
        output.append(text)
        if code:
            return code, "".join(output)
    return 0, "".join(output)


def _log_result(
    log_root: Path,
    check_id: str,
    started: float,
    result: Result | None,
) -> dict:
    if result is None:
        code = None
        output = "not run because an earlier required candidate check failed\n"
        status = "not_run"
        duration_ms = 0
    else:
        code, output = result
        status = "passed" if code == 0 else "failed"
        duration_ms = max(0, round((time.monotonic() - started) * 1000))
    log_path = log_root / f"{check_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(output, encoding="utf-8")
    return {
        "id": check_id,
        "result": status,
        "exit_code": code,
        "duration_ms": duration_ms,
        "log_path": f"logs/{check_id}.log",
        "log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
    }


def run_candidate(plan_path, output, fail_check=None, command_overrides=None):
    from v2_release_checks import run_candidate as current
    return current(plan_path, output, fail_check, command_overrides)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--fail-check", choices=STABLE_CHECK_IDS)
    parser.add_argument("--defer-exit", action="store_true", help="write failed evidence and let a later validation step fail the job")
    parser.add_argument("--github-output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        evidence, result = run_candidate(args.plan, args.output, args.fail_check)
        if args.github_output:
            with args.github_output.open("a", encoding="utf-8") as stream:
                stream.write(f"evidence_digest={file_sha256(args.output)}\n")
                stream.write(f"candidate_passed={str(evidence['overall_result'] == 'passed').lower()}\n")
        print(f"candidate evidence: {evidence['overall_result']}")
        return 0 if args.defer_exit else result
    except ContractError as exc:
        print(f"release candidate: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
