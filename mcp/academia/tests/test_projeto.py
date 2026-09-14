"""academia.roadmap.* + academia.tarefa.* — CONTRACT §B.4 / §C, every
row's method/path/body."""
from __future__ import annotations

import asyncio

from academia.tools.projeto import (
    roadmap_atualizar,
    roadmap_ler,
    tarefa_atualizar,
    tarefa_criar,
    tarefa_listar,
    tarefa_preparar_sessao,
)


def test_roadmap_ler_is_get_api_roadmap_no_params(fake_client):
    fake_client.set_response("GET", "/api/roadmap", {"ok": True, "items": [], "total": 0})
    out = asyncio.run(roadmap_ler({}))
    assert out == {"ok": True, "items": [], "total": 0}
    assert fake_client.calls == [{"method": "GET", "path": "/api/roadmap", "params": None, "json_body": None}]


def test_roadmap_atualizar_is_patch_api_roadmap_codigo(fake_client):
    fake_client.set_response("PATCH", "/api/roadmap/P1", {"ok": True, "codigo": "P1", "estado": "concluida"})
    out = asyncio.run(roadmap_atualizar({"codigo": "P1", "estado": "concluida"}))
    assert out == {"ok": True, "codigo": "P1", "estado": "concluida"}
    assert fake_client.calls == [
        {"method": "PATCH", "path": "/api/roadmap/P1", "params": None, "json_body": {"estado": "concluida"}}
    ]


def test_roadmap_atualizar_only_sends_provided_fields(fake_client):
    asyncio.run(roadmap_atualizar({"codigo": "P1", "titulo": "Novo título"}))
    assert fake_client.calls[0]["json_body"] == {"titulo": "Novo título"}


def test_tarefa_criar_is_post_api_tasks(fake_client):
    fake_client.set_response("POST", "/api/tasks", {"ok": True, "codigo": "T-030"})
    out = asyncio.run(tarefa_criar({"titulo": "Escrever roteiro", "fase": "P1", "detalhe": "usar D-10"}))
    assert out == {"ok": True, "codigo": "T-030"}
    assert fake_client.calls == [
        {
            "method": "POST",
            "path": "/api/tasks",
            "params": None,
            "json_body": {"titulo": "Escrever roteiro", "fase": "P1", "detalhe": "usar D-10"},
        }
    ]


def test_tarefa_criar_unknown_fase_422_passes_through(fake_client):
    fake_client.set_response(
        "POST", "/api/tasks", {"ok": False, "error": {"status": 422, "code": "validation_error", "detail": "fase desconhecida"}}
    )
    out = asyncio.run(tarefa_criar({"titulo": "T", "fase": "P99"}))
    assert out["ok"] is False
    assert out["error"]["status"] == 422


def test_tarefa_atualizar_is_patch_api_tasks_codigo(fake_client):
    fake_client.set_response("PATCH", "/api/tasks/T-030", {"ok": True, "codigo": "T-030", "estado": "concluida"})
    out = asyncio.run(tarefa_atualizar({"codigo": "T-030", "estado": "concluida"}))
    assert out == {"ok": True, "codigo": "T-030", "estado": "concluida"}
    assert fake_client.calls == [
        {"method": "PATCH", "path": "/api/tasks/T-030", "params": None, "json_body": {"estado": "concluida"}}
    ]


def test_tarefa_listar_is_get_api_tasks_with_filters(fake_client):
    fake_client.set_response("GET", "/api/tasks", {"ok": True, "items": [], "total": 0})
    out = asyncio.run(tarefa_listar({"fase": "P1", "estado": "pendente"}))
    assert out == {"ok": True, "items": [], "total": 0}
    assert fake_client.calls == [
        {"method": "GET", "path": "/api/tasks", "params": {"fase": "P1", "estado": "pendente"}, "json_body": None}
    ]


def test_tarefa_preparar_sessao_is_get_api_session_prep(fake_client):
    fake_client.set_response(
        "GET",
        "/api/session-prep",
        {"ok": True, "fase_atual": None, "proximas": [], "bloqueadas": [], "perguntas_abertas": 0, "perguntas_bloqueantes": []},
    )
    out = asyncio.run(tarefa_preparar_sessao({}))
    assert out["ok"] is True
    assert out["perguntas_abertas"] == 0
    assert fake_client.calls == [
        {"method": "GET", "path": "/api/session-prep", "params": None, "json_body": None}
    ]
