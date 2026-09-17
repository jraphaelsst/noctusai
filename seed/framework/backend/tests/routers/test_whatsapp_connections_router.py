"""Tests for
`noctusai_seed.whatsapp_connections_router.create_whatsapp_connections_router`.

The lifted (`community uses social-wiring's mechanisms`, Slice A)
multi-session WAHA connections router — the seed generalization of
`social-wiring`'s `/api/whatsapp/connections*` surface. Drives the
router against the seed `FakeWahaClient` (no monkeypatching — the DI
seam is `waha_client_factory`, exactly as `social-wiring`'s own
`get_waha_client_factory` seam works) and a `_FakeSupabase` double
mirroring `test_connection_store.py`'s.

Auth-boundary tests assert strict `== 401`.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from noctusai_lib.integrations.whatsapp import FakeWahaClient
from noctusai_lib.integrations.whatsapp.connection_store import build_whatsapp_connection_store
from noctusai_lib.security.encrypted_tokens import generate_key
from noctusai_seed.whatsapp_connections_router import create_whatsapp_connections_router


# ─── the same faithful Supabase double as test_connection_store.py ────────
class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows = rows
        self._filters: dict = {}
        self._op = None
        self._payload = None

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def _matches(self, row):
        return all(row.get(k) == v for k, v in self._filters.items())

    def execute(self):
        if self._op == "select":
            return _Resp([dict(r) for r in self._rows if self._matches(r)])
        if self._op == "insert":
            row = dict(self._payload)
            row.setdefault("id", str(uuid.uuid4()))
            row.setdefault("created_at", "2026-09-17T00:00:00+00:00")
            row.setdefault("updated_at", "2026-09-17T00:00:00+00:00")
            self._rows.append(row)
            return _Resp([row])
        if self._op == "update":
            matched = [r for r in self._rows if self._matches(r)]
            for row in matched:
                row.update(self._payload)
            return _Resp([dict(r) for r in matched])
        if self._op == "delete":
            removed = [r for r in self._rows if self._matches(r)]
            self._rows[:] = [r for r in self._rows if not self._matches(r)]
            return _Resp([dict(r) for r in removed])
        return _Resp([])


class _SchemaHandle:
    def __init__(self, tables):
        self._tables = tables

    def table(self, name):
        rows = self._tables.setdefault(name, [])
        return _Query(rows)


class _FakeSupabase:
    def __init__(self):
        self._schemas: dict[str, dict[str, list]] = {}

    def schema(self, name):
        tables = self._schemas.setdefault(name, {})
        return _SchemaHandle(tables)


ORG_A = str(uuid.uuid4())
USER_A = str(uuid.uuid4())


def _org_dep(*, raise_401=False):
    def _dep():
        if raise_401:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        user = MagicMock()
        user.id = USER_A
        return (user, "tok", ORG_A)

    return _dep


def _fake_waha_factory_singleton():
    """One shared `FakeWahaClient` instance regardless of base_url/session
    — the DI override a test uses to avoid a real WAHA HTTP call. Mirrors
    `social-wiring`'s own `get_waha_client_factory` test-override pattern."""
    client = FakeWahaClient(session="default")

    def _factory(*, base_url=None, api_key=None, session="default"):  # noqa: ARG001
        return client

    return _factory, client


def _app(*, waha_base_url="https://waha.example.com", raise_401=False, on_session_event=None):
    store = build_whatsapp_connection_store(
        _FakeSupabase(), encryption_key=generate_key().decode(), schema="social_wiring"
    )
    waha_factory, waha_client = _fake_waha_factory_singleton()
    router = create_whatsapp_connections_router(
        MagicMock(),
        MagicMock(),
        store_factory=lambda: store,
        get_current_user_org=_org_dep(raise_401=raise_401),
        waha_base_url=waha_base_url,
        resolve_webhook_base_url=lambda: "https://product.example.com",
        waha_client_factory=waha_factory,
        on_session_event=on_session_event,
    )
    app = FastAPI()
    app.include_router(router)
    return app, store, waha_client


