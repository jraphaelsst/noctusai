"""Status-pinned tests for the methodology router."""
from __future__ import annotations

from app.dependencies import get_data_dir
from app.main import app


def test_methodology_available(client, seeded_data_dir):
    r = client.get("/api/methodology")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert "manual do curso" in body["markdown"]
    assert "modulo-1" in body["modules"]


def test_methodology_unavailable(client, tmp_path):
    app.dependency_overrides[get_data_dir] = lambda: tmp_path
    r = client.get("/api/methodology")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert body["markdown"] is None
    assert body["modules"] == []
