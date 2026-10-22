"""RequestTimingMiddleware: Server-Timing header + one route-TEMPLATE log line
per request, wired into configure_app (so every product gets it)."""
from __future__ import annotations

import logging
import re
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.api.app_factory import configure_app
from noctusai_lib.api.request_timing import LOG_PREFIX, UNMATCHED_ROUTE


def _client() -> TestClient:
    app = FastAPI()

    @app.get("/api/things/{thing_id}")
    def thing(thing_id: str) -> dict:
        return {"id": thing_id}

    settings = SimpleNamespace(cors_origins_list=[], sentry_dsn="", is_production=False, debug=True)
    configure_app(app, settings)
    return TestClient(app)


def _lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records
            if r.name == "noctusai.request_timing" and r.getMessage().startswith(LOG_PREFIX)]


def test_server_timing_header_present(caplog):
    r = _client().get("/api/things/abc")
    assert re.fullmatch(r"app;dur=\d+(\.\d+)?", r.headers["server-timing"])


def test_logs_route_template_never_the_raw_path(caplog):
    with caplog.at_level(logging.INFO, logger="noctusai.request_timing"):
        _client().get("/api/things/secret-id-123@x.com")
    lines = _lines(caplog)
    assert len(lines) == 1
    assert "route=/api/things/{thing_id}" in lines[0]
    assert "secret-id-123" not in lines[0]
    assert re.search(r"method=GET route=\S+ status=200 dur_ms=\d+\.\d", lines[0])


def test_unmatched_path_logs_bounded_placeholder(caplog):
    with caplog.at_level(logging.INFO, logger="noctusai.request_timing"):
        r = _client().get("/api/attacker-controlled/../path")
    lines = _lines(caplog)
    assert r.status_code == 404
    assert len(lines) == 1 and f"route={UNMATCHED_ROUTE}" in lines[0] and "attacker" not in lines[0]
