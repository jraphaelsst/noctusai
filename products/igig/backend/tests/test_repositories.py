"""Repository-layer tests.

Run against the REAL SQLite store with the REAL domain schema, not the Fake:
these tests are what prove the schema and the repositories agree, so
substituting an in-memory dict would remove the thing being verified. The
schema file is the same one `app/store.py` applies at boot.
"""
from __future__ import annotations

import sqlite3

import pytest
from noctusai_lib.integrations.persistence import RecordNotFound, SqliteRecordStore

from app.repositories import ETAPAS, Repositorios
from app.store import aplicar_schema_sqlite

ORG = "org-igig"
OUTRA_ORG = "org-outra"


@pytest.fixture
def repos() -> Repositorios:
    store = SqliteRecordStore(":memory:")
    aplicar_schema_sqlite(store)
    return Repositorios(store)


@pytest.fixture
def cliente(repos: Repositorios) -> dict:
    return repos.cliente.criar(ORG, {"nome": "Padaria Sol", "nicho": "alimentacao"})


@pytest.fixture
def tarefa(repos: Repositorios, cliente: dict) -> dict:
    pauta = repos.pauta.criar(
        ORG, {"cliente_id": cliente["id"], "titulo": "Post institucional", "funil": "topo"}
    )
    return repos.tarefa.criar(ORG, {"pauta_id": pauta["id"], "titulo": "Arte do post"})


# ── Cliente ─────────────────────────────────────────────────────────
def test_cliente_defaults_to_prospect(repos, cliente):
    assert cliente["status"] == "prospect"


def test_ativar_flips_prospect_to_ativo(repos, cliente):
    assert repos.cliente.ativar(ORG, cliente["id"])["status"] == "ativo"


def test_busca_por_nome_is_case_insensitive(repos, cliente):
    assert len(repos.cliente.buscar_por_nome(ORG, "padaria")) == 1


def test_listar_por_status(repos, cliente):
    repos.cliente.criar(ORG, {"nome": "Outro"})
    repos.cliente.ativar(ORG, cliente["id"])
    assert [c["nome"] for c in repos.cliente.listar_por_status(ORG, "ativo")] == ["Padaria Sol"]


def test_cliente_is_org_scoped(repos, cliente):
    assert repos.cliente.listar(OUTRA_ORG) == []
    with pytest.raises(RecordNotFound):
        repos.cliente.buscar(OUTRA_ORG, cliente["id"])


def test_schema_rejects_an_invalid_status(repos):
    from noctusai_lib.integrations.persistence import PersistenceError

    with pytest.raises(PersistenceError):
        repos.cliente.criar(ORG, {"nome": "X", "status": "inventado"})


# ── Marca (Módulo 2 sidebar payload) ────────────────────────────────
def test_repertorio_returns_none_when_no_brand(repos, cliente):
    assert repos.marca.repertorio(ORG, cliente["id"]) is None


def test_repertorio_round_trips_json_columns(repos, cliente):
    paleta = [{"nome": "laranja", "hex": "#f97316"}]
    linhas = ["institucional", "educacional"]
    repos.marca.criar(
        ORG,
        {
            "cliente_id": cliente["id"],
            "nome": "Padaria Sol",
            "paleta": paleta,
            "linhas_editoriais": linhas,
            "tom_de_voz": "próximo e caloroso",
        },
    )
    repertorio = repos.marca.repertorio(ORG, cliente["id"])
    assert repertorio["paleta"] == paleta
    assert repertorio["linhas_editoriais"] == linhas
    assert repertorio["tom_de_voz"] == "próximo e caloroso"


# ── Tarefa / esteira (Módulo 4) ─────────────────────────────────────
def test_tarefa_starts_at_the_first_etapa(repos, tarefa):
    assert tarefa["etapa"] == ETAPAS[0] == "aguardando_roteiro"


def test_quadro_has_every_column_even_when_empty(repos, tarefa):
    quadro = repos.tarefa.quadro(ORG)
    assert set(quadro) == set(ETAPAS)
    assert len(quadro["aguardando_roteiro"]) == 1
    assert quadro["agendado"] == []


def test_mover_advances_the_etapa(repos, tarefa):
    assert repos.tarefa.mover(ORG, tarefa["id"], "design_em_producao")["etapa"] == "design_em_producao"


def test_mover_rejects_an_unknown_etapa(repos, tarefa):
    with pytest.raises(ValueError, match="etapa inválida"):
        repos.tarefa.mover(ORG, tarefa["id"], "etapa_inventada")


