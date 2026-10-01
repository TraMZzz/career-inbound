"""The capstone HTTP contract (v0.1) as Pydantic models.

Every capstone, in any language, exposes:
  GET  /health -> {"status": "ok", "version": "<git sha or tag>"}
  POST /ask    -> AskResponse (below)

Fields a stage does not need yet may be empty or absent; ci-check knows what each stage expects.
Unknown extra fields are allowed so projects can return more than the contract requires.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Open(BaseModel):
    model_config = ConfigDict(extra="allow")


class AskRequest(BaseModel):
    input: str
    context: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True


class Source(_Open):
    id: str
    title: str = ""
    snippet: str = ""


class Step(_Open):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    ok: bool


class ActionProposed(_Open):
    type: str
    target: str = ""
    requires_confirmation: bool


class Usage(_Open):
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: float | None = None
    model: str | None = None

    def missing_fields(self) -> list[str]:
        return [
            name
            for name in ("input_tokens", "output_tokens", "cost_usd", "latency_ms", "model")
            if getattr(self, name) is None
        ]


class AskResponse(_Open):
    answer: str
    sources: list[Source] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    actions_proposed: list[ActionProposed] = Field(default_factory=list)
    usage: Usage | None = None


class Health(_Open):
    status: str
    version: str = ""
