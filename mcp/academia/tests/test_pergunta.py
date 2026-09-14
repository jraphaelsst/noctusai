"""academia.pergunta.* — CONTRACT §B.3 / §C, every row's method/path/body."""
from __future__ import annotations

import asyncio

from academia.tools.pergunta import pergunta_adicionar, pergunta_listar, pergunta_responder


def test_pergunta_adicionar_is_post_api_questions(fake_client):
    fake_client.set_response("POST", "/api/questions", {"ok": True, "codigo": "Q-05"})
    out = asyncio.run(
        pergunta_adicionar(
            {
                "pergunta": "Qual o prazo legal?",
                "por_que_importa": "define o roteiro",
                "bloqueia": "T-010",
                "destino_kb": "dominio-regulatorio-pnrs",
            }
        )
    )
    assert out == {"ok": True, "codigo": "Q-05"}
    assert fake_client.calls == [
        {
            "method": "POST",
            "path": "/api/questions",
            "params": None,
            "json_body": {
                "pergunta": "Qual o prazo legal?",
                "por_que_importa": "define o roteiro",
                "bloqueia": "T-010",
                "destino_kb": "dominio-regulatorio-pnrs",
            },
        }
    ]


def test_pergunta_adicionar_omits_destino_kb_when_unset(fake_client):
    asyncio.run(pergunta_adicionar({"pergunta": "P", "por_que_importa": "X", "bloqueia": "T-001"}))
    assert "destino_kb" not in fake_client.calls[0]["json_body"]


def test_pergunta_listar_defaults_to_aberta(fake_client):
    fake_client.set_response("GET", "/api/questions", {"ok": True, "items": [], "total": 0})
    out = asyncio.run(pergunta_listar({}))
    assert out == {"ok": True, "items": [], "total": 0}
    assert fake_client.calls == [
        {"method": "GET", "path": "/api/questions", "params": {"estado": "aberta"}, "json_body": None}
    ]


def test_pergunta_listar_accepts_respondida_and_todas(fake_client):
    asyncio.run(pergunta_listar({"estado": "respondida"}))
    asyncio.run(pergunta_listar({"estado": "todas"}))
    assert fake_client.calls[0]["params"] == {"estado": "respondida"}
    assert fake_client.calls[1]["params"] == {"estado": "todas"}


def test_pergunta_responder_is_post_answer_path(fake_client):
    fake_client.set_response("POST", "/api/questions/Q-05/answer", {"ok": True, "codigo": "Q-05", "estado": "respondida"})
    out = asyncio.run(pergunta_responder({"codigo": "Q-05", "resposta": "30 dias"}))
    assert out == {"ok": True, "codigo": "Q-05", "estado": "respondida"}
    assert fake_client.calls == [
        {
            "method": "POST",
            "path": "/api/questions/Q-05/answer",
            "params": None,
            "json_body": {"resposta": "30 dias"},
        }
    ]


def test_pergunta_responder_conflict_passes_through(fake_client):
    fake_client.set_response(
        "POST", "/api/questions/Q-05/answer", {"ok": False, "error": {"status": 409, "code": "conflict", "detail": "já respondida"}}
    )
    out = asyncio.run(pergunta_responder({"codigo": "Q-05", "resposta": "de novo"}))
    assert out["ok"] is False
    assert out["error"]["status"] == 409
