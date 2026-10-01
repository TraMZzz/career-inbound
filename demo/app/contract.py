"""Course HTTP contract v0.1 (server side). Same shape as ci-tools/contract.py."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    input: str
    context: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True


class Source(BaseModel):
    id: str
    title: str
    snippet: str


class Step(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    ok: bool


class ActionProposed(BaseModel):
    type: str
    target: str
    requires_confirmation: bool = True


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    latency_ms: float
    model: str


class AskResponse(BaseModel):
    answer: str
    sources: list[Source] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    actions_proposed: list[ActionProposed] = Field(default_factory=list)
    usage: Usage
    # Not part of the course contract (extra fields are allowed): problems the service noticed in its own output.
    warnings: list[str] = Field(default_factory=list)
