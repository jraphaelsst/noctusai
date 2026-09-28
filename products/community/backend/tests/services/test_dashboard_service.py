"""Tests for `DashboardService` — CONTRACT.md §Cashflow + dashboard,
slice BE-C. One test per contract-normative definition (contract's own
wording: "Definitions (tests assert these)"), plus the pure helpers in
isolation.

Exercises the service directly (no HTTP) against a data-seeded
`MockSupabaseClient` — no monkeypatching of our own code. "Now" is
pinned via `noctusai_lib.primitives.timeutil.frozen_time`, the seed's
sanctioned clock DI seam.
"""
import asyncio
from datetime import date, datetime, timezone
from uuid import UUID

from noctusai_lib.primitives.timeutil import frozen_time
from noctusai_lib.testing import MockSupabaseClient

from app.services.dashboard_service import (
    DashboardService,
    _pct,
    _round_div_centavos,
    estado_em,
    month_window,
    monthly_equivalent_centavos,
)

ORG = UUID("00000000-0000-0000-0000-000000000123")


def _plano(id_: str, *, preco_centavos: int, ciclo: str = "mensal",
           nivel: str = "nenhum", ordem: int = 0, nome: str = "Plano") -> dict:
    return {
        "id": id_, "org_id": str(ORG), "nome": nome, "descricao": None,
        "preco_centavos": preco_centavos, "ciclo": ciclo,
        "entitlements": {"grupoterapia": nivel}, "ativo": True, "ordem": ordem,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _membro(id_: str, *, status: str = "ativo", plano_id: str | None = None,
            origem: str = "checkout", entrou_em: str | None = None) -> dict:
    return {
        "id": id_, "org_id": str(ORG), "nome": f"Membro {id_[-1]}", "email": f"{id_}@x.com",
        "telefone": None, "status": status, "plano_id": plano_id, "origem": origem,
        "tags": [], "user_id": None, "observacoes": None, "entrou_em": entrou_em,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _assinatura(id_: str, *, membro_id: str, plano_id: str, estado: str,
                 ativa_em: str | None = None, cancelada_em: str | None = None,
                 expirada_em: str | None = None) -> dict:
    return {
        "id": id_, "org_id": str(ORG), "membro_id": membro_id, "plano_id": plano_id,
        "gateway": "asaas", "assinatura_externa_id": None, "cliente_externo_id": None,
        "estado": estado, "metodo": "pix", "ciclo": "mensal",
        "iniciada_em": ativa_em, "ativa_em": ativa_em, "cancelada_em": cancelada_em,
        "inadimplente_desde": None, "carencia_ate": None, "pago_ate": None,
        "proxima_cobranca": None, "expirada_em": expirada_em,
        "cancelamento_solicitado_por": None, "cancelamento_motivo": None,
        "gateway_cancelamento_pendente": False,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _sessao(id_: str, *, inicio: str, vagas_fala: int = 8, titulo: str = "Roda") -> dict:
    return {
        "id": id_, "org_id": str(ORG), "titulo": titulo, "descricao": None,
        "inicio": inicio, "duracao_minutos": 90, "link_sala": None,
        "vagas_fala": vagas_fala, "status": "agendada", "criado_por": None,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _reserva(id_: str, *, sessao_id: str, membro_id: str, status: str = "confirmada") -> dict:
    return {
        "id": id_, "org_id": str(ORG), "sessao_id": sessao_id, "membro_id": membro_id,
        "status": status, "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _svc(*, membros=None, planos=None, assinaturas=None, lancamentos=None,
         sessoes=None, reservas=None) -> DashboardService:
    mock = MockSupabaseClient()
    mock.set_table_data("membros", membros or [])
    mock.set_table_data("planos", planos or [])
    mock.set_table_data("assinaturas", assinaturas or [])
    mock.set_table_data("lancamentos", lancamentos or [])
    mock.set_table_data("grupoterapia_sessoes", sessoes or [])
    mock.set_table_data("grupoterapia_reservas", reservas or [])
    return DashboardService(mock, org_id=ORG)


# ── pure-helper unit tests (one per named formula) ──────────────────────


def test_monthly_equivalent_anual_divides_by_12_rounded_half_up():
    # 1000 / 12 = 83.33... -> 83
    assert monthly_equivalent_centavos(1000, "anual") == 83
    # exact division stays exact
    assert monthly_equivalent_centavos(32400, "anual") == 2700
    # mensal passes through unchanged
    assert monthly_equivalent_centavos(2700, "mensal") == 2700


def test_pct_zero_base_is_zero_not_a_division_error():
    assert _pct(5, 0) == 0.0
    assert _pct(0, 0) == 0.0
    assert _pct(50, 200) == 25.0


def test_round_div_centavos_zero_denominator_is_zero():
    assert _round_div_centavos(2700, 0) == 0
    assert _round_div_centavos(2700, 2) == 1350


def test_estado_em_reconstructs_from_the_three_timestamps_only():
    a = _assinatura(
        "a1", membro_id="m1", plano_id="p1", estado="cancelada",
        ativa_em="2026-04-01T00:00:00+00:00", cancelada_em="2026-06-01T00:00:00+00:00",
    )
    assert estado_em(a, date(2026, 3, 31)) == "nenhuma"  # before ativa_em
    assert estado_em(a, date(2026, 5, 31)) == "ativa_ou_carencia"  # active, not yet cancelled
    assert estado_em(a, date(2026, 6, 30)) == "cancelada"  # cancelled by then


def test_month_window_is_oldest_first_and_zero_fills_every_month():
    window = month_window(3, date(2026, 6, 15))
    assert window == [date(2026, 4, 1), date(2026, 5, 1), date(2026, 6, 1)]


# ── DashboardService.build() — composite behaviors ──────────────────────


class TestMrrAndArpu:
    def test_mrr_sums_mensal_and_anual_over_twelve(self):
        plano_mensal = _plano("p1", preco_centavos=2700, ciclo="mensal")
        plano_anual = _plano("p2", preco_centavos=32400, ciclo="anual")
        membro_1 = _membro("m1", plano_id="p1")
        membro_2 = _membro("m2", plano_id="p2")
        assinaturas = [
            _assinatura("a1", membro_id="m1", plano_id="p1", estado="ativa",
                        ativa_em="2026-01-01T00:00:00+00:00"),
            _assinatura("a2", membro_id="m2", plano_id="p2", estado="carencia",
                        ativa_em="2026-01-01T00:00:00+00:00"),
        ]
        svc = _svc(membros=[membro_1, membro_2], planos=[plano_mensal, plano_anual],
                    assinaturas=assinaturas)
        with frozen_time(datetime(2026, 6, 15, tzinfo=timezone.utc)):
            result = asyncio.run(svc.build(meses=1))
        assert result["kpis"]["mrr_centavos"] == 2700 + 2700  # anual/12 == 2700 exact

    def test_arpu_is_zero_when_no_paying_subscription(self):
        svc = _svc(membros=[_membro("m1")], planos=[], assinaturas=[])
        with frozen_time(datetime(2026, 6, 15, tzinfo=timezone.utc)):
            result = asyncio.run(svc.build(meses=1))
        assert result["kpis"]["mrr_centavos"] == 0
        assert result["kpis"]["arpu_centavos"] == 0

    def test_arpu_divides_mrr_by_distinct_paying_members(self):
        plano = _plano("p1", preco_centavos=2700, ciclo="mensal")
        assinaturas = [
            _assinatura("a1", membro_id="m1", plano_id="p1", estado="ativa",
                        ativa_em="2026-01-01T00:00:00+00:00"),
            _assinatura("a2", membro_id="m2", plano_id="p1", estado="ativa",
                        ativa_em="2026-01-01T00:00:00+00:00"),
        ]
        svc = _svc(membros=[_membro("m1", plano_id="p1"), _membro("m2", plano_id="p1")],
                    planos=[plano], assinaturas=assinaturas)
        with frozen_time(datetime(2026, 6, 15, tzinfo=timezone.utc)):
            result = asyncio.run(svc.build(meses=1))
        assert result["kpis"]["mrr_centavos"] == 5400
        assert result["kpis"]["arpu_centavos"] == 2700


class TestChurn:
    def test_churn_pct_is_zero_when_base_is_zero(self):
        # No subscriptions existed before this month at all — base is 0
        # regardless of whether a churn event happened.
        svc = _svc(membros=[], planos=[], assinaturas=[])
        with frozen_time(datetime(2026, 6, 15, tzinfo=timezone.utc)):
            result = asyncio.run(svc.build(meses=1))
        assert result["kpis"]["churn_mes_pct"] == 0.0
        assert result["kpis"]["cancelamentos_mes"] == 0

    def test_churn_counts_cancellations_within_the_calendar_month_over_the_prior_base(self):
        plano = _plano("p1", preco_centavos=1000, ciclo="mensal")
        # 4 subscriptions active as of the end of May (the base); 1 of
        # them cancels during June.
        assinaturas = [
            _assinatura(f"a{i}", membro_id=f"m{i}", plano_id="p1", estado="ativa",
                        ativa_em="2026-01-01T00:00:00+00:00")
            for i in range(3)
        ] + [
            _assinatura("a4", membro_id="m4", plano_id="p1", estado="cancelada",
                        ativa_em="2026-01-01T00:00:00+00:00",
                        cancelada_em="2026-06-10T00:00:00+00:00"),
        ]
        svc = _svc(membros=[], planos=[plano], assinaturas=assinaturas)
        with frozen_time(datetime(2026, 6, 15, tzinfo=timezone.utc)):
            result = asyncio.run(svc.build(meses=1))
        assert result["kpis"]["cancelamentos_mes"] == 1
        assert result["kpis"]["churn_mes_pct"] == 25.0  # 1 / 4 * 100


class TestConversao:
    def test_conversao_pago_pct_over_active_members(self):
        plano_pago = _plano("p1", preco_centavos=2700, ciclo="mensal")
        plano_gratis = _plano("p0", preco_centavos=0, ciclo="mensal")
        membros = [
            _membro("m1", status="ativo", plano_id="p1"),
            _membro("m2", status="atrasado", plano_id="p1"),
            _membro("m3", status="ativo", plano_id="p0"),
            _membro("m4", status="ativo", plano_id="p0"),
            _membro("m5", status="cancelado", plano_id="p1"),  # not "ativo"
        ]
        svc = _svc(membros=membros, planos=[plano_pago, plano_gratis], assinaturas=[])
        with frozen_time(datetime(2026, 6, 15, tzinfo=timezone.utc)):
            result = asyncio.run(svc.build(meses=1))
        assert result["kpis"]["membros_ativos"] == 4  # m5 excluded (status=cancelado)
        assert result["kpis"]["conversao_pago_pct"] == 50.0  # 2 paid / 4 active


class TestMensalSeries:
    def test_zero_filled_oldest_first(self):
        svc = _svc(membros=[], planos=[], assinaturas=[], lancamentos=[])
        with frozen_time(datetime(2026, 6, 15, tzinfo=timezone.utc)):
            result = asyncio.run(svc.build(meses=3))
        mensal = result["series"]["mensal"]
        assert [m["mes"] for m in mensal] == ["2026-04", "2026-05", "2026-06"]
        for m in mensal:
            assert m["entradas_centavos"] == 0
            assert m["saidas_centavos"] == 0
            assert m["novos_membros"] == 0
            assert m["cancelamentos"] == 0
            assert m["mrr_centavos"] == 0

    def test_mensal_mrr_reconstructed_from_ativa_cancelada_expirada(self):
        plano = _plano("p1", preco_centavos=1000, ciclo="mensal")
        # Active since April; cancels on the first day of June.
        assinaturas = [
            _assinatura("a1", membro_id="m1", plano_id="p1", estado="cancelada",
                        ativa_em="2026-04-05T00:00:00+00:00",
                        cancelada_em="2026-06-01T00:00:00+00:00"),
        ]
        svc = _svc(membros=[], planos=[plano], assinaturas=assinaturas)
        with frozen_time(datetime(2026, 6, 15, tzinfo=timezone.utc)):
            result = asyncio.run(svc.build(meses=3))
        by_month = {m["mes"]: m["mrr_centavos"] for m in result["series"]["mensal"]}
        assert by_month["2026-04"] == 1000  # active by April's last day
        assert by_month["2026-05"] == 1000  # still active by May's last day
        assert by_month["2026-06"] == 0     # cancelled by June's last day


class TestGrupoterapiaSeries:
    def test_next_ten_and_last_ten_combined_chronologically(self):
        sessoes = [
            _sessao("past-2", inicio="2026-06-01T10:00:00+00:00"),
            _sessao("past-1", inicio="2026-06-10T10:00:00+00:00"),
            _sessao("future-1", inicio="2026-06-20T10:00:00+00:00"),
            _sessao("future-2", inicio="2026-06-25T10:00:00+00:00"),
        ]
        reservas = [
            _reserva("r1", sessao_id="past-1", membro_id="m1", status="confirmada"),
            _reserva("r2", sessao_id="past-1", membro_id="m2", status="confirmada"),
            _reserva("r3", sessao_id="past-1", membro_id="m3", status="cancelada"),
        ]
        svc = _svc(sessoes=sessoes, reservas=reservas)
        with frozen_time(datetime(2026, 6, 15, tzinfo=timezone.utc)):
            result = asyncio.run(svc.build(meses=1))
        gt = result["series"]["grupoterapia"]
        assert [item["sessao_id"] for item in gt] == ["past-2", "past-1", "future-1", "future-2"]
        past_1 = next(item for item in gt if item["sessao_id"] == "past-1")
        assert past_1["reservas"] == 2  # cancelled reservation not counted
