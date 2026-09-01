"""DashboardService — agregados com o relógio fixado.

`montar(hoje=...)` aceita a data, então as séries temporais podem ser
afirmadas com valores literais. Pelas rotas isso seria impossível: um teste
que rodasse dia 1º ou 31 veria janelas diferentes.
"""
from datetime import date, timedelta

import pytest

from app.services.dashboard_service import ClienteMetricasService, DashboardService
from tests.conftest import FakeDB, make_row

ORG = "00000000-0000-0000-0000-0000000000ff"
HOJE = date(2026, 7, 31)  # uma quinta-feira, mês cheio


def _dashboard(**tabelas) -> dict:
    db = FakeDB({
        "negocios": tabelas.get("negocios", []),
        "captacoes": tabelas.get("captacoes", []),
        "producoes": tabelas.get("producoes", []),
        "lancamentos": tabelas.get("lancamentos", []),
    })
    return DashboardService(db, ORG).montar(hoje=HOJE)


def test_receita_por_mes_cobre_seis_meses_terminando_hoje():
    corpo = _dashboard()
    assert [p["mes"] for p in corpo["receita_por_mes"]] == [
        "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07",
    ]
    assert [p["label"] for p in corpo["receita_por_mes"]] == [
        "Fev", "Mar", "Abr", "Mai", "Jun", "Jul",
    ]


def test_receita_por_mes_aloca_no_mes_do_pagamento():
    lancamentos = [
        make_row("lancamentos", org_id=ORG, status="recebido",
                 pago_em="2026-05-10", valor=500),
        make_row("lancamentos", org_id=ORG, status="recebido",
                 pago_em="2026-07-02", valor=800),
        # fora da janela de 6 meses — não deve aparecer em lugar nenhum
        make_row("lancamentos", org_id=ORG, status="recebido",
                 pago_em="2025-01-01", valor=9999),
    ]
    serie = {p["mes"]: p["valor"] for p in _dashboard(lancamentos=lancamentos)["receita_por_mes"]}
    assert serie["2026-05"] == 500
    assert serie["2026-07"] == 800
    assert serie["2026-06"] == 0
    assert sum(serie.values()) == 1300


def test_receita_por_mes_ignora_o_que_nao_foi_recebido():
    lancamentos = [
        make_row("lancamentos", org_id=ORG, status="faturado",
                 vencimento="2026-07-10", valor=9999),
    ]
    serie = _dashboard(lancamentos=lancamentos)["receita_por_mes"]
    assert sum(p["valor"] for p in serie) == 0


def test_captacoes_por_semana_distribui_em_quatro_baldes():
    """Janela de 28 dias terminando hoje; S1 é a mais antiga."""
    captacoes = [
        make_row("captacoes", org_id=ORG, data="2026-07-05"),  # S1 (inicio 07-04)
        make_row("captacoes", org_id=ORG, data="2026-07-12"),  # S2
        make_row("captacoes", org_id=ORG, data="2026-07-20"),  # S3
        make_row("captacoes", org_id=ORG, data="2026-07-31"),  # S4 (hoje)
        make_row("captacoes", org_id=ORG, data="2026-06-01"),  # fora da janela
    ]
    baldes = {b["semana"]: b["captacoes"] for b in _dashboard(captacoes=captacoes)["captacoes_por_semana"]}
    assert baldes == {"S1": 1, "S2": 1, "S3": 1, "S4": 1}


def test_captacoes_por_semana_ignora_canceladas():
    captacoes = [
        make_row("captacoes", org_id=ORG, data="2026-07-30", status="agendado"),
        make_row("captacoes", org_id=ORG, data="2026-07-30", status="cancelado"),
    ]
    baldes = _dashboard(captacoes=captacoes)["captacoes_por_semana"]
    assert sum(b["captacoes"] for b in baldes) == 1


