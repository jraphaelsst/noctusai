"""Financeiro, excedentes e DRE — Módulo 6.

These are billing numbers, so the arithmetic is checked against hand-computed
values, and the edge cases that would quietly cost money — under-delivery
treated as a credit, a re-run double-billing, a total that disagrees with its
own lines — are each asserted.
"""
import pytest
from noctusai_lib.integrations.persistence import ForeignKeyViolation, SqliteRecordStore, UniqueViolation

from app.dependencies import coerce_org_uuid
from app.email_deps import get_email_sender_factory, get_email_settings
from app.repositories import Repositorios
from app.services import email_config
from app.services.financeiro_service import limites_da_competencia, proxima_competencia
from app.store import aplicar_schema_sqlite, get_repositorios, get_repositorios_admin
from tests.email_support import SEM_GCP, SMTP, Senders

ORG = str(coerce_org_uuid("test-org-123"))


@pytest.fixture
def repos() -> Repositorios:
    store = SqliteRecordStore(":memory:")
    aplicar_schema_sqlite(store)
    return Repositorios(store)


@pytest.fixture
def api(client, repos):
    """`marcar_paga`/`cancelar`/`gerar-competencia` are admin-only
    (`exigir_admin_da_org`); every test EXCEPT the permission tests below
    exercises the actual business logic under an admin bypass, matching the
    same pattern `test_automacao_router.py`'s `admin` fixture uses."""
    from app.main import app
    from app.pipelines import exigir_admin_da_org

    app.dependency_overrides[get_repositorios] = lambda: repos
    app.dependency_overrides[get_repositorios_admin] = lambda: repos
    app.dependency_overrides[exigir_admin_da_org] = lambda: None
    yield client
    app.dependency_overrides.pop(get_repositorios, None)
    app.dependency_overrides.pop(get_repositorios_admin, None)
    app.dependency_overrides.pop(exigir_admin_da_org, None)


@pytest.fixture
def cliente(repos) -> dict:
    return repos.cliente.criar(ORG, {"nome": "Padaria Sol"})


def _contrato(repos, cliente, *, pacote=12, excedente=150.0):
    return repos.contrato.criar(ORG, {
        "cliente_id": cliente["id"], "status": "ativo",
        "valor_mensal": 5000.0, "posts_por_mes": pacote, "valor_excedente": excedente,
    })


