"""academia.roadmap.* + academia.tarefa.* tools — roadmap and tasks
(CONTRACT §B.4 / §C).

`academia.roadmap.render` is DEPRECATED and REMOVED (CONTRACT §C) — the
UI renders the roadmap now. Do not re-add it.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from ..client import get_client
from ..types import (
    RoadmapAtualizarInput,
    RoadmapLerInput,
    TarefaAtualizarInput,
    TarefaCriarInput,
    TarefaListarInput,
    TarefaPrepararSessaoInput,
)


def _patch_body(inp, fields: tuple[str, ...]) -> dict:
    body: dict = {}
    for field in fields:
        value = getattr(inp, field)
        if value is not None:
            body[field] = value
    return body


async def roadmap_ler(args: dict) -> dict:
    RoadmapLerInput(**args)
    client = get_client()
    return await client.request("GET", "/api/roadmap")


async def roadmap_atualizar(args: dict) -> dict:
    inp = RoadmapAtualizarInput(**args)
    client = get_client()
    body = _patch_body(inp, ("estado", "titulo", "objetivo", "concluida_quando"))
    return await client.request("PATCH", f"/api/roadmap/{inp.codigo}", json_body=body)


async def tarefa_criar(args: dict) -> dict:
    inp = TarefaCriarInput(**args)
    client = get_client()
    body: dict = {"titulo": inp.titulo, "fase": inp.fase}
    if inp.detalhe is not None:
        body["detalhe"] = inp.detalhe
    if inp.bloqueada_por is not None:
        body["bloqueada_por"] = inp.bloqueada_por
    return await client.request("POST", "/api/tasks", json_body=body)


async def tarefa_atualizar(args: dict) -> dict:
    inp = TarefaAtualizarInput(**args)
    client = get_client()
    body = _patch_body(inp, ("estado", "detalhe", "bloqueada_por"))
    return await client.request("PATCH", f"/api/tasks/{inp.codigo}", json_body=body)


async def tarefa_listar(args: dict) -> dict:
    inp = TarefaListarInput(**args)
    client = get_client()
    return await client.request("GET", "/api/tasks", params={"fase": inp.fase, "estado": inp.estado})


async def tarefa_preparar_sessao(args: dict) -> dict:
    TarefaPrepararSessaoInput(**args)
    client = get_client()
    return await client.request("GET", "/api/session-prep")


HANDLERS = {
    "academia.roadmap.ler": roadmap_ler,
    "academia.roadmap.atualizar": roadmap_atualizar,
    "academia.tarefa.criar": tarefa_criar,
    "academia.tarefa.atualizar": tarefa_atualizar,
    "academia.tarefa.listar": tarefa_listar,
    "academia.tarefa.preparar_sessao": tarefa_preparar_sessao,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="academia.roadmap.ler",
            description="LEITURA — lista as fases do roadmap, ordenadas (GET /api/roadmap).",
            inputSchema=RoadmapLerInput.model_json_schema(),
        ),
        Tool(
            name="academia.roadmap.atualizar",
            description="ESCRITA — atualiza uma fase do roadmap (PATCH /api/roadmap/{codigo}).",
            inputSchema=RoadmapAtualizarInput.model_json_schema(),
        ),
        Tool(
            name="academia.tarefa.criar",
            description="ESCRITA — cria uma tarefa vinculada a uma fase (POST /api/tasks). 422 se fase desconhecida.",
            inputSchema=TarefaCriarInput.model_json_schema(),
        ),
        Tool(
            name="academia.tarefa.atualizar",
            description="ESCRITA — atualiza uma tarefa (PATCH /api/tasks/{codigo}).",
            inputSchema=TarefaAtualizarInput.model_json_schema(),
        ),
        Tool(
            name="academia.tarefa.listar",
            description="LEITURA — lista tarefas, filtráveis por fase/estado (GET /api/tasks?fase=&estado=).",
            inputSchema=TarefaListarInput.model_json_schema(),
        ),
        Tool(
            name="academia.tarefa.preparar_sessao",
            description=(
                "LEITURA — resumo de preparação de sessão: fase atual, "
                "próximas tarefas, tarefas bloqueadas, perguntas em aberto "
                "(GET /api/session-prep)."
            ),
            inputSchema=TarefaPrepararSessaoInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
