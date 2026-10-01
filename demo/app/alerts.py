"""Parse the alert text that comes in POST /ask.

Expected shape (Alertmanager-like):
    [FIRING:1] HighErrorRate service=checkout severity=page
    error_rate 13.0% > 5% for 5m
    startsAt=2026-10-05T14:03:00Z
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

_NAME = re.compile(r"\[FIRING(?::\d+)?\]\s+(\w+)")
_SERVICE = re.compile(r"\bservice=([a-z0-9][a-z0-9-]*)")
_STARTS = re.compile(r"\bstartsAt=(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)")


@dataclass(frozen=True)
class Alert:
    name: str
    service: str
    starts_at: datetime
    text: str


def parse_alert(text: str) -> Alert | None:
    """Return None if the text is not a firing alert with a service and a start time."""
    name, service, starts = _NAME.search(text), _SERVICE.search(text), _STARTS.search(text)
    if not (name and service and starts):
        return None
    ts = datetime.fromisoformat(starts.group(1).replace("Z", "+00:00"))
    return Alert(name=name.group(1), service=service.group(1), starts_at=ts, text=text.strip())
