"""Rotas de /api/dashboard, /api/clientes-metricas e /api/me.

Os nove indicadores da spec § 1 eram literais num arquivo TypeScript no
protótipo. Aqui eles saem dos dados — então cada um ganha um teste que fixa
a regra de contagem, não só o formato.
"""
from datetime import date, timedelta

from tests.conftest import USER_ID, dias, make_row, seed_basico

HOJE = date.today()
INICIO_MES = HOJE.replace(day=1).isoformat()


def _neste_mes(dia_offset: int = 0) -> str:
    """Data dentro do mês corrente, segura contra virada de mês."""
    return (HOJE.replace(day=1) + timedelta(days=dia_offset)).isoformat()


# ── /api/me ──────────────────────────────────────────────────────────────

def test_me_devolve_o_usuario_logado(client):
    corpo = client.get("/api/me").json()
    assert corpo["id"] == USER_ID
    assert corpo["email"] == "equipe@pstudio.app"
    assert corpo["nome"] == "Equipe"
    assert corpo["org_id"]


# ── /api/dashboard ───────────────────────────────────────────────────────

def test_dashboard_vazio_devolve_zeros_e_series_completas(client):
    corpo = client.get("/api/dashboard").json()
    assert corpo["captacoes_mes"] == 0
    assert corpo["faturamento_mes"] == 0
    assert corpo["ticket_medio"] == 0
    assert corpo["prazo_medio_dias"] is None
    assert corpo["taxa_recorrencia"] == 0
    assert len(corpo["receita_por_mes"]) == 6
    assert [s["semana"] for s in corpo["captacoes_por_semana"]] == ["S1", "S2", "S3", "S4"]
    assert len(corpo["funil"]) == 9


def test_captacoes_mes_ignora_canceladas(client, fake_db):
    seed = seed_basico(fake_db)
    cid = seed["cliente"]["id"]
    fake_db.data["captacoes"] = [
        make_row("captacoes", cliente_id=cid, data=_neste_mes(), status="agendado"),
        make_row("captacoes", cliente_id=cid, data=_neste_mes(1), status="concluido"),
        make_row("captacoes", cliente_id=cid, data=_neste_mes(2), status="cancelado"),
    ]
    assert client.get("/api/dashboard").json()["captacoes_mes"] == 2


def test_servicos_andamento_conta_so_o_miolo_do_pipeline(client, fake_db):
    """Agendado ainda não começou; entregue e arquivado já saíram."""
    seed = seed_basico(fake_db)
    cid = seed["cliente"]["id"]
    fake_db.data["producoes"] = [
        make_row("producoes", cliente_id=cid, etapa="agendado"),
        make_row("producoes", cliente_id=cid, etapa="edicao"),
        make_row("producoes", cliente_id=cid, etapa="revisao"),
        make_row("producoes", cliente_id=cid, etapa="entregue"),
        make_row("producoes", cliente_id=cid, etapa="arquivado"),
    ]
    assert client.get("/api/dashboard").json()["servicos_andamento"] == 2


def test_ticket_medio_so_considera_negocios_ganhos(client, fake_db):
    """Leads e orçamentos perdidos puxariam o número para baixo."""
    seed = seed_basico(fake_db)
    cid = seed["cliente"]["id"]
    fake_db.data["negocios"] = [
        make_row("negocios", cliente_id=cid, etapa="novo_lead", valor=10),
        make_row("negocios", cliente_id=cid, etapa="orcamento", valor=10),
        make_row("negocios", cliente_id=cid, etapa="aprovado", valor=1000),
        make_row("negocios", cliente_id=cid, etapa="recebido", valor=2000),
    ]
    assert client.get("/api/dashboard").json()["ticket_medio"] == 1500


def test_a_receber_soma_aberto_e_atrasado_mas_nao_recebido(client, fake_db):
    seed = seed_basico(fake_db)
    cid = seed["cliente"]["id"]
    fake_db.data["lancamentos"] = [
        make_row("lancamentos", cliente_id=cid, status="a_faturar", valor=100),
        make_row("lancamentos", cliente_id=cid, status="faturado",
                 vencimento=dias(10), valor=200),
        make_row("lancamentos", cliente_id=cid, status="faturado",
                 vencimento=dias(-10), valor=300),
        make_row("lancamentos", cliente_id=cid, status="recebido",
                 pago_em=dias(-1), valor=9999),
    ]
    assert client.get("/api/dashboard").json()["a_receber"] == 600


def test_faturamento_mes_conta_so_o_pago_dentro_do_mes(client, fake_db):
    seed = seed_basico(fake_db)
    cid = seed["cliente"]["id"]
    fake_db.data["lancamentos"] = [
        make_row("lancamentos", cliente_id=cid, status="recebido",
                 pago_em=_neste_mes(), valor=700),
        make_row("lancamentos", cliente_id=cid, status="recebido",
                 pago_em="2020-01-15", valor=9999),
    ]
    assert client.get("/api/dashboard").json()["faturamento_mes"] == 700


