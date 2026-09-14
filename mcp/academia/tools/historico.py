"""academia.historico.* tools — timeline (CONTRACT §B.5 / §C)."""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from ..client import get_client
from ..types import HistoricoAppendInput, HistoricoTimelineInput


async def historico_append(args: dict) -> dict:
    inp = HistoricoAppendInput(**args)
    client = get_client()
    body: dict = {"titulo": inp.titulo, "descricao": inp.descricao}
    if inp.data is not None:
        body["data"] = inp.data
    return await client.request("POST", "/api/timeline", json_body=body)


async def historico_timeline(args: dict) -> dict:
    inp = HistoricoTimelineInput(**args)
    client = get_client()
    return await client.request("GET", "/api/timeline", params={"limite": inp.limite})


HANDLERS = {
    "academia.historico.append": historico_append,
    "academia.historico.timeline": historico_timeline,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="academia.historico.append",
            description="ESCRITA — adiciona um evento à linha do tempo (POST /api/timeline).",
            inputSchema=HistoricoAppendInput.model_json_schema(),
        ),
        Tool(
            name="academia.historico.timeline",
            description="LEITURA — lista eventos da linha do tempo, mais recentes primeiro (GET /api/timeline?limite=).",
            inputSchema=HistoricoTimelineInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
