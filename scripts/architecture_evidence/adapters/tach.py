"""Tach-backed Python dependency collection for the architecture pilot.

Tach is the sole source analyzer in this adapter.  The adapter joins Tach's
machine-readable map to its human-readable dependency reports; it does not
parse Python source to discover imports.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


_REPORT_IMPORT = re.compile(
    r"^(?P<file>[^:\n]+\.py):(?P<line>[1-9][0-9]*): Import '(?P<target>[^']+)'$"
)
_VERSION = re.compile(r"^tach (?P<version>\S+)$")


class TachAdapterError(ValueError):
    """Raised when Tach cannot produce trustworthy graph evidence."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_root(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise ValueError("source_roots entries must be non-empty relative paths")
    root = PurePosixPath(value.replace("\\", "/"))
    if root.is_absolute() or ".." in root.parts or root == PurePosixPath("."):
        raise ValueError(f"unsafe source root: {value!r}")
    return root


def _module_name(root: PurePosixPath, relative_file: PurePosixPath) -> str:
    within_root = relative_file.relative_to(root)
    parts = list(within_root.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _write_tach_config(
    destination: Path,
    roots: list[PurePosixPath],
    modules: list[str],
) -> None:
    lines = [
        "source_roots = ["
        + ", ".join(_toml_string(root.as_posix()) for root in roots)
        + "]",
        "ignore_type_checking_imports = false",
        "forbid_circular_dependencies = true",
        "",
    ]
    for module in modules:
        lines.extend(
            [
                "[[modules]]",
                f"path = {_toml_string(module)}",
                "depends_on = []",
                "",
            ]
        )
    destination.write_text("\n".join(lines), encoding="utf-8")


def _minimal_environment(executable: Path) -> dict[str, str]:
    environment = {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": str(executable.parent),
        "PYTHONHASHSEED": "0",
    }
    system_root = os.environ.get("SYSTEMROOT")
    if system_root:
        environment["SYSTEMROOT"] = system_root
    return environment


def _run(
    arguments: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            arguments,
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise TachAdapterError(f"unable to execute Tach: {exc}") from exc


def _copy_declared_roots(
    source_root: Path,
    analysis_root: Path,
    roots: list[PurePosixPath],
    excludes: list[str],
) -> list[PurePosixPath]:
    inventory: list[PurePosixPath] = []
    resolved_source = source_root.resolve(strict=True)
    for root in roots:
        source = source_root.joinpath(*root.parts)
        resolved = source.resolve(strict=True)
        if not resolved.is_relative_to(resolved_source) or not resolved.is_dir():
            raise ValueError(
                f"source root is not a contained directory: {root.as_posix()}"
            )
        for candidate in sorted(resolved.rglob("*")):
            if candidate.is_symlink():
                raise ValueError(f"symlink is not allowed in source root: {candidate}")
            if candidate.is_file():
                relative = root / PurePosixPath(
                    candidate.relative_to(resolved).as_posix()
                )
                if not any(
                    fnmatch.fnmatch(relative.as_posix(), pattern)
                    for pattern in excludes
                ):
                    inventory.append(relative)
        shutil.copytree(resolved, analysis_root.joinpath(*root.parts), symlinks=True)
    return sorted(inventory, key=lambda item: item.as_posix())


def _edge_id(source_id: str, target_id: str) -> str:
    return f"{source_id}|direct-import|{target_id}"


def collect_graph(
    source_root: Path,
    config: dict[str, Any],
    raw_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Collect a canonical module graph and exact import-line provenance.

    The source checkout is never modified.  Tach receives a disposable copy
    containing a generated ``tach.toml`` and an analyzer-only ``pyproject.toml``.
    """

    source_root = Path(source_root)
    raw_dir = Path(raw_dir)
    executable_value = config.get("tach_executable")
    if not isinstance(executable_value, str) or not executable_value:
        raise ValueError("config.tach_executable must be an explicit path")
    executable = Path(executable_value)
    if not executable.is_absolute() or not executable.is_file():
        raise ValueError("config.tach_executable must name an existing absolute file")
    roots_value = config.get("source_roots")
    if not isinstance(roots_value, list) or not roots_value:
        raise ValueError("config.source_roots must be a non-empty list")
    roots = [_relative_root(value) for value in roots_value]
    if len({root.as_posix() for root in roots}) != len(roots):
        raise ValueError("config.source_roots contains duplicates")
    timeout = config.get("tach_timeout_seconds", 60)
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or timeout <= 0
    ):
        raise ValueError("config.tach_timeout_seconds must be positive")
    raw_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = raw_dir / "tach-reports"
    reports_dir.mkdir(exist_ok=True)

    excludes_value = config.get("identity_excludes", [])
    if not isinstance(excludes_value, list) or not all(
        isinstance(item, str) for item in excludes_value
    ):
        raise ValueError("config.identity_excludes must be a list of patterns")
    gaps: list[str] = []
    environment = _minimal_environment(executable)
    with tempfile.TemporaryDirectory(prefix="flow-architecture-tach-") as temporary:
        analysis_root = Path(temporary)
        all_files = _copy_declared_roots(
            source_root, analysis_root, roots, excludes_value
        )
        python_files = [path for path in all_files if path.suffix == ".py"]
        modules = sorted(
            {
                _module_name(root, path)
                for root in roots
                for path in python_files
                if path.is_relative_to(root) and _module_name(root, path)
            }
        )
        if not python_files:
            gaps.append(
                "tach:no-python-files: no Python files in declared source roots"
            )
        _write_tach_config(analysis_root / "tach.toml", roots, modules)
        overlay = '[project]\nname = "flow-architecture-probe"\nversion = "0.0.0"\n'
        for root in roots:
            overlay_path = analysis_root.joinpath(*root.parts) / "pyproject.toml"
            if overlay_path.exists():
                raise TachAdapterError(
                    f"refusing to replace existing analyzer metadata: {root.as_posix()}/pyproject.toml"
                )
            overlay_path.write_text(overlay, encoding="utf-8")

        version_result = _run(
            [str(executable), "--version"],
            cwd=analysis_root,
            environment=environment,
            timeout=float(timeout),
        )
        (raw_dir / "tach-version.stdout.txt").write_text(
            version_result.stdout, encoding="utf-8"
        )
        (raw_dir / "tach-version.stderr.txt").write_text(
            version_result.stderr, encoding="utf-8"
        )
        version_match = _VERSION.fullmatch(version_result.stdout.strip())
        if version_result.returncode != 0 or not version_match:
            raise TachAdapterError("unable to establish Tach version")
        if version_match.group("version") != "0.35.0":
            raise TachAdapterError(
                f"unsupported Tach version {version_match.group('version')}; expected 0.35.0"
            )

        map_path = raw_dir / "tach-map.json"
        map_arguments = [str(executable), "map", "-o", str(map_path)]
        map_result = _run(
            map_arguments,
            cwd=analysis_root,
            environment=environment,
            timeout=float(timeout),
        )
        (raw_dir / "tach-map.stdout.txt").write_text(
            map_result.stdout, encoding="utf-8"
        )
        (raw_dir / "tach-map.stderr.txt").write_text(
            map_result.stderr, encoding="utf-8"
        )
        if map_result.returncode != 0 or not map_path.is_file():
            raise TachAdapterError(
                f"tach map failed with exit code {map_result.returncode}"
            )
        try:
            dependency_map = json.loads(map_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TachAdapterError(f"invalid Tach map output: {exc}") from exc
        if not isinstance(dependency_map, dict):
            raise TachAdapterError("Tach map output must be an object")

        report_sources: dict[str, list[dict[str, Any]]] = {}
        for relative_file in python_files:
            relative_text = relative_file.as_posix()
            report_name = relative_text.replace("/", "__") + ".txt"
            arguments = [str(executable), "report", relative_text, "--dependencies"]
            result = _run(
                arguments,
                cwd=analysis_root,
                environment=environment,
                timeout=float(timeout),
            )
            (reports_dir / report_name).write_text(result.stdout, encoding="utf-8")
            (reports_dir / (report_name + ".stderr")).write_text(
                result.stderr, encoding="utf-8"
            )
            if result.returncode != 0:
                gaps.append(
                    f"tach:report-failed:{relative_text}: dependency report failed"
                )
                continue
            line_count = len(
                (analysis_root / relative_text).read_text(encoding="utf-8").splitlines()
            )
            source_module = _module_name(
                next(root for root in roots if relative_file.is_relative_to(root)),
                relative_file,
            )
            for line in result.stdout.splitlines():
                match = _REPORT_IMPORT.fullmatch(line)
                if not match:
                    continue
                line_number = int(match.group("line"))
                if match.group("file") != Path(relative_text).name:
                    gaps.append(
                        f"tach:report-file-mismatch:{relative_text}:{match.group('file')}: "
                        "report line names a different source file"
                    )
                    continue
                if line_number > line_count:
                    gaps.append(
                        f"tach:invalid-line:{relative_text}:{line_number}: reported line is out of range"
                    )
                    continue
                target_module = match.group("target").split(".", 1)[0]
                if target_module not in modules:
                    continue
                key = f"python:{source_module}|python:{target_module}"
                report_sources.setdefault(key, []).append(
                    {
                        "path": relative_text,
                        "start_line": line_number,
                        "end_line": line_number,
                    }
                )

        path_to_module: dict[str, str] = {}
        for root in roots:
            for path in python_files:
                if path.is_relative_to(root):
                    path_to_module[path.as_posix()] = _module_name(root, path)
        nodes = []
        inventory = []
        for path in all_files:
            path_text = path.as_posix()
            if path.suffix != ".py":
                inventory.append(
                    {"path": path_text, "status": "excluded", "reason": "not-python"}
                )
                continue
            module = path_to_module[path_text]
            source_file = source_root.joinpath(*path.parts)
            nodes.append(
                {
                    "id": f"python:{module}",
                    "label": module,
                    "parent": f"component:{next(root for root in roots if path.is_relative_to(root)).as_posix()}",
                    "path": path_text,
                    "sha256": _sha256(source_file),
                    "language": "python",
                }
            )
            inventory.append(
                {"path": path_text, "status": "processed", "reason": "tach-0.35.0"}
            )

        edges = []
        expected_keys: set[str] = set()
        for source_path, dependencies in dependency_map.items():
            if source_path not in path_to_module or not isinstance(dependencies, list):
                raise TachAdapterError(
                    f"Tach map contains an unexpected path or value: {source_path!r}"
                )
            source_id = f"python:{path_to_module[source_path]}"
            if not all(isinstance(target_path, str) for target_path in dependencies):
                raise TachAdapterError(
                    f"Tach map contains a non-string dependency: {source_path!r}"
                )
            for target_path in sorted(set(dependencies)):
                if target_path not in path_to_module:
                    raise TachAdapterError(
                        f"Tach map contains an unknown dependency path: {target_path!r}"
                    )
                target_id = f"python:{path_to_module[target_path]}"
                key = f"{source_id}|{target_id}"
                expected_keys.add(key)
                pointers = {
                    (item["path"], item["start_line"], item["end_line"])
                    for item in report_sources.get(key, [])
                }
                sources = [
                    {"path": path, "start_line": start, "end_line": end}
                    for path, start, end in sorted(pointers)
                ]
                if not sources:
                    gaps.append(
                        f"tach:missing-source:{source_id}:{target_id}: no exact Tach source line joined edge"
                    )
                edges.append(
                    {
                        "id": _edge_id(source_id, target_id),
                        "from": source_id,
                        "to": target_id,
                        "kind": "direct-import",
                        "sources": sources,
                    }
                )

        extra_report_keys = sorted(set(report_sources) - expected_keys)
        for key in extra_report_keys:
            gaps.append(
                f"tach:report-map-mismatch:{key}: report dependency absent from map"
            )
        graph = {
            "nodes": sorted(nodes, key=lambda item: item["id"]),
            "edges": sorted(edges, key=lambda item: item["id"]),
            "unresolved": [],
            "inventory": sorted(inventory, key=lambda item: item["path"]),
        }
        metadata = {
            "adapter": "tach",
            "adapter_contract_version": 1,
            "tool": "tach",
            "tool_version": version_match.group("version"),
            "executable_sha256": _sha256(executable),
            "source_roots": [root.as_posix() for root in roots],
            "analysis_overlay": {
                "kind": "analyzer-only-pyproject",
                "content_sha256": hashlib.sha256(overlay.encode("utf-8")).hexdigest(),
            },
            "generated_tach_config_sha256": _sha256(analysis_root / "tach.toml"),
            "capabilities": {
                "static_direct_imports": "available",
                "dynamic_imports": "unsupported",
                "unresolved_import_classification": "unsupported",
                "module_layout": "flat-source-root",
            },
            "command_contract": {
                "map": ["map", "-o", "<raw-dir>/tach-map.json"],
                "report": ["report", "<relative-module-file>", "--dependencies"],
            },
            "raw_artifacts": [
                path.relative_to(raw_dir).as_posix()
                for path in sorted(raw_dir.rglob("*"))
                if path.is_file()
            ],
        }
        return graph, metadata, sorted(gaps)
