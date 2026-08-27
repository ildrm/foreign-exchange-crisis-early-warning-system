"""Small content-addressed JSON cache with explicit freshness metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from .dates import parse_datetime
from .json_io import read_json, write_json


@dataclass(frozen=True, slots=True)
class CacheEntry:
    value: Any
    stored_at: datetime
    expires_at: datetime | None

    @property
    def stale(self) -> bool:
        return self.expires_at is not None and datetime.now(timezone.utc) > self.expires_at


class JsonFileCache:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = sha256(key.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    def set(self, key: str, value: Any, *, ttl: timedelta | None = None) -> CacheEntry:
        stored = datetime.now(timezone.utc)
        expires = stored + ttl if ttl is not None else None
        write_json(
            self._path(key),
            {
                "key_sha256": sha256(key.encode("utf-8")).hexdigest(),
                "stored_at": stored,
                "expires_at": expires,
                "value": value,
            },
        )
        return CacheEntry(value, stored, expires)

    def get(self, key: str, *, allow_stale: bool = False) -> CacheEntry | None:
        path = self._path(key)
        if not path.exists():
            return None
        payload = read_json(path)
        expected = sha256(key.encode("utf-8")).hexdigest()
        if payload.get("key_sha256") != expected:
            raise ValueError("cache key digest mismatch")
        entry = CacheEntry(
            value=payload.get("value"),
            stored_at=parse_datetime(payload["stored_at"]),
            expires_at=parse_datetime(payload["expires_at"]) if payload.get("expires_at") else None,
        )
        return entry if allow_stale or not entry.stale else None
