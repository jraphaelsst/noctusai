"""``AuditMiddleware`` — pure-ASGI shape + the recording contract.

Mirrors ``seed/lib/backend/tests/api/test_middleware_is_pure_asgi.py``'s
structural assertion, then a small FastAPI app (with
``CorrelationIdMiddleware`` mounted the same way
``noctusai_lib.api.app_factory.configure_app`` mounts it — nested
OUTSIDE this middleware) drives the functional behaviour.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from noctusai_lib.api.audit.middleware import AuditMiddleware
from noctusai_lib.api.audit.sink import FakeAuditSink
from noctusai_lib.api.audit.types import AuditActor
from noctusai_lib.api.middleware import CorrelationIdMiddleware


def test_never_subclasses_base_http_middleware() -> None:
    """Same guard as `test_middleware_is_pure_asgi.py` — see that file's
    module docstring for the 2026-08-25 502 incident this prevents."""
    assert not issubclass(AuditMiddleware, BaseHTTPMiddleware)


def test_implements_the_asgi_callable_shape() -> None:
    assert not hasattr(AuditMiddleware, "dispatch")
    assert list(AuditMiddleware.__call__.__code__.co_varnames[:4]) == [
        "self", "scope", "receive", "send",
    ]


def _build_app(sink: FakeAuditSink, *, enabled: bool = True) -> FastAPI:
    app = FastAPI()

    # Mount order mirrors `configure_app`: AuditMiddleware added BEFORE
    # CorrelationIdMiddleware so it stays nested inside it (last-added =
    # outermost in Starlette's `add_middleware`).
    app.add_middleware(AuditMiddleware, sink=sink, product="test-product", enabled=enabled)
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/api/things/{thing_id}")
    async def get_thing(thing_id: str):
        return {"id": thing_id}

    @app.post("/api/things/{thing_id}")
    async def create_thing(thing_id: str, request: Request):
        request.state.audit_actor = AuditActor(user_id="u1", org_id="o1", role="admin")
        return {"id": thing_id}

    @app.put("/api/anon/{item_id}")
    async def put_anon(item_id: str):
        # No auth dependency ran — `request.state.audit_actor` was never
        # set. The middleware must still record with a blank actor,
        # never crash.
        return {"id": item_id}

    @app.delete("/api/things/{thing_id}")
    async def delete_thing(thing_id: str):
        return {"id": thing_id}

    return app


class TestMutatingOnlyFilter:
    def test_get_is_never_recorded(self) -> None:
        sink = FakeAuditSink()
        client = TestClient(_build_app(sink))
        resp = client.get("/api/things/t1")
        assert resp.status_code == 200
        assert sink.entries == []

    def test_post_is_recorded(self) -> None:
        sink = FakeAuditSink()
        client = TestClient(_build_app(sink))
        resp = client.post("/api/things/t1")
        assert resp.status_code == 200
        assert len(sink.entries) == 1
        entry = sink.entries[0]
        assert entry.method == "POST"
        assert entry.route_template == "/api/things/{thing_id}"
        assert entry.path_params == {"thing_id": "t1"}
        assert entry.status == 200
        assert entry.product == "test-product"

    def test_delete_is_recorded(self) -> None:
        sink = FakeAuditSink()
        client = TestClient(_build_app(sink))
        resp = client.delete("/api/things/t1")
        assert resp.status_code == 200
        assert len(sink.entries) == 1
        assert sink.entries[0].method == "DELETE"

    def test_unmatched_route_is_not_recorded(self) -> None:
        sink = FakeAuditSink()
        client = TestClient(_build_app(sink))
        resp = client.post("/api/does-not-exist")
        assert resp.status_code == 404
        assert sink.entries == []

    def test_disabled_middleware_records_nothing(self) -> None:
        sink = FakeAuditSink()
        client = TestClient(_build_app(sink, enabled=False))
        resp = client.post("/api/things/t1")
        assert resp.status_code == 200
        assert sink.entries == []


class TestActorFromState:
    def test_actor_set_by_a_dependency_is_captured(self) -> None:
        sink = FakeAuditSink()
        client = TestClient(_build_app(sink))
        client.post("/api/things/t1")
        actor = sink.entries[0].actor
        assert actor.user_id == "u1"
        assert actor.org_id == "o1"
        assert actor.role == "admin"

    def test_no_actor_set_defaults_to_blank_actor_not_a_crash(self) -> None:
        sink = FakeAuditSink()
        client = TestClient(_build_app(sink))
        resp = client.put("/api/anon/x1")
        assert resp.status_code == 200
        actor = sink.entries[0].actor
        assert actor.user_id is None
        assert actor.org_id is None


class TestActorKindDetection:
    def test_default_web_header_is_user(self) -> None:
        sink = FakeAuditSink()
        client = TestClient(_build_app(sink))
        client.post("/api/things/t1", headers={"X-Noctus-Client": "web"})
        assert sink.entries[0].actor_kind == "user"

    def test_agent_header_is_agent(self) -> None:
        sink = FakeAuditSink()
        client = TestClient(_build_app(sink))
        client.post("/api/things/t1", headers={"X-Noctus-Client": "agent:webdriver"})
        assert sink.entries[0].actor_kind == "agent"

    def test_headless_ua_without_header_is_agent(self) -> None:
        sink = FakeAuditSink()
        client = TestClient(_build_app(sink))
        client.post(
            "/api/things/t1",
            headers={"User-Agent": "Mozilla/5.0 HeadlessChrome/120.0 Safari/537.36"},
        )
        assert sink.entries[0].actor_kind == "agent"

    def test_service_header_is_service(self) -> None:
        sink = FakeAuditSink()
        client = TestClient(_build_app(sink))
        client.post("/api/things/t1", headers={"X-Noctus-Client": "service"})
        assert sink.entries[0].actor_kind == "service"


class TestCorrelationId:
    def test_correlation_id_survives_the_nested_mount(self) -> None:
        """The load-bearing mount-order assertion: AuditMiddleware must
        read a real correlation id, not None, because it's nested
        INSIDE CorrelationIdMiddleware (added before it)."""
        sink = FakeAuditSink()
        client = TestClient(_build_app(sink))
        resp = client.post("/api/things/t1", headers={"X-Correlation-ID": "corr-xyz"})
        assert resp.headers["X-Correlation-ID"] == "corr-xyz"
        assert sink.entries[0].correlation_id == "corr-xyz"
