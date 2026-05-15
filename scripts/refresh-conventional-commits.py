#!/usr/bin/env python3
"""Refresh the vendored Conventional Commits spec against upstream.

Maintainer-only — runs from the flow repo root. Consumers never run this.

What it does:
  1. Shallow-clones the upstream conventionalcommits.org repo to a temp dir.
  2. Resolves the current HEAD SHA on master.
  3. Reads the v1.0.0 spec file (content/v1.0.0/index.md).
  4. Re-writes the local vendor mirror with the upstream body, preserving the
     flow attribution header (`<!-- VENDORED VERBATIM -->`) above it.
  5. Updates scaffolds/default/flow.toml's `[standards.git-commits]` block:
     `vendored_sha` and `vendored_at`.
  6. Prints a unified diff summary and instructs the maintainer to commit.

What it does NOT do:
  - commit anything (the maintainer reviews and commits)
  - update the flow-authored standard (standards/git-commits.md) — if the
    upstream spec changes materially, that file needs human judgment to
    reconcile

Usage:
  python3 scripts/refresh-conventional-commits.py
  python3 scripts/refresh-conventional-commits.py --upstream-ref master
  python3 scripts/refresh-conventional-commits.py --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import re
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCAFFOLD_DIR = REPO_ROOT / "scaffolds" / "default"
VENDOR_FILE = SCAFFOLD_DIR / "standards" / "vendor" / "conventional-commits-1.0.0.md"
VENDOR_LICENSE = SCAFFOLD_DIR / "standards" / "vendor" / "conventional-commits-LICENSE.txt"
FLOW_TOML = SCAFFOLD_DIR / "flow.toml"
UPSTREAM_REPO = "https://github.com/conventional-commits/conventionalcommits.org"
UPSTREAM_SPEC_PATH = "content/v1.0.0/index.md"
UPSTREAM_LICENSE_PATH = "LICENSE"

# Marker the existing vendor file uses to separate the flow attribution comment
# from the verbatim upstream body. Refreshes replace the body, never the header.
HEADER_END_MARKER = "-->"


def run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(f"command failed: {' '.join(cmd)}\n{result.stderr}\n")
        sys.exit(result.returncode)
    return result.stdout


def fetch_upstream(ref: str) -> tuple[Path, str]:
    """Clone upstream at the given ref. Returns (clone_path, resolved_sha)."""
    tmp = Path(tempfile.mkdtemp(prefix="flow-cc-refresh-"))
    clone = tmp / "upstream"
    run(["git", "clone", "--depth", "1", "--branch", ref, UPSTREAM_REPO, str(clone)])
    sha = run(["git", "rev-parse", "HEAD"], cwd=clone).strip()
    return clone, sha


def read_header(path: Path) -> str:
    """Return the leading flow attribution comment (up to and including --> + blank line)."""
    text = path.read_text()
    idx = text.find(HEADER_END_MARKER)
    if idx == -1:
        sys.stderr.write(
            f"vendor file at {path} is missing the flow attribution header; "
            f"refresh aborted to avoid clobbering hand edits.\n"
        )
        sys.exit(1)
    # Include the marker and the blank line after it (if present).
    after = idx + len(HEADER_END_MARKER)
    if text[after:after + 1] == "\n":
        after += 1
    if text[after:after + 1] == "\n":
        after += 1
    return text[:after]


def patch_header_metadata(header: str, sha: str, today: str) -> str:
    """Update the SHA and date lines in the flow attribution header in place."""
    header = re.sub(r"(Pinned SHA:\s+)\S+", rf"\g<1>{sha}", header)
    header = re.sub(r"(Vendored at:\s+)\S+", rf"\g<1>{today}", header)
    return header


def update_flow_toml(sha: str, today: str) -> tuple[str, str]:
    """Patch flow.toml's [standards.git-commits] block. Returns (old, new) text."""
    text = FLOW_TOML.read_text()
    new = text
    new = re.sub(
        r'(\[standards\.git-commits\][^\[]*?vendored_sha\s*=\s*")[^"]*(")',
        rf"\g<1>{sha}\g<2>",
        new,
        count=1,
        flags=re.DOTALL,
    )
    new = re.sub(
        r'(\[standards\.git-commits\][^\[]*?vendored_at\s*=\s*")[^"]*(")',
        rf"\g<1>{today}\g<2>",
        new,
        count=1,
        flags=re.DOTALL,
    )
    return text, new


