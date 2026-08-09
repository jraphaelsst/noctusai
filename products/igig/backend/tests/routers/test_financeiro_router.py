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
from app.services.financeiro_service import proxima_competencia
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
        tarefa = repos.tarefa.criar(ORG, {"pauta_id": pauta["id"], "titulo": "Arte"})
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
        tarefa = repos.tarefa.criar(ORG, {"pauta_id": pauta["id"], "titulo": "Arte"})
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
