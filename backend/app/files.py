"""Atomic file writes for local JSON and binary artifacts."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def write_bytes_atomic(path: str | os.PathLike, content: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f"{target.name}-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json_atomic(path: str | os.PathLike, payload, *, indent: int = 2) -> None:
    write_bytes_atomic(
        path,
        (json.dumps(payload, ensure_ascii=False, indent=indent) + "\n").encode("utf-8"),
    )