def diff_summary(old: str, new: str, label: str) -> str:
    lines = list(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"{label} (current)",
            tofile=f"{label} (refreshed)",
            n=3,
        )
    )
    return "".join(lines) if lines else "(no changes)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--upstream-ref",
        default="master",
        help="upstream branch or tag to refresh against (default: master)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print diffs without writing files",
    )
    args = parser.parse_args()

    if not VENDOR_FILE.exists():
        sys.stderr.write(f"vendor mirror not found at {VENDOR_FILE}; aborting.\n")
        return 1
    if not FLOW_TOML.exists():
        sys.stderr.write(f"flow.toml not found at {FLOW_TOML}; aborting.\n")
        return 1

    print(f"upstream: {UPSTREAM_REPO}@{args.upstream_ref}")
    clone, sha = fetch_upstream(args.upstream_ref)
    print(f"resolved SHA: {sha}")

    upstream_spec = clone / UPSTREAM_SPEC_PATH
    upstream_license = clone / UPSTREAM_LICENSE_PATH
    if not upstream_spec.exists():
        sys.stderr.write(f"upstream spec missing at {upstream_spec}; aborting.\n")
        return 1

    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    header = patch_header_metadata(read_header(VENDOR_FILE), sha, today)
    new_body = upstream_spec.read_text()
    new_vendor = header + new_body
    old_vendor = VENDOR_FILE.read_text()

    new_license = upstream_license.read_text() if upstream_license.exists() else None
    old_license = VENDOR_LICENSE.read_text() if VENDOR_LICENSE.exists() else ""

    old_toml, new_toml = update_flow_toml(sha, today)

    print()
    print("=" * 72)
    print(f"vendor mirror diff ({VENDOR_FILE.relative_to(REPO_ROOT)}):")
    print("=" * 72)
    print(diff_summary(old_vendor, new_vendor, "vendor mirror"))

    if new_license is not None:
        print()
        print("=" * 72)
        print(f"license file diff ({VENDOR_LICENSE.relative_to(REPO_ROOT)}):")
        print("=" * 72)
        print(diff_summary(old_license, new_license, "license"))

    print()
    print("=" * 72)
    print(f"flow.toml diff ({FLOW_TOML.relative_to(REPO_ROOT)}):")
    print("=" * 72)
    print(diff_summary(old_toml, new_toml, "flow.toml"))

    if args.dry_run:
        print()
        print("dry-run: no files written")
        return 0

    if old_vendor == new_vendor and old_toml == new_toml and (new_license is None or old_license == new_license):
        print()
        print("nothing to update; vendored content already matches upstream.")
        return 0

    VENDOR_FILE.write_text(new_vendor)
    if new_license is not None:
        VENDOR_LICENSE.write_text(new_license)
    FLOW_TOML.write_text(new_toml)

    print()
    print("refreshed. Review the diffs, then commit:")
    print(f"  git -C {REPO_ROOT} add {VENDOR_FILE.relative_to(REPO_ROOT)}")
    if new_license is not None and old_license != new_license:
        print(f"  git -C {REPO_ROOT} add {VENDOR_LICENSE.relative_to(REPO_ROOT)}")
    print(f"  git -C {REPO_ROOT} add {FLOW_TOML.relative_to(REPO_ROOT)}")
    print(f'  git -C {REPO_ROOT} commit -m "chore(standards): refresh Conventional Commits vendor to {sha[:7]}"')
    print()
    print("If the upstream spec changed materially, also review:")
    print(f"  scaffolds/default/standards/git-commits.md")
    print("(the flow-authored summary may need reconciliation with the new spec body)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
