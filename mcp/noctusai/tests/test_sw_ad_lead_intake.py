"""``noctus.sw.ad_lead_intake`` — injected httpx.MockTransport, no network."""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from tools.noctus.sw import ad_lead_intake as tool  # noqa: E402

TOKEN = "admin_session_token_value"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("NOCTUS_SW_TOKEN", TOKEN)
    monkeypatch.setenv("NOCTUS_SW_URL", "https://sw.test/")


def _t(handler):
    return httpx.MockTransport(handler)


def test_not_configured_is_a_typed_error(monkeypatch):
    monkeypatch.delenv("NOCTUS_SW_TOKEN")
    assert tool.ad_lead_intake("status")["error"]["codigo"] == "nao_configurado"


def test_status_reads_the_summary_with_the_bearer_token():
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json={"data": {"intakes": {"ok": 3}, "total": 3, "divergencias_corretor_pendentes": 1}})

    out = tool.ad_lead_intake("status", org="one", _transport=_t(handler))
    assert out["resumo"]["total"] == 3 and seen[0].url.path == "/api/leads/ad-intake/resumo"
    assert seen[0].headers["authorization"] == f"Bearer {TOKEN}" and TOKEN not in str(out)


def test_backfill_defaults_to_a_server_side_dry_run_and_never_writes_without_confirm():
    seen = []

    def handler(req):
        seen.append(dict(req.url.params))
        return httpx.Response(200, json={"data": {"lote": 2, "a_processar": 2, "proximo_cursor": None}})

    out = tool.ad_lead_intake("backfill", dry_run=False, confirm=False, _transport=_t(handler))
    assert seen[0]["dry_run"] == "true" and out["dry_run"] is True and out["status"] == "planned"
    assert "confirm=True" in out["mensagem"]


def test_backfill_walks_batches_by_cursor_and_aggregates():
    cursors = []

    def handler(req):
        cursors.append(req.url.params.get("cursor"))
        if len(cursors) == 1:
            return httpx.Response(200, json={"data": {"lote": 2, "processados": 2, "por_status": {"ok": 2}, "proximo_cursor": "m2"}})
        return httpx.Response(200, json={"data": {"lote": 1, "processados": 1, "por_status": {"pendente_retry": 1}, "falhas": [{"lead_id": "x"}], "proximo_cursor": None}})

    out = tool.ad_lead_intake("backfill", dry_run=False, confirm=True, max_lotes=5, _transport=_t(handler))
    assert cursors == [None, "m2"] and out["status"] == "done" and out["lotes"] == 2
    assert out["total"]["processados"] == 3 and out["total"]["por_status"] == {"ok": 2, "pendente_retry": 1} and len(out["total"]["falhas"]) == 1


def test_http_error_returns_partial_with_the_cursor():
    def handler(req):
        return httpx.Response(403, json={"error": {"code": "forbidden", "message": "só admin"}})

    out = tool.ad_lead_intake("backfill", cursor="c1", _transport=_t(handler))
    assert out["error"]["codigo"] == "forbidden" and out["proximo_cursor"] == "c1"
