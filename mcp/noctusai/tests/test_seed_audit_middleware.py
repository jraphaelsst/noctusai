"""CI-gating coverage for `noctusai_lib.api.auth.session.audit_middleware`
(SEED-1 follow-up, `julia-agents-academia-2026-09` slice A1b).

``seed/lib/backend/tests/`` is NOT run by CI (open drift, 2026-09-09) —
this file is the CI-gating leg. Exercises the REAL
`make_get_auth_context` composition (not a hand-rolled fake dependency)
through a live `TestClient`, so both halves of the SEED-1 wiring are
proven together:

  - `session/dep.py`'s `get_auth_context` stashes the resolved
    `AuthContext` on `request.state.auth_context` on every successful
    resolution (cookie, `pk_*` token, or the legacy-JWT bridge).
  - `ApiTokenAuditMiddleware` reads it back AFTER the downstream ASGI
    app returns and fires exactly one `audit_writer.record(...)` per
    resolved `caller_kind == "product"` request — never for a
    `caller_kind == "user"` request, and never when no credential ever
    resolved (a 401 with nothing to audit).
"""
from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from noctusai_lib.api.auth.session import (
    ApiTokenAuditMiddleware,
    AuthContext,
    FakeApiTokenAuditWriter,
    FakeApiTokenResolver,
    FakeSessionStore,
    make_get_auth_context,
)

_ORG = UUID("00000000-0000-4000-8000-0000000000aa")


def _build_app():
    session_store = FakeSessionStore()
    token_resolver = FakeApiTokenResolver()

    async def _legacy_jwt_resolver(token: str) -> AuthContext | None:
        if token != "valid-jwt":
            return None
        return AuthContext(
            org_id=_ORG,
            caller_kind="user",
            user_id=uuid4(),
            scopes=[],
            raw_token=token,
            api_token_id=None,
        )

    get_auth_context = make_get_auth_context(
        session_store=session_store,
        api_token_resolver=token_resolver,
        legacy_jwt_resolver=_legacy_jwt_resolver,
        session_cookie_name="nai_session",
    )

    app = FastAPI()

    @app.get("/ping")
    async def ping(ctx: AuthContext = Depends(get_auth_context)):
        return {"ok": True}

    @app.get("/boom")
    async def boom(ctx: AuthContext = Depends(get_auth_context)):
        raise HTTPException(status_code=500, detail="boom")

    writer = FakeApiTokenAuditWriter()
    app.add_middleware(ApiTokenAuditMiddleware, audit_writer=writer)

    return app, writer, token_resolver


class TestApiTokenAuditMiddleware:
    def test_records_once_for_a_resolved_product_token(self):
        app, writer, token_resolver = _build_app()
        token_id = token_resolver.register("pk_" + "a" * 32, org_id=_ORG, scopes=["read"])
        client = TestClient(app)

        resp = client.get("/ping", headers={"Authorization": "Bearer pk_" + "a" * 32})

        assert resp.status_code == 200
        assert len(writer.records) == 1
        record = writer.records[0]
        assert record["api_token_id"] == token_id
        assert record["org_id"] == _ORG
        assert record["method"] == "GET"
        assert record["path"] == "/ping"
        assert record["status"] == 200

    def test_records_the_actual_response_status_on_error(self):
        app, writer, token_resolver = _build_app()
        token_resolver.register("pk_" + "b" * 32, org_id=_ORG, scopes=[])
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.get("/boom", headers={"Authorization": "Bearer pk_" + "b" * 32})

        assert resp.status_code == 500
        assert len(writer.records) == 1
        assert writer.records[0]["status"] == 500

    def test_never_records_for_a_user_caller(self):
        app, writer, _token_resolver = _build_app()
        client = TestClient(app)

        resp = client.get("/ping", headers={"Authorization": "Bearer valid-jwt"})

        assert resp.status_code == 200
        assert writer.records == []

    def test_never_records_when_no_credential_resolved(self):
        app, writer, _token_resolver = _build_app()
        client = TestClient(app)

        resp = client.get("/ping")

        assert resp.status_code == 401
        assert writer.records == []

    def test_never_records_for_an_invalid_product_token(self):
        app, writer, _token_resolver = _build_app()
        client = TestClient(app)

        resp = client.get("/ping", headers={"Authorization": "Bearer pk_" + "z" * 32})

        assert resp.status_code == 401
        assert writer.records == []

    def test_exactly_one_record_per_call_across_multiple_requests(self):
        app, writer, token_resolver = _build_app()
        token_resolver.register("pk_" + "c" * 32, org_id=_ORG, scopes=[])
        client = TestClient(app)

        for _ in range(3):
            resp = client.get("/ping", headers={"Authorization": "Bearer pk_" + "c" * 32})
            assert resp.status_code == 200

        assert len(writer.records) == 3
