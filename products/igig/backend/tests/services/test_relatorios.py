"""Relatórios — comercial e financeiro.

`gerar_relatorio` is pure data over `Repositorios`, so these tests build the
funnel/orçamento/fatura state directly through the repositories (the same
SQLite-backed seam `test_financeiro_router.py` uses) and never touch HTTP —
proving the function really is callable without a request in flight.
"""
from datetime import date

import pytest
from noctusai_lib.integrations.persistence import SqliteRecordStore

from app.dependencies import coerce_org_uuid
from app.repositories import Repositorios
from app.services.relatorios import gerar_relatorio, para_csv, para_pdf
from app.store import aplicar_schema_sqlite

ORG = str(coerce_org_uuid("test-org-123"))


@pytest.fixture
def repos() -> Repositorios:
    store = SqliteRecordStore(":memory:")
    aplicar_schema_sqlite(store)
    return Repositorios(store)


def _dt(dia: str) -> str:
    return f"{dia}T12:00:00+00:00"


def _etapa(repos, *, slug, label, posicao=0, papel=None):
    return repos.etapa.criar(ORG, {
        "pipeline": "comercial", "slug": slug, "label": label,
        "posicao": posicao, "papel": papel,
    })


def _lead(repos, nome="Lead"):
    return repos.lead.criar(ORG, {"nome": nome})


def _negocio(repos, lead, etapa, **campos):
    dados = {
        "lead_id": lead["id"],
        "titulo": campos.pop("titulo", "Negócio"),
        "etapa_id": etapa["id"],
        "stage_entered_at": campos.pop("stage_entered_at", _dt("2026-08-01")),
        "status": "aberto",
    }
    dados.update(campos)
    return repos.negocio.criar(ORG, dados)


def _movimento(repos, *, de, para, quando):
    return repos.movimento.criar(ORG, {
        "pipeline": "comercial", "entidade_id": "negocio-x",
        "de_etapa_id": de, "para_etapa_id": para, "created_at": quando,
    })


def _orcamento(repos, negocio, **campos):
    dados = {"titulo": "Proposta", "negocio_id": negocio["id"]}
    dados.update(campos)
    return repos.orcamento.criar(ORG, dados)


INICIO = date(2026, 8, 1)
FIM = date(2026, 8, 31)


class TestGerarRelatorioEntrypoint:
    def test_invalid_tipo_raises_valueerror(self, repos):
        with pytest.raises(ValueError):
            gerar_relatorio(repos, ORG, "invalido", INICIO, FIM)

    def test_inverted_period_raises_valueerror(self, repos):
        with pytest.raises(ValueError):
            gerar_relatorio(repos, ORG, "comercial", FIM, INICIO)

    def test_comercial_and_financeiro_populate_their_own_half(self, repos):
        comercial = gerar_relatorio(repos, ORG, "comercial", INICIO, FIM)
        assert comercial.comercial is not None
        assert comercial.financeiro is None

        financeiro = gerar_relatorio(repos, ORG, "financeiro", INICIO, FIM)
        assert financeiro.financeiro is not None
        assert financeiro.comercial is None