def _pautas(repos, cliente, quantidade, mes="2026-08"):
    """`quantidade` EXTRA (hand-added, non-plan) pautas DELIVERED in `mes` —
    `publicado_em` is the delivery signal `FinanceiroService.excedentes` now
    reads (achado 10 follow-up); `data_publicacao` stays too, since it is
    what the Calendário Editorial itself scheduled them against."""
    for i in range(quantidade):
        quando = f"{mes}-{(i % 28) + 1:02d}T09:00:00"
        repos.pauta.criar(ORG, {
            "cliente_id": cliente["id"], "titulo": f"Post {i}",
            "data_publicacao": quando, "publicado_em": quando,
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

    def test_a_non_unique_constraint_failure_is_not_mislabelled_as_duplicate(
        self, api, repos, cliente, monkeypatch
    ):
        """finding #7's root cause: catching the wide `PersistenceError`
        could not tell a genuine unique-index race from any OTHER write
        failure, so it silently relabelled both as "duplicate invoice".
        Catching the specific `UniqueViolation` member fixes it — a
        `ForeignKeyViolation` from the same call must propagate as a real
        error, never get reinterpreted as the 409 "já existe fatura"."""
        def _criar_com_fk_violation(org_id, valores):
            raise ForeignKeyViolation("simulated dangling reference")

        monkeypatch.setattr(repos.fatura, "criar", _criar_com_fk_violation)
        with pytest.raises(ForeignKeyViolation):
            api.post("/api/financeiro/faturas", json={
                "cliente_id": cliente["id"], "competencia": "2026-08",
            })

    def test_duplicate_for_a_contract_month_returns_409(self, api, repos, cliente):
        """Re-running the monthly close must be idempotent, not double-billing."""
        contrato = _contrato(repos, cliente)
        corpo = {
            "cliente_id": cliente["id"], "contrato_id": contrato["id"],
            "competencia": "2026-08",
        }
        assert api.post("/api/financeiro/faturas", json=corpo).status_code == 201
        assert api.post("/api/financeiro/faturas", json=corpo).status_code == 409

    def test_unknown_contrato_returns_404(self, api, cliente):
        """The UI now lets the manual form pick a contrato (finding #4) — a
        bad id must 404 cleanly, not surface as a FK `PersistenceError`
        mislabelled as "duplicate invoice" (finding #7)."""
        resp = api.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "contrato_id": "nao-existe",
            "competencia": "2026-08",
        })
        assert resp.status_code == 404

    def test_malformed_vencimento_returns_422(self, api, cliente):
        resp = api.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
            "vencimento": "31/08/2026",
        })
        assert resp.status_code == 422

    def test_manual_invoice_with_contrato_id_shares_the_generated_idempotency_guard(
        self, api, repos, cliente
    ):
        """Finding #4: the UI now lets the manual form pick a contrato, and
        picking one means the same unique index `gerar_competencia` relies on
        applies — a manual + a generated invoice for the same contract+month
        can no longer coexist."""
        contrato = _contrato(repos, cliente)
        corpo = {
            "cliente_id": cliente["id"], "contrato_id": contrato["id"],
            "competencia": "2026-08",
        }
        assert api.post("/api/financeiro/faturas", json=corpo).status_code == 201
        resp = api.post("/api/financeiro/faturas/gerar-competencia", json={"competencia": "2026-08"})
        assert resp.json()["criadas"] == []
        assert len(resp.json()["existentes"]) == 1

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

    def test_desconto_line_subtracts_from_the_total(self, api, cliente):
        """finding #3, 2026-09 audit: every line used to ADD regardless of
        `tipo`, so a "Desconto" line silently INCREASED the invoice."""
        fatura = api.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
        }).json()
        api.post(f"/api/financeiro/faturas/{fatura['id']}/itens", json={
            "descricao": "Mensalidade", "valor_unit": 1000.0,
        })
        resp = api.post(f"/api/financeiro/faturas/{fatura['id']}/itens", json={
            "descricao": "Desconto negociado", "tipo": "desconto", "valor_unit": 200.0,
        })
        assert resp.status_code == 201
        assert resp.json()["valor_total"] == 800.0

    def test_a_discount_that_would_go_negative_is_refused(self, api, cliente):
        fatura = api.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
        }).json()
        api.post(f"/api/financeiro/faturas/{fatura['id']}/itens", json={
            "descricao": "Mensalidade", "valor_unit": 100.0,
        })
        resp = api.post(f"/api/financeiro/faturas/{fatura['id']}/itens", json={
            "descricao": "Desconto grande demais", "tipo": "desconto", "valor_unit": 200.0,
        })
        assert resp.status_code == 422
        assert resp.json()["code"] == "total_negativo"
        # The line must NOT have been persisted — the invoice's total is untouched.
        assert api.get(f"/api/financeiro/faturas/{fatura['id']}/itens").json()[0]["descricao"] == "Mensalidade"
        assert len(api.get(f"/api/financeiro/faturas/{fatura['id']}/itens").json()) == 1

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

    def test_multiple_active_contracts_are_skipped_not_double_counted(self, api, repos, cliente):
        """An EXTRA (non-plan) pauta only carries `cliente_id` — attributing
        it to EACH of a client's active packaged contracts would double-bill
        (finding #10, 2026-09 audit). Skipped, not guessed: both contracts
        still appear (each is a real active package), but with zero counted
        against either, rather than one guess landing on the wrong one."""
        _contrato(repos, cliente, pacote=12, excedente=150.0)
        _contrato(repos, cliente, pacote=5, excedente=50.0)
        _pautas(repos, cliente, 15)
        linhas = api.get("/api/financeiro/excedentes/2026-08").json()
        assert len(linhas) == 2
        assert all(l["entregues"] == 0 and l["excedentes"] == 0 for l in linhas)


def _plano(repos, cliente, contrato, *, quantidade_plano, mes="2026-08"):
    """`quantidade_plano` PLAN pautas — traced back to the accepted
    orçamento's own recurring item, the same way `pautas.gerar`/`estender`
    stamp them at generation time."""
    orcamento = repos.orcamento.criar(ORG, {"cliente_id": cliente["id"], "titulo": "Plano mensal"})
    repos.contrato.atualizar(ORG, contrato["id"], {"orcamento_id": orcamento["id"]})
    item = repos.orcamento_item.criar(ORG, {
        "orcamento_id": orcamento["id"], "secao": "criacao_conteudo",
        "descricao": "Posts recorrentes", "recorrente": True,
        "dias_semana": 3, "qtd_por_dia": 1,
    })
    for i in range(quantidade_plano):
        quando = f"{mes}-{(i % 28) + 1:02d}T09:00:00"
        repos.pauta.criar(ORG, {
            "cliente_id": cliente["id"], "titulo": f"Plano {i}",
            "gerada_automaticamente": True, "orcamento_item_id": item["id"],
            "publicado_em": quando,
        })
    return item


