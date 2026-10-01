from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_matches_contract(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "lesson-01")
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "lesson-01"}
