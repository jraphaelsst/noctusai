"""academia.conteudo.* — CONTRACT §B.5 / §C, every row's method/path/body."""
from __future__ import annotations

import asyncio

from academia.tools.conteudo import conteudo_ler, conteudo_listar, conteudo_salvar


def test_conteudo_salvar_is_post_api_content(fake_client):
    fake_client.set_response("POST", "/api/content", {"ok": True, "codigo": "C-004"})
    out = asyncio.run(
        conteudo_salvar(
            {
                "tipo": "roteiro",
                "titulo": "Episódio 1",
                "corpo_md": "roteiro completo",
                "referencia": "briefing.md",
                "fontes": ["dominio-regulatorio-pnrs"],
            }
        )
    )
    assert out == {"ok": True, "codigo": "C-004"}
    assert fake_client.calls == [
        {
            "method": "POST",
            "path": "/api/content",
            "params": None,
            "json_body": {
                "tipo": "roteiro",
                "titulo": "Episódio 1",
                "corpo_md": "roteiro completo",
                "referencia": "briefing.md",
                "fontes": ["dominio-regulatorio-pnrs"],
            },
        }
    ]


def test_conteudo_salvar_omits_unset_optional_fields(fake_client):
    asyncio.run(conteudo_salvar({"tipo": "outro", "titulo": "T", "corpo_md": "x"}))
    assert fake_client.calls[0]["json_body"] == {"tipo": "outro", "titulo": "T", "corpo_md": "x"}


def test_conteudo_listar_is_get_api_content_with_tipo_filter(fake_client):
    fake_client.set_response("GET", "/api/content", {"ok": True, "items": [], "total": 0})
    out = asyncio.run(conteudo_listar({"tipo": "quiz"}))
    assert out == {"ok": True, "items": [], "total": 0}
    assert fake_client.calls == [
        {"method": "GET", "path": "/api/content", "params": {"tipo": "quiz"}, "json_body": None}
    ]


def test_conteudo_ler_is_get_api_content_codigo(fake_client):
    """`ler` takes `codigo` instead of the sibling's `caminho` (CONTRACT §C)."""
    fake_client.set_response("GET", "/api/content/C-004", {"ok": True, "codigo": "C-004"})
    out = asyncio.run(conteudo_ler({"codigo": "C-004"}))
    assert out == {"ok": True, "codigo": "C-004"}
    assert fake_client.calls == [
        {"method": "GET", "path": "/api/content/C-004", "params": None, "json_body": None}
    ]
