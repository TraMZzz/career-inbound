"""Golden set: evals/golden.jsonl, one case per line.

{"id": "g-001", "input": "...", "context": {...}, "expect": {"contains": [...], "not_contains": [...],
 "sources_include": [...], "action_type": "..."}, "tags": ["edge"]}

`context` is optional and is sent as-is in the /ask request.
All string comparisons in `contains` / `not_contains` are case-insensitive substring checks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Expect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contains: list[str] = Field(default_factory=list)
    not_contains: list[str] = Field(default_factory=list)
    sources_include: list[str] = Field(default_factory=list)
    action_type: str | None = None

    def is_empty(self) -> bool:
        return not (self.contains or self.not_contains or self.sources_include or self.action_type)


class GoldenCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    input: str
    context: dict[str, Any] = Field(default_factory=dict)
    expect: Expect = Field(default_factory=Expect)
    tags: list[str] = Field(default_factory=list)


class GoldenError(Exception):
    """Raised with a human-readable, line-numbered list of problems."""


def load_golden(path: Path) -> list[GoldenCase]:
    if not path.exists():
        raise GoldenError(f"{path}: file not found")
    problems: list[str] = []
    cases: list[GoldenCase] = []
    seen: set[str] = set()
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(f"line {lineno}: invalid JSON ({exc.msg})")
            continue
        try:
            case = GoldenCase.model_validate(data)
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first["loc"])
            problems.append(f"line {lineno}: {loc}: {first['msg']}")
            continue
        if case.id in seen:
            problems.append(f"line {lineno}: duplicate id {case.id!r}")
            continue
        seen.add(case.id)
        cases.append(case)
    if problems:
        raise GoldenError(f"{path}:\n  " + "\n  ".join(problems))
    if not cases:
        raise GoldenError(f"{path}: no cases")
    return cases
