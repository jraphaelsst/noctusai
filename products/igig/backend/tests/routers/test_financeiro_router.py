"""Financeiro, excedentes e DRE — Módulo 6.

These are billing numbers, so the arithmetic is checked against hand-computed
values, and the edge cases that would quietly cost money — under-delivery
treated as a credit, a re-run double-billing, a total that disagrees with its
own lines — are each asserted.
"""
import pytest
from noctusai_lib.integrations.persistence import SqliteRecordStore

from app.dependencies import coerce_org_uuid
from app.repositories import Repositorios
from app.services.financeiro_service import limites_da_competencia, proxima_competencia
from app.store import aplicar_schema_sqlite, get_repositorios, get_repositorios_admin

ORG = str(coerce_org_uuid("test-org-123"))


@pytest.fixture
def repos() -> Repositorios:
    store = SqliteRecordStore(":memory:")
    aplicar_schema_sqlite(store)
    return Repositorios(store)


@pytest.fixture
def api(client, repos):
    from app.main import app

    app.dependency_overrides[get_repositorios] = lambda: repos
    app.dependency_overrides[get_repositorios_admin] = lambda: repos
    yield client
    app.dependency_overrides.pop(get_repositorios, None)
    app.dependency_overrides.pop(get_repositorios_admin, None)


@pytest.fixture
def cliente(repos) -> dict:
    return repos.cliente.criar(ORG, {"nome": "Padaria Sol"})


def _contrato(repos, cliente, *, pacote=12, excedente=150.0):
    return repos.contrato.criar(ORG, {
        "cliente_id": cliente["id"], "status": "ativo",
        "valor_mensal": 5000.0, "posts_por_mes": pacote, "valor_excedente": excedente,
    })


def _pautas(repos, cliente, quantidade, mes="2026-08"):
    for i in range(quantidade):
        repos.pauta.criar(ORG, {
            "cliente_id": cliente["id"], "titulo": f"Post {i}",
            "data_publicacao": f"{mes}-{(i % 28) + 1:02d}T09:00:00",
        })


class TestCompetencia:
    def test_rolls_the_month(self):
        assert proxima_competencia("2026-08") == "2026-09"

    def test_rolls_the_year_in_december(self):
        assert proxima_competencia("2026-12") == "2027-01"

    @pytest.mark.parametrize(
        ("competencia", "ultimo"),
        [("2026-02", "2026-02-28"), ("2028-02", "2028-02-29"),
         ("2026-04", "2026-04-30"), ("2026-12", "2026-12-31")],
    )
    def test_month_bounds_come_from_the_calendar(self, competencia, ultimo):
        """Smoke finding 1: a literal `-31` is not a timestamp Postgres accepts
        in a short month — the SQLite suite compares TEXT and never saw it."""
        inicio, fim = limites_da_competencia(competencia)
        assert inicio == f"{competencia}-01T00:00:00"
        assert fim == f"{ultimo}T23:59:59.999999"
        # Every bound must parse as a real instant — the property Postgres enforces.
        from datetime import datetime

        datetime.fromisoformat(inicio)
        datetime.fromisoformat(fim)

    @pytest.mark.parametrize("ruim", ["2026-13", "2026-00", "26-02", "2026-2", "abc"])
    def test_malformed_competencia_is_a_valueerror(self, ruim):
        with pytest.raises(ValueError):
            limites_da_competencia(ruim)


