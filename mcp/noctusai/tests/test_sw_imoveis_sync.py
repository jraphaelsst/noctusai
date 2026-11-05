"""``noctus.sw.imoveis_sync`` — injected httpx.MockTransport, no network."""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from tools.noctus.sw import imoveis_sync as tool  # noqa: E402

TOKEN = "admin_session_token_value"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("NOCTUS_SW_TOKEN", TOKEN)
    monkeypatch.setenv("NOCTUS_SW_URL", "https://sw.test/")


def _t(handler):
    return httpx.MockTransport(handler)


def test_status_reads_the_last_run_with_the_bearer_token():
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json={"status": "ok", "caminho": "detalhes", "novos": 2})

    out = tool.imoveis_sync("status", org="one", _transport=_t(handler))
    assert out == {"status": "ok", "org": "one", "http_status": 200, "resultado": {"status": "ok", "caminho": "detalhes", "novos": 2}}
    assert seen[0].method == "GET" and seen[0].url.path == "/api/imoveis/sync/ultimo" and seen[0].headers["authorization"] == f"Bearer {TOKEN}"


def test_run_is_a_dry_run_by_default_and_sends_nothing():
    def handler(req):  # pragma: no cover - must not be called
        raise AssertionError("dry-run sent a request")

    out = tool.imoveis_sync("run", modo="detalhes", escopo="todos", _transport=_t(handler))
    assert out["status"] == "planned" and out["plano"] == {"method": "POST", "url": "https://sw.test/api/imoveis/sync", "params": {"modo": "detalhes", "escopo": "todos"}}
    assert TOKEN not in str(out)


def test_run_with_confirm_queues_the_refresh():
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(202, json={"execucao_id": "e1", "status": "em_andamento", "ja_em_andamento": False})

    out = tool.imoveis_sync("run", modo="auto", confirm=True, _transport=_t(handler))
    assert out["status"] == "queued" and out["http_status"] == 202 and out["resultado"]["execucao_id"] == "e1"
    assert seen[0].method == "POST" and dict(seen[0].url.params) == {"modo": "auto", "escopo": "vitrine"}


@pytest.mark.parametrize("status,corpo,codigo", [
    (401, {"detail": "Not authenticated"}, "http_401"), (403, {"error": {"code": "forbidden", "message": "só admin"}}, "forbidden"),
    (503, {"detail": "Vista não configurada para esta empresa"}, "http_503"),
])
def test_http_errors_are_typed(status, corpo, codigo):
    out = tool.imoveis_sync("status", _transport=_t(lambda r: httpx.Response(status, json=corpo)))
    assert out["error"]["codigo"] == codigo and out["error"]["http_status"] == status and TOKEN not in str(out)


def test_missing_config_is_a_typed_error_not_a_stub(monkeypatch):
    monkeypatch.delenv("NOCTUS_SW_TOKEN")
    assert tool.imoveis_sync("status")["error"]["codigo"] == "nao_configurado"


@pytest.mark.parametrize("kw", [{"action": "apagar"}, {"modo": "x"}, {"escopo": "y"}])
def test_invalid_arguments_are_refused_before_any_call(kw):
    assert "error" in tool.imoveis_sync(**kw)


def test_network_errors_never_leak_the_token():
    def handler(req):
        raise httpx.ConnectError("boom", request=req)

    out = tool.imoveis_sync("status", _transport=_t(handler))
    assert out["error"]["codigo"] == "erro_de_rede" and TOKEN not in str(out)
