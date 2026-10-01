"""Read-only access to demo-shop observability data (the files in data/demo-shop/).

This is what the copilot is allowed to see: logs, metrics and deploys. Ground truth
(data/demo-shop/incidents.jsonl) is deliberately NOT exposed here.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "demo-shop"
LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _read(name: str, data_dir: Path) -> list[dict]:
    path = data_dir / f"{name}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run `make data` to generate demo-shop data")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class Store:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.logs = _read("logs", data_dir)
        self.metrics = _read("metrics", data_dir)
        self.deploys = _read("deploys", data_dir)
        for rows in (self.logs, self.metrics, self.deploys):
            for r in rows:
                r["_ts"] = parse_ts(r["ts"])

    @staticmethod
    def _public(row: dict) -> dict:
        return {k: v for k, v in row.items() if not k.startswith("_")}

    def search_logs(
        self,
        service: str,
        start: datetime,
        end: datetime,
        min_level: str = "INFO",
        contains: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        floor = LEVELS[min_level]
        needle = contains.lower() if contains else None
        rows = [
            r
            for r in self.logs
            if r["service"] == service
            and start <= r["_ts"] <= end
            and LEVELS[r["level"]] >= floor
            and (needle is None or needle in r["msg"].lower())
        ]
        return [self._public(r) for r in rows[-limit:]]

    def get_metrics(self, service: str, start: datetime, end: datetime) -> list[dict]:
        return [self._public(r) for r in self.metrics if r["service"] == service and start <= r["_ts"] <= end]

    def list_deploys(self, start: datetime, end: datetime, service: str | None = None) -> list[dict]:
        return [
            self._public(r)
            for r in self.deploys
            if start <= r["_ts"] <= end and (service is None or r["service"] == service)
        ]

    def log_ids(self) -> set[str]:
        return {r["id"] for r in self.logs}


@lru_cache(maxsize=1)
def default_store() -> Store:
    return Store()