class TestFaturas:
    def test_requires_auth(self, api):
        assert api.raw().get("/api/financeiro/faturas").status_code == 401

    def test_create_returns_201(self, api, cliente):
        resp = api.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
        })
        assert resp.status_code == 201
        assert resp.json()["status"] == "aberta"

    def test_malformed_competencia_returns_422(self, api, cliente):
        resp = api.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "agosto",
        })
        assert resp.status_code == 422

    def test_duplicate_for_a_contract_month_returns_409(self, api, repos, cliente):
        """Re-running the monthly close must be idempotent, not double-billing."""
        contrato = _contrato(repos, cliente)
        corpo = {
            "cliente_id": cliente["id"], "contrato_id": contrato["id"],
            "competencia": "2026-08",
        }
        assert api.post("/api/financeiro/faturas", json=corpo).status_code == 201
        assert api.post("/api/financeiro/faturas", json=corpo).status_code == 409

    def test_total_is_derived_from_the_lines(self, api, cliente):
        """A header that disagrees with its own lines is what a client spots first."""
        fatura = api.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
        }).json()
        api.post(f"/api/financeiro/faturas/{fatura['id']}/itens", json={
            "descricao": "Mensalidade", "valor_unit": 5000.0,
        })
        resp = api.post(f"/api/financeiro/faturas/{fatura['id']}/itens", json={
            "descricao": "Excedentes", "tipo": "excedente",
            "quantidade": 3, "valor_unit": 150.0,
        })
        assert resp.status_code == 201
        assert resp.json()["valor_total"] == 5450.0  # 5000 + 3×150

    def test_a_paid_invoice_refuses_new_items(self, api, cliente):
        fatura = api.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
        }).json()
        api.post(f"/api/financeiro/faturas/{fatura['id']}/pagar")
        resp = api.post(f"/api/financeiro/faturas/{fatura['id']}/itens", json={
            "descricao": "Tarde demais", "valor_unit": 100.0,
        })
        assert resp.status_code == 409
        assert resp.json()["code"] == "fatura_fechada"

    def test_a_cancelled_invoice_refuses_new_items(self, api, repos, cliente):
        fatura = repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-08", "status": "cancelada",
        })
        resp = api.post(f"/api/financeiro/faturas/{fatura['id']}/itens", json={
            "descricao": "Não deveria entrar", "valor_unit": 100.0,
        })
        assert resp.status_code == 409
        assert resp.json()["code"] == "fatura_fechada"

    def test_mark_paid(self, api, cliente):
        fatura = api.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
        }).json()
        resp = api.post(f"/api/financeiro/faturas/{fatura['id']}/pagar")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paga"
        assert resp.json()["pago_em"]

    def test_faturas_are_org_scoped(self, api, repos, cliente):
        repos.fatura.criar("outra-org", {"cliente_id": cliente["id"], "competencia": "2026-08"})
        assert api.get("/api/financeiro/faturas").json() == []


class TestExcedentes:
    def test_over_delivery_is_charged(self, api, repos, cliente):
        _contrato(repos, cliente, pacote=12, excedente=150.0)
        _pautas(repos, cliente, 15)
        linha = api.get("/api/financeiro/excedentes/2026-08").json()[0]
        assert linha["contratados"] == 12
        assert linha["entregues"] == 15
        assert linha["excedentes"] == 3
        assert linha["valor_total"] == 450.0  # 3 × 150

    def test_under_delivery_is_never_a_credit(self, api, repos, cliente):
        """Delivering under the package must not discount the retainer."""
        _contrato(repos, cliente, pacote=12)
        _pautas(repos, cliente, 8)
        linha = api.get("/api/financeiro/excedentes/2026-08").json()[0]
        assert linha["excedentes"] == 0
        assert linha["valor_total"] == 0.0

    def test_charge_lands_on_the_following_month(self, api, repos, cliente):
        """Per the spec: 'na fatura do mês subsequente'."""
        _contrato(repos, cliente)
        _pautas(repos, cliente, 15)
        linha = api.get("/api/financeiro/excedentes/2026-08").json()[0]
        assert linha["competencia"] == "2026-08"
        assert linha["competencia_cobranca"] == "2026-09"

    def test_other_months_are_not_counted(self, api, repos, cliente):
        _contrato(repos, cliente, pacote=1)
        _pautas(repos, cliente, 5, mes="2026-07")
        linha = api.get("/api/financeiro/excedentes/2026-08").json()[0]
        assert linha["entregues"] == 0

    def test_contract_without_a_package_is_skipped(self, api, repos, cliente):
        _contrato(repos, cliente, pacote=0)
        _pautas(repos, cliente, 5)
        assert api.get("/api/financeiro/excedentes/2026-08").json() == []

    def test_short_month_is_counted_to_its_real_last_day(self, api, repos, cliente):
        _contrato(repos, cliente, pacote=1)
        _pautas(repos, cliente, 2, mes="2026-02")
        linha = api.get("/api/financeiro/excedentes/2026-02").json()[0]
        assert linha["entregues"] == 2

    def test_malformed_competencia_is_422_not_500(self, api, cliente):
        assert api.get("/api/financeiro/excedentes/2026-13").status_code == 422

    def test_inactive_contracts_are_skipped(self, api, repos, cliente):
        repos.contrato.criar(ORG, {
            "cliente_id": cliente["id"], "status": "encerrado", "posts_por_mes": 5,
        })
        _pautas(repos, cliente, 10)
        assert api.get("/api/financeiro/excedentes/2026-08").json() == []