class TestExcedentesPlanoVsExtra:
    """A PLAN pauta (`gerada_automaticamente`, traced to the accepted
    orçamento's own recurring item) can never be an excedente, no matter how
    many of it the real calendar produces in a given month. A hand-added
    EXTRA pauta bills against whatever PACKAGE CAPACITY the plan did NOT
    already use that competência —
    `capacidade_restante = max(0, posts_por_mes − plano_entregue)`,
    `excedentes = max(0, extras − capacidade_restante)` — never against the
    raw `posts_por_mes` (achado A, 2026-09 audit: the old code compared
    extras straight to `posts_por_mes`, under-billing whenever the plan
    itself had already delivered part, or all, of the package). Worked
    examples mirrored in `scratchpad/kb/delta-excedentes-fatura.md`."""

    def test_a_5_week_month_never_bills_the_plans_own_calendar_variance(self, api, repos, cliente):
        """pacote=8 ('2x/semana', priced flat at 4 semanas/mês —
        `orcamentos.quantidade_mensal`); this month's real calendar gives 10
        occurrences of that same recurring item — still zero excedentes, even
        though the plan alone already exceeds the nominal package size."""
        contrato = _contrato(repos, cliente, pacote=8, excedente=100.0)
        _plano(repos, cliente, contrato, quantidade_plano=10)
        linha = api.get("/api/financeiro/excedentes/2026-08").json()[0]
        assert linha["contratados"] == 8
        assert linha["entregues"] == 10
        assert linha["excedentes"] == 0
        assert linha["valor_total"] == 0.0

    def test_plan_fully_consuming_the_package_bills_every_avulsa(self, api, repos, cliente):
        """pacote=12, plano=12 (the plan alone fills the whole package this
        month) ⇒ remaining capacity is zero, so BOTH avulsas bill — not zero,
        which is what comparing them to the raw `posts_por_mes` would give."""
        contrato = _contrato(repos, cliente, pacote=12, excedente=150.0)
        _plano(repos, cliente, contrato, quantidade_plano=12)
        _pautas(repos, cliente, 2)
        linha = api.get("/api/financeiro/excedentes/2026-08").json()[0]
        assert linha["entregues"] == 14  # 12 plano + 2 avulsas
        assert linha["excedentes"] == 2  # max(0, 2 avulsas − max(0, 12 − 12))
        assert linha["valor_total"] == 300.0  # 2 × 150

    def test_partial_remaining_capacity_after_the_plan(self, api, repos, cliente):
        """pacote=12, plano=10 ⇒ 2 slots of the package are still free; 3
        avulsas ⇒ only the ONE beyond those 2 free slots bills."""
        contrato = _contrato(repos, cliente, pacote=12, excedente=150.0)
        _plano(repos, cliente, contrato, quantidade_plano=10)
        _pautas(repos, cliente, 3)
        linha = api.get("/api/financeiro/excedentes/2026-08").json()[0]
        assert linha["entregues"] == 13  # 10 plano + 3 avulsas
        assert linha["excedentes"] == 1  # max(0, 3 avulsas − max(0, 12 − 10))
        assert linha["valor_total"] == 150.0

    def test_extras_within_the_remaining_capacity_are_not_billed(self, api, repos, cliente):
        """pacote=12, plano=8 ⇒ 4 slots free; 3 avulsas fit inside that
        remaining capacity ⇒ zero excedentes."""
        contrato = _contrato(repos, cliente, pacote=12, excedente=150.0)
        _plano(repos, cliente, contrato, quantidade_plano=8)
        _pautas(repos, cliente, 3)
        linha = api.get("/api/financeiro/excedentes/2026-08").json()[0]
        assert linha["excedentes"] == 0
        assert linha["valor_total"] == 0.0

    def test_extras_measured_against_remaining_capacity_never_the_plans_own_count(
        self, api, repos, cliente
    ):
        """Same contract, same month: the plan's own 10 (still free, and
        already ABOVE the 8-post package on its own — a 5-week-month
        variance) PLUS 9 hand-added extras — since the plan already used up
        (and exceeded) the whole package, remaining capacity is zero and
        every extra bills."""
        contrato = _contrato(repos, cliente, pacote=8, excedente=100.0)
        _plano(repos, cliente, contrato, quantidade_plano=10)
        _pautas(repos, cliente, 9)
        linha = api.get("/api/financeiro/excedentes/2026-08").json()[0]
        assert linha["entregues"] == 19  # 10 plano + 9 extras
        assert linha["excedentes"] == 9  # max(0, 9 extras − max(0, 8 − 10))
        assert linha["valor_total"] == 900.0

    def test_a_plan_pauta_from_a_different_orcamento_is_not_conflated(self, api, repos, cliente):
        """Two clients, two plans, two contracts — a plan pauta never
        crosses over to the other contract even though both recurring items
        look identical."""
        outro_cliente = repos.cliente.criar(ORG, {"nome": "Outra Padaria"})
        c1 = _contrato(repos, cliente, pacote=8, excedente=100.0)
        c2 = _contrato(repos, outro_cliente, pacote=8, excedente=100.0)
        _plano(repos, cliente, c1, quantidade_plano=10)
        _plano(repos, outro_cliente, c2, quantidade_plano=1)
        linhas = {l["contrato_id"]: l for l in api.get("/api/financeiro/excedentes/2026-08").json()}
        assert linhas[c1["id"]]["entregues"] == 10
        assert linhas[c2["id"]]["entregues"] == 1


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


