"""academia.kb.* tools — knowledge base (CONTRACT §B.1 / §C).

`academia.kb.index_sync` and `academia.kb.link_check` are DEPRECATED
and REMOVED (CONTRACT §C) — the DB has no unindexed documents and no
file pointers any more. Do not re-add them.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from ..client import get_client
from ..types import KbBuscarInput, KbEscreverInput, KbLerInput, KbMoverInput


async def kb_buscar(args: dict) -> dict:
    inp = KbBuscarInput(**args)
    client = get_client()
    params = {
        "consulta": inp.consulta,
        "categoria": inp.categoria,
        "subcategoria": inp.subcategoria,
        "tag": inp.tag,
        "limite": inp.limite,
        "offset": inp.offset,
    }
    return await client.request("GET", "/api/kb", params=params)


async def kb_ler(args: dict) -> dict:
    inp = KbLerInput(**args)
    client = get_client()
    return await client.request("GET", f"/api/kb/{inp.slug}")


async def kb_escrever(args: dict) -> dict:
    inp = KbEscreverInput(**args)
    client = get_client()
    if inp.modo == "criar":
        body: dict = {
            "categoria": inp.categoria,
            "titulo": inp.titulo,
            "corpo_md": inp.corpo_md,
            "motivo": inp.motivo,
        }
        if inp.slug is not None:
            body["slug"] = inp.slug
        if inp.subcategoria is not None:
            body["subcategoria"] = inp.subcategoria
        if inp.resumo is not None:
            body["resumo"] = inp.resumo
        if inp.tags is not None:
            body["tags"] = inp.tags
        return await client.request("POST", "/api/kb", json_body=body)

    # modo == "atualizar" — pydantic model_validator guarantees slug is set.
    body = {"motivo": inp.motivo}
    for field in ("titulo", "resumo", "tags", "corpo_md", "categoria", "subcategoria"):
        value = getattr(inp, field)
        if value is not None:
            body[field] = value
    return await client.request("PUT", f"/api/kb/{inp.slug}", json_body=body)


async def kb_mover(args: dict) -> dict:
    inp = KbMoverInput(**args)
    client = get_client()
    body = {"novo_slug": inp.destino, "motivo": inp.motivo}
    return await client.request("PUT", f"/api/kb/{inp.origem}", json_body=body)


HANDLERS = {
    "academia.kb.buscar": kb_buscar,
    "academia.kb.ler": kb_ler,
    "academia.kb.escrever": kb_escrever,
    "academia.kb.mover": kb_mover,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="academia.kb.buscar",
            description=(
                "LEITURA — busca entradas da base de conhecimento por texto "
                "livre, categoria, subcategoria ou tag (GET /api/kb)."
            ),
            inputSchema=KbBuscarInput.model_json_schema(),
        ),
        Tool(
            name="academia.kb.ler",
            description="LEITURA — lê uma entrada da base de conhecimento por slug (GET /api/kb/{slug}).",
            inputSchema=KbLerInput.model_json_schema(),
        ),
        Tool(
            name="academia.kb.escrever",
            description=(
                "ESCRITA — cria (modo='criar') ou atualiza (modo='atualizar') "
                "uma entrada da base de conhecimento. Não sonda o servidor "
                "para decidir o modo — é sempre explícito."
            ),
            inputSchema=KbEscreverInput.model_json_schema(),
        ),
        Tool(
            name="academia.kb.mover",
            description="ESCRITA — renomeia o slug de uma entrada (PUT /api/kb/{origem} com novo_slug).",
            inputSchema=KbMoverInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
