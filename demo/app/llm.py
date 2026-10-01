"""One structured LLM call: prompt in, validated Diagnosis out.

Uses the official Anthropic SDK with structured outputs (`messages.parse` + a Pydantic model), so the
response is guaranteed to match the schema instead of being parsed out of free text.
Docs: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, Protocol

from anthropic import Anthropic
from pydantic import BaseModel, Field, ValidationError

from demo_shop.topology import ACTION_TYPES, CATEGORIES, SERVICES

DEFAULT_MODEL = "claude-sonnet-5-5"

# Literal types become JSON-schema enums: the model can only answer with known values.
Category = Literal[tuple(CATEGORIES)]  # type: ignore[valid-type]
ServiceName = Literal[tuple([*SERVICES, "unknown"])]  # type: ignore[valid-type]
ActionType = Literal[tuple(ACTION_TYPES)]  # type: ignore[valid-type]


class ProposedAction(BaseModel):
    type: ActionType
    target: ServiceName
    reason: str = Field(description="why this action, one sentence")


class Diagnosis(BaseModel):
    summary: str = Field(description="what is happening, 1-2 sentences, in Ukrainian")
    category: Category
    root_service: ServiceName = Field(description="the service where the failure starts, not where it is observed")
    evidence_log_ids: list[str] = Field(description="ids of log lines from the input that support the diagnosis")
    next_steps: list[str] = Field(description="2-4 concrete next steps for the on-call engineer, in Ukrainian")
    actions: list[ProposedAction] = Field(description="actions a human may approve; empty if none is justified")


@dataclass
class LLMResult:
    diagnosis: Diagnosis
    input_tokens: int
    output_tokens: int
    model: str


class LLMError(RuntimeError):
    pass


class Diagnoser(Protocol):
    model: str

    def diagnose(self, system: str, user: str) -> LLMResult: ...


class AnthropicDiagnoser:
    def __init__(self, client: Anthropic | None = None, model: str | None = None, max_tokens: int = 1500):
        self.model = model or os.getenv("COPILOT_MODEL", DEFAULT_MODEL)
        self.max_tokens = max_tokens
        # timeout per request and SDK-level retries with backoff on 429/5xx/connection errors
        self._client = client or Anthropic(timeout=30.0, max_retries=2)

    def diagnose(self, system: str, user: str) -> LLMResult:
        try:
            resp = self._client.messages.parse(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=Diagnosis,
            )
        except ValidationError as exc:
            # e.g. the answer was cut off by max_tokens and the JSON is incomplete
            raise LLMError(f"model output does not match the schema: {exc.error_count()} error(s)") from exc
        if resp.stop_reason in ("max_tokens", "refusal") or resp.parsed_output is None:
            raise LLMError(f"model returned no complete structured output (stop_reason={resp.stop_reason})")
        return LLMResult(
            diagnosis=resp.parsed_output,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            model=resp.model,
        )