class TestDRECustoPorCompetencia:
    """`custo_por_competencia` — the Dashboard's "Margem no mês" fix.

    Worked example: a designer at R$100/h logged 10h in julho (R$1000, work
    on a PRIOR month's deliverable) and 4h in agosto (R$400). Agosto's
    invoice is R$5000. Without the flag (the M6 DRE screen's own, documented
    behaviour) cost is the full R$1400. WITH it, cost is agosto's R$400 only
    — the number a "margin THIS MONTH" card must show.
    """

    def _apontamento(self, repos, cliente, *, mes_dia: str, minutos: int, funcao=None):
        if funcao is None:
            funcao = repos.funcao.criar(ORG, {"nome": "designer", "custo_hora_padrao": 100.0})
            repos.profissional.criar(
                ORG, {"nome": "Ana", "usuario_id": "user-1", "funcao_id": funcao["id"]}
            )
        pauta = repos.pauta.criar(ORG, {"cliente_id": cliente["id"], "titulo": "Post"})
        tarefa = repos.tarefa.criar(
            ORG, {"pauta_id": pauta["id"], "titulo": "Arte", "etapa_id": "etapa-1"}
        )
        repos.apontamento.criar(ORG, {
            "tarefa_id": tarefa["id"], "usuario_id": "user-1",
            "iniciado_em": f"{mes_dia}T09:00:00", "encerrado_em": f"{mes_dia}T09:00:00",
            "minutos": minutos,
        })
        return funcao

    def test_default_keeps_the_full_history_cost(self, api, repos, cliente):
        """The M6 DRE screen's own behaviour must not change."""
        funcao = self._apontamento(repos, cliente, mes_dia="2026-07-15", minutos=600)  # 10h
        self._apontamento(repos, cliente, mes_dia="2026-08-01", minutos=240, funcao=funcao)  # 4h
        repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-08", "valor_total": 5000.0,
        })
        linha = api.get("/api/financeiro/dre?competencia=2026-08").json()[0]
        assert linha["receita"] == 5000.0
        assert linha["custo"] == 1400.0  # 14h × R$100 — julho AND agosto

    def test_flag_scopes_cost_to_the_same_competencia_as_revenue(self, api, repos, cliente):
        funcao = self._apontamento(repos, cliente, mes_dia="2026-07-15", minutos=600)  # 10h
        self._apontamento(repos, cliente, mes_dia="2026-08-01", minutos=240, funcao=funcao)  # 4h
        repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-08", "valor_total": 5000.0,
        })
        linha = api.get(
            "/api/financeiro/dre?competencia=2026-08&custo_por_competencia=true"
        ).json()[0]
        assert linha["receita"] == 5000.0
        assert linha["custo"] == 400.0  # 4h × R$100 — agosto only
        assert linha["margem"] == 4600.0
        assert linha["margem_percentual"] == 92.0

    def test_flag_without_a_competencia_is_rejected(self, api):
        resp = api.get("/api/financeiro/dre?custo_por_competencia=true")
        assert resp.status_code == 422


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

    def test_excedente_line_is_added_to_an_already_existing_invoice(self, api, repos, cliente):
        """Finding #11: an invoice opened before the close ran (or by a
        previous close before excedentes were computed) must still receive
        the excedente line — idempotently, never duplicated on a re-run."""
        contrato = _contrato(repos, cliente, pacote=12, excedente=150.0)
        _pautas(repos, cliente, 15, mes="2026-07")
        fatura = repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "contrato_id": contrato["id"], "competencia": "2026-08",
        })
        repos.fatura_item.criar(ORG, {
            "fatura_id": fatura["id"], "descricao": "Retainer mensal",
            "tipo": "mensalidade", "quantidade": 1, "valor_unit": 5000.0,
        })
        repos.fatura.recalcular_total(ORG, fatura["id"], repos.fatura_item.da_fatura(ORG, fatura["id"]))

        resp = api.post("/api/financeiro/faturas/gerar-competencia", json={"competencia": "2026-08"})
        corpo = resp.json()
        assert corpo["criadas"] == []
        existente = corpo["existentes"][0]
        assert existente["id"] == fatura["id"]
        assert existente["valor_total"] == 5450.0  # 5000 retainer + 3×150 excedente

        itens = repos.fatura_item.da_fatura(ORG, fatura["id"])
        assert sum(1 for i in itens if i["tipo"] == "excedente") == 1

        # Re-running must not duplicate the line.
        api.post("/api/financeiro/faturas/gerar-competencia", json={"competencia": "2026-08"})
        itens_depois = repos.fatura_item.da_fatura(ORG, fatura["id"])
        assert sum(1 for i in itens_depois if i["tipo"] == "excedente") == 1

    def test_excedente_not_added_to_a_paid_invoice(self, api, repos, cliente):
        """A closed invoice cannot accept new lines — same guard as
        `POST /faturas/{id}/itens`."""
        contrato = _contrato(repos, cliente, pacote=12, excedente=150.0)
        _pautas(repos, cliente, 15, mes="2026-07")
        fatura = repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "contrato_id": contrato["id"],
            "competencia": "2026-08", "status": "paga", "valor_total": 5000.0,
        })
        api.post("/api/financeiro/faturas/gerar-competencia", json={"competencia": "2026-08"})
        itens = repos.fatura_item.da_fatura(ORG, fatura["id"])
        assert all(i["tipo"] != "excedente" for i in itens)

    def test_a_race_on_the_unique_index_is_reported_as_existente_not_500(
        self, api, repos, cliente, monkeypatch
    ):
        """Two concurrent closes hitting the SAME contrato+competência must
        not 500 — the unique index enforces the guarantee; this call just
        has to report it honestly (finding #9, 2026-09 audit)."""
        contrato = _contrato(repos, cliente)
        original_criar = repos.fatura.criar
        estado = {"corrida_simulada": False}

        def _criar_com_corrida(org_id, valores):
            if not estado["corrida_simulada"]:
                estado["corrida_simulada"] = True
                original_criar(org_id, valores)  # a "concurrent" request wins first
                raise UniqueViolation("unique violation (simulado)")
            return original_criar(org_id, valores)

        monkeypatch.setattr(repos.fatura, "criar", _criar_com_corrida)
        resp = api.post("/api/financeiro/faturas/gerar-competencia", json={"competencia": "2026-08"})
        assert resp.status_code == 200
        corpo = resp.json()
        assert corpo["criadas"] == []
        assert len(corpo["existentes"]) == 1
        assert corpo["existentes"][0]["contrato_id"] == contrato["id"]


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

    def test_malformed_hoje_returns_422_not_500(self, api):
        """`date.fromisoformat` was unguarded (finding #8, 2026-09 audit)."""
        assert api.get("/api/financeiro/inadimplentes?hoje=hoje-mesmo").status_code == 422


