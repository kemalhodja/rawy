"""FastAPI duman testi (DB yok)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data.get("name") == "Rawy"


def test_health():
    r = client.get("/health/")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"