class TestDRE:
    def _com_custo(self, repos, cliente, *, custo_hora=100.0, minutos=600):
        funcao = repos.funcao.criar(ORG, {"nome": "designer", "custo_hora_padrao": custo_hora})
        repos.profissional.criar(
            ORG, {"nome": "Ana", "usuario_id": "user-1", "funcao_id": funcao["id"]}
        )
        pauta = repos.pauta.criar(ORG, {"cliente_id": cliente["id"], "titulo": "Post"})
        tarefa = repos.tarefa.criar(ORG, {"pauta_id": pauta["id"], "titulo": "Arte", "etapa_id": "etapa-1"})
        repos.apontamento.criar(ORG, {
            "tarefa_id": tarefa["id"], "usuario_id": "user-1",
            "iniciado_em": "2026-08-01T09:00:00", "minutos": minutos,
        })

    def test_margin_is_revenue_minus_measured_cost(self, api, repos, cliente):
        self._com_custo(repos, cliente, custo_hora=100.0, minutos=600)  # 10 h ⇒ R$1000
        fatura = api.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
        }).json()
        api.post(f"/api/financeiro/faturas/{fatura['id']}/itens",
                 json={"descricao": "Mensalidade", "valor_unit": 5000.0})

        linha = api.get("/api/financeiro/dre").json()[0]
        assert linha["receita"] == 5000.0
        assert linha["custo"] == 1000.0
        assert linha["margem"] == 4000.0
        assert linha["margem_percentual"] == 80.0

    def test_cancelled_invoices_are_excluded(self, api, repos, cliente):
        repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-08",
            "valor_total": 9999.0, "status": "cancelada",
        })
        assert api.get("/api/financeiro/dre").json()[0]["receita"] == 0.0

    def test_no_revenue_is_not_a_division_error(self, api, repos, cliente):
        self._com_custo(repos, cliente)
        linha = api.get("/api/financeiro/dre").json()[0]
        assert linha["receita"] == 0.0
        assert linha["margem_percentual"] == 0.0

    def test_uncosted_hours_warn_that_margin_is_overstated(self, api, repos, cliente):
        """The mirror image of the BI screen's warning."""
        pauta = repos.pauta.criar(ORG, {"cliente_id": cliente["id"], "titulo": "Post"})
        tarefa = repos.tarefa.criar(ORG, {"pauta_id": pauta["id"], "titulo": "Arte", "etapa_id": "etapa-1"})
        repos.apontamento.criar(ORG, {
            "tarefa_id": tarefa["id"], "usuario_id": "sem-rate",
            "iniciado_em": "2026-08-01T09:00:00", "minutos": 300,
        })
        repos.profissional.criar(ORG, {"nome": "Ana", "usuario_id": "sem-rate"})
        linha = api.get("/api/financeiro/dre").json()[0]
        assert linha["alertas"]
        assert "SUPERESTIMADA" in linha["alertas"][0]

    def test_competencia_filters_revenue(self, api, repos, cliente):
        for comp, valor in (("2026-07", 1000.0), ("2026-08", 5000.0)):
            repos.fatura.criar(ORG, {
                "cliente_id": cliente["id"], "competencia": comp, "valor_total": valor,
            })
        assert api.get("/api/financeiro/dre?competencia=2026-08").json()[0]["receita"] == 5000.0