class TestRelatorioComercial:
    def test_funnel_counts_entries_and_exits_in_period(self, repos):
        entrada = _etapa(repos, slug="entrada", label="Entrada", posicao=0)
        proposta = _etapa(repos, slug="proposta", label="Proposta", posicao=1)
        _movimento(repos, de=None, para=entrada["id"], quando=_dt("2026-08-05"))
        _movimento(repos, de=entrada["id"], para=proposta["id"], quando=_dt("2026-08-10"))
        # Fora do período — não deve contar.
        _movimento(repos, de=None, para=entrada["id"], quando=_dt("2026-07-01"))

        relatorio = gerar_relatorio(repos, ORG, "comercial", INICIO, FIM).comercial
        por_id = {e.etapa_id: e for e in relatorio.funil}
        assert por_id[entrada["id"]].entradas == 1
        assert por_id[entrada["id"]].saidas == 1
        assert por_id[entrada["id"]].taxa_conversao == 100.0
        assert por_id[proposta["id"]].entradas == 1
        assert por_id[proposta["id"]].saidas == 0
        assert por_id[proposta["id"]].taxa_conversao == 0.0

    def test_negocio_ganho_uses_accepted_orcamento_value_over_estimate(self, repos):
        fechado = _etapa(repos, slug="fechado", label="Fechado", papel="fechado")
        lead = _lead(repos)
        negocio = _negocio(
            repos, lead, fechado, valor_estimado=1000.0,
            status="ganho", ganho_em=_dt("2026-08-15"),
        )
        orcamento = _orcamento(
            repos, negocio, status="aceito", total_mensal=3500.0, aceito_em=_dt("2026-08-14"),
        )
        repos.negocio.atualizar(ORG, negocio["id"], {"orcamento_aceito_id": orcamento["id"]})

        relatorio = gerar_relatorio(repos, ORG, "comercial", INICIO, FIM).comercial
        assert relatorio.negocios_ganhos == 1
        assert relatorio.negocios_ganhos_valor == 3500.0  # não os 1000 estimados

    def test_negocio_perdido_groups_by_motivo_and_stage_with_dwell_time(self, repos):
        proposta = _etapa(repos, slug="proposta", label="Proposta")
        lead = _lead(repos)
        _negocio(
            repos, lead, proposta, valor_estimado=800.0, status="perdido",
            stage_entered_at=_dt("2026-08-01"), perdido_em=_dt("2026-08-06"),
            motivo_perda="Preço alto", perdido_stage_id=proposta["id"],
        )

        relatorio = gerar_relatorio(repos, ORG, "comercial", INICIO, FIM).comercial
        assert relatorio.negocios_perdidos == 1
        assert relatorio.negocios_perdidos_valor == 800.0
        assert len(relatorio.motivos_perda) == 1
        motivo = relatorio.motivos_perda[0]
        assert motivo.motivo == "Preço alto"
        assert motivo.etapa_label == "Proposta"
        assert motivo.quantidade == 1
        # 5 dias entre stage_entered_at e perdido_em.
        assert relatorio.dwell_time_medio_dias == 5.0

    def test_dwell_time_is_zero_when_nothing_was_lost(self, repos):
        relatorio = gerar_relatorio(repos, ORG, "comercial", INICIO, FIM).comercial
        assert relatorio.dwell_time_medio_dias == 0.0
        assert relatorio.motivos_perda == []

    def test_orcamentos_enviados_aceitos_recusados_and_ticket_medio(self, repos):
        etapa = _etapa(repos, slug="entrada", label="Entrada")
        lead = _lead(repos)
        negocio = _negocio(repos, lead, etapa)
        _orcamento(repos, negocio, versao=1, status="enviado", enviado_em=_dt("2026-08-02"),
                   total_mensal=1000.0)
        _orcamento(repos, negocio, versao=2, status="aceito", enviado_em=_dt("2026-08-03"),
                   aceito_em=_dt("2026-08-05"), total_mensal=2000.0)
        _orcamento(repos, negocio, versao=3, status="recusado", enviado_em=_dt("2026-08-04"),
                   recusado_em=_dt("2026-08-06"), total_mensal=3000.0)

        relatorio = gerar_relatorio(repos, ORG, "comercial", INICIO, FIM).comercial
        assert relatorio.orcamentos_enviados == 3
        assert relatorio.orcamentos_aceitos == 1
        assert relatorio.orcamentos_recusados == 1
        assert relatorio.ticket_medio == 2000.0  # só o aceito entra na média

    def test_ticket_medio_is_zero_when_none_accepted(self, repos):
        relatorio = gerar_relatorio(repos, ORG, "comercial", INICIO, FIM).comercial
        assert relatorio.ticket_medio == 0.0

    def test_events_outside_the_period_are_excluded(self, repos):
        etapa = _etapa(repos, slug="entrada", label="Entrada")
        lead = _lead(repos)
        _negocio(
            repos, lead, etapa, status="ganho", ganho_em=_dt("2026-07-15"), valor_estimado=500.0,
        )
        relatorio = gerar_relatorio(repos, ORG, "comercial", INICIO, FIM).comercial
        assert relatorio.negocios_ganhos == 0


