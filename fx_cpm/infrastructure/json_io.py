"""Deterministic JSON serialization with atomic file replacement."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from fx_cpm.application.report_service import to_primitive


def dumps(value: Any, *, indent: int | None = 2) -> str:
    return json.dumps(
        to_primitive(value),
        ensure_ascii=False,
        allow_nan=False,
        indent=indent,
        sort_keys=True,
        separators=(",", ":") if indent is None else None,
    )


def loads(payload: str | bytes) -> Any:
    return json.loads(payload)


def read_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str | Path, value: Any, *, indent: int | None = 2) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(dumps(value, indent=indent))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
    return destination
