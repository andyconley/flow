"""TOML reading for flow manifests, with a parser for interpreters without tomllib.

Named `flowtoml` rather than `toml` on purpose: `cli/` goes on `sys.path`, so a
module named `toml.py` here would shadow the widely-installed PyPI `toml`
package for anything else running in the same interpreter.

`read_toml` prefers stdlib `tomllib` (Python 3.11+) and falls back to
`parse_simple_toml`, which handles only the subset flow.toml actually uses:
tables, arrays of tables, double-quoted strings, bools, and integers. The
fallback is live and covered by the test suite — flow supports interpreters
older than 3.11.
"""

from pathlib import Path

try:
    import tomllib as _tomllib
except ModuleNotFoundError:
    _tomllib = None


def parse_toml_value(raw: str):
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    if raw in {"true", "false"}:
        return raw == "true"
    if raw.isdigit():
        return int(raw)
    raise ValueError(f"unsupported TOML value: {raw}")


def assign_nested(container: dict, dotted_key: str, value) -> None:
    parts = dotted_key.split(".")
    current = container
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def parse_simple_toml(text: str) -> dict:
    root: dict = {}
    current = root
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[[") and line.endswith("]]"):
            path = line[2:-2].strip().split(".")
            current = root
            for part in path[:-1]:
                current = current.setdefault(part, {})
            current = current.setdefault(path[-1], [])
            current.append({})
            current = current[-1]
            continue
        if line.startswith("[") and line.endswith("]"):
            path = line[1:-1].strip().split(".")
            current = root
            for part in path:
                current = current.setdefault(part, {})
            continue
        key, value = line.split("=", 1)
        assign_nested(current, key.strip(), parse_toml_value(value))
    return root


def loads(text: str) -> dict:
    """Parse TOML text the same way `read_toml` parses a file.

    Callers that hold text rather than a path used to reach for
    `parse_simple_toml` directly, which is the fallback for interpreters
    without tomllib and raises on anything outside its subset — floats,
    arrays, inline comments. Reaching past `read_toml` like that turns a
    perfectly ordinary manifest into a crash.
    """
    if _tomllib is not None:
        return _tomllib.loads(text)
    return parse_simple_toml(text)


def read_toml(path: Path) -> dict:
    return loads(path.read_text())
