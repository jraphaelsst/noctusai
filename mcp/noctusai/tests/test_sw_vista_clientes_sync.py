"""``noctus.sw.vista_clientes_sync`` — injected httpx.MockTransport, no network."""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from tools.noctus.sw import vista_clientes_sync as tool  # noqa: E402

TOKEN = "admin_session_token_value"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("NOCTUS_SW_TOKEN", TOKEN)
    monkeypatch.setenv("NOCTUS_SW_URL", "https://sw.test/")


def _t(handler):
    return httpx.MockTransport(handler)


def test_not_configured_is_a_typed_error(monkeypatch):
    monkeypatch.delenv("NOCTUS_SW_TOKEN")
    assert tool.vista_clientes_sync("status")["error"]["codigo"] == "nao_configurado"


def test_a_sync_without_confirm_is_a_server_side_dry_run():
    seen = []

    def handler(req):
        seen.append(dict(req.url.params))
        return httpx.Response(200, json={"data": {"lote": 5, "casados": 2, "proximo_cursor": "5", "sem_match_por_flag": {"cliente": 3}}})

    out = tool.vista_clientes_sync("sync", dry_run=False, confirm=False, limite=5, _transport=_t(handler))
    assert seen[0]["dry_run"] == "true" and out["status"] == "planned" and out["proximo_cursor"] == "5" and "confirm=True" in out["mensagem"]


def test_it_never_loops_past_max_lotes_and_follows_the_cursor():
    cursors = []

    def handler(req):
        cursors.append(req.url.params.get("cursor"))
        n = len(cursors)
        return httpx.Response(200, json={"data": {"lote": 50, "casados": 1, "proximo_cursor": str(n * 50)}})

    out = tool.vista_clientes_sync("sync", max_lotes=3, _transport=_t(handler))
    assert cursors == [None, "50", "100"] and out["lotes"] == 3 and out["total"]["lote"] == 150 and out["proximo_cursor"] == "150"
    assert tool.vista_clientes_sync("sync", max_lotes=tool.MAX_LOTES + 1)["error"]["codigo"] == "parametro_invalido"


def test_an_http_error_is_typed_and_the_token_never_leaks():
    out = tool.vista_clientes_sync("sync", _transport=_t(lambda r: httpx.Response(403, json={"error": {"code": "forbidden", "message": "restrito"}})))
    assert out["error"]["http_status"] == 403 and TOKEN not in str(out)
