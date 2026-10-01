"""Copilot v1 without network: the LLM is replaced by a scripted fake, everything else is real."""

import json
from pathlib import Path

import httpx2
import pytest
from anthropic import Anthropic
from fastapi.testclient import TestClient

from app.copilot import Copilot, render
from app.llm import AnthropicDiagnoser, Diagnosis, LLMResult
from app.main import app, get_copilot
from app.pricing import cost_usd
from demo_shop.store import default_store

GOLDEN = [json.loads(line) for line in Path("evals/golden.jsonl").read_text(encoding="utf-8").splitlines()]
INC_001 = next(g for g in GOLDEN if g["id"] == "inc-001")["input"]


class FakeLLM:
    model = "claude-sonnet-5-5"

    def __init__(self, diagnosis: dict):
        self.diagnosis = diagnosis
        self.calls: list[tuple[str, str]] = []

    def diagnose(self, system: str, user: str) -> LLMResult:
        self.calls.append((system, user))
        return LLMResult(Diagnosis.model_validate(self.diagnosis), 1000, 200, self.model)


def diag(**over) -> dict:
    base = {
        "summary": "Пул зʼєднань payments вичерпано",
        "category": "db_pool_exhausted",
        "root_service": "payments",
        "evidence_log_ids": [],
        "next_steps": ["Перевірити payments"],
        "actions": [],
    }
    return base | over


@pytest.fixture
def store():
    return default_store()


def test_answer_format_matches_golden_expectations(store):
    llm = FakeLLM(diag())
    resp = Copilot(store, llm).ask(INC_001)
    expected = next(g for g in GOLDEN if g["id"] == "inc-001")["expect"]["contains"]
    for term in expected:
        assert term in resp.answer.lower()


def test_prompt_contains_only_alerting_service_data(store):
    llm = FakeLLM(diag())
    Copilot(store, llm).ask(INC_001)
    _, user = llm.calls[0]
    assert "LOGS of checkout" in user
    assert "upstream payments returned 503" in user  # the symptom is visible
    assert "QueuePool" not in user  # the cause (payments logs) is not: v1 limitation


def test_invented_evidence_is_dropped_and_real_is_cited(store):
    llm = FakeLLM(diag())
    Copilot(store, llm).ask(INC_001)
    real_id = llm.calls[0][1].split("[", 2)[2].split("]")[0]  # first log id in the prompt
    resp = Copilot(store, FakeLLM(diag(evidence_log_ids=[real_id, "L99999", real_id]))).ask(INC_001)
    assert [s.id for s in resp.sources] == [real_id]
    assert resp.warnings and "L99999" in resp.warnings[0]


def test_actions_always_require_confirmation(store):
    action = {"type": "restart_service", "target": "payments", "reason": "звільнити пул"}
    resp = Copilot(store, FakeLLM(diag(actions=[action]))).ask(INC_001)
    assert [(a.type, a.target, a.requires_confirmation) for a in resp.actions_proposed] == [
        ("restart_service", "payments", True)
    ]


@pytest.mark.parametrize("case_id", ["edge-01", "edge-02", "edge-03"])
def test_edge_cases_skip_the_model(store, case_id):
    llm = FakeLLM(diag())
    case = next(g for g in GOLDEN if g["id"] == case_id)
    resp = Copilot(store, llm).ask(case["input"])
    assert llm.calls == []
    assert "категорія: unknown" in resp.answer.lower()
    assert resp.usage.cost_usd == 0.0


def test_usage_and_cost(store):
    resp = Copilot(store, FakeLLM(diag())).ask(INC_001)
    assert resp.usage.input_tokens == 1000 and resp.usage.output_tokens == 200
    assert resp.usage.cost_usd == cost_usd("claude-sonnet-5-5", 1000, 200) == 0.004
    assert cost_usd("some-unknown-model", 10, 10) is None


def test_prompt_versions(store):
    v1 = Copilot(store, FakeLLM(diag()), prompt_version="v1")
    v2 = Copilot(store, FakeLLM(diag()), prompt_version="v2")
    assert "demo-shop" not in v1.system and "Сервіс-причина" in v2.system
    with pytest.raises(ValueError):
        Copilot(store, FakeLLM(diag()), prompt_version="v3")


def test_render_is_stable():
    text = render(Diagnosis.model_validate(diag(next_steps=["a", "b"])))
    assert text.splitlines()[1:3] == ["Категорія: db_pool_exhausted", "Сервіс-причина: payments"]


def test_ask_endpoint_contract(store):
    app.dependency_overrides[get_copilot] = lambda: Copilot(store, FakeLLM(diag()))
    try:
        r = TestClient(app).post("/ask", json={"input": INC_001, "context": {}, "dry_run": True})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"answer", "sources", "steps", "actions_proposed", "usage"}
    assert set(body["usage"]) == {"input_tokens", "output_tokens", "cost_usd", "latency_ms", "model"}


def test_ask_without_api_key_is_a_clear_503(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_copilot.cache_clear()
    r = TestClient(app).post("/ask", json={"input": INC_001})
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_anthropic_request_shape():
    """The real SDK path against a mocked HTTP transport: request body and parsing of the response."""
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        return httpx2.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-5-5",
                "content": [{"type": "text", "text": json.dumps(diag(), ensure_ascii=False)}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1500, "output_tokens": 180},
            },
        )

    client = Anthropic(api_key="test", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    result = AnthropicDiagnoser(client=client, model="claude-sonnet-5-5").diagnose("SYSTEM", "USER")
    assert result.diagnosis.category == "db_pool_exhausted"
    assert (result.input_tokens, result.output_tokens) == (1500, 180)
    body = seen["body"]
    assert body["model"] == "claude-sonnet-5-5" and body["system"] == "SYSTEM"
    schema = body["output_config"]["format"]["schema"]
    assert "db_pool_exhausted" in schema["properties"]["category"]["enum"]
    assert "anyOf" not in json.dumps(schema)  # structured outputs do not support unions


def test_prompt_includes_deploys_of_alerting_service(store):
    inc_003 = next(g for g in GOLDEN if g["id"] == "inc-003")["input"]
    llm = FakeLLM(diag(category="bad_deploy", root_service="checkout"))
    Copilot(store, llm).ask(inc_003)
    user = llm.calls[0][1]
    assert "DEPLOYS of checkout" in user and "2.13.2 -> 2.14.0" in user


@pytest.mark.parametrize("stop_reason", ["max_tokens", "refusal"])
def test_incomplete_model_output_is_a_502_not_a_500(store, stop_reason):
    """A truncated or refused answer must surface as a clear 502, not an unhandled 500."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        text = json.dumps(diag(), ensure_ascii=False)[:40] if stop_reason == "max_tokens" else "I can't help with that."
        return httpx2.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-5-5",
                "content": [{"type": "text", "text": text}],
                "stop_reason": stop_reason,
                "stop_sequence": None,
                "usage": {"input_tokens": 1500, "output_tokens": 1500},
            },
        )

    client = Anthropic(api_key="test", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    diagnoser = AnthropicDiagnoser(client=client, model="claude-sonnet-5-5")
    app.dependency_overrides[get_copilot] = lambda: Copilot(store, diagnoser)
    try:
        r = TestClient(app).post("/ask", json={"input": INC_001})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 502
    assert "model" in r.json()["detail"]
