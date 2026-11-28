"""``noctus.sw.imovel_videos_vista_import`` — injected httpx.MockTransport, no network."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from tools.noctus.sw import imovel_videos_vista_import as tool  # noqa: E402

TOKEN = "platform_admin_session_token_value"
RUN = "00000000-0000-4000-8000-000000000001"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("NOCTUS_SW_TOKEN", TOKEN)
    monkeypatch.setenv("NOCTUS_SW_URL", "https://sw.test/")


def _t(seen, status=202, corpo=None):
    def handler(req):
        seen.append(req)
        return httpx.Response(status, json=corpo if corpo is not None else {"data": {"execucao_id": RUN, "status": "em_andamento"}})
    return httpx.MockTransport(handler)


def test_dry_run_is_the_default_and_posts_dry_run_true_with_the_bearer():
    seen = []
    out = tool.imovel_videos_vista_import(codigos=["CA0001"], limite=5, _transport=_t(seen))
    assert out["status"] == "queued_dry_run" and out["resultado"]["execucao_id"] == RUN
    [req] = seen
    assert req.method == "POST" and req.url.path == "/api/imoveis/videos-youtube/importar-vista"
    assert json.loads(req.content) == {"dry_run": True, "codigos": ["CA0001"], "limite": 5}
    assert req.headers["authorization"] == f"Bearer {TOKEN}" and TOKEN not in json.dumps(out)


def test_run_requires_confirm_and_sends_nothing_without_it():
    seen = []
    out = tool.imovel_videos_vista_import("run", _transport=_t(seen))
    assert out["error"]["codigo"] == "confirmacao_obrigatoria" and seen == []
    out = tool.imovel_videos_vista_import("run", confirm=True, _transport=_t(seen))
    assert out["status"] == "queued" and json.loads(seen[0].content) == {"dry_run": False}


def test_status_reads_the_run_with_filters_or_the_list():
    seen = []
    tool.imovel_videos_vista_import("status", execucao_id=RUN, resultados="criaria,erros", limit=50, _transport=_t(seen, 200, {"data": {}}))
    assert seen[0].method == "GET" and seen[0].url.path.endswith(RUN)
    assert seen[0].url.params["resultados"] == "criaria,erros" and seen[0].url.params["limit"] == "50"
    tool.imovel_videos_vista_import("status", _transport=_t(seen, 200, {"data": []}))
    assert seen[1].url.path == "/api/imoveis/videos-youtube/importar-vista"


def test_errors_are_typed():
    assert tool.imovel_videos_vista_import("x")["error"]["codigo"] == "acao_invalida"
    assert tool.imovel_videos_vista_import("status", execucao_id="../x")["error"]["codigo"] == "execucao_id_invalido"
    seen = []
    out = tool.imovel_videos_vista_import(_transport=_t(seen, 403, {"detail": "Restrito a administradores da plataforma NoctusAI."}))
    assert out["error"]["http_status"] == 403 and "administradores" in out["error"]["mensagem"]


def test_missing_or_insecure_config(monkeypatch):
    monkeypatch.setenv("NOCTUS_SW_URL", "http://sw.test")
    assert tool.imovel_videos_vista_import()["error"]["codigo"] == "url_insegura"
    monkeypatch.delenv("NOCTUS_SW_TOKEN")
    assert tool.imovel_videos_vista_import()["error"]["codigo"] == "nao_configurado"
