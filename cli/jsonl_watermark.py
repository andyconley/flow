"""Incremental byte-level reading of append-only JSONL files.

Harness-agnostic: nothing here knows about Codex or Claude, only about the
one property both harnesses' transcripts share — a file that is appended to
over time, one JSON object per line, sometimes mid-write. Extracted out of
`codex_collector.py` rather than duplicated into `claude_collector.py`, since
none of it had any Codex-specific content to begin with.

Decoding happens in the caller, not here: lines are returned as raw bytes, so
a decode failure and a JSON-parse failure can funnel through the same
hard-stop path in whichever collector calls this.
"""

import hashlib
from pathlib import Path


class WatermarkAnomaly(Exception):
    """The file is smaller than the recorded watermark. Never a silent no-op.

    A file that shrank was not appended to — it was replaced or truncated.
    Silently re-harvesting from 0 would either skip data or double-count it
    depending on what actually happened, so this is raised rather than guessed
    at.
    """


def read_new_lines(path: Path, last_offset: int) -> tuple[list[bytes], int, int]:
    """Read complete lines appended since `last_offset`, as raw bytes.

    Returns `(lines, new_offset, current_size)`. `new_offset` is the byte
    offset immediately after the last complete line — what the caller should
    persist as `harvest.last_offset` once those lines are committed. A
    trailing line with no terminating newline is left unread entirely; it is
    neither returned nor counted toward `new_offset`.
    """
    current_size = path.stat().st_size
    if current_size < last_offset:
        raise WatermarkAnomaly(
            f"{path}: size {current_size} < recorded offset {last_offset}"
        )
    if current_size == last_offset:
        return [], last_offset, current_size

    with path.open("rb") as fh:
        fh.seek(last_offset)
        chunk = fh.read()

    lines: list[bytes] = []
    start = 0
    while True:
        nl = chunk.find(b"\n", start)
        if nl == -1:
            break  # remainder, if any, is an incomplete trailing line
        lines.append(chunk[start:nl])
        start = nl + 1
    new_offset = last_offset + start
    return lines, new_offset, current_size


def line_byte_length(raw: bytes) -> int:
    return len(raw) + 1  # +1 for the newline stripped during reading


def line_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
