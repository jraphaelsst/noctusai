"""academia.decisao.* tools — decisions (CONTRACT §B.2 / §C)."""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from ..client import get_client
from ..types import DecisaoListarInput, DecisaoRegistrarInput, DecisaoSubstituirInput


def _decision_body(inp) -> dict:
    body: dict = {"titulo": inp.titulo, "decisao": inp.decisao, "motivo": inp.motivo}
    if inp.contexto is not None:
        body["contexto"] = inp.contexto
    if inp.alternativas_rejeitadas is not None:
        body["alternativas_rejeitadas"] = inp.alternativas_rejeitadas
    if inp.relacionadas is not None:
        body["relacionadas"] = inp.relacionadas
    return body


async def decisao_registrar(args: dict) -> dict:
    inp = DecisaoRegistrarInput(**args)
    client = get_client()
    return await client.request("POST", "/api/decisions", json_body=_decision_body(inp))


async def decisao_listar(args: dict) -> dict:
    inp = DecisaoListarInput(**args)
    client = get_client()
    return await client.request("GET", "/api/decisions", params={"estado": inp.estado})


async def decisao_substituir(args: dict) -> dict:
    inp = DecisaoSubstituirInput(**args)
    client = get_client()
    return await client.request(
        "POST", f"/api/decisions/{inp.substitui}/supersede", json_body=_decision_body(inp)
    )


HANDLERS = {
    "academia.decisao.registrar": decisao_registrar,
    "academia.decisao.listar": decisao_listar,
    "academia.decisao.substituir": decisao_substituir,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="academia.decisao.registrar",
            description="ESCRITA — registra uma nova decisão (POST /api/decisions). Código alocado pelo servidor.",
            inputSchema=DecisaoRegistrarInput.model_json_schema(),
        ),
        Tool(
            name="academia.decisao.listar",
            description="LEITURA — lista decisões, opcionalmente filtradas por estado (GET /api/decisions).",
            inputSchema=DecisaoListarInput.model_json_schema(),
        ),
        Tool(
            name="academia.decisao.substituir",
            description=(
                "ESCRITA — registra uma nova decisão que substitui outra "
                "(POST /api/decisions/{substitui}/supersede). 409 se a "
                "decisão antiga já foi substituída."
            ),
            inputSchema=DecisaoSubstituirInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