@pytest.mark.parametrize(
    "hoje",
    [
        date(2026, 1, 1),   # dia 1, mês de 31 dias — o caso que expôs o bug
        date(2026, 1, 2),   # dia 2 — o outro dia de risco
        date(2026, 1, 15),  # meio do mês
        date(2026, 1, 31),  # último dia, mês de 31
        date(2026, 4, 30),  # último dia, mês de 30
        date(2026, 2, 1),   # dia 1 de fevereiro
        date(2026, 2, 28),  # último dia de fevereiro (2026 não é bissexto)
        date(2024, 2, 29),  # último dia de fevereiro bissexto
    ],
)
def test_captacoes_mes_ignora_canceladas_em_qualquer_dia_do_mes(hoje):
    """Mesma regra de `test_captacoes_mes_ignora_canceladas` (rota), mas
    pelo seam `montar(hoje=...)` — relógio controlado, sem depender de
    `date.today()`. Prova que a contagem fica certa em qualquer posição do
    mês, inclusive no 1º e 2º dia, onde `inicio_mes + offset` cairia no
    futuro sem o clamp em `_neste_mes`."""
    inicio_mes = hoje.replace(day=1)
    d0 = inicio_mes
    d1 = min(inicio_mes + timedelta(days=1), hoje)
    d2 = min(inicio_mes + timedelta(days=2), hoje)
    captacoes = [
        make_row("captacoes", org_id=ORG, data=d0.isoformat(), status="agendado"),
        make_row("captacoes", org_id=ORG, data=d1.isoformat(), status="concluido"),
        make_row("captacoes", org_id=ORG, data=d2.isoformat(), status="cancelado"),
    ]
    db = FakeDB({"negocios": [], "captacoes": captacoes, "producoes": [], "lancamentos": []})
    assert DashboardService(db, ORG).montar(hoje=hoje)["captacoes_mes"] == 2


def test_captacoes_mes_usa_o_mes_corrente_e_nao_os_ultimos_30_dias():
    captacoes = [
        make_row("captacoes", org_id=ORG, data="2026-07-01"),  # dentro
        make_row("captacoes", org_id=ORG, data="2026-06-30"),  # mês anterior
    ]
    assert _dashboard(captacoes=captacoes)["captacoes_mes"] == 1


def test_captacao_futura_no_mes_nao_conta_como_realizada():
    """A janela termina hoje: o que ainda vai acontecer não foi captado."""
    captacoes = [make_row("captacoes", org_id=ORG, data="2026-07-31")]
    assert _dashboard(captacoes=captacoes)["captacoes_mes"] == 1

    futuras = [make_row("captacoes", org_id=ORG, data="2026-08-05")]
    assert _dashboard(captacoes=futuras)["captacoes_mes"] == 0


def test_clientes_ativos_usa_janela_de_90_dias():
    negocios = [
        make_row("negocios", org_id=ORG, cliente_id="c1", created_at="2026-07-01"),
        make_row("negocios", org_id=ORG, cliente_id="c2", created_at="2026-01-01"),
    ]
    assert _dashboard(negocios=negocios)["clientes_ativos"] == 1


def test_clientes_ativos_conta_cliente_uma_vez_so():
    negocios = [
        make_row("negocios", org_id=ORG, cliente_id="c1", created_at="2026-07-01"),
        make_row("negocios", org_id=ORG, cliente_id="c1", created_at="2026-07-15"),
    ]
    assert _dashboard(negocios=negocios)["clientes_ativos"] == 1


def test_prazo_medio_e_a_media_dos_dias_entre_captacao_e_entrega():
    captacao_a = make_row("captacoes", org_id=ORG, data="2026-07-01")
    captacao_b = make_row("captacoes", org_id=ORG, data="2026-07-10")
    producoes = [
        make_row("producoes", org_id=ORG, captacao_id=captacao_a["id"],
                 etapa="entregue", entregue_em="2026-07-05"),   # 4 dias
        make_row("producoes", org_id=ORG, captacao_id=captacao_b["id"],
                 etapa="entregue", entregue_em="2026-07-18"),   # 8 dias
    ]
    corpo = _dashboard(captacoes=[captacao_a, captacao_b], producoes=producoes)
    assert corpo["prazo_medio_dias"] == 6.0


