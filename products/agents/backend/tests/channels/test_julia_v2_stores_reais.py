"""The Real (PostgREST) halves added by A-RT, through the scripted client double: the conformance / limits store and
the per-thread usage counter. The query SHAPE each sends (org-scoped, table + columns of migration 037)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.stores.conformidade import LIMITES_PADRAO, Impressao, SupabaseConformidadeStore, Violacao
from app.stores.messages import SupabaseMessageStore
from tests.channels.test_real_stores import ScriptedClient


def _calls(client, table):
    return [c for t, c in client.log if t == table]


def test_rules_are_the_code_defaults_overlaid_by_the_stored_rows():
    org, agent = uuid4(), uuid4()
    row = {"regra": "termina_sem_pergunta", "ativo": False, "politica": "bloquear",
           "mensagem_correcao_texto_chave": "conformidade.correcao.termina_sem_pergunta", "parametros": {"x": 1}}
    client = ScriptedClient(SimpleNamespace(data=[row]))
    regras = SupabaseConformidadeStore(client).regras(org, agent)
    assert regras["termina_sem_pergunta"].ativo is False and regras["termina_sem_pergunta"].politica == "bloquear"
    assert regras["vazamento_prompt"].politica == "bloquear" and regras["fallback_enviado"].politica == "registrar"
    names = [c[0] for c in _calls(client, "conformidade_regras")[0]]
    assert names == ["select", "eq", "eq"]  # org AND agent scoped


def test_a_violation_is_one_insert_of_codes_and_counts():
    org, agent, thread = uuid4(), uuid4(), uuid4()
    client = ScriptedClient(SimpleNamespace(data=[{"id": str(uuid4()), "created_at": "2026-10-19T00:00:00+00:00"}]))
    out = SupabaseConformidadeStore(client).registrar_violacao(
        org, agent, Violacao("vazamento_prompt", "bloquear", {"janelas": 2}, True), thread_id=thread,
        compiled_hash="sha256:x", origem="canal")
    assert out.id is not None
    [(name, args, _kw)] = [c for c in _calls(client, "conformidade_violacoes")[0] if c[0] == "insert"]
    row = args[0]
    assert row["org_id"] == str(org) and row["agent_id"] == str(agent) and row["thread_id"] == str(thread)
    assert row["detalhe"] == {"janelas": 2} and row["bloqueada"] is True and "texto" not in row


def test_limits_upsert_a_row_on_first_use_and_read_the_db_defaults():
    org, agent = uuid4(), uuid4()
    stored = {"janela_segundos": 60, "max_turnos_janela": 6, "max_turnos_dia": 200, "max_custo_dia_usd": "2.0000",
              "max_imoveis_distintos": 30, "max_recusas_por_turno": 2, "max_erros_ferramenta_por_turno": 3,
              "max_turnos_hora": 60, "max_novos_leads_hora": 30, "max_novos_leads_dia": 200,
              "reserva_leads_existentes_pct": 50, "loop_ativo": True, "loop_repeticoes": 3,
              "loop_similaridade": "0.900", "loop_janela_segundos": 600, "loop_min_chars": 8, "loop_eco_tokens": 12,
              "loop_latencia_mediana_s": "3.00", "loop_trocas": 5, "max_chamadas_ferramenta_turno": 8,
              "max_oferecer_turno": 1, "max_abrir_skill_turno": 4, "max_detalhes_turno": 3,
              "catalogo_descricao_max": 600, "catalogo_titulo_max": 120, "catalogo_caracteristicas_max": 30,
              "catalogo_item_max": 60}
    client = ScriptedClient(SimpleNamespace(data=[]), SimpleNamespace(data=[]), SimpleNamespace(data=[stored]))
    lim = SupabaseConformidadeStore(client).limites(org, agent)
    assert lim == LIMITES_PADRAO and isinstance(lim.max_custo_dia_usd, float)
    kinds = [c[0] for t, calls in client.log for c in calls]
    assert "upsert" in kinds  # the row is created from the column defaults, never from numbers in code


def test_the_fingerprint_is_stored_as_hashes_only():
    org, version = uuid4(), uuid4()
    client = ScriptedClient(SimpleNamespace(data=[]))
    SupabaseConformidadeStore(client).salvar_impressao(org, Impressao(version, 12, frozenset({3, -7})))
    [(name, args, kw)] = [c for c in _calls(client, "conformidade_impressoes")[0] if c[0] == "upsert"]
    assert args[0]["shingles"] == [-7, 3] and args[0]["version_id"] == str(version) and kw == {"on_conflict": "version_id"}


def test_thread_usage_counts_assistant_rows_of_that_thread_since_the_cutoff():
    org, thread = uuid4(), uuid4()
    rows = [{"id": str(uuid4()), "custo_usd": 0.5}, {"id": str(uuid4()), "custo_usd": None}]
    client = ScriptedClient(SimpleNamespace(data=rows), SimpleNamespace(data=[]))
    turns, cost = SupabaseMessageStore(client).thread_usage_since(org, thread, datetime(2026, 10, 19, tzinfo=timezone.utc))
    assert (turns, cost) == (2, 0.5)
    calls = _calls(client, "messages")[0]
    eqs = [c[1] for c in calls if c[0] == "eq"]
    assert ("org_id", str(org)) in eqs and ("conversation_id", str(thread)) in eqs and ("role", "assistant") in eqs


def test_redacting_an_identification_updates_only_the_rows_that_change_scoped_by_org_and_thread():
    org, thread = uuid4(), uuid4()
    sujo, limpo = str(uuid4()), str(uuid4())
    rows = [
        {"id": sujo, "texto": "meu cpf 529.982.247-25", "blocks": [], "meta": {"midia": {"texto_extraido": "52998224725"}}},
        {"id": limpo, "texto": "oi", "blocks": [], "meta": {}},
    ]
    client = ScriptedClient(SimpleNamespace(data=rows), SimpleNamespace(data=[{"id": sujo}]))
    n = SupabaseMessageStore(client).redigir_identificacao(org, thread, ["52998224725"])
    assert n == 1
    select, update = _calls(client, "messages")
    eqs = [c[1] for c in select if c[0] == "eq"]
    assert ("org_id", str(org)) in eqs and ("conversation_id", str(thread)) in eqs
    [(payload,)] = [c[1] for c in update if c[0] == "update"]
    assert payload == {"texto": "meu cpf ***", "meta": {"midia": {"texto_extraido": "***"}}}
    assert ("id", sujo) in [c[1] for c in update if c[0] == "eq"] and ("org_id", str(org)) in [c[1] for c in update if c[0] == "eq"]
