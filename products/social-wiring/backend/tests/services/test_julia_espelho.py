"""The read mirror of agents' qualification state (`julia_espelho_service`): what lands in SW's own columns, from where."""
from __future__ import annotations

from app.services import julia_contatos_service as contatos
from app.services import julia_espelho_service as espelho
from app.clients.agents import QualificacaoResumo
from tests.support.julia_world import CONNECTION_ID, LEAD_CHAT, ORG_ID as ORG, World


def _contato(w: World, **over) -> dict:
    c = contatos.obter_ou_criar_contato(w.sw, org_id=ORG, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT)
    if over:
        contatos.atualizar_contato(w.sw, c["id"], over)
    return w.contato()


def test_values_become_display_strings_and_columns():
    s = espelho.slots_do_espelho({
        "operacao": "compra", "nome": "Ana", "email": "a@x.com", "quartos_min": 3, "animais": False,
        "regioes": ["Granja Viana", "Cotia"], "estrutura": {"x": 1}, "vazio": None, "cpf": "123", "faixa": "400-500k",
    })
    assert s == {"quartos_min": "3", "animais": "false", "regioes": "Granja Viana, Cotia", "faixa": "400-500k"}


def test_sensitive_keys_never_reach_the_mirror():
    from app.services import julia_slots_sensiveis as sens

    s = espelho.slots_do_espelho({k: "x" for k in sens.SENSIVEIS} | {"bairro": "Granja"})
    assert s == {"bairro": "Granja"}


def test_aplicar_valores_writes_only_what_changed_and_fills_empty_columns_only():
    w = World()
    c = _contato(w, nome="Nome do CRM")
    out = espelho.aplicar_valores(w.sw, ORG, c, {"operacao": "aluguel", "nome": "Outro", "email": "a@x.com", "bairro": "Granja"})
    assert out == {"slots": {"bairro": "Granja"}, "operacao": "aluguel", "email": "a@x.com"}  # an existing name is never overwritten
    again = espelho.aplicar_valores(w.sw, ORG, w.contato(), {"operacao": "aluguel", "email": "a@x.com", "bairro": "Granja"})
    assert again == {}


def test_a_bad_email_or_an_unknown_operation_is_not_mirrored():
    w = World()
    c = _contato(w)
    out = espelho.aplicar_valores(w.sw, ORG, c, {"operacao": "atualizacao", "email": "nao-e-email"})
    assert out == {}


def test_the_open_interacao_follows():
    w = World()
    c = _contato(w)
    inter = contatos.abrir_interacao(w.sw, ORG, c)
    espelho.aplicar_valores(w.sw, ORG, c, {"operacao": "compra", "bairro": "Granja"}, inter)
    row = w.rows("julia_interacoes")[0]
    assert (row["operacao"], row["slots"]) == ("compra", {"bairro": "Granja"})


def test_registrar_estagio_writes_on_change_only():
    w = World()
    w.sw.set_table_data("ai_outputs", [])
    c = _contato(w)
    q = QualificacaoResumo(versao="imob-lead@3", estagio="qualificado", score=61)
    assert espelho.registrar_estagio(w.sw, c["id"], q) is True
    assert espelho.registrar_estagio(w.sw, c["id"], q) is False
    assert espelho.registrar_estagio(w.sw, c["id"], QualificacaoResumo(estagio="qualificado", score=70)) is True
    assert [(r["label"], r["score"]) for r in w.rows("ai_outputs")] == [("qualificado", 61), ("qualificado", 70)]
    assert espelho.registrar_estagio(w.sw, c["id"], None) is False
