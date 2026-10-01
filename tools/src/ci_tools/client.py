"""Thin HTTP client for the contract. Measures client-side latency (what a user actually waits)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx2
from pydantic import ValidationError

from .contract import AskRequest, AskResponse, Health


@dataclass
class AskResult:
    response: AskResponse | None
    latency_ms: float
    error: str | None = None
    raw: Any = None


class ContractClient:
    def __init__(self, base_url: str, timeout_s: float = 60.0, transport: httpx2.BaseTransport | None = None):
        self._http = httpx2.Client(base_url=base_url.rstrip("/"), timeout=timeout_s, transport=transport)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> ContractClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def health(self) -> tuple[Health | None, str | None]:
        try:
            r = self._http.get("/health")
        except httpx2.HTTPError as exc:
            return None, f"GET /health failed: {type(exc).__name__}: {exc}"
        if r.status_code != 200:
            return None, f"GET /health returned HTTP {r.status_code}"
        try:
            return Health.model_validate(r.json()), None
        except (ValueError, ValidationError) as exc:
            return None, f"GET /health body does not match contract: {exc}"

    def ask(self, text: str, context: dict[str, Any] | None = None, dry_run: bool = True) -> AskResult:
        payload = AskRequest(input=text, context=context or {}, dry_run=dry_run).model_dump()
        started = time.perf_counter()
        try:
            r = self._http.post("/ask", json=payload)
        except httpx2.HTTPError as exc:
            elapsed = (time.perf_counter() - started) * 1000
            return AskResult(None, elapsed, f"request failed: {type(exc).__name__}: {exc}")
        elapsed = (time.perf_counter() - started) * 1000
        if r.status_code != 200:
            return AskResult(None, elapsed, f"HTTP {r.status_code}: {r.text[:300]}")
        try:
            body = r.json()
        except ValueError:
            return AskResult(None, elapsed, f"response is not JSON: {r.text[:300]}")
        try:
            return AskResult(AskResponse.model_validate(body), elapsed, None, body)
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first["loc"])
            return AskResult(None, elapsed, f"response does not match contract: {loc}: {first['msg']}", body)