def test_solicitar_ajuste_reopens_and_increments_refacoes(repos, tarefa):
    repos.tarefa.mover(ORG, tarefa["id"], "aprovacao_cliente")
    ajustada = repos.tarefa.solicitar_ajuste(ORG, tarefa["id"], "trocar a cor do fundo")
    assert ajustada["etapa"] == "revisao_interna"
    assert ajustada["refacoes"] == 1
    assert ajustada["observacao_cliente"] == "trocar a cor do fundo"

    de_novo = repos.tarefa.solicitar_ajuste(ORG, tarefa["id"], "outra coisa")
    assert de_novo["refacoes"] == 2, "the contador must accumulate across rounds"


def test_aprovar_jumps_to_scheduling(repos, tarefa):
    repos.tarefa.mover(ORG, tarefa["id"], "aprovacao_cliente")
    assert repos.tarefa.aprovar(ORG, tarefa["id"])["etapa"] == "pronto_para_agendamento"


# ── Apontamento / timesheet (Módulo 4) ──────────────────────────────
def test_iniciar_opens_a_segment(repos, tarefa):
    apontamento = repos.apontamento.iniciar(ORG, tarefa["id"], "user-1")
    assert apontamento["encerrado_em"] is None
    assert repos.apontamento.aberto_do_usuario(ORG, "user-1")["id"] == apontamento["id"]


def test_starting_another_tarefa_auto_closes_the_running_timer(repos, tarefa, cliente):
    """The spec requires the clock to pause when another tarefa starts."""
    outra_pauta = repos.pauta.criar(ORG, {"cliente_id": cliente["id"], "titulo": "Outra"})
    outra_tarefa = repos.tarefa.criar(
        ORG, {"pauta_id": outra_pauta["id"], "titulo": "Outra arte"}
    )

    primeiro = repos.apontamento.iniciar(ORG, tarefa["id"], "user-1")
    segundo = repos.apontamento.iniciar(ORG, outra_tarefa["id"], "user-1")

    assert repos.apontamento.buscar(ORG, primeiro["id"])["encerrado_em"] is not None
    assert repos.apontamento.aberto_do_usuario(ORG, "user-1")["id"] == segundo["id"]


def test_two_users_can_run_timers_simultaneously(repos, tarefa):
    """The one-open-segment rule is per USER, not global."""
    repos.apontamento.iniciar(ORG, tarefa["id"], "user-1")
    repos.apontamento.iniciar(ORG, tarefa["id"], "user-2")
    assert repos.apontamento.aberto_do_usuario(ORG, "user-1") is not None
    assert repos.apontamento.aberto_do_usuario(ORG, "user-2") is not None


def test_encerrar_persists_minutes(repos, tarefa):
    apontamento = repos.apontamento.iniciar(ORG, tarefa["id"], "user-1")
    encerrado = repos.apontamento.encerrar(ORG, apontamento["id"])
    assert encerrado["encerrado_em"] is not None
    assert encerrado["minutos"] >= 0
    assert repos.apontamento.aberto_do_usuario(ORG, "user-1") is None


def test_minutos_da_tarefa_sums_every_segment(repos, tarefa):
    for _ in range(2):
        seg = repos.apontamento.iniciar(ORG, tarefa["id"], "user-1")
        repos.apontamento.encerrar(ORG, seg["id"])
    assert repos.apontamento.minutos_da_tarefa(ORG, tarefa["id"]) >= 0
    assert len(repos.apontamento.da_tarefa(ORG, tarefa["id"])) == 2


# ── Contrato (Módulo 1 → 6) ─────────────────────────────────────────
def test_registrar_assinatura_activates_the_contract(repos, cliente):
    contrato = repos.contrato.criar(
        ORG, {"cliente_id": cliente["id"], "valor_mensal": 5000.0, "posts_por_mes": 12}
    )
    assert contrato["status"] == "rascunho"
    assinado = repos.contrato.registrar_assinatura(ORG, contrato["id"])
    assert assinado["status"] == "ativo"
    assert assinado["assinado_em"] is not None


# ── Pauta (Módulo 3) ────────────────────────────────────────────────
def test_no_periodo_filters_the_calendar_window(repos, cliente):
    for titulo, data in (("jan", "2026-01-10T09:00:00"), ("fev", "2026-02-10T09:00:00")):
        repos.pauta.criar(
            ORG, {"cliente_id": cliente["id"], "titulo": titulo, "data_publicacao": data}
        )
    janeiro = repos.pauta.no_periodo(ORG, "2026-01-01T00:00:00", "2026-01-31T23:59:59")
    assert [p["titulo"] for p in janeiro] == ["jan"]


def test_cascade_delete_removes_dependent_rows(repos, cliente, tarefa):
    """FKs are ON in SQLite, matching what Postgres enforces."""
    assert repos.pauta.do_cliente(ORG, cliente["id"])
    repos.cliente.remover(ORG, cliente["id"])
    assert repos.pauta.do_cliente(ORG, cliente["id"]) == []
    assert repos.tarefa.listar(ORG) == []
