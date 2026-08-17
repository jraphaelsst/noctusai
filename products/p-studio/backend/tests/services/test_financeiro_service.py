"""FinanceiroService — a derivação de `atrasado` nas bordas.

Pelas rotas não dá para escolher que dia é hoje, então o caso de fronteira
(vencimento == hoje) fica indecidível. Aqui `status_exibido` recebe `hoje`
explicitamente e a regra pode ser fixada sem depender do relógio.
"""
from datetime import date

import pytest

from app.services.financeiro_service import (
    FinanceiroService,
    registrar_recebimento,
    status_exibido,
)
from tests.conftest import FakeDB, make_row

HOJE = date(2026, 7, 31)


@pytest.mark.parametrize(
    "status,vencimento,esperado",
    [
        ("faturado", "2026-07-30", "atrasado"),   # ontem
        ("faturado", "2026-07-31", "faturado"),   # vence hoje — ainda não atrasou
        ("faturado", "2026-08-01", "faturado"),   # amanhã
        ("a_faturar", "2026-07-30", "atrasado"),
        ("a_faturar", "2026-08-01", "a_faturar"),
        ("recebido", "2026-01-01", "recebido"),   # pago não atrasa
        ("cancelado", "2026-01-01", "cancelado"),
    ],
)
def test_status_exibido_nas_bordas(status, vencimento, esperado):
    lancamento = {"status": status, "vencimento": vencimento}
    assert status_exibido(lancamento, HOJE) == esperado


def test_vencer_hoje_nao_e_atraso():
    """Regra de negócio: o cliente tem o dia inteiro para pagar."""
    assert status_exibido({"status": "faturado", "vencimento": HOJE.isoformat()}, HOJE) == "faturado"


def test_status_ausente_cai_para_a_faturar():
    assert status_exibido({}, HOJE) == "a_faturar"


def test_vencimento_com_timestamp_completo_e_truncado():
    """O PostgREST pode devolver `date` como string ISO longa."""
    lancamento = {"status": "faturado", "vencimento": "2026-07-30T00:00:00+00:00"}
    assert status_exibido(lancamento, HOJE) == "atrasado"


def test_vencimento_como_objeto_date_tambem_funciona():
    lancamento = {"status": "faturado", "vencimento": date(2026, 7, 30)}
    assert status_exibido(lancamento, HOJE) == "atrasado"


# ── resumo com relógio controlado ────────────────────────────────────────

ORG = "00000000-0000-0000-0000-0000000000ff"


def _service(lancamentos: list[dict]) -> FinanceiroService:
    db = FakeDB({"lancamentos": lancamentos, "clientes": []})
    return FinanceiroService(db, ORG)


def test_resumo_soma_zero_sem_lancamentos():
    resumo = _service([]).resumo()
    assert resumo["faturamento_total"] == 0
    assert resumo["ticket_medio"] == 0


def test_resumo_atrasado_esta_contido_em_em_aberto():
    """Invariante da tela: `em_aberto` inclui o atrasado, não o exclui."""
    hoje = date.today()
    vencido = (hoje.replace(day=1)).isoformat()
    lancamentos = [
        make_row("lancamentos", org_id=ORG, status="faturado",
                 vencimento="2020-01-01", valor=300),
        make_row("lancamentos", org_id=ORG, status="a_faturar", valor=200),
    ]
    resumo = _service(lancamentos).resumo()
    assert resumo["atrasado"] == 300
    assert resumo["em_aberto"] == 500
    assert resumo["em_aberto"] >= resumo["atrasado"]


def test_resumo_ticket_medio_divide_por_recebidos_e_nao_por_todos():
    hoje = date.today().isoformat()
    lancamentos = [
        make_row("lancamentos", org_id=ORG, status="recebido", pago_em=hoje, valor=900),
        make_row("lancamentos", org_id=ORG, status="a_faturar", valor=100),
        make_row("lancamentos", org_id=ORG, status="a_faturar", valor=100),
    ]
    assert _service(lancamentos).resumo()["ticket_medio"] == 900


def test_resumo_receita_do_ano_inclui_a_do_mes():
    hoje = date.today()
    lancamentos = [
        make_row("lancamentos", org_id=ORG, status="recebido",
                 pago_em=hoje.isoformat(), valor=400),
    ]
    resumo = _service(lancamentos).resumo()
    assert resumo["receita_mes"] == 400
    assert resumo["receita_ano"] >= resumo["receita_mes"]


# ── registrar_recebimento — a transição guardada ─────────────────────────

def _db_com(lancamento: dict) -> FakeDB:
    return FakeDB({"lancamentos": [lancamento], "clientes": []})


def test_registrar_recebimento_liquida_lancamento_em_aberto():
    l = make_row("lancamentos", org_id=ORG, status="faturado", valor=100)
    db = _db_com(l)

    assert registrar_recebimento(db, l, date(2026, 7, 20), "pix") is True

    linha = db.data["lancamentos"][0]
    assert linha["status"] == "recebido"
    assert linha["pago_em"] == "2026-07-20"
    assert linha["forma_pagamento"] == "pix"


def test_registrar_recebimento_sem_data_usa_hoje():
    l = make_row("lancamentos", org_id=ORG, status="a_faturar")
    db = _db_com(l)

    assert registrar_recebimento(db, l) is True
    assert db.data["lancamentos"][0]["pago_em"] == date.today().isoformat()


def test_registrar_recebimento_nao_reescreve_pago_em_de_ja_recebido():
    """A regressão que motivou a extração: receita mudando de mês sem rastro."""
    l = make_row("lancamentos", org_id=ORG, status="recebido", pago_em="2026-01-15")
    db = _db_com(l)

    assert registrar_recebimento(db, l, date(2026, 7, 31)) is False
    assert db.data["lancamentos"][0]["pago_em"] == "2026-01-15"


def test_registrar_recebimento_recusa_cancelado():
    """Lançamento cancelado não é liquidado nem pelo funil nem pelo banco."""
    l = make_row("lancamentos", org_id=ORG, status="cancelado")
    db = _db_com(l)

    assert registrar_recebimento(db, l) is False
    assert db.data["lancamentos"][0]["status"] == "cancelado"


def test_registrar_recebimento_nao_levanta_para_id_inexistente():
    """O webhook não pode levantar — o Asaas pausa a fila após 15 não-2xx."""
    db = FakeDB({"lancamentos": []})
    fantasma = make_row("lancamentos", org_id=ORG, status="faturado")

    assert registrar_recebimento(db, fantasma) is True  # update sem alvo, sem erro


def test_registrar_recebimento_sem_forma_preserva_a_existente():
    l = make_row("lancamentos", org_id=ORG, status="faturado", forma_pagamento="boleto")
    db = _db_com(l)

    registrar_recebimento(db, l, None, None)
    assert db.data["lancamentos"][0]["forma_pagamento"] == "boleto"


def test_resumo_recebido_sem_pago_em_nao_entra_na_serie_temporal():
    """Sem data de pagamento não dá para alocar a receita num mês."""
    lancamentos = [
        make_row("lancamentos", org_id=ORG, status="recebido", pago_em=None, valor=500),
    ]
    resumo = _service(lancamentos).resumo()
    assert resumo["recebido"] == 500
    assert resumo["receita_mes"] == 0