def test_entregas_mes_usa_a_data_de_entrega(client, fake_db):
    seed = seed_basico(fake_db)
    cid = seed["cliente"]["id"]
    fake_db.data["producoes"] = [
        make_row("producoes", cliente_id=cid, etapa="entregue", entregue_em=_neste_mes()),
        make_row("producoes", cliente_id=cid, etapa="entregue", entregue_em="2020-03-02"),
        make_row("producoes", cliente_id=cid, etapa="edicao", entregue_em=None),
    ]
    assert client.get("/api/dashboard").json()["entregas_mes"] == 1


def test_prazo_medio_exige_as_duas_pontas(client, fake_db):
    """Produção entregue sem captação vinculada não tem marco inicial."""
    seed = seed_basico(fake_db)
    cid = seed["cliente"]["id"]
    captacao = make_row("captacoes", cliente_id=cid, data=dias(-10))
    fake_db.data["captacoes"] = [captacao]
    fake_db.data["producoes"] = [
        make_row("producoes", cliente_id=cid, captacao_id=captacao["id"],
                 etapa="entregue", entregue_em=dias(-4)),
        make_row("producoes", cliente_id=cid, captacao_id=None,
                 etapa="entregue", entregue_em=dias(-1)),
    ]
    assert client.get("/api/dashboard").json()["prazo_medio_dias"] == 6.0


def test_taxa_recorrencia_e_fracao_de_clientes_que_voltaram(client, fake_db):
    seed = seed_basico(fake_db)
    outro = make_row("clientes", nome="Imobiliária Beta")
    fake_db.data["clientes"].append(outro)
    cid = seed["cliente"]["id"]
    fake_db.data["negocios"] = [
        make_row("negocios", cliente_id=cid),
        make_row("negocios", cliente_id=cid),
        make_row("negocios", cliente_id=outro["id"]),
    ]
    # 1 de 2 clientes contratou mais de uma vez
    assert client.get("/api/dashboard").json()["taxa_recorrencia"] == 0.5


def test_funil_agrega_quantidade_e_valor_por_etapa(client, fake_db):
    seed = seed_basico(fake_db)
    cid = seed["cliente"]["id"]
    fake_db.data["negocios"] = [
        make_row("negocios", cliente_id=cid, etapa="orcamento", valor=100),
        make_row("negocios", cliente_id=cid, etapa="orcamento", valor=250),
        make_row("negocios", cliente_id=cid, etapa="entregue", valor=900),
    ]

    funil = {e["etapa"]: e for e in client.get("/api/dashboard").json()["funil"]}
    assert funil["orcamento"]["quantidade"] == 2
    assert funil["orcamento"]["valor"] == 350
    assert funil["entregue"]["quantidade"] == 1
    assert funil["novo_lead"]["quantidade"] == 0


def test_receita_por_mes_termina_no_mes_corrente(client):
    serie = client.get("/api/dashboard").json()["receita_por_mes"]
    assert serie[-1]["mes"] == f"{HOJE.year:04d}-{HOJE.month:02d}"
    assert all("label" in ponto for ponto in serie)


# ── /api/clientes-metricas ───────────────────────────────────────────────

def test_metricas_vazias_sem_clientes(client):
    assert client.get("/api/clientes-metricas").json() == []


def test_metricas_consolidam_faturamento_servicos_e_imoveis(client, fake_db):
    seed = seed_basico(fake_db)
    cid = seed["cliente"]["id"]
    fake_db.data["negocios"] = [
        make_row("negocios", cliente_id=cid, valor=1000),
        make_row("negocios", cliente_id=cid, valor=500),
    ]
    fake_db.data["lancamentos"] = [
        make_row("lancamentos", cliente_id=cid, status="recebido",
                 pago_em=dias(-1), valor=1200),
        make_row("lancamentos", cliente_id=cid, status="a_faturar", valor=9999),
    ]

    corpo = client.get("/api/clientes-metricas").json()
    assert len(corpo) == 1
    assert corpo[0]["nome"] == "Imobiliária Alfa"
    assert corpo[0]["faturamento_total"] == 1200  # só o recebido
    assert corpo[0]["total_servicos"] == 2
    assert corpo[0]["total_imoveis"] == 1
    assert corpo[0]["ticket_medio"] == 600


def test_metricas_incluem_clientes_inativos(client, fake_db):
    """A tela de histórico precisa mostrar quem parou de comprar."""
    seed_basico(fake_db)
    fake_db.data["clientes"].append(
        make_row("clientes", nome="Imobiliária Dormente", ativo=False)
    )
    nomes = [c["nome"] for c in client.get("/api/clientes-metricas").json()]
    assert "Imobiliária Dormente" in nomes


def test_metricas_sem_negocios_zeram_sem_dividir_por_zero(client, fake_db):
    seed_basico(fake_db)
    corpo = client.get("/api/clientes-metricas").json()
    assert corpo[0]["ticket_medio"] == 0
    assert corpo[0]["ultimo_servico"] is None
    assert corpo[0]["frequencia_mensal"] == 0