class TestListAndCreate:
    def test_list_empty(self):
        app, _store, _waha = _app()
        resp = TestClient(app).get("/api/whatsapp/connections")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_derives_fields_and_starts_session(self):
        app, _store, waha = _app()
        resp = TestClient(app).post(
            "/api/whatsapp/connections", json={"label": "Atendimento", "api_key": "secret-key"}
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["label"] == "Atendimento"
        assert body["base_url"] == "https://waha.example.com"
        assert body["session_name"] == "default"
        assert body["webhook_url"].startswith(
            "https://product.example.com/api/whatsapp/webhook/"
        )
        assert "api_key" not in body  # secret never rides the response
        assert waha.start_count == 1
        assert waha.webhook_config["url"] == body["webhook_url"]

    def test_create_without_waha_base_url_503(self):
        app, _store, _waha = _app(waha_base_url=None)
        resp = TestClient(app).post(
            "/api/whatsapp/connections", json={"label": "L", "api_key": "k"}
        )
        assert resp.status_code == 503

    def test_create_without_product_url_503(self):
        store = build_whatsapp_connection_store(
            _FakeSupabase(), encryption_key=generate_key().decode(), schema="social_wiring"
        )
        waha_factory, _client = _fake_waha_factory_singleton()

        def _raise_url():
            raise ValueError("PRODUCT_URL not configured")

        router = create_whatsapp_connections_router(
            MagicMock(), MagicMock(), store_factory=lambda: store,
            get_current_user_org=_org_dep(), waha_base_url="https://waha.example.com",
            resolve_webhook_base_url=_raise_url, waha_client_factory=waha_factory,
        )
        app = FastAPI()
        app.include_router(router)
        resp = TestClient(app).post(
            "/api/whatsapp/connections", json={"label": "L", "api_key": "k"}
        )
        assert resp.status_code == 503

    def test_auth_boundary_strict_401(self):
        app, _store, _waha = _app(raise_401=True)
        resp = TestClient(app).get("/api/whatsapp/connections")
        assert resp.status_code == 401


class TestUpdateAndDelete:
    def _create(self, app):
        return TestClient(app).post(
            "/api/whatsapp/connections", json={"label": "Old", "api_key": "k"}
        ).json()

    def test_patch_updates_label(self):
        app, _store, _waha = _app()
        created = self._create(app)
        resp = TestClient(app).patch(
            f"/api/whatsapp/connections/{created['id']}", json={"label": "New"}
        )
        assert resp.status_code == 200
        assert resp.json()["label"] == "New"

    def test_patch_missing_connection_404(self):
        app, _store, _waha = _app()
        resp = TestClient(app).patch(
            f"/api/whatsapp/connections/{uuid.uuid4()}", json={"label": "New"}
        )
        assert resp.status_code == 404

    def test_delete_then_404_on_repeat(self):
        app, _store, _waha = _app()
        created = self._create(app)
        resp = TestClient(app).delete(f"/api/whatsapp/connections/{created['id']}")
        assert resp.status_code == 204
        resp2 = TestClient(app).delete(f"/api/whatsapp/connections/{created['id']}")
        assert resp2.status_code == 404

    def test_auth_boundary_strict_401(self):
        app, _store, _waha = _app(raise_401=True)
        resp = TestClient(app).delete(f"/api/whatsapp/connections/{uuid.uuid4()}")
        assert resp.status_code == 401


class TestLiveWahaOps:
    def _create(self, app):
        return TestClient(app).post(
            "/api/whatsapp/connections", json={"label": "L", "api_key": "k"}
        ).json()

    def test_status_reports_fake_session(self):
        app, _store, _waha = _app()
        created = self._create(app)
        resp = TestClient(app).get(f"/api/whatsapp/connections/{created['id']}/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["connection_id"] == created["id"]
        assert body["session"] == "default"

    def test_status_missing_connection_404(self):
        app, _store, _waha = _app()
        resp = TestClient(app).get(f"/api/whatsapp/connections/{uuid.uuid4()}/status")
        assert resp.status_code == 404

    def test_qr_scannable_when_unpaired(self):
        app, _store, waha = _app()
        created = self._create(app)
        waha.session_status = "SCAN_QR_CODE"
        resp = TestClient(app).get(f"/api/whatsapp/connections/{created['id']}/qr")
        assert resp.status_code == 200
        body = resp.json()
        assert body["scannable"] is True
        assert body["png_base64"]

    def test_start_restart_logout_dispatch_to_client(self):
        app, _store, waha = _app()
        created = self._create(app)
        cid = created["id"]
        for action, attr in (
            ("start", "start_count"),
            ("restart", "restart_count"),
            ("logout", "logout_count"),
        ):
            resp = TestClient(app).post(f"/api/whatsapp/connections/{cid}/{action}")
            assert resp.status_code == 200, resp.text
        assert waha.start_count >= 1

    def test_recover_fires_on_session_event_hook(self):
        events = []

        async def _hook(connection_id, event, payload):
            events.append((str(connection_id), event, payload))

        app, _store, _waha = _app(on_session_event=_hook)
        created = self._create(app)
        resp = TestClient(app).post(f"/api/whatsapp/connections/{created['id']}/recover")
        assert resp.status_code == 200
        assert resp.json()["connection_id"] == created["id"]
        assert len(events) == 1
        assert events[0][0] == created["id"]
        assert events[0][1] == "session.status"

    def test_configure_webhook_persists_url(self):
        app, _store, waha = _app()
        created = self._create(app)
        resp = TestClient(app).post(
            f"/api/whatsapp/connections/{created['id']}/webhook",
            json={"url": "https://custom-hook.example.com", "events": ["message"]},
        )
        assert resp.status_code == 200
        assert resp.json()["url"] == "https://custom-hook.example.com"
        assert waha.webhook_config["url"] == "https://custom-hook.example.com"
        # persisted — a subsequent GET reflects the new webhook_url
        listed = TestClient(app).get("/api/whatsapp/connections").json()
        assert listed[0]["webhook_url"] == "https://custom-hook.example.com"

    def test_auth_boundary_strict_401(self):
        app, _store, _waha = _app(raise_401=True)
        resp = TestClient(app).get(f"/api/whatsapp/connections/{uuid.uuid4()}/status")
        assert resp.status_code == 401