class TestGerarCompetencia:
    def test_requires_auth(self, api):
        resp = api.raw().post(
            "/api/financeiro/faturas/gerar-competencia", json={"competencia": "2026-08"}
        )
        assert resp.status_code == 401

    def test_malformed_competencia_returns_422(self, api):
        resp = api.post("/api/financeiro/faturas/gerar-competencia",
                         json={"competencia": "agosto"})
        assert resp.status_code == 422

    def test_creates_one_invoice_per_active_contract(self, api, repos, cliente):
        contrato = _contrato(repos, cliente, pacote=12, excedente=150.0)
        resp = api.post("/api/financeiro/faturas/gerar-competencia",
                         json={"competencia": "2026-08"})
        assert resp.status_code == 200
        corpo = resp.json()
        assert len(corpo["criadas"]) == 1
        assert corpo["existentes"] == []
        fatura = corpo["criadas"][0]
        assert fatura["contrato_id"] == contrato["id"]
        assert fatura["valor_total"] == 5000.0  # só o retainer — sem excedentes ainda

        itens = repos.fatura_item.da_fatura(ORG, fatura["id"])
        assert [i["descricao"] for i in itens] == ["Retainer mensal"]

    def test_inactive_contracts_are_skipped(self, api, repos, cliente):
        repos.contrato.criar(ORG, {
            "cliente_id": cliente["id"], "status": "encerrado", "valor_mensal": 999.0,
        })
        resp = api.post("/api/financeiro/faturas/gerar-competencia",
                         json={"competencia": "2026-08"})
        assert resp.json() == {"criadas": [], "existentes": []}

    def test_rerunning_is_idempotent(self, api, repos, cliente):
        """The point of the endpoint: closing the month twice must not
        double-bill a single active contract."""
        _contrato(repos, cliente)
        primeira = api.post("/api/financeiro/faturas/gerar-competencia",
                             json={"competencia": "2026-08"}).json()
        segunda = api.post("/api/financeiro/faturas/gerar-competencia",
                            json={"competencia": "2026-08"}).json()
        assert len(primeira["criadas"]) == 1
        assert segunda["criadas"] == []
        assert len(segunda["existentes"]) == 1
        assert segunda["existentes"][0]["id"] == primeira["criadas"][0]["id"]
        assert len(repos.fatura.da_competencia(ORG, "2026-08")) == 1

    def test_includes_excedentes_billed_to_this_competencia(self, api, repos, cliente):
        """Delivered in July, package of 12, 15 delivered ⇒ 3 excedentes ×
        R$150 — billed on AUGUST's invoice, per the spec ('mês subsequente')."""
        _contrato(repos, cliente, pacote=12, excedente=150.0)
        _pautas(repos, cliente, 15, mes="2026-07")

        resp = api.post("/api/financeiro/faturas/gerar-competencia",
                         json={"competencia": "2026-08"})
        fatura = resp.json()["criadas"][0]
        assert fatura["valor_total"] == 5450.0  # 5000 retainer + 3×150

        itens = repos.fatura_item.da_fatura(ORG, fatura["id"])
        excedente = next(i for i in itens if i["tipo"] == "excedente")
        assert excedente["quantidade"] == 3
        assert excedente["valor_unit"] == 150.0

    def test_no_excedente_line_when_delivery_is_within_package(self, api, repos, cliente):
        _contrato(repos, cliente, pacote=12, excedente=150.0)
        _pautas(repos, cliente, 8, mes="2026-07")

        resp = api.post("/api/financeiro/faturas/gerar-competencia",
                         json={"competencia": "2026-08"})
        fatura = resp.json()["criadas"][0]
        assert fatura["valor_total"] == 5000.0
        itens = repos.fatura_item.da_fatura(ORG, fatura["id"])
        assert all(i["tipo"] != "excedente" for i in itens)

    def test_vencimento_derived_from_contract_day(self, api, repos, cliente):
        contrato = repos.contrato.criar(ORG, {
            "cliente_id": cliente["id"], "status": "ativo",
            "valor_mensal": 1000.0, "dia_vencimento": 31,  # Feb has no 31st
        })
        resp = api.post("/api/financeiro/faturas/gerar-competencia",
                         json={"competencia": "2026-02"})
        fatura = resp.json()["criadas"][0]
        assert fatura["contrato_id"] == contrato["id"]
        assert fatura["vencimento"] == "2026-02-28"

    def test_a_cancelled_invoice_does_not_block_a_new_one(self, api, repos, cliente):
        contrato = _contrato(repos, cliente)
        repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "contrato_id": contrato["id"],
            "competencia": "2026-08", "status": "cancelada", "valor_total": 999.0,
        })
        resp = api.post("/api/financeiro/faturas/gerar-competencia",
                         json={"competencia": "2026-08"})
        assert len(resp.json()["criadas"]) == 1