class TestRelatorioFinanceiro:
    def test_faturamento_is_scoped_to_period_by_competencia(self, repos):
        cliente = repos.cliente.criar(ORG, {"nome": "Padaria Sol"})
        repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-07",
            "valor_total": 1000.0, "status": "paga",
        })
        repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-08",
            "valor_total": 2000.0, "status": "enviada",
        })
        repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-08",
            "valor_total": 999.0, "status": "cancelada",
        })

        relatorio = gerar_relatorio(repos, ORG, "financeiro", INICIO, FIM).financeiro
        assert relatorio.faturamento == 2000.0
        assert relatorio.a_receber == 2000.0
        assert relatorio.recebido == 0.0

    def test_per_cliente_breakdown(self, repos):
        c1 = repos.cliente.criar(ORG, {"nome": "Cliente A"})
        c2 = repos.cliente.criar(ORG, {"nome": "Cliente B"})
        repos.fatura.criar(ORG, {
            "cliente_id": c1["id"], "competencia": "2026-08",
            "valor_total": 500.0, "status": "paga",
        })
        repos.fatura.criar(ORG, {
            "cliente_id": c2["id"], "competencia": "2026-08",
            "valor_total": 300.0, "status": "enviada",
        })

        relatorio = gerar_relatorio(repos, ORG, "financeiro", INICIO, FIM).financeiro
        por_nome = {c.cliente_nome: c for c in relatorio.clientes}
        assert por_nome["Cliente A"].recebido == 500.0
        assert por_nome["Cliente B"].a_receber == 300.0

    def test_inadimplencia_is_counted(self, repos):
        cliente = repos.cliente.criar(ORG, {"nome": "Cliente C"})
        repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-08",
            "valor_total": 700.0, "vencimento": "2020-01-01", "status": "enviada",
        })
        relatorio = gerar_relatorio(repos, ORG, "financeiro", INICIO, FIM).financeiro
        assert relatorio.inadimplencia_qtd == 1
        assert relatorio.inadimplencia_valor == 700.0

    def test_no_revenue_is_not_a_division_error(self, repos):
        repos.cliente.criar(ORG, {"nome": "Cliente sem fatura"})
        relatorio = gerar_relatorio(repos, ORG, "financeiro", INICIO, FIM).financeiro
        assert relatorio.clientes[0].margem_percentual == 0.0

    def test_alerta_present_when_cost_is_measured(self, repos):
        cliente = repos.cliente.criar(ORG, {"nome": "Cliente D"})
        funcao = repos.funcao.criar(ORG, {"nome": "designer", "custo_hora_padrao": 100.0})
        repos.profissional.criar(ORG, {"nome": "Ana", "usuario_id": "u1", "funcao_id": funcao["id"]})
        pauta = repos.pauta.criar(ORG, {"cliente_id": cliente["id"], "titulo": "Post"})
        tarefa = repos.tarefa.criar(ORG, {"pauta_id": pauta["id"], "titulo": "Arte", "etapa_id": "e1"})
        repos.apontamento.criar(ORG, {
            "tarefa_id": tarefa["id"], "usuario_id": "u1",
            "iniciado_em": "2026-08-01T09:00:00", "minutos": 60,
        })

        relatorio = gerar_relatorio(repos, ORG, "financeiro", INICIO, FIM).financeiro
        cliente_dre = next(c for c in relatorio.clientes if c.cliente_id == cliente["id"])
        assert cliente_dre.custo == 100.0
        assert relatorio.alertas


class TestRenderers:
    def test_csv_is_non_empty_for_comercial_and_financeiro(self, repos):
        for tipo in ("comercial", "financeiro"):
            relatorio = gerar_relatorio(repos, ORG, tipo, INICIO, FIM)
            conteudo = para_csv(relatorio)
            assert isinstance(conteudo, bytes)
            assert len(conteudo) > 0
            assert tipo in conteudo.decode("utf-8-sig")

    def test_pdf_is_non_empty_and_a_real_pdf(self, repos):
        for tipo in ("comercial", "financeiro"):
            relatorio = gerar_relatorio(repos, ORG, tipo, INICIO, FIM)
            conteudo = para_pdf(relatorio)
            assert isinstance(conteudo, bytes)
            assert len(conteudo) > 500
            assert conteudo[:5] == b"%PDF-"
