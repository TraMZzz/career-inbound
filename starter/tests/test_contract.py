from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ask_returns_contract_shape():
    r = client.post("/ask", json={"input": "hello", "context": {}, "dry_run": True})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["answer"], str)
    for key in ("sources", "steps", "actions_proposed"):
        assert isinstance(body[key], list)