class TestMarcarPagaGuards:
    def test_paying_twice_does_not_overwrite_pago_em(self, api, cliente):
        fatura = api.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
        }).json()
        primeiro = api.post(f"/api/financeiro/faturas/{fatura['id']}/pagar").json()
        segundo = api.post(f"/api/financeiro/faturas/{fatura['id']}/pagar").json()
        assert segundo["status"] == "paga"
        assert segundo["pago_em"] == primeiro["pago_em"]

    def test_cannot_pay_a_cancelled_invoice(self, api, repos, cliente):
        fatura = repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-08", "status": "cancelada",
        })
        resp = api.post(f"/api/financeiro/faturas/{fatura['id']}/pagar")
        assert resp.status_code == 409
        assert resp.json()["code"] == "fatura_cancelada"

    def test_unknown_invoice_returns_404(self, api):
        assert api.post("/api/financeiro/faturas/nao-existe/pagar").status_code == 404


class TestCancelarFatura:
    def test_requires_auth(self, api):
        assert api.raw().post("/api/financeiro/faturas/x/cancelar").status_code == 401

    def test_cancels_an_open_invoice(self, api, cliente):
        fatura = api.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
        }).json()
        resp = api.post(f"/api/financeiro/faturas/{fatura['id']}/cancelar")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelada"

    def test_cancelling_a_cancelled_invoice_is_idempotent(self, api, repos, cliente):
        fatura = repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-08", "status": "cancelada",
        })
        assert api.post(f"/api/financeiro/faturas/{fatura['id']}/cancelar").status_code == 200

    def test_cannot_cancel_a_paid_invoice(self, api, cliente):
        fatura = api.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
        }).json()
        api.post(f"/api/financeiro/faturas/{fatura['id']}/pagar")
        resp = api.post(f"/api/financeiro/faturas/{fatura['id']}/cancelar")
        assert resp.status_code == 409
        assert resp.json()["code"] == "fatura_paga"

    def test_cancelling_frees_the_contract_competencia_slot(self, api, repos, cliente):
        contrato = _contrato(repos, cliente)
        corpo = {"cliente_id": cliente["id"], "contrato_id": contrato["id"], "competencia": "2026-08"}
        primeira = api.post("/api/financeiro/faturas", json=corpo).json()
        api.post(f"/api/financeiro/faturas/{primeira['id']}/cancelar")
        assert api.post("/api/financeiro/faturas", json=corpo).status_code == 201

    def test_unknown_invoice_returns_404(self, api):
        assert api.post("/api/financeiro/faturas/nao-existe/cancelar").status_code == 404


