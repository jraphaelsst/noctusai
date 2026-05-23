"""Tests for the Core Fleet Control router (admin-gated container ops).

Each test builds a dedicated app with ONLY the fleet router mounted and uses
FastAPI ``dependency_overrides`` (real DI seam — no monkeypatching of our own
symbols) to (a) inject the seed Fake controller and (b) toggle the admin gate.
The seed allowlist is exercised through the live HTTP boundary:
  - bad verb → 422 (FleetVerb enum at the path boundary),
  - unregistered slug → 400 (FleetControlError raised inside the controller).
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException, Header
from fastapi.testclient import TestClient

from app.routers import fleet_control as fc
from app.dependencies import get_current_admin
from noctusai_lib.domain.fleet_control import FakeContainerController

REGISTERED = {"core", "erp-imobiliario", "social-wiring"}


def _make_app(*, admin_ok: bool):
    """Minimal app, fleet router only. Fake controller + admin gate injected
    purely through FastAPI's dependency-override map (no symbol reassignment)."""
    app = FastAPI()
    app.include_router(fc.router)

    fake = FakeContainerController(
        slugs=["core", "social-wiring"], registered_slugs=REGISTERED
    )

    async def _admin_ok(authorization: str | None = Header(None)):
        return ("admin-user", "token")

    async def _admin_403(authorization: str | None = Header(None)):
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")

    app.dependency_overrides[fc.get_controller] = lambda: fake
    app.dependency_overrides[get_current_admin] = _admin_ok if admin_ok else _admin_403
    return app, fake


# ── admin gate ──────────────────────────────────────────────────────
def test_non_admin_gets_403_on_status():
    app, _ = _make_app(admin_ok=False)
    resp = TestClient(app).get("/api/fleet")
    assert resp.status_code == 403, resp.text


def test_non_admin_gets_403_on_action():
    app, _ = _make_app(admin_ok=False)
    resp = TestClient(app).post("/api/fleet/core/stop")
    assert resp.status_code == 403, resp.text


# ── happy path ──────────────────────────────────────────────────────
def test_admin_lists_fleet_status():
    app, _ = _make_app(admin_ok=True)
    resp = TestClient(app).get("/api/fleet")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 2
    slugs = {p["slug"] for p in body["products"]}
    assert slugs == {"core", "social-wiring"}
    assert all("display" in p and "running" in p for p in body["products"])


def test_admin_stops_and_status_reflects():
    app, fake = _make_app(admin_ok=True)
    client = TestClient(app)
    resp = client.post("/api/fleet/core/stop")
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True and resp.json()["verb"] == "stop"
    status = client.get("/api/fleet").json()
    core = next(p for p in status["products"] if p["slug"] == "core")
    assert core["running"] is False


@pytest.mark.parametrize("verb", ["start", "stop", "restart"])
def test_admin_each_allowed_verb_ok(verb):
    app, _ = _make_app(admin_ok=True)
    resp = TestClient(app).post(f"/api/fleet/core/{verb}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["verb"] == verb


# ── verb validation (422 at the boundary) ───────────────────────────
@pytest.mark.parametrize("verb", ["rm", "exec", "down", "kill", "delete"])
def test_disallowed_verb_is_422(verb):
    app, _ = _make_app(admin_ok=True)
    resp = TestClient(app).post(f"/api/fleet/core/{verb}")
    assert resp.status_code == 422, resp.text


# ── slug validation (400 from the seed allowlist) ───────────────────
def test_unregistered_slug_is_400():
    app, _ = _make_app(admin_ok=True)
    resp = TestClient(app).post("/api/fleet/not-a-product/start")
    assert resp.status_code == 400, resp.text
    assert "not a registered product" in resp.json()["detail"]
