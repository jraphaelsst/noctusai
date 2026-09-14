"""academia.decisao.* — CONTRACT §B.2 / §C, every row's method/path/body."""
from __future__ import annotations

import asyncio

from academia.tools.decisao import decisao_listar, decisao_registrar, decisao_substituir


def test_decisao_registrar_is_post_api_decisions(fake_client):
    fake_client.set_response("POST", "/api/decisions", {"ok": True, "codigo": "D-22"})
    out = asyncio.run(
        decisao_registrar(
            {
                "titulo": "Usar httpx",
                "contexto": "precisamos de um cliente async",
                "decisao": "adotar httpx",
                "motivo": "suporte async nativo",
                "alternativas_rejeitadas": "urllib",
                "relacionadas": ["D-10"],
            }
        )
    )
    assert out == {"ok": True, "codigo": "D-22"}
    assert fake_client.calls == [
        {
            "method": "POST",
            "path": "/api/decisions",
            "params": None,
            "json_body": {
                "titulo": "Usar httpx",
                "decisao": "adotar httpx",
                "motivo": "suporte async nativo",
                "contexto": "precisamos de um cliente async",
                "alternativas_rejeitadas": "urllib",
                "relacionadas": ["D-10"],
            },
        }
    ]


def test_decisao_registrar_omits_unset_optional_fields(fake_client):
    asyncio.run(decisao_registrar({"titulo": "T", "decisao": "D", "motivo": "M"}))
    assert fake_client.calls[0]["json_body"] == {"titulo": "T", "decisao": "D", "motivo": "M"}


def test_decisao_listar_is_get_api_decisions_with_estado_filter(fake_client):
    fake_client.set_response("GET", "/api/decisions", {"ok": True, "items": [], "total": 0})
    out = asyncio.run(decisao_listar({"estado": "vigente"}))
    assert out == {"ok": True, "items": [], "total": 0}
    assert fake_client.calls == [
        {"method": "GET", "path": "/api/decisions", "params": {"estado": "vigente"}, "json_body": None}
    ]


def test_decisao_listar_no_filter(fake_client):
    asyncio.run(decisao_listar({}))
    assert fake_client.calls[0]["params"] == {"estado": None}


def test_decisao_substituir_is_post_supersede_path_with_body(fake_client):
    """CONTRACT §C: `substitui` is the PATH param (the code being
    superseded), never a body field."""
    fake_client.set_response(
        "POST", "/api/decisions/D-10/supersede", {"ok": True, "nova": {"codigo": "D-22"}, "substituida": {"codigo": "D-10"}}
    )
    out = asyncio.run(
        decisao_substituir(
            {
                "substitui": "D-10",
                "titulo": "Revisão da decisão",
                "decisao": "nova decisão",
                "motivo": "mudança de contexto",
            }
        )
    )
    assert out == {"ok": True, "nova": {"codigo": "D-22"}, "substituida": {"codigo": "D-10"}}
    call = fake_client.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/api/decisions/D-10/supersede"
    assert "substitui" not in call["json_body"]
    assert call["json_body"] == {"titulo": "Revisão da decisão", "decisao": "nova decisão", "motivo": "mudança de contexto"}