class TestEnviarFatura:
    """`POST /faturas/{id}/enviar` — e-mails the fatura's PDF (achado 12
    parcial, 2026-09 audit: no action ever moved a fatura to `enviada`)."""

    @pytest.fixture
    def senders(self) -> Senders:
        return Senders()

    @pytest.fixture
    def api_email(self, api, senders):
        from app.main import app

        overrides = {get_email_settings: lambda: SEM_GCP, get_email_sender_factory: lambda: senders}
        app.dependency_overrides.update(overrides)
        yield api
        for dep in overrides:
            app.dependency_overrides.pop(dep, None)

    @pytest.fixture
    def smtp(self, repos):
        email_config.salvar_smtp(repos, ORG, SEM_GCP, **SMTP)

    def test_requires_auth(self, api_email):
        assert api_email.raw().post("/api/financeiro/faturas/x/enviar").status_code == 401

    def test_sends_the_pdf_and_marks_enviada(self, api_email, senders, smtp, repos, cliente):
        cliente_com_email = repos.cliente.atualizar(ORG, cliente["id"], {"email": "cliente@padaria.com"})
        fatura = api_email.post("/api/financeiro/faturas", json={
            "cliente_id": cliente_com_email["id"], "competencia": "2026-08",
        }).json()
        api_email.post(f"/api/financeiro/faturas/{fatura['id']}/itens",
                        json={"descricao": "Mensalidade", "valor_unit": 5000.0})

        resp = api_email.post(f"/api/financeiro/faturas/{fatura['id']}/enviar")
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert corpo["fatura"]["status"] == "enviada"
        assert corpo["fatura"]["enviada_em"] is not None
        assert corpo["message_id"]

        [enviado] = senders.fake.sent
        assert enviado.to == ["cliente@padaria.com"]
        assert enviado.attachments[0].mime_type == "application/pdf"
        assert enviado.attachments[0].content.startswith(b"%PDF")

    def test_without_smtp_is_409(self, api_email, repos, cliente):
        repos.cliente.atualizar(ORG, cliente["id"], {"email": "cliente@padaria.com"})
        fatura = api_email.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
        }).json()
        resp = api_email.post(f"/api/financeiro/faturas/{fatura['id']}/enviar")
        assert resp.status_code == 409
        assert resp.json()["code"] == "smtp_nao_configurado"

    def test_client_without_email_is_422(self, api_email, smtp, cliente):
        fatura = api_email.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
        }).json()
        resp = api_email.post(f"/api/financeiro/faturas/{fatura['id']}/enviar")
        assert resp.status_code == 422
        assert resp.json()["code"] == "email_destinatario_ausente"

    def test_a_closed_invoice_cannot_be_sent(self, api_email, smtp, repos, cliente):
        repos.cliente.atualizar(ORG, cliente["id"], {"email": "cliente@padaria.com"})
        fatura = api_email.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
        }).json()
        api_email.post(f"/api/financeiro/faturas/{fatura['id']}/cancelar")
        resp = api_email.post(f"/api/financeiro/faturas/{fatura['id']}/enviar")
        assert resp.status_code == 409
        assert resp.json()["code"] == "fatura_fechada"

    def test_send_failure_is_502_and_not_marked_enviada(self, api_email, senders, smtp, repos, cliente):
        senders.falhar = True
        repos.cliente.atualizar(ORG, cliente["id"], {"email": "cliente@padaria.com"})
        fatura = api_email.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
        }).json()
        resp = api_email.post(f"/api/financeiro/faturas/{fatura['id']}/enviar")
        assert resp.status_code == 502
        assert resp.json()["code"] == "envio_falhou"
        assert repos.fatura.buscar(ORG, fatura["id"])["status"] != "enviada"

    def test_unknown_invoice_returns_404(self, api_email, smtp):
        assert api_email.post("/api/financeiro/faturas/nao-existe/enviar").status_code == 404

    def test_sending_a_vencida_invoice_does_not_undo_the_overdue_status(
        self, api_email, senders, smtp, repos, cliente
    ):
        """achado B, 2026-09 audit: sending a `vencida` invoice used to flip
        it back to `enviada`, and the next 06:00 `atualizar_inadimplencia`
        sweep flipped it right back to `vencida` — flip-flop, with the
        cliente's inadimplente state wobbling along with it. `enviar` may
        still be used on an overdue invoice (it is not in `FATURA_FECHADA`),
        but the status must stay `vencida`."""
        repos.cliente.atualizar(ORG, cliente["id"], {"email": "cliente@padaria.com"})
        fatura = api_email.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
        }).json()
        repos.fatura.atualizar(ORG, fatura["id"], {"status": "vencida"})

        resp = api_email.post(f"/api/financeiro/faturas/{fatura['id']}/enviar")
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert corpo["fatura"]["status"] == "vencida"
        assert corpo["fatura"]["enviada_em"] is not None


