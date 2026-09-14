"""academia.pergunta.* tools — open questions (CONTRACT §B.3 / §C)."""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from ..client import get_client
from ..types import PerguntaAdicionarInput, PerguntaListarInput, PerguntaResponderInput


async def pergunta_adicionar(args: dict) -> dict:
    inp = PerguntaAdicionarInput(**args)
    client = get_client()
    body: dict = {
        "pergunta": inp.pergunta,
        "por_que_importa": inp.por_que_importa,
        "bloqueia": inp.bloqueia,
    }
    if inp.destino_kb is not None:
        body["destino_kb"] = inp.destino_kb
    return await client.request("POST", "/api/questions", json_body=body)


async def pergunta_listar(args: dict) -> dict:
    inp = PerguntaListarInput(**args)
    client = get_client()
    return await client.request("GET", "/api/questions", params={"estado": inp.estado})


async def pergunta_responder(args: dict) -> dict:
    inp = PerguntaResponderInput(**args)
    client = get_client()
    return await client.request(
        "POST", f"/api/questions/{inp.codigo}/answer", json_body={"resposta": inp.resposta}
    )


HANDLERS = {
    "academia.pergunta.adicionar": pergunta_adicionar,
    "academia.pergunta.listar": pergunta_listar,
    "academia.pergunta.responder": pergunta_responder,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="academia.pergunta.adicionar",
            description="ESCRITA — registra uma pergunta em aberto (POST /api/questions).",
            inputSchema=PerguntaAdicionarInput.model_json_schema(),
        ),
        Tool(
            name="academia.pergunta.listar",
            description="LEITURA — lista perguntas por estado (GET /api/questions?estado=).",
            inputSchema=PerguntaListarInput.model_json_schema(),
        ),
        Tool(
            name="academia.pergunta.responder",
            description=(
                "ESCRITA — responde uma pergunta em aberto (POST "
                "/api/questions/{codigo}/answer). 409 se já respondida."
            ),
            inputSchema=PerguntaResponderInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
