"""Bounded JSON input for canonical expertise and local fact definitions."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat


class BoundedJSONError(ValueError):
    pass


def read_json(path: Path, *, maximum_bytes: int, maximum_nodes: int = 10000,
              maximum_depth: int = 32, maximum_string: int = 8192):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise BoundedJSONError("input is not a regular file")
            payload = stream.read(maximum_bytes + 1)
        if len(payload) > maximum_bytes:
            raise BoundedJSONError("input exceeds the byte limit")
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise BoundedJSONError("input is unreadable or invalid JSON") from error
    stack = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > maximum_nodes or depth > maximum_depth:
            raise BoundedJSONError("input exceeds shape limits")
        if isinstance(item, dict):
            stack.extend((child, depth + 1) for child in item.values())
            stack.extend((key, depth + 1) for key in item)
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
        elif isinstance(item, str) and len(item) > maximum_string:
            raise BoundedJSONError("input string exceeds the length limit")
    return value
