"""Bounded standard-library HTTP client for optional public data adapters."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class HttpResponse:
    url: str
    status: int
    headers: Mapping[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


class HttpClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        retries: int = 2,
        maximum_bytes: int = 20_000_000,
        user_agent: str = "FX-CPM/1.0 research-client",
        require_https: bool = True,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.maximum_bytes = maximum_bytes
        self.user_agent = user_agent
        self.require_https = require_https

    def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> HttpResponse:
        parsed = urlparse(url)
        if parsed.scheme not in ({"https"} if self.require_https else {"http", "https"}):
            raise ValueError("source URL must use an allowed HTTP scheme")
        request_headers = {"Accept": "application/json,text/csv,text/plain,*/*", "User-Agent": self.user_agent}
        request_headers.update(headers or {})
        request = Request(url, headers=request_headers, method="GET")
        last_error: BaseException | None = None
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - scheme is validated above
                    declared = response.headers.get("Content-Length")
                    if declared is not None and int(declared) > self.maximum_bytes:
                        raise ValueError("HTTP response exceeds configured size limit")
                    body = response.read(self.maximum_bytes + 1)
                    if len(body) > self.maximum_bytes:
                        raise ValueError("HTTP response exceeds configured size limit")
                    return HttpResponse(
                        url=response.geturl(),
                        status=int(response.status),
                        headers={key.lower(): value for key, value in response.headers.items()},
                        body=body,
                    )
            except HTTPError as exc:
                last_error = exc
                if exc.code < 500 and exc.code != 429:
                    break
            except URLError as exc:
                last_error = exc
            if attempt < self.retries:
                time.sleep(0.25 * (2**attempt))
        raise RuntimeError(f"HTTP GET failed for {url}") from last_error