class TestResumo:
    def test_requires_auth(self, api):
        assert api.raw().get("/api/financeiro/resumo").status_code == 401

    def test_malformed_competencia_returns_422(self, api):
        assert api.get("/api/financeiro/resumo?competencia=agosto").status_code == 422

    def test_mrr_is_the_sum_of_active_contracts(self, api, repos, cliente):
        _contrato(repos, cliente)  # valor_mensal 5000, ativo
        repos.contrato.criar(ORG, {
            "cliente_id": cliente["id"], "status": "encerrado", "valor_mensal": 999.0,
        })
        resumo = api.get("/api/financeiro/resumo").json()
        assert resumo["mrr"] == 5000.0

    def test_a_receber_and_recebido_split_by_status(self, api, repos, cliente):
        repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-08",
            "valor_total": 3000.0, "status": "paga",
        })
        repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-08",
            "valor_total": 2000.0, "status": "enviada",
        })
        repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-08",
            "valor_total": 999.0, "status": "cancelada",
        })
        resumo = api.get("/api/financeiro/resumo?competencia=2026-08").json()
        assert resumo["recebido"] == 3000.0
        assert resumo["a_receber"] == 2000.0

    def test_competencia_scopes_a_receber_and_recebido(self, api, repos, cliente):
        repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-07",
            "valor_total": 1000.0, "status": "paga",
        })
        repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-08",
            "valor_total": 2000.0, "status": "paga",
        })
        resumo = api.get("/api/financeiro/resumo?competencia=2026-08").json()
        assert resumo["recebido"] == 2000.0

    def test_inadimplente_counts_overdue_invoices(self, api, repos, cliente):
        repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-07",
            "valor_total": 500.0, "vencimento": "2020-01-01", "status": "enviada",
        })
        resumo = api.get("/api/financeiro/resumo").json()
        assert resumo["inadimplente_qtd"] == 1
        assert resumo["inadimplente_valor"] == 500.0


class TestInadimplentes:
    def test_overdue_invoice_is_listed_with_days_late(self, api, repos, cliente):
        repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-07",
            "valor_total": 5000.0, "vencimento": "2026-07-10", "status": "enviada",
        })
        linha = api.get("/api/financeiro/inadimplentes?hoje=2026-07-25").json()[0]
        assert linha["dias_atraso"] == 15

    def test_paid_invoices_are_excluded(self, api, repos, cliente):
        repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-07",
            "valor_total": 5000.0, "vencimento": "2026-07-10", "status": "paga",
        })
        assert api.get("/api/financeiro/inadimplentes?hoje=2026-07-25").json() == []

    def test_not_yet_due_is_excluded(self, api, repos, cliente):
        repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-08",
            "valor_total": 5000.0, "vencimento": "2026-08-30", "status": "enviada",
        })
        assert api.get("/api/financeiro/inadimplentes?hoje=2026-08-01").json() == []

    def test_worst_first(self, api, repos, cliente):
        for venc in ("2026-07-01", "2026-07-20"):
            repos.fatura.criar(ORG, {
                "cliente_id": cliente["id"], "competencia": "2026-07",
                "valor_total": 100.0, "vencimento": venc, "status": "enviada",
            })
        atrasos = [f["dias_atraso"] for f in
                   api.get("/api/financeiro/inadimplentes?hoje=2026-07-25").json()]
        assert atrasos == sorted(atrasos, reverse=True)
