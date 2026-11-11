"""S4: the owner's blind labels -- strict 401, 403 for a non-admin, append-only events (relabel = a new round), the
blind sample never carrying the verdict nor re-offering a labelled message, and the agreement read."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from noctusai_lib.integrations.prompt_registry import FakePromptRegistry, PromptEntry, configure_prompt_registry, invalidar_cache

from app.routers import classificacao_router as cr
from app.shadow import classificador as clf

INTAKE = "00000000-0000-0000-0000-0000000000a1"
OUTPUT = "00000000-0000-0000-0000-0000000000b1"
CORPO = {"intake_id": INTAKE, "output_id": OUTPUT, "rotulo": "agendamento", "rodada": 1}
ROTAS = [
    ("post", "/api/classificacao/rotulos", {"json": CORPO}),
    ("get", "/api/classificacao/rotulos/progresso", {}),
    ("get", "/api/classificacao/rotulos/concordancia", {}),
]


@pytest.mark.parametrize("metodo,rota,kw", ROTAS)
def test_unauthenticated_is_strictly_401(client, metodo, rota, kw):
    assert getattr(client.raw(), metodo)(rota, **kw).status_code == 401


@pytest.mark.parametrize("metodo,rota,kw", ROTAS)
def test_a_member_who_is_not_an_org_admin_is_403(client, metodo, rota, kw):
    assert getattr(client, metodo)(rota, **kw).status_code == 403


@pytest.fixture
def admin(client):
    from app.main import app

    invalidar_cache()
    configure_prompt_registry(FakePromptRegistry([PromptEntry(
        chave=clf.CHAVE, nome="t", descricao="t", vendor="anthropic", modelo="claude-haiku-5-5", prompt="P")]))
    app.dependency_overrides[cr.require_org_admin] = lambda: (SimpleNamespace(id="user-1"), "t", "test-org-123")
    yield client
    app.dependency_overrides.pop(cr.require_org_admin, None)
    configure_prompt_registry(None)
    invalidar_cache()


def test_a_label_is_recorded_through_the_writer_rpc_and_a_repeat_is_flagged(admin):
    admin.mock_supabase.set_rpc_data("registrar_rotulo", [{"evento_id": "e1", "repetido": False}])
    resp = admin.post("/api/classificacao/rotulos", json=CORPO)
    assert resp.status_code == 200
    assert resp.json() == {"evento_id": "e1", "repetido": False, "intake_id": INTAKE, "output_id": OUTPUT,
                           "rotulo": "agendamento", "rodada": 1}
    (nome, params), = [c for c in admin.mock_supabase.rpc_calls if c[0] == "registrar_rotulo"]
    assert params["p_rotulo"] == "agendamento" and params["p_rodada"] == 1 and params["p_intake_id"] == INTAKE
    admin.mock_supabase.set_rpc_data("registrar_rotulo", [{"evento_id": "e1", "repetido": True}])
    assert admin.post("/api/classificacao/rotulos", json=CORPO).json()["repetido"] is True


def test_a_message_or_output_outside_this_org_is_404(admin):
    admin.mock_supabase.set_rpc_data("registrar_rotulo", [])
    assert admin.post("/api/classificacao/rotulos", json=CORPO).status_code == 404


@pytest.mark.parametrize("corpo", [
    {**CORPO, "rotulo": "talvez"}, {**CORPO, "rodada": 0}, {**CORPO, "intake_id": "x"}, {**CORPO, "extra": 1},
    {k: v for k, v in CORPO.items() if k != "rodada"},
])
def test_an_invalid_label_body_is_422(admin, corpo):
    assert admin.post("/api/classificacao/rotulos", json=corpo).status_code == 422


def test_there_is_no_update_or_delete_route_for_labels(admin):
    for metodo in ("put", "patch", "delete"):
        for rota in ("/api/classificacao/rotulos", f"/api/classificacao/rotulos/{INTAKE}"):
            assert getattr(admin, metodo)(rota).status_code in (404, 405)


def test_the_blind_sample_skips_what_the_caller_already_labelled_and_never_carries_the_verdict(admin):
    admin.mock_supabase.set_rpc_data("amostra_classificacoes", [
        {"intake_id": INTAKE, "output_id": OUTPUT, "body": "Pode ser quinta?", "received_at": "2026-11-10T12:00:00+00:00",
         "label": "agendamento", "confidence": 0.9, "reason_code": "propoe_horario", "estrato": "agendamento:alta"},
        {"intake_id": "00000000-0000-0000-0000-0000000000a2", "output_id": "00000000-0000-0000-0000-0000000000b2",
         "body": "Viu o jogo?", "received_at": "2026-11-10T12:01:00+00:00",
         "label": "outro", "confidence": 0.4, "reason_code": "sem_agendamento", "estrato": "outro:baixa"},
    ])
    admin.mock_supabase.set_rpc_data("rotulos_do_rotulador", [{"intake_id": INTAKE, "rotulo": "agendamento", "rodada": 1}])
    itens = admin.get("/api/classificacao/amostra").json()["itens"]
    assert [i["texto"] for i in itens] == ["Viu o jogo?"]
    assert set(itens[0]) == {"intake_id", "output_id", "texto", "recebida_em"}


def test_progress_counts_the_callers_latest_labels(admin):
    admin.mock_supabase.set_rpc_data("rotulos_do_rotulador", [
        {"intake_id": "a", "rotulo": "agendamento", "rodada": 1}, {"intake_id": "b", "rotulo": "nao_sei", "rodada": 2},
        {"intake_id": "c", "rotulo": "agendamento", "rodada": 1}])
    assert admin.get("/api/classificacao/rotulos/progresso").json() == {
        "rotuladas": 3, "por_rotulo": {"agendamento": 2, "nao_agendamento": 0, "nao_sei": 1}}


def test_agreement_route_reveals_the_verdict_only_as_counts(admin):
    admin.mock_supabase.set_rpc_data("resumo_rotulos", [
        {"prompt_version": "v1", "modelo": "m", "veredito": "agendamento", "rotulo": "agendamento", "n": 8},
        {"prompt_version": "v1", "modelo": "m", "veredito": "agendamento", "rotulo": "nao_agendamento", "n": 2},
        {"prompt_version": "v1", "modelo": "m", "veredito": "outro", "rotulo": "nao_agendamento", "n": 9},
        {"prompt_version": "v1", "modelo": "m", "veredito": "outro", "rotulo": "nao_sei", "n": 5}])
    g, = admin.get("/api/classificacao/rotulos/concordancia").json()["grupos"]
    assert (g["total"], g["nao_sei"], g["decididos"], g["concordam"], g["concordancia"]) == (24, 5, 19, 17, round(17 / 19, 4))
    assert g["matriz"]["agendamento"] == {"agendamento": 8, "nao_agendamento": 2, "nao_sei": 0}


def test_the_labels_migration_pins_the_seed_template_and_the_events_table_is_append_only():
    from noctusai_lib.domain.sql_templates import ai_feedback_events_table_sql

    sql, = (Path(__file__).resolve().parents[2] / "migrations").glob("*_rotulos_avaliacao.sql")
    sql = sql.read_text()
    assert ai_feedback_events_table_sql("assistant", ("agendamento", "nao_agendamento", "nao_sei")) in sql
    assert "BEFORE UPDATE OR DELETE ON assistant.ai_feedback_events" in sql
    assert "ON CONFLICT ON CONSTRAINT ai_feedback_events_once_per_round DO NOTHING" in sql
    assert "('avaliacao', 'producao')" in sql
    # LGPD: no message text or phone is stored by the label table or read by the summary
    assert "body" not in sql.split("-- ----- 2. The writer -----")[1].split("amostra")[0].replace("-- the body", "")
