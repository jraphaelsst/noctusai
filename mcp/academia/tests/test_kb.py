"""academia.kb.* — CONTRACT §B.1 / §C, every row's method/path/body.

Every handler is exercised through the `fake_client` DI seam
(`FakeAcademiaApi`, no network) — this proves the REAL handler path
(pydantic validation → request construction → envelope passthrough)
without a network round-trip.
"""
from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from academia.tools.kb import kb_buscar, kb_escrever, kb_ler, kb_mover


def test_kb_buscar_is_get_api_kb_with_query_params(fake_client):
    fake_client.set_response("GET", "/api/kb", {"ok": True, "items": [{"slug": "a"}], "total": 1})
    out = asyncio.run(
        kb_buscar({"consulta": "pnrs", "categoria": "dominio", "subcategoria": "regulatorio", "limite": 10, "offset": 5})
    )
    assert out == {"ok": True, "items": [{"slug": "a"}], "total": 1}
    assert fake_client.calls == [
        {
            "method": "GET",
            "path": "/api/kb",
            "params": {
                "consulta": "pnrs",
                "categoria": "dominio",
                "subcategoria": "regulatorio",
                "tag": None,
                "limite": 10,
                "offset": 5,
            },
            "json_body": None,
        }
    ]


def test_kb_buscar_defaults(fake_client):
    asyncio.run(kb_buscar({}))
    call = fake_client.calls[0]
    assert call["method"] == "GET"
    assert call["path"] == "/api/kb"
    assert call["params"]["limite"] == 20
    assert call["params"]["offset"] == 0


def test_kb_ler_is_get_api_kb_slug(fake_client):
    """`caminho` (sibling) becomes `slug` (CONTRACT §C)."""
    fake_client.set_response("GET", "/api/kb/dominio-regulatorio-pnrs", {"ok": True, "slug": "dominio-regulatorio-pnrs"})
    out = asyncio.run(kb_ler({"slug": "dominio-regulatorio-pnrs"}))
    assert out == {"ok": True, "slug": "dominio-regulatorio-pnrs"}
    assert fake_client.calls == [
        {"method": "GET", "path": "/api/kb/dominio-regulatorio-pnrs", "params": None, "json_body": None}
    ]


def test_kb_escrever_criar_is_post_api_kb(fake_client):
    fake_client.set_response("POST", "/api/kb", {"ok": True, "slug": "novo-topico"})
    out = asyncio.run(
        kb_escrever(
            {
                "modo": "criar",
                "categoria": "geral",
                "titulo": "Novo tópico",
                "corpo_md": "conteúdo",
                "motivo": "primeira captura",
            }
        )
    )
    assert out == {"ok": True, "slug": "novo-topico"}
    assert fake_client.calls == [
        {
            "method": "POST",
            "path": "/api/kb",
            "params": None,
            "json_body": {
                "categoria": "geral",
                "titulo": "Novo tópico",
                "corpo_md": "conteúdo",
                "motivo": "primeira captura",
            },
        }
    ]


def test_kb_escrever_criar_includes_optional_fields_when_given(fake_client):
    asyncio.run(
        kb_escrever(
            {
                "modo": "criar",
                "slug": "meu-slug",
                "categoria": "geral",
                "subcategoria": "sub",
                "titulo": "T",
                "resumo": "R",
                "tags": ["a", "b"],
                "corpo_md": "x",
                "motivo": "m",
            }
        )
    )
    body = fake_client.calls[0]["json_body"]
    assert body == {
        "slug": "meu-slug",
        "categoria": "geral",
        "subcategoria": "sub",
        "titulo": "T",
        "resumo": "R",
        "tags": ["a", "b"],
        "corpo_md": "x",
        "motivo": "m",
    }


def test_kb_escrever_criar_missing_required_fields_raises(fake_client):
    with pytest.raises(ValidationError):
        asyncio.run(kb_escrever({"modo": "criar", "motivo": "m"}))
    assert fake_client.calls == []


def test_kb_escrever_atualizar_is_put_api_kb_slug(fake_client):
    fake_client.set_response("PUT", "/api/kb/dominio-regulatorio-pnrs", {"ok": True, "slug": "dominio-regulatorio-pnrs"})
    out = asyncio.run(
        kb_escrever(
            {
                "modo": "atualizar",
                "slug": "dominio-regulatorio-pnrs",
                "corpo_md": "atualizado",
                "motivo": "correção",
            }
        )
    )
    assert out == {"ok": True, "slug": "dominio-regulatorio-pnrs"}
    assert fake_client.calls == [
        {
            "method": "PUT",
            "path": "/api/kb/dominio-regulatorio-pnrs",
            "params": None,
            "json_body": {"motivo": "correção", "corpo_md": "atualizado"},
        }
    ]


def test_kb_escrever_atualizar_missing_slug_raises(fake_client):
    """Build step 3: never probes to decide which — slug is required
    up-front for modo='atualizar', not discovered via a GET."""
    with pytest.raises(ValidationError):
        asyncio.run(kb_escrever({"modo": "atualizar", "motivo": "m"}))
    assert fake_client.calls == []


def test_kb_mover_is_put_api_kb_origem_with_novo_slug(fake_client):
    """CONTRACT §C: `PUT /api/kb/{origem}` with `{"novo_slug": destino,
    "motivo": motivo}`."""
    fake_client.set_response("PUT", "/api/kb/slug-antigo", {"ok": True, "slug": "slug-novo"})
    out = asyncio.run(kb_mover({"origem": "slug-antigo", "destino": "slug-novo", "motivo": "reorganização"}))
    assert out == {"ok": True, "slug": "slug-novo"}
    assert fake_client.calls == [
        {
            "method": "PUT",
            "path": "/api/kb/slug-antigo",
            "params": None,
            "json_body": {"novo_slug": "slug-novo", "motivo": "reorganização"},
        }
    ]


def test_kb_error_envelope_passes_through_unchanged(fake_client):
    fake_client.set_response(
        "POST", "/api/kb", {"ok": False, "error": {"status": 409, "code": "conflict", "detail": "slug já existe"}}
    )
    out = asyncio.run(
        kb_escrever({"modo": "criar", "categoria": "geral", "titulo": "T", "corpo_md": "x", "motivo": "m"})
    )
    assert out == {"ok": False, "error": {"status": 409, "code": "conflict", "detail": "slug já existe"}}


def test_index_sync_and_link_check_are_not_registered():
    """CONTRACT §C: DEPRECATED, removed. No module attribute at all."""
    import academia.tools.kb as kb_module

    assert not hasattr(kb_module, "kb_index_sync")
    assert not hasattr(kb_module, "kb_link_check")
    assert "academia.kb.index_sync" not in kb_module.HANDLERS
    assert "academia.kb.link_check" not in kb_module.HANDLERS
