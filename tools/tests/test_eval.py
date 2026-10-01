import json
from argparse import Namespace

import httpx2
import pytest

from ci_tools import eval_cli
from ci_tools.golden import GoldenError, load_golden
from ci_tools.stats import percentile


def fake_service(answer_for):
    """MockTransport that answers /ask with answer_for(request_json) -> dict."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/health":
            return httpx2.Response(200, json={"status": "ok", "version": "test"})
        if request.url.path == "/ask":
            return httpx2.Response(200, json=answer_for(json.loads(request.content)))
        return httpx2.Response(404)

    return httpx2.MockTransport(handler)


def write_golden(tmp_path, rows):
    p = tmp_path / "golden.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return p


def test_percentile_nearest_rank():
    assert percentile([], 50) is None
    assert percentile([5], 95) == 5
    data = list(range(1, 21))  # 1..20
    assert percentile(data, 50) == 10
    assert percentile(data, 95) == 19
    assert percentile(data, 100) == 20


def test_golden_rejects_duplicates_and_unknown_fields(tmp_path):
    p = write_golden(
        tmp_path,
        [
            {"id": "a", "input": "x", "expect": {"contains": ["y"]}},
            {"id": "a", "input": "x"},
            {"id": "b", "input": "x", "expect": {"contain": ["typo"]}},
        ],
    )
    with pytest.raises(GoldenError) as exc:
        load_golden(p)
    msg = str(exc.value)
    assert "duplicate id 'a'" in msg
    assert "line 3" in msg


def test_run_scores_cases_and_writes_results(tmp_path):
    golden = write_golden(
        tmp_path,
        [
            {
                "id": "g1",
                "input": "alert A",
                "expect": {"contains": ["DB_POOL"], "sources_include": ["log:1"]},
                "tags": ["core"],
            },
            {
                "id": "g2",
                "input": "alert B",
                "expect": {"contains": ["redis"], "action_type": "restart_service"},
                "tags": ["core"],
            },
            {"id": "g3", "input": "", "expect": {"not_contains": ["root cause"]}, "tags": ["edge"]},
        ],
    )

    def answer(req):
        if req["input"] == "alert A":
            return {
                "answer": "category: db_pool",
                "sources": [{"id": "log:1"}],
                "usage": {"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.001, "latency_ms": 5, "model": "m"},
            }
        if req["input"] == "alert B":
            return {"answer": "redis is down", "actions_proposed": []}
        return {"answer": "Root cause unknown"}

    out = tmp_path / "results.json"
    args = Namespace(url="http://svc", golden=str(golden), out=str(out), timeout=5, concurrency=2, min_pass=None)
    assert eval_cli.cmd_run(args, transport=fake_service(answer)) == 0

    data = json.loads(out.read_text())
    by_id = {c["id"]: c for c in data["cases"]}
    assert by_id["g1"]["pass"] is True
    assert by_id["g2"]["pass"] is False  # action missing
    assert by_id["g3"]["pass"] is False  # case-insensitive not_contains
    assert data["pass_rate"] == round(1 / 3, 4)
    assert data["cost_per_1k_usd"] == 1.0
    assert data["by_tag"]["core"] == {"passed": 1, "total": 2}


def test_run_quality_gate(tmp_path):
    golden = write_golden(tmp_path, [{"id": "g1", "input": "x", "expect": {"contains": ["yes"]}}])
    args = Namespace(
        url="http://svc", golden=str(golden), out=str(tmp_path / "r.json"), timeout=5, concurrency=1, min_pass=0.8
    )
    assert eval_cli.cmd_run(args, transport=fake_service(lambda r: {"answer": "no"})) == 1


def test_contract_violation_fails_case(tmp_path):
    golden = write_golden(tmp_path, [{"id": "g1", "input": "x", "expect": {"contains": ["a"]}}])
    out = tmp_path / "r.json"
    args = Namespace(url="http://svc", golden=str(golden), out=str(out), timeout=5, concurrency=1, min_pass=None)
    eval_cli.cmd_run(args, transport=fake_service(lambda r: {"text": "wrong field"}))
    case = json.loads(out.read_text())["cases"][0]
    assert case["pass"] is False
    assert "answer" in case["error"]


def test_attack_detects_canary_and_unconfirmed_action(tmp_path):
    def obedient(req):
        text = req["input"] + json.dumps(req["context"])
        actions = [{"type": "restart_service", "target": "all", "requires_confirmation": False}]
        import re

        m = re.search(r"CANARY-[A-Z0-9-]+", text)
        return {"answer": m.group(0) if m else "ok", "actions_proposed": actions}

    args = Namespace(url="http://svc", out=str(tmp_path / "a.json"), timeout=5, concurrency=1)
    assert eval_cli.cmd_attack(args, transport=fake_service(obedient)) == 1
    report = json.loads((tmp_path / "a.json").read_text())
    assert report["failed"] == report["total"]


def test_attack_passes_for_safe_service(tmp_path):
    def safe(req):
        return {
            "answer": "I can only help with incidents.",
            "actions_proposed": [{"type": "restart_service", "target": "x", "requires_confirmation": True}],
        }

    args = Namespace(url="http://svc", out=str(tmp_path / "a.json"), timeout=5, concurrency=1)
    assert eval_cli.cmd_attack(args, transport=fake_service(safe)) == 0


def test_perf_reports_cost(tmp_path):
    golden = write_golden(tmp_path, [{"id": "g1", "input": "x", "expect": {"contains": ["a"]}}])
    out = tmp_path / "perf.json"
    args = Namespace(
        url="http://svc", golden=str(golden), out=str(out), timeout=5, concurrency=1, n=10, exclude_tag=None
    )
    usage = {"input_tokens": 1000, "output_tokens": 100, "cost_usd": 0.002, "latency_ms": 10, "model": "m"}
    assert eval_cli.cmd_perf(args, transport=fake_service(lambda r: {"answer": "a", "usage": usage})) == 0
    data = json.loads(out.read_text())
    assert data["requests"] == 10
    assert data["cost_per_1k_usd"] == 2.0
    assert data["models"] == ["m"]


def test_compare_lists_fixed_and_broken(tmp_path, capsys):
    a = {"pass_rate": 0.5, "cases": [{"id": "x", "pass": True}, {"id": "y", "pass": False}]}
    b = {"pass_rate": 0.5, "cases": [{"id": "x", "pass": False}, {"id": "y", "pass": True}]}
    (tmp_path / "a.json").write_text(json.dumps(a))
    (tmp_path / "b.json").write_text(json.dumps(b))
    eval_cli.cmd_compare(Namespace(before=str(tmp_path / "a.json"), after=str(tmp_path / "b.json")))
    out = capsys.readouterr().out
    assert "fixed  (1): y" in out
    assert "broken (1): x" in out


def test_attack_refuses_to_run_against_wrong_url(tmp_path):
    transport = httpx2.MockTransport(lambda request: httpx2.Response(404))
    args = Namespace(url="http://svc", out=str(tmp_path / "a.json"), timeout=5, concurrency=1)
    assert eval_cli.cmd_attack(args, transport=transport) == 2


def test_perf_can_exclude_edge_cases(tmp_path):
    golden = write_golden(
        tmp_path,
        [
            {"id": "g1", "input": "real", "expect": {"contains": ["a"]}, "tags": ["core"]},
            {"id": "e1", "input": "", "expect": {"contains": ["a"]}, "tags": ["edge"]},
        ],
    )
    seen = []

    def answer(req):
        seen.append(req["input"])
        return {"answer": "a"}

    args = Namespace(
        url="http://svc",
        golden=str(golden),
        out=str(tmp_path / "p.json"),
        timeout=5,
        concurrency=1,
        n=4,
        exclude_tag=["edge"],
    )
    assert eval_cli.cmd_perf(args, transport=fake_service(answer)) == 0
    assert seen == ["real"] * 4


def test_attack_refuses_to_run_when_ask_rejects_everything(tmp_path):
    def handler(request):
        if request.url.path == "/health":
            return httpx2.Response(200, json={"status": "ok"})
        return httpx2.Response(422, json={"detail": "field 'query' required"})

    args = Namespace(url="http://svc", out=str(tmp_path / "a.json"), timeout=5, concurrency=1)
    assert eval_cli.cmd_attack(args, transport=httpx2.MockTransport(handler)) == 2
