"""Parity test — the seed router factories vs. `social-wiring`'s FROZEN
contract (`community uses social-wiring's mechanisms`, Slice A).

Drives `create_api_keys_router` / `create_whatsapp_connections_router`
with `social-wiring`-shaped fixtures (its real managed-key specs, its
real route list) and asserts against the paths + response-field shapes
`social-wiring`'s own routers/schemas declare — read directly from
`products/social-wiring/backend/app/routers/settings_router.py` +
`app/schemas/settings.py` + `app/routers/whatsapp_connections_router.py`
+ `app/schemas/whatsapp_connection.py` docstrings/field lists (this test
does NOT import product code — seed tests never depend on a product;
the fixtures below are transcribed verbatim from those files so a
future SW contract change that isn't mirrored here fails loudly).

`social-wiring` itself is untouched by this slice; this test exists so
a LATER slice's "SW now consumes the seed router" migration has a
pre-existing contract witness to diff against.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from noctusai_lib.integrations.whatsapp import FakeWahaClient
from noctusai_lib.integrations.whatsapp.connection_store import build_whatsapp_connection_store
from noctusai_lib.security.api_keys import ApiKeyOption, ApiKeySpec, build_api_key_store
from noctusai_lib.security.encrypted_tokens import generate_key
from noctusai_seed.api_keys_router import create_api_keys_router
from noctusai_seed.whatsapp_connections_router import create_whatsapp_connections_router


# ─── social-wiring's REAL managed-key specs, transcribed verbatim from
# products/social-wiring/backend/app/services/api_keys_store.py:152-350
# (name / is_secret / testable / input_type / options / default only —
# the pt-BR label/description/placeholder prose is not contract-load-bearing
# for this parity check).
SW_API_KEY_SPECS = (
    ApiKeySpec("openai_api_key", "OpenAI API Key", "d", is_secret=True, testable=True, input_type="password"),
    ApiKeySpec("anthropic_api_key", "Anthropic Key", "d", is_secret=True, testable=True, input_type="password"),
    ApiKeySpec("gemini_api_key", "Gemini Key", "d", is_secret=True, testable=True, input_type="password"),
    ApiKeySpec(
        "llm_vision_provider", "Provedor de leitura", "d", is_secret=False, testable=False, input_type="select",
        options=(
            ApiKeyOption("openai", "OpenAI"),
            ApiKeyOption("anthropic", "Anthropic (Claude)"),
            ApiKeyOption("gemini", "Google Gemini"),
        ),
        default="openai",
    ),
    ApiKeySpec(
        "llm_embedding_provider", "Provedor embeddings", "d", is_secret=False, testable=False, input_type="select",
        options=(ApiKeyOption("openai", "OpenAI"), ApiKeyOption("gemini", "Google Gemini")),
        default="openai",
    ),
    ApiKeySpec(
        "llm_chat_provider", "Provedor de análise", "d", is_secret=False, testable=False, input_type="select",
        options=(
            ApiKeyOption("openai", "OpenAI"),
            ApiKeyOption("anthropic", "Anthropic (Claude)"),
            ApiKeyOption("gemini", "Google Gemini"),
        ),
        default="openai",
    ),
    ApiKeySpec("infosimples_token", "InfoSimples Token", "d", is_secret=True, testable=True, input_type="password"),
    ApiKeySpec("infosimples_email_envio", "E-mail de Envio", "d", is_secret=False, testable=False, input_type="email"),
)
SW_MANAGED_API_KEYS = tuple(spec.name for spec in SW_API_KEY_SPECS)

#: `social-wiring/app/schemas/settings.py::ApiKeyStatus` field set (verbatim).
SW_API_KEY_STATUS_FIELDS = {
    "key", "label", "description", "is_secret", "testable", "input_type",
    "placeholder", "configured", "options", "default", "hint", "source", "updated_at",
}

#: `social-wiring/app/routers/whatsapp_connections_router.py` module docstring
#: (lines 6-20) — CRUD + live-WAHA-ops paths only (chat inbox / SSE excluded,
#: those are product-specific and out of this slice's scope).
SW_WHATSAPP_CONNECTIONS_PATHS = {
    ("GET", "/api/whatsapp/connections"),
    ("POST", "/api/whatsapp/connections"),
    ("PATCH", "/api/whatsapp/connections/{connection_id}"),
    ("DELETE", "/api/whatsapp/connections/{connection_id}"),
    ("GET", "/api/whatsapp/connections/{connection_id}/status"),
    ("GET", "/api/whatsapp/connections/{connection_id}/qr"),
    ("POST", "/api/whatsapp/connections/{connection_id}/start"),
    ("POST", "/api/whatsapp/connections/{connection_id}/restart"),
    ("POST", "/api/whatsapp/connections/{connection_id}/logout"),
    ("POST", "/api/whatsapp/connections/{connection_id}/recover"),
    ("POST", "/api/whatsapp/connections/{connection_id}/webhook"),
}

#: `social-wiring/app/schemas/whatsapp_connection.py::WhatsAppConnectionOut`
#: CORE fields — the extension columns (auto_reply_enabled/authorized_numbers/
#: bound_chats/marca_id) are DELIBERATELY excluded from the seed lift (see
#: `connection_store.py`'s module docstring) and are NOT asserted here.
SW_WHATSAPP_CONNECTION_OUT_CORE_FIELDS = {
    "id", "label", "base_url", "session_name", "webhook_url", "created_at", "updated_at",
}


def _org_dep():
    """Same (user, org_id) on every call within a test — a fresh random
    org per invocation would make a create-then-read sequence 404 on an
    org mismatch that has nothing to do with the router under test."""
    org_id = str(uuid.uuid4())

    def _dep():
        user = MagicMock()
        user.id = str(uuid.uuid4())
        return (user, "tok", org_id)

    return _dep


class TestApiKeysRouterParity:
    def _app(self):
        store = build_api_key_store(None, encryption_key=generate_key().decode())
        router = create_api_keys_router(
            MagicMock(), MagicMock(), specs=SW_API_KEY_SPECS, store_factory=lambda: store,
            get_current_user_org=_org_dep(),
            # DI seam (KB § PATTERNS/backend/di-test-seam.md, Class-B) —
            # never the real `resolve_credential` chain here: a sibling
            # test file elsewhere in this same process may have already
            # configured the ambient `noctusai_lib.config.credentials`
            # singleton via `create_product_app`, and this suite must not
            # depend on collection order to pass.
            resolver=lambda key, org_id: None,
        )
        app = FastAPI()
        app.include_router(router)
        return app

    def test_route_paths_and_methods_match_sw(self):
        app = self._app()
        seen = {(m, r.path) for r in app.routes for m in getattr(r, "methods", ())}
        expected = {
            ("GET", "/api/settings/api-keys"),
            ("PUT", "/api/settings/api-keys/{key}"),
            ("DELETE", "/api/settings/api-keys/{key}"),
            ("POST", "/api/settings/api-keys/{key}/test"),
        }
        assert expected <= seen

    def test_all_sw_managed_keys_are_listed(self):
        app = self._app()
        body = TestClient(app).get("/api/settings/api-keys").json()
        listed = {item["key"] for item in body["items"]}
        assert listed == set(SW_MANAGED_API_KEYS)

    def test_response_item_field_set_matches_sw_schema(self):
        app = self._app()
        body = TestClient(app).get("/api/settings/api-keys").json()
        assert set(body["items"][0].keys()) == SW_API_KEY_STATUS_FIELDS

    def test_put_get_delete_status_codes_match_sw_contract(self):
        app = self._app()
        client = TestClient(app)
        assert client.put("/api/settings/api-keys/openai_api_key", json={"value": "sk-x"}).status_code == 200
        assert client.put("/api/settings/api-keys/openai_api_key", json={"value": ""}).status_code == 422
        assert client.put("/api/settings/api-keys/unknown", json={"value": "x"}).status_code == 404
        assert client.delete("/api/settings/api-keys/openai_api_key").status_code == 200
        assert client.delete("/api/settings/api-keys/unknown").status_code == 404

    def test_auth_boundary_strict_401(self):
        store = build_api_key_store(None, encryption_key=generate_key().decode())

        def _raise_401():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

        router = create_api_keys_router(
            MagicMock(), MagicMock(), specs=SW_API_KEY_SPECS, store_factory=lambda: store,
            get_current_user_org=_raise_401,
        )
        app = FastAPI()
        app.include_router(router)
        resp = TestClient(app).get("/api/settings/api-keys")
        assert resp.status_code == 401


class _FakeSupabase:
    """Minimal `.schema().table()` double — same shape as
    `test_connection_store.py`'s, kept local here (single use, no
    reason to import a sibling test module)."""

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
                return _FakeSupabase._Resp([dict(r) for r in self._rows if self._matches(r)])
            if self._op == "insert":
                row = dict(self._payload)
                row.setdefault("id", str(uuid.uuid4()))
                row.setdefault("created_at", "2026-09-17T00:00:00+00:00")
                row.setdefault("updated_at", "2026-09-17T00:00:00+00:00")
                self._rows.append(row)
                return _FakeSupabase._Resp([row])
            if self._op == "update":
                matched = [r for r in self._rows if self._matches(r)]
                for row in matched:
                    row.update(self._payload)
                return _FakeSupabase._Resp([dict(r) for r in matched])
            if self._op == "delete":
                removed = [r for r in self._rows if self._matches(r)]
                self._rows[:] = [r for r in self._rows if not self._matches(r)]
                return _FakeSupabase._Resp([dict(r) for r in removed])
            return _FakeSupabase._Resp([])

    def __init__(self):
        self._schemas: dict[str, dict[str, list]] = {}

    def schema(self, name):
        tables = self._schemas.setdefault(name, {})
        outer = self

        class _Handle:
            def table(self, tname):
                rows = tables.setdefault(tname, [])
                return outer._Query(rows)

        return _Handle()


class TestWhatsAppConnectionsRouterParity:
    def _app(self):
        store = build_whatsapp_connection_store(
            _FakeSupabase(), encryption_key=generate_key().decode(), schema="social_wiring"
        )
        client_singleton = FakeWahaClient(session="default")
        router = create_whatsapp_connections_router(
            MagicMock(), MagicMock(), store_factory=lambda: store,
            get_current_user_org=_org_dep(), waha_base_url="https://waha.example.com",
            resolve_webhook_base_url=lambda: "https://sw.example.com",
            waha_client_factory=lambda **_kw: client_singleton,
        )
        app = FastAPI()
        app.include_router(router)
        return app

    def test_route_paths_and_methods_match_sw(self):
        app = self._app()
        seen = {(m, r.path) for r in app.routes for m in getattr(r, "methods", ())}
        assert SW_WHATSAPP_CONNECTIONS_PATHS <= seen

    def test_create_response_core_fields_match_sw_schema(self):
        app = self._app()
        resp = TestClient(app).post(
            "/api/whatsapp/connections", json={"label": "L", "api_key": "k"}
        )
        assert resp.status_code == 201
        assert set(resp.json().keys()) == SW_WHATSAPP_CONNECTION_OUT_CORE_FIELDS

    def test_status_codes_match_sw_contract(self):
        app = self._app()
        client = TestClient(app)
        created = client.post(
            "/api/whatsapp/connections", json={"label": "L", "api_key": "k"}
        ).json()
        assert client.get(f"/api/whatsapp/connections/{created['id']}/status").status_code == 200
        assert client.patch(f"/api/whatsapp/connections/{created['id']}", json={"label": "N"}).status_code == 200
        assert client.delete(f"/api/whatsapp/connections/{created['id']}").status_code == 204
        assert client.get(f"/api/whatsapp/connections/{uuid.uuid4()}/status").status_code == 404

    def test_auth_boundary_strict_401(self):
        store = build_whatsapp_connection_store(
            _FakeSupabase(), encryption_key=generate_key().decode(), schema="social_wiring"
        )

        def _raise_401():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

        router = create_whatsapp_connections_router(
            MagicMock(), MagicMock(), store_factory=lambda: store,
            get_current_user_org=_raise_401, waha_base_url="https://waha.example.com",
            resolve_webhook_base_url=lambda: "https://sw.example.com",
        )
        app = FastAPI()
        app.include_router(router)
        resp = TestClient(app).get("/api/whatsapp/connections")
        assert resp.status_code == 401
