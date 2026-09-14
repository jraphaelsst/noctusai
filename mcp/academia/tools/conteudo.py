"""academia.conteudo.* tools — content drafts (CONTRACT §B.5 / §C)."""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from ..client import get_client
from ..types import ConteudoLerInput, ConteudoListarInput, ConteudoSalvarInput


async def conteudo_salvar(args: dict) -> dict:
    inp = ConteudoSalvarInput(**args)
    client = get_client()
    body: dict = {"tipo": inp.tipo, "titulo": inp.titulo, "corpo_md": inp.corpo_md}
    if inp.referencia is not None:
        body["referencia"] = inp.referencia
    if inp.fontes is not None:
        body["fontes"] = inp.fontes
    return await client.request("POST", "/api/content", json_body=body)


async def conteudo_listar(args: dict) -> dict:
    inp = ConteudoListarInput(**args)
    client = get_client()
    return await client.request("GET", "/api/content", params={"tipo": inp.tipo})


async def conteudo_ler(args: dict) -> dict:
    inp = ConteudoLerInput(**args)
    client = get_client()
    return await client.request("GET", f"/api/content/{inp.codigo}")


HANDLERS = {
    "academia.conteudo.salvar": conteudo_salvar,
    "academia.conteudo.listar": conteudo_listar,
    "academia.conteudo.ler": conteudo_ler,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="academia.conteudo.salvar",
            description="ESCRITA — salva um rascunho de conteúdo (POST /api/content).",
            inputSchema=ConteudoSalvarInput.model_json_schema(),
        ),
        Tool(
            name="academia.conteudo.listar",
            description="LEITURA — lista rascunhos de conteúdo, opcionalmente por tipo (GET /api/content?tipo=).",
            inputSchema=ConteudoListarInput.model_json_schema(),
        ),
        Tool(
            name="academia.conteudo.ler",
            description="LEITURA — lê um rascunho de conteúdo por código (GET /api/content/{codigo}).",
            inputSchema=ConteudoLerInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
