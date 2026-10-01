"""Course HTTP contract v0.1. Do not rename fields: the course tools (ci-eval, ci-check) rely on them."""

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
    """One tool call of the agent. Required from stage 3."""

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    ok: bool


class ActionProposed(BaseModel):
    type: str
    target: str
    requires_confirmation: bool = True


class Usage(BaseModel):
    """Required from stage 5 (latency and cost)."""

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
    usage: Usage | None = None
