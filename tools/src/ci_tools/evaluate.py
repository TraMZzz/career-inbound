"""Deterministic checks of one /ask response against one golden case."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .client import AskResult
from .golden import GoldenCase


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class CaseResult:
    id: str
    tags: list[str]
    passed: bool
    checks: list[Check]
    latency_ms: float
    error: str | None
    answer_preview: str
    cost_usd: float | None
    input_tokens: int | None
    output_tokens: int | None

    def to_json(self) -> dict:
        data = asdict(self)
        data["pass"] = data.pop("passed")
        return data


def check_case(case: GoldenCase, result: AskResult) -> CaseResult:
    checks: list[Check] = []
    resp = result.response
    if resp is None:
        checks.append(Check("contract", False, result.error or "no response"))
        return CaseResult(
            case.id, case.tags, False, checks, round(result.latency_ms, 1), result.error, "", None, None, None
        )

    checks.append(Check("contract", True))
    answer_lc = resp.answer.lower()
    exp = case.expect

    for term in exp.contains:
        ok = term.lower() in answer_lc
        checks.append(Check(f"contains:{term}", ok, "" if ok else "not found in answer"))
    for term in exp.not_contains:
        ok = term.lower() not in answer_lc
        checks.append(Check(f"not_contains:{term}", ok, "" if ok else "found in answer"))
    source_ids = {s.id for s in resp.sources}
    for sid in exp.sources_include:
        ok = sid in source_ids
        detail = "" if ok else f"sources were {sorted(source_ids) or '[]'}"
        checks.append(Check(f"sources_include:{sid}", ok, detail))
    if exp.action_type:
        types = [a.type for a in resp.actions_proposed]
        ok = exp.action_type in types
        checks.append(Check(f"action_type:{exp.action_type}", ok, "" if ok else f"actions were {types or '[]'}"))

    usage = resp.usage
    return CaseResult(
        id=case.id,
        tags=case.tags,
        passed=all(c.ok for c in checks),
        checks=checks,
        latency_ms=round(result.latency_ms, 1),
        error=None,
        answer_preview=resp.answer[:240],
        cost_usd=usage.cost_usd if usage else None,
        input_tokens=usage.input_tokens if usage else None,
        output_tokens=usage.output_tokens if usage else None,
    )