class TestMarcarFaturaEnviada:
    """`POST /faturas/{id}/marcar-enviada` — a manual flag for a fatura sent
    outside the system, same status+timestamp `enviar` sets, no e-mail."""

    def test_requires_auth(self, api):
        assert api.raw().post("/api/financeiro/faturas/x/marcar-enviada").status_code == 401

    def test_marks_an_open_invoice_enviada(self, api, cliente):
        fatura = api.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
        }).json()
        resp = api.post(f"/api/financeiro/faturas/{fatura['id']}/marcar-enviada")
        assert resp.status_code == 200
        assert resp.json()["status"] == "enviada"
        assert resp.json()["enviada_em"] is not None

    def test_a_closed_invoice_cannot_be_marked(self, api, cliente):
        fatura = api.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
        }).json()
        api.post(f"/api/financeiro/faturas/{fatura['id']}/pagar")
        resp = api.post(f"/api/financeiro/faturas/{fatura['id']}/marcar-enviada")
        assert resp.status_code == 409
        assert resp.json()["code"] == "fatura_fechada"

    def test_unknown_invoice_returns_404(self, api):
        assert api.post("/api/financeiro/faturas/nao-existe/marcar-enviada").status_code == 404

    def test_marking_a_vencida_invoice_does_not_undo_the_overdue_status(self, api, repos, cliente):
        """Same flip-flop guard as `enviar` (achado B, 2026-09 audit) — the
        manual 'sent outside the system' flag must not resurrect a `vencida`
        invoice as `enviada` either."""
        fatura = api.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
        }).json()
        repos.fatura.atualizar(ORG, fatura["id"], {"status": "vencida"})

        resp = api.post(f"/api/financeiro/faturas/{fatura['id']}/marcar-enviada")
        assert resp.status_code == 200
        assert resp.json()["status"] == "vencida"
        assert resp.json()["enviada_em"] is not None


class TestPermissoes:
    """`pagar`/`cancelar`/`gerar-competencia` are admin-only. Uses the bare
    `client` fixture (no `exigir_admin_da_org` bypass) — the `api` fixture in
    this file bakes the bypass in for every other test."""

    @pytest.fixture
    def sem_admin(self, client, repos):
        from app.main import app

        app.dependency_overrides[get_repositorios] = lambda: repos
        app.dependency_overrides[get_repositorios_admin] = lambda: repos
        yield client
        app.dependency_overrides.pop(get_repositorios, None)
        app.dependency_overrides.pop(get_repositorios_admin, None)

    def test_marcar_paga_requires_admin(self, sem_admin, repos, cliente):
        fatura = repos.fatura.criar(ORG, {"cliente_id": cliente["id"], "competencia": "2026-08"})
        assert sem_admin.post(f"/api/financeiro/faturas/{fatura['id']}/pagar").status_code == 403

    def test_cancelar_requires_admin(self, sem_admin, repos, cliente):
        fatura = repos.fatura.criar(ORG, {"cliente_id": cliente["id"], "competencia": "2026-08"})
        assert sem_admin.post(f"/api/financeiro/faturas/{fatura['id']}/cancelar").status_code == 403

    def test_gerar_competencia_requires_admin(self, sem_admin):
        resp = sem_admin.post(
            "/api/financeiro/faturas/gerar-competencia", json={"competencia": "2026-08"}
        )
        assert resp.status_code == 403

    def test_enviar_requires_admin(self, sem_admin, repos, cliente):
        fatura = repos.fatura.criar(ORG, {"cliente_id": cliente["id"], "competencia": "2026-08"})
        assert sem_admin.post(f"/api/financeiro/faturas/{fatura['id']}/enviar").status_code == 403

    def test_edit_endpoints_require_admin(self, sem_admin, repos, cliente):
        fatura = repos.fatura.criar(ORG, {"cliente_id": cliente["id"], "competencia": "2026-08"})
        base = f"/api/financeiro/faturas/{fatura['id']}"
        assert sem_admin.patch(base, json={}).status_code == 403
        assert sem_admin.patch(f"{base}/itens/x", json={}).status_code == 403
        assert sem_admin.delete(f"{base}/itens/x").status_code == 403

    def test_marcar_enviada_requires_admin(self, sem_admin, repos, cliente):
        fatura = repos.fatura.criar(ORG, {"cliente_id": cliente["id"], "competencia": "2026-08"})
        assert sem_admin.post(
            f"/api/financeiro/faturas/{fatura['id']}/marcar-enviada"
        ).status_code == 403


