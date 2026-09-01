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
from pathlib import Path
from typing import Callable

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
    _git("push", str(destination), "--tags")
    candidate_tag = plan["predicted_release"]["tag"]
    existing = _git("show-ref", "--verify", "--hash", f"refs/tags/{candidate_tag}") if _tag_exists(candidate_tag) else ""
    if existing and existing != source_sha:
        raise ContractError(f"candidate tag {candidate_tag} already exists at another commit")
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


def run_candidate(plan_path: Path, output: Path, fail_check: str | None = None) -> tuple[dict, int]:
    plan = load_plan(plan_path)
    if not plan["release_required"]:
        raise ContractError("candidate validation cannot run for a no-release plan")
    if _git("rev-parse", "HEAD") != plan["source_sha"]:
        raise ContractError("candidate checkout HEAD does not match the planned source SHA")

    output.parent.mkdir(parents=True, exist_ok=True)
    log_root = output.parent / "logs"
    checks: list[dict] = []
    blocked = False
    fresh_home: Path | None = None

    with tempfile.TemporaryDirectory(prefix="flow-release-candidate-") as raw:
        temp_root = Path(raw)
        candidate_bare = temp_root / "candidate.git"
        previous_bare = temp_root / "previous.git"
        candidate_remote = create_candidate_remote(plan, candidate_bare)
        previous_remote = create_previous_remote(plan, previous_bare)
        fresh_home = temp_root / "fresh-home"
        upgrade_home = temp_root / "upgrade-home"
        fresh_home.mkdir()
        upgrade_home.mkdir()

        def fresh_install() -> Result:
            return _install(candidate_remote, fresh_home)

        def upgrade() -> Result:
            install_result = _install(previous_remote, upgrade_home)
            if install_result[0]:
                return install_result
            return _combine(install_result, _flow(upgrade_home, "update", "--remote", candidate_remote))

        commands: dict[str, Callable[[], Result]] = {
            "python-test-suite": lambda: _run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"]),
            "generated-help": lambda: _run([sys.executable, "scripts/regenerate-flow-help.py", "--check"]),
            "release-staging": _release_staging,
            "clean-tracked-tree": _tracked_tree_clean,
            "candidate-fresh-install": fresh_install,
            "candidate-upgrade": upgrade,
            "setup-machine": lambda: _flow(fresh_home, "setup", "machine"),
            "setup-user": lambda: _setup_user(fresh_home),
            "claude-sync-check": lambda: _flow(fresh_home, "sync", "claude", "--user", "--check"),
            "codex-sync-check": lambda: _flow(fresh_home, "sync", "codex", "--user", "--check"),
            "doctor-check": lambda: _doctor_check(fresh_home),
            "runtime-smoke-static": lambda: _flow(fresh_home, "runtime", "smoke", "--target", "all"),
            "representative-cli": lambda: _flow(fresh_home, "update", "--check", "--json", "--remote", candidate_remote),
        }

        for check_id in STABLE_CHECK_IDS:
            started = time.monotonic()
            if blocked:
                result = None
            elif fail_check == check_id:
                result = (97, f"injected failure for mutation proof: {check_id}\n")
            else:
                result = commands[check_id]()
            record = _log_result(log_root, check_id, started, result)
            checks.append(record)
            blocked = blocked or record["result"] == "failed"

        evidence = {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "plan_digest": canonical_digest(plan),
            "source_sha": plan["source_sha"],
            "candidate_version": plan["predicted_release"]["version"],
            "candidate_tag": plan["predicted_release"]["tag"],
            "candidate_repository": {
                "url": candidate_remote,
                "main_sha": plan["source_sha"],
                "tag_sha": plan["source_sha"],
            },
            "runner_sha": _git("rev-parse", "HEAD"),
            "checks": checks,
            "overall_result": "failed" if blocked else "passed",
        }
        write_evidence(output, evidence, plan=plan)
    return evidence, 0 if evidence["overall_result"] == "passed" else 1


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
