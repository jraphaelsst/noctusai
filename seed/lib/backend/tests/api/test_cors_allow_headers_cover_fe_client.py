"""Every request header the seed FE api client sends must pass Core's CORS
preflight.

`seed/lib/frontend/src/api.ts` `buildHeaders` adds `X-Noctus-Client` to every
call. It was missing from `configure_app`'s default `allow_headers`, so each
product's cross-origin `coreApi` call (`/api/me/consents`,
`/api/admin/llm-spend/{org}`) failed its preflight, `fetch` threw, and the FE
toasted "Servidor indisponivel" on every page load (measured live on
social.noctusai.com → core.noctusai.com, 2026-09-28). This test reads the header
names from the FE source itself, so adding a header there without allowing it
here fails CI instead of production.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.api.app_factory import DEFAULT_CORS_ALLOW_HEADERS, configure_app

_API_TS = Path(__file__).resolve().parents[3] / "frontend" / "src" / "api.ts"
_ORIGIN = "https://social.example.test"


def _fe_client_headers() -> set[str]:
    src = _API_TS.read_text(encoding="utf-8")
    corpo = src.split("async function buildHeaders", 1)[1].split("\n  }\n", 1)[0]
    nomes = set(re.findall(r"'([A-Za-z][A-Za-z0-9-]+)'\s*:", corpo))
    nomes |= set(re.findall(r"headers\['([A-Za-z][A-Za-z0-9-]+)'\]", corpo))
    return nomes


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/ping")
    def ping() -> dict:
        return {"ok": True}

    settings = SimpleNamespace(
        cors_origins_list=[_ORIGIN], sentry_dsn="", is_production=False, debug=True,
    )
    configure_app(app, settings, allow_credentials=True)
    return app


def test_the_fe_source_still_has_the_headers_this_test_reads():
    headers = _fe_client_headers()
    assert {"Content-Type", "X-Noctus-Client", "Authorization"} <= headers


def test_every_fe_client_header_is_in_the_default_allow_list():
    permitidos = {h.lower() for h in DEFAULT_CORS_ALLOW_HEADERS}
    faltando = sorted(h for h in _fe_client_headers() if h.lower() not in permitidos)
    assert faltando == []


def test_preflight_with_the_fe_client_headers_is_allowed():
    client = TestClient(_app())
    pedido = ", ".join(sorted(h.lower() for h in _fe_client_headers()))
    r = client.options(
        "/api/ping",
        headers={
            "Origin": _ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": pedido,
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == _ORIGIN
