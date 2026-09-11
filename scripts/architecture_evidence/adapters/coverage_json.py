"""Candidate-bound quality collection for the architecture evidence pilot."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from .mutmut import collect_all_results, collect_results
from .radon import collect_complexity

_TARGET_PATH = "cli/jsonl_watermark.py"
_TARGET_SYMBOL = "read_new_lines"
_PINS = {"radon": "6.0.1", "coverage": "7.14.0", "mutmut": "3.7.0"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _environment(
    executable: str,
    cwd: Path,
    pythonpath: str | None = None,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    home = cwd / ".quality-home"
    home.mkdir(exist_ok=True)
    result = {
        "PATH": f"{Path(executable).parent}:/usr/bin:/bin",
        "HOME": str(home),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if pythonpath is not None:
        result["PYTHONPATH"] = pythonpath
    if extra:
        result.update(extra)
    return result


def _run(
    args: list[str],
    cwd: Path,
    raw_path: Path,
    timeout: int = 180,
    env: dict[str, str] | None = None,
    allow_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env or _environment(args[0], cwd),
    )
    raw_path.write_text(
        "$ "
        + " ".join(args)
        + "\nenv names: "
        + ",".join(sorted((env or _environment(args[0], cwd))))
        + "\n"
        + result.stdout
        + result.stderr,
        encoding="utf-8",
    )
    if result.returncode and not allow_failure:
        raise RuntimeError(f"command exited {result.returncode}: {' '.join(args[:4])}")
    return result


def _gap(
    message: str, records: list[dict] | None = None, artifacts: list[dict] | None = None
) -> dict:
    return {
        "status": "inconclusive",
        "records": records or [],
        "gaps": [message],
        "artifacts": artifacts or [],
    }


def _versions(
    executable: str, source_root: Path, raw_dir: Path, expected: dict
) -> None:
    code = "import importlib.metadata as m; print(m.version('radon')); print(m.version('coverage')); print(m.version('mutmut'))"
    output = _run(
        [executable, "-c", code], source_root, raw_dir / "quality-versions.txt", 30
    ).stdout.splitlines()
    actual = dict(zip(_PINS, output, strict=True))
    if actual != expected:
        raise RuntimeError(f"tool pin mismatch: expected {expected}, got {actual}")


def _write_test(path: Path, strong: bool) -> None:
    offset = (
        "\n    assert new_offset == len(b'{\\\"event\\\": 1}\\n')" if strong else ""
    )
    path.write_text(
        "import json, os, sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path.cwd() / 'cli'))\nimport cli.jsonl_watermark as target\n\n"
        "def test_complete_line_and_offset(tmp_path):\n"
        "    path = tmp_path / 'events.jsonl'\n"
        "    path.write_bytes(b'{\\\"event\\\": 1}\\npartial')\n"
        "    module_path = Path(target.__file__).resolve()\n"
        "    assert module_path.is_relative_to(Path.cwd().resolve())\n"
        "    proof = os.getenv('TARGET_LOAD_PROOF')\n"
        "    if proof: Path(proof).write_text(json.dumps({'module_file': str(module_path), 'mutant_under_test': os.getenv('MUTANT_UNDER_TEST')}), encoding='utf-8')\n"
        "    lines, new_offset, size = target.read_new_lines(path, 0)\n"
        "    assert lines == [b'{\\\"event\\\": 1}']\n"
        "    assert size == len(b'{\\\"event\\\": 1}\\npartial')" + offset + "\n",
        encoding="utf-8",
    )


def _coverage_record(path: Path, copied_source: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    details = next(
        (
            v
            for k, v in data.get("files", {}).items()
            if k.replace("\\", "/") == _TARGET_PATH
            or Path(k).resolve() == copied_source.resolve()
        ),
        None,
    )
    summary = details and details.get("functions", {}).get(_TARGET_SYMBOL, {}).get(
        "summary", {}
    )
    total = summary and summary.get("num_statements")
    covered = summary and summary.get("covered_lines")
    if (
        not isinstance(total, int)
        or total <= 0
        or not isinstance(covered, int)
        or not 0 <= covered <= total
    ):
        raise RuntimeError(
            "fresh coverage JSON has no valid selected-function denominator"
        )
    return {
        "unit": "statements",
        "covered": covered,
        "total": total,
        "branch_covered": summary.get("covered_branches"),
        "branch_total": summary.get("num_branches"),
    }


def _selected_survivor(executable: str, workspace: Path, raw_dir: Path) -> str:
    _run(
        [executable, "-m", "mutmut", "run"],
        workspace,
        raw_dir / "mutmut-weak-run.txt",
        240,
    )
    records = collect_results(
        executable, workspace, raw_dir / "mutmut-weak-results.txt"
    )["records"]
    for item in records:
        if item["status"] == "survived" and ".x_read_new_lines__" in item["id"]:
            shown = _run(
                [executable, "-m", "mutmut", "show", item["id"]],
                workspace,
                raw_dir / ("mutmut-" + item["id"].replace(".", "_") + ".diff"),
                60,
            ).stdout
            if (
                "-        start = nl + 1" in shown
                and "+        start = nl + 2" in shown
            ):
                return item["id"]
    raise RuntimeError(
        "no selected read_new_lines offset mutant survived the weak assertion"
    )


def _fresh_mutation(
    executable: str,
    source_root: Path,
    source_path: Path,
    raw_dir: Path,
    target: str | None,
    proof_mode: str,
) -> dict:
    workspace = raw_dir / "mutmut-workspace"
    workspace.mkdir()
    shutil.copytree(source_root / "cli", workspace / "cli")
    (workspace / "tests").mkdir()
    copied = workspace / _TARGET_PATH
    (workspace / "pyproject.toml").write_text(
        "[tool.mutmut]\nsource_paths=['.']\nonly_mutate=['cli/jsonl_watermark.py']\npytest_add_cli_args_test_selection=['tests/test_target.py']\nuse_setproctitle=false\non_dependency_change='rerun'\n",
        encoding="utf-8",
    )
    test_path = workspace / "tests/test_target.py"
    _write_test(test_path, strong=proof_mode != "weak_strong")
    weak_hash = _sha(test_path) if proof_mode == "weak_strong" else None
    _run(
        [executable, "-m", "pytest", "-q", "tests/test_target.py"],
        workspace,
        raw_dir / "mutation-baseline.txt",
        60,
    )
    mutant = (
        _selected_survivor(executable, workspace, raw_dir)
        if proof_mode == "weak_strong"
        else target
    )
    if not mutant:
        raise RuntimeError("fresh selected mutation requires quality.mutation_target")
    if proof_mode == "weak_strong":
        _write_test(test_path, strong=True)
    strong_hash = _sha(test_path)
    _run(
        [executable, "-m", "pytest", "-q", "tests/test_target.py"],
        workspace,
        raw_dir / "mutation-strong-baseline.txt",
        60,
    )
    proof_path = raw_dir / "target-load-proof.json"
    run_env = _environment(
        executable, workspace, extra={"TARGET_LOAD_PROOF": str(proof_path)}
    )
    _run(
        [executable, "-m", "mutmut", "run", mutant],
        workspace,
        raw_dir / "mutmut-strong-run.txt",
        120,
        run_env,
        allow_failure=True,
    )
    native = collect_all_results(workspace, raw_dir / "mutmut-native-meta.json")[
        "records"
    ]
    selected = next((item for item in native if item["id"] == mutant), None)
    if selected is None or selected["status"] in ("not checked", "suspicious"):
        raise RuntimeError("mutmut did not produce a native selected-mutant outcome")
    if proof_mode == "weak_strong" and selected["status"] != "killed":
        raise RuntimeError("strengthened assertion did not kill selected mutant")
    if not proof_path.is_file():
        raise RuntimeError("mutation test did not emit target-loaded-path proof")
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    if proof.get("mutant_under_test") != mutant or not Path(
        proof.get("module_file", "")
    ).is_relative_to((workspace / "mutants").resolve()):
        raise RuntimeError(
            "mutation test did not import the selected target from its disposable workspace"
        )
    return {
        "tool": "mutmut",
        "selected_mutant": mutant,
        "selected_status": selected["status"],
        "weak_test_sha256": weak_hash,
        "strong_test_sha256": strong_hash,
        "source_input_sha256": _sha(copied),
        "instrumented_source_sha256": _sha(workspace / "mutants" / _TARGET_PATH),
        "target_loaded_path": _TARGET_PATH,
        "target_loaded_proof": proof_path.name,
        "records": native,
        "proof_mode": proof_mode,
    }


def collect_quality(source_root: Path, config: dict, raw_dir: Path) -> dict:
    """Collect fresh Radon, coverage, and mutmut evidence from this candidate."""
    quality = config.get("quality", {})
    if not quality.get("enabled", False):
        return {
            "status": "unsupported",
            "records": [],
            "gaps": ["quality capability disabled"],
            "artifacts": [],
        }
    if "coverage_json" in quality or "mutation_workspace" in quality:
        return _gap("external coverage or mutation workspace is not candidate-bound")
    try:
        executable = quality["python_executable"]
        if quality.get("versions", _PINS) != _PINS:
            raise RuntimeError(
                "quality config must pin Radon 6.0.1, coverage 7.14.0 and mutmut 3.7.0"
            )
        source_root = Path(source_root).resolve()
        source_path = source_root / _TARGET_PATH
        if not source_path.is_file():
            raise RuntimeError("selected quality source is absent")
        if quality.get("source_sha256") is not None and quality.get(
            "source_sha256"
        ) != _sha(source_path):
            raise RuntimeError(
                "quality source_sha256 does not bind this candidate source"
            )
        raw_dir.mkdir(parents=True, exist_ok=True)
        _versions(executable, raw_dir, raw_dir, _PINS)
        complexity = collect_complexity(
            executable, source_path, _TARGET_SYMBOL, raw_dir / "radon.json"
        )
        coverage_workspace = raw_dir / "coverage-workspace"
        coverage_workspace.mkdir()
        shutil.copytree(source_root / "cli", coverage_workspace / "cli")
        (coverage_workspace / "tests").mkdir()
        copied_source = coverage_workspace / _TARGET_PATH
        shutil.copy2(source_path, copied_source)
        coverage_test = coverage_workspace / "tests/test_target.py"
        _write_test(coverage_test, strong=True)
        _run(
            [executable, "-m", "coverage", "erase"],
            coverage_workspace,
            raw_dir / "coverage-erase.txt",
            30,
        )
        _run(
            [
                executable,
                "-m",
                "coverage",
                "run",
                "--branch",
                "-m",
                "pytest",
                "-q",
                "tests/test_target.py",
            ],
            coverage_workspace,
            raw_dir / "coverage-run.txt",
            60,
        )
        coverage_path = raw_dir / "coverage.json"
        _run(
            [executable, "-m", "coverage", "json", "-o", str(coverage_path)],
            coverage_workspace,
            raw_dir / "coverage-json.txt",
            30,
        )
        coverage = _coverage_record(coverage_path, copied_source)
        coverage["test_scope"] = (
            "supplemental selected-function behavior harness; collector baseline checked separately"
        )
        baseline_copy = raw_dir / "collector-workspace"
        shutil.copytree(
            source_root,
            baseline_copy,
            ignore=shutil.ignore_patterns(
                ".git", ".quality-home", "__pycache__", "*.pyc"
            ),
        )
        baseline_env = _environment(executable, baseline_copy, pythonpath="cli:tests")
        _run(
            [
                executable,
                "-m",
                "unittest",
                "test_flow.CodexCollectorTests",
                "test_flow.ClaudeCollectorTests",
            ],
            baseline_copy,
            raw_dir / "collector-baseline.txt",
            120,
            baseline_env,
        )
        mutation = _fresh_mutation(
            executable,
            source_root,
            source_path,
            raw_dir,
            quality.get("mutation_target"),
            quality.get("mutation_proof", "selected"),
        )
        crap = (
            complexity["value"] ** 2
            * (1 - coverage["covered"] / coverage["total"]) ** 3
            + complexity["value"]
        )
        record = {
            "id": "python:cli/jsonl_watermark.py:read_new_lines",
            "path": _TARGET_PATH,
            "symbol": _TARGET_SYMBOL,
            "source_sha256": _sha(source_path),
            "complexity": complexity,
            "coverage": coverage,
            "crap": {
                "formula": "C*C*(1-covered/total)^3+C",
                "value": crap,
                "coverage_basis": "statements",
            },
            "mutation": mutation,
            "coverage_test_sha256": _sha(coverage_test),
        }
        artifacts = [
            {"path": p.name, "sha256": _sha(p)}
            for p in raw_dir.iterdir()
            if p.is_file()
        ]
        return {
            "status": "available",
            "records": [record],
            "gaps": [],
            "artifacts": artifacts,
        }
    except (
        KeyError,
        OSError,
        RuntimeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
    ) as exc:
        return _gap(str(exc))