class TestEditarFatura:
    """PATCH /faturas/{id}, PATCH + DELETE /faturas/{id}/itens/{item_id}."""

    def _fatura_com_itens(self, api, cliente):
        fatura = api.post("/api/financeiro/faturas", json={
            "cliente_id": cliente["id"], "competencia": "2026-08",
        }).json()
        base = f"/api/financeiro/faturas/{fatura['id']}"
        api.post(f"{base}/itens", json={"descricao": "Mensalidade", "valor_unit": 100.0})
        api.post(f"{base}/itens", json={"descricao": "Extra", "quantidade": 2, "valor_unit": 50.0})
        return fatura, base, api.get(f"{base}/itens").json()

    def test_edit_header(self, api, cliente):
        fatura, base, _ = self._fatura_com_itens(api, cliente)
        resp = api.patch(base, json={"vencimento": "2026-09-10", "competencia": "2026-09"})
        assert resp.status_code == 200
        assert resp.json()["vencimento"] == "2026-09-10"
        assert resp.json()["competencia"] == "2026-09"

    def test_edit_item_recomputes_total(self, api, cliente):
        _, base, itens = self._fatura_com_itens(api, cliente)
        resp = api.patch(f"{base}/itens/{itens[0]['id']}", json={"valor_unit": 300.0})
        assert resp.status_code == 200
        assert resp.json()["valor_total"] == 400.0

    def test_delete_item_recomputes_total(self, api, cliente):
        _, base, itens = self._fatura_com_itens(api, cliente)
        resp = api.delete(f"{base}/itens/{itens[1]['id']}")
        assert resp.status_code == 200
        assert resp.json()["valor_total"] == 100.0
        assert len(api.get(f"{base}/itens").json()) == 1

    def test_paid_invoice_refuses_every_edit(self, api, cliente):
        _, base, itens = self._fatura_com_itens(api, cliente)
        api.post(f"{base}/pagar")
        assert api.patch(base, json={"vencimento": "2026-09-10"}).status_code == 409
        assert api.patch(f"{base}/itens/{itens[0]['id']}", json={"descricao": "x"}).status_code == 409
        assert api.delete(f"{base}/itens/{itens[0]['id']}").status_code == 409

    def test_other_org_invoice_is_404(self, api, repos):
        outra_org = "3b0c7f2e-9a41-4d8e-b0a6-2f1d5c7e9a10"
        cliente_outro = repos.cliente.criar(outra_org, {"nome": "Outra Org"})
        outra = repos.fatura.criar(
            outra_org, {"cliente_id": cliente_outro["id"], "competencia": "2026-08"},
        )
        base = f"/api/financeiro/faturas/{outra['id']}"
        assert api.patch(base, json={"vencimento": "2026-09-10"}).status_code == 404
        assert api.delete(f"{base}/itens/zzz").status_code == 404

    def test_unknown_item_is_404(self, api, cliente):
        _, base, _ = self._fatura_com_itens(api, cliente)
        assert api.delete(f"{base}/itens/nao-existe").status_code == 404

    def test_extra_fields_are_refused(self, api, cliente):
        _, base, _ = self._fatura_com_itens(api, cliente)
        assert api.patch(base, json={"valor_total": 1}).status_code == 422

    def test_requires_auth(self, api):
        assert api.raw().patch("/api/financeiro/faturas/x", json={}).status_code == 401
        assert api.raw().patch("/api/financeiro/faturas/x/itens/y", json={}).status_code == 401
        assert api.raw().delete("/api/financeiro/faturas/x/itens/y").status_code == 401
