"""academia.pesquisa.* — CONTRACT §B.5 / §C, every row's method/path/body."""
from __future__ import annotations

import asyncio

from academia.tools.pesquisa import pesquisa_capturar_fonte


def test_pesquisa_capturar_fonte_is_post_api_sources(fake_client):
    """CONTRACT §C: the sibling's `destino` path becomes `kb_slug`."""
    fake_client.set_response("POST", "/api/sources", {"ok": True, "id": "abc"})
    out = asyncio.run(
        pesquisa_capturar_fonte(
            {
                "url": "https://www.gov.br/pnrs",
                "titulo": "Lei PNRS",
                "trecho_citado": "art. 3º...",
                "resumo": "define a política nacional",
                "kb_slug": "dominio-regulatorio-pnrs",
                "vigencia_confirmada": True,
                "exige_da_empresa": "relatório anual",
            }
        )
    )
    assert out == {"ok": True, "id": "abc"}
    assert fake_client.calls == [
        {
            "method": "POST",
            "path": "/api/sources",
            "params": None,
            "json_body": {
                "url": "https://www.gov.br/pnrs",
                "titulo": "Lei PNRS",
                "trecho_citado": "art. 3º...",
                "resumo": "define a política nacional",
                "kb_slug": "dominio-regulatorio-pnrs",
                "vigencia_confirmada": True,
                "exige_da_empresa": "relatório anual",
            },
        }
    ]


def test_pesquisa_capturar_fonte_omits_exige_da_empresa_when_unset(fake_client):
    asyncio.run(
        pesquisa_capturar_fonte(
            {
                "url": "https://x.test",
                "titulo": "T",
                "trecho_citado": "x",
                "resumo": "r",
                "kb_slug": "slug",
                "vigencia_confirmada": False,
            }
        )
    )
    assert "exige_da_empresa" not in fake_client.calls[0]["json_body"]


def test_pesquisa_capturar_fonte_unknown_kb_slug_404_passes_through(fake_client):
    fake_client.set_response(
        "POST", "/api/sources", {"ok": False, "error": {"status": 404, "code": "not_found", "detail": "Não encontrado."}}
    )
    out = asyncio.run(
        pesquisa_capturar_fonte(
            {
                "url": "https://x.test",
                "titulo": "T",
                "trecho_citado": "x",
                "resumo": "r",
                "kb_slug": "desconhecido",
                "vigencia_confirmada": False,
            }
        )
    )
    assert out["ok"] is False
    assert out["error"]["status"] == 404
