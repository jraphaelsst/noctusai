"""`meta.leadgen.simulate` — confirm gate, config gate, and the real HTTP call
against a local stand-in for the product endpoint (no mocking of our own code)."""
from __future__ import annotations

import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "mcp"))

from _kit.seed_pin import pin_in_tree_seed

pin_in_tree_seed(Path(__file__))

import pytest


class _Product:
    """Records the request; answers with whatever the test queued."""

    def __init__(self, status: int, body: dict) -> None:
        self.status, self.body = status, body
        self.seen: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                outer.seen.append({
                    "path": self.path,
                    "auth": self.headers.get("Authorization"),
                    "body": json.loads(raw or b"{}"),
                })
                data = json.dumps(outer.body).encode()
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_a):  # silence
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def product(monkeypatch):
    from meta.settings import get_settings

    made: list[_Product] = []

    def _make(status=200, body=None):
        p = _Product(status, body or {})
        made.append(p)
        monkeypatch.setenv("SOCIAL_WIRING_URL", p.url)
        monkeypatch.setenv("SOCIAL_WIRING_OPERATOR_TOKEN", "staff-token")
        get_settings.cache_clear()
        return p

    yield _make
    for p in made:
        p.close()
    get_settings.cache_clear()


def _run(args):
    from meta.tools import all_handlers

    return asyncio.run(all_handlers()["meta.leadgen.simulate"](args))


def test_registered():
    from meta.tools import all_descriptors

    assert "meta.leadgen.simulate" in {t.name for t in all_descriptors()}


def test_blocked_without_confirm_and_sends_nothing(product):
    p = product(200, {"data": {}})
    out = _run({"nome": "Maria"})
    assert out["simulated"] is False
    assert out["error"]["status"] == 412
    assert p.seen == []


def test_not_configured_is_a_424_not_a_silent_skip(monkeypatch):
    from meta.settings import get_settings

    monkeypatch.delenv("SOCIAL_WIRING_URL", raising=False)
    monkeypatch.delenv("SOCIAL_WIRING_OPERATOR_TOKEN", raising=False)
    get_settings.cache_clear()
    try:
        out = _run({"nome": "Maria", "confirm": True})
        # a co-located mcp/meta/.env could configure it; only assert the gate
        # when it is genuinely unset.
        if not get_settings().leadgen_simulate_configured:
            assert out["simulated"] is False and out["error"]["status"] == 424
    finally:
        get_settings.cache_clear()


def test_posts_the_body_with_the_operator_token_and_maps_the_response(product):
    p = product(200, {"data": {
        "meta_lead_id": "sim-1", "lead_id": "L1", "atendimento_id": "A1",
        "cliente_id": "C1", "imoveis": [{"codigo": "AAA1", "origem": "campanha"}],
    }})
    out = _run({"nome": "Maria", "ad_id": "AD1", "respostas": {"REF": "X1"}, "confirm": True})
    assert out["simulated"] is True and out["http_status"] == 200
    assert out["meta_lead_id"] == "sim-1" and out["cliente_id"] == "C1"
    assert out["imoveis"] == [{"codigo": "AAA1", "origem": "campanha"}]
    (seen,) = p.seen
    assert seen["path"] == "/api/meta/leadgen/simular"
    assert seen["auth"] == "Bearer staff-token"
    # `confirm` is the tool's gate, never forwarded; unset fields are omitted.
    assert seen["body"] == {"nome": "Maria", "ad_id": "AD1", "respostas": {"REF": "X1"}}


def test_a_403_is_surfaced_with_the_products_own_code(product):
    product(403, {"detail": "Apenas a equipe", "code": "not_platform_staff"})
    out = _run({"nome": "Maria", "confirm": True})
    assert out["simulated"] is False and out["http_status"] == 403
    assert "not_platform_staff" in out["error"]["message"]