def test_prazo_medio_descarta_entrega_anterior_a_captacao():
    """Dado incoerente vira ruído negativo na média — melhor ficar de fora."""
    captacao = make_row("captacoes", org_id=ORG, data="2026-07-20")
    producoes = [
        make_row("producoes", org_id=ORG, captacao_id=captacao["id"],
                 etapa="entregue", entregue_em="2026-07-10"),
    ]
    assert _dashboard(captacoes=[captacao], producoes=producoes)["prazo_medio_dias"] is None


def test_prazo_medio_sem_entregas_e_none_e_nao_zero():
    """Zero dia de prazo diria algo falso: o certo é 'ainda não dá para medir'."""
    assert _dashboard()["prazo_medio_dias"] is None


def test_taxa_recorrencia_com_cliente_unico_que_nao_voltou():
    negocios = [make_row("negocios", org_id=ORG, cliente_id="c1")]
    assert _dashboard(negocios=negocios)["taxa_recorrencia"] == 0.0


def test_taxa_recorrencia_ignora_negocios_sem_cliente():
    negocios = [
        make_row("negocios", org_id=ORG, cliente_id="c1"),
        make_row("negocios", org_id=ORG, cliente_id="c1"),
        make_row("negocios", org_id=ORG, cliente_id=None),
    ]
    assert _dashboard(negocios=negocios)["taxa_recorrencia"] == 1.0


def test_funil_devolve_as_nove_etapas_mesmo_vazias():
    funil = _dashboard()["funil"]
    assert len(funil) == 9
    assert all(e["quantidade"] == 0 for e in funil)
    assert funil[0]["etapa"] == "novo_lead"


# ── métricas por cliente ─────────────────────────────────────────────────

def test_frequencia_mensal_mede_ritmo_e_nao_volume():
    """Dez negócios em seis meses ≠ dez negócios em três anos."""
    cliente = make_row("clientes", org_id=ORG, nome="Alfa")
    negocios = [
        make_row("negocios", org_id=ORG, cliente_id=cliente["id"],
                 created_at="2026-04-30")  # ~92 dias antes de HOJE
        for _ in range(3)
    ]
    db = FakeDB({
        "clientes": [cliente], "negocios": negocios,
        "imoveis": [], "lancamentos": [],
    })
    metricas = ClienteMetricasService(db, ORG).metricas(hoje=HOJE)
    assert metricas[0]["frequencia_mensal"] == 0.98  # 3 / (92/30)


def test_frequencia_mensal_nunca_divide_por_menos_de_um_mes():
    """Contrato de ontem não pode virar 'trinta negócios por mês'."""
    cliente = make_row("clientes", org_id=ORG, nome="Alfa")
    negocios = [
        make_row("negocios", org_id=ORG, cliente_id=cliente["id"],
                 created_at="2026-07-30")
    ]
    db = FakeDB({
        "clientes": [cliente], "negocios": negocios,
        "imoveis": [], "lancamentos": [],
    })
    assert ClienteMetricasService(db, ORG).metricas(hoje=HOJE)[0]["frequencia_mensal"] == 1.0


def test_ultimo_servico_e_o_negocio_mais_recente():
    cliente = make_row("clientes", org_id=ORG, nome="Alfa")
    negocios = [
        make_row("negocios", org_id=ORG, cliente_id=cliente["id"], created_at="2026-03-01"),
        make_row("negocios", org_id=ORG, cliente_id=cliente["id"], created_at="2026-06-15"),
    ]
    db = FakeDB({
        "clientes": [cliente], "negocios": negocios,
        "imoveis": [], "lancamentos": [],
    })
    assert ClienteMetricasService(db, ORG).metricas(hoje=HOJE)[0]["ultimo_servico"] == "2026-06-15"
