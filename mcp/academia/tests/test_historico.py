"""academia.historico.* — CONTRACT §B.5 / §C, every row's method/path/body."""
from __future__ import annotations

import asyncio

from academia.tools.historico import historico_append, historico_timeline


def test_historico_append_is_post_api_timeline(fake_client):
    fake_client.set_response("POST", "/api/timeline", {"ok": True, "titulo": "Marco"})
    out = asyncio.run(historico_append({"titulo": "Marco", "descricao": "Assinatura do contrato", "data": "2026-09-14"}))
    assert out == {"ok": True, "titulo": "Marco"}
    assert fake_client.calls == [
        {
            "method": "POST",
            "path": "/api/timeline",
            "params": None,
            "json_body": {"titulo": "Marco", "descricao": "Assinatura do contrato", "data": "2026-09-14"},
        }
    ]


def test_historico_append_omits_data_when_unset(fake_client):
    asyncio.run(historico_append({"titulo": "T", "descricao": "D"}))
    assert fake_client.calls[0]["json_body"] == {"titulo": "T", "descricao": "D"}


def test_historico_timeline_is_get_api_timeline_with_limite(fake_client):
    fake_client.set_response("GET", "/api/timeline", {"ok": True, "items": [], "total": 0})
    out = asyncio.run(historico_timeline({"limite": 50}))
    assert out == {"ok": True, "items": [], "total": 0}
    assert fake_client.calls == [
        {"method": "GET", "path": "/api/timeline", "params": {"limite": 50}, "json_body": None}
    ]


def test_historico_timeline_defaults_to_20(fake_client):
    asyncio.run(historico_timeline({}))
    assert fake_client.calls[0]["params"] == {"limite": 20}
