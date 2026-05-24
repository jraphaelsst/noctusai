"""Status-pinned tests for the runs router (DI-seam'd executor — no Drive/OpenAI)."""
from __future__ import annotations

from app.main import app
from app.routers import runs_router
from app.services import runs_service


async def _fake_exec(run_id: str, mode: str, drive_url: str | None) -> None:
    runs_service.mark_done(run_id, f"fake {mode}")


def test_start_run_fake_accepted(client):
    app.dependency_overrides[runs_router.get_run_executor] = lambda: _fake_exec
    r = client.post("/api/runs", json={"fake": True})
    assert r.status_code == 202
    body = r.json()
    assert body["accepted"] is True and body["mode"] == "fake"
    run_id = body["run_id"]
    # Starlette runs the BackgroundTask before the response returns → status done.
    runs = client.get("/api/runs").json()["runs"]
    assert any(x["run_id"] == run_id and x["status"] == "done" for x in runs)


def test_start_run_drive_accepted(client):
    app.dependency_overrides[runs_router.get_run_executor] = lambda: _fake_exec
    r = client.post("/api/runs", json={"drive_url": "https://drive.google.com/x"})
    assert r.status_code == 202
    assert r.json()["mode"] == "drive"


def test_start_run_requires_source(client):
    app.dependency_overrides[runs_router.get_run_executor] = lambda: _fake_exec
    r = client.post("/api/runs", json={})
    assert r.status_code == 400


def test_list_runs_empty(client):
    r = client.get("/api/runs")
    assert r.status_code == 200
    assert r.json()["runs"] == []
