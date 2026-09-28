"""Billing sweep + settings — projects/ninho-vazio/CONTRACT.md §Billing
lifecycle (the "sweep:" rows) and §Billing — slice BE-B.

`MockSupabaseClient(schema="community")` (schema validation ON). The
gateway is injected through `CobrancaService(gateway_factory=...)` — the
service's DI seam — with a from-scratch recording double; the clock is
injected the same way.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest
from noctusai_lib.integrations.payments import PaymentGatewayError
from noctusai_lib.testing import MockSupabaseClient

from app.scheduler import ROTINA_COBRANCA_JOB, configure, rotina_cobranca_job
from app.services.ciclo_assinatura import (
    GatewayNaoConfigurado,
    TransicaoIlegal,
    plano_gratuito,
    somar_ciclo,
    validar_transicao,
)
from app.services.cobranca_service import (
    PLANO_GRATUITO_AUSENTE,
    ROTINA_CANCELAMENTOS_PENDENTES,
    ROTINA_CARENCIA_EXPIRADA,
    ROTINA_FIM_DO_PERIODO,
    ROTINAS,
    CobrancaService,
)

ORG_ID = "11111111-1111-1111-1111-111111111111"
MEMBRO_1 = "22222222-2222-2222-2222-222222222222"
PREMIUM = "33333333-3333-3333-3333-333333333333"
GRATUITO = "66666666-6666-6666-6666-666666666666"
SUB_1 = "44444444-4444-4444-4444-444444444444"

NOW = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)
PASSADO = (NOW - timedelta(hours=1)).isoformat()
FUTURO = (NOW + timedelta(days=2)).isoformat()


class _Gateway:
    """Records cancels; raises `erro` when set."""

    def __init__(self, erro: Exception | None = None) -> None:
        self.erro = erro
        self.cancelados: list[str] = []

    def cancel_subscription(self, id_at_gateway: str):
        if self.erro is not None:
            raise self.erro
        self.cancelados.append(id_at_gateway)


def _plano(id_, nome, preco, ordem, ativo=True) -> dict:
    return {
        "id": id_, "org_id": ORG_ID, "nome": nome, "descricao": None, "preco_centavos": preco,
        "ciclo": "mensal", "entitlements": {}, "ativo": ativo, "ordem": ordem,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _membro(**over) -> dict:
    base = {
        "id": MEMBRO_1, "org_id": ORG_ID, "nome": "Ana", "email": "ana@x.com",
        "telefone": None, "status": "atrasado", "plano_id": PREMIUM, "origem": "checkout",
        "tags": [], "user_id": None, "observacoes": None, "entrou_em": "2026-01-01T00:00:00+00:00",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _assinatura(**over) -> dict:
    base = {
        "id": SUB_1, "org_id": ORG_ID, "membro_id": MEMBRO_1, "plano_id": PREMIUM,
        "gateway": "asaas", "assinatura_externa_id": "sub_asaas_1", "cliente_externo_id": None,
        "estado": "carencia", "metodo": "pix", "ciclo": "mensal",
        "iniciada_em": None, "ativa_em": "2026-09-01T00:00:00+00:00", "cancelada_em": None,
        "inadimplente_desde": "2026-10-10T00:00:00+00:00", "carencia_ate": PASSADO,
        "pago_ate": None, "proxima_cobranca": None, "expirada_em": None,
        "cancelamento_solicitado_por": None, "cancelamento_motivo": None,
        "gateway_cancelamento_pendente": False,
        "created_at": "2026-09-01T00:00:00+00:00", "updated_at": "2026-09-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _client(*, assinaturas=None, membro=None, planos=None, automacoes=True) -> MockSupabaseClient:
    c = MockSupabaseClient(schema="community")
    c.set_table_data("assinaturas", assinaturas if assinaturas is not None else [_assinatura()])
    c.set_table_data("membros", [membro or _membro()])
    c.set_table_data("planos", planos if planos is not None else [
        _plano(GRATUITO, "Gratuito", 0, 0), _plano(PREMIUM, "Premium", 2700, 2),
    ])
    c.set_table_data("membro_eventos", [])
    c.set_table_data("configuracoes_cobranca", [
        {"org_id": ORG_ID, "dias_carencia": 5, "automacoes_ativas": automacoes},
    ])
    return c


def _service(client, gateway=None) -> CobrancaService:
    gw = gateway or _Gateway()
    return CobrancaService(client, org_id=ORG_ID, gateway_factory=lambda _name: gw, clock=lambda: NOW)


def _rotina(client, gateway=None) -> dict:
    relatorios = asyncio.run(_service(client, gateway).executar_rotina())
    return {r.nome: r for r in relatorios}


def _row(client, table, id_) -> dict:
    return client.table(table).select("*").eq("id", id_).maybe_single().execute().data


def _eventos(client) -> list[dict]:
    return client.table("membro_eventos").select("*").execute().data or []


class TestGraceExpiry:
    def test_expired_grace_expires_cancels_at_gateway_and_moves_member_to_free(self):
        client = _client()
        gateway = _Gateway()
        rel = _rotina(client, gateway)[ROTINA_CARENCIA_EXPIRADA]

        assert rel.examinadas == 1 and rel.erros == []
        assert rel.alteradas == [f"{SUB_1}: carencia → expirada"]
        sub = _row(client, "assinaturas", SUB_1)
        assert sub["estado"] == "expirada"
        assert sub["expirada_em"] == NOW.isoformat()
        assert sub["gateway_cancelamento_pendente"] is False
        assert gateway.cancelados == ["sub_asaas_1"]
        membro = _row(client, "membros", MEMBRO_1)
        assert membro["plano_id"] == GRATUITO
        assert membro["status"] == "ativo"
        (evento,) = _eventos(client)
        assert evento["tipo"] == "assinatura"

    def test_grace_not_yet_over_is_untouched(self):
        client = _client(assinaturas=[_assinatura(carencia_ate=FUTURO)])
        rel = _rotina(client)[ROTINA_CARENCIA_EXPIRADA]
        assert rel.examinadas == 0
        assert _row(client, "assinaturas", SUB_1)["estado"] == "carencia"
        assert _row(client, "membros", MEMBRO_1)["plano_id"] == PREMIUM

    def test_gateway_failure_flags_pending_and_next_run_retries(self):
        client = _client()
        rel = _rotina(client, _Gateway(PaymentGatewayError("asaas", "timeout")))
        assert len(rel[ROTINA_CARENCIA_EXPIRADA].erros) == 1
        sub = _row(client, "assinaturas", SUB_1)
        assert sub["estado"] == "expirada"  # local expiry still applies
        assert sub["gateway_cancelamento_pendente"] is True

        gateway = _Gateway()
        rel = _rotina(client, gateway)[ROTINA_CANCELAMENTOS_PENDENTES]
        assert rel.examinadas == 1 and rel.erros == []
        assert gateway.cancelados == ["sub_asaas_1"]
        assert _row(client, "assinaturas", SUB_1)["gateway_cancelamento_pendente"] is False

    def test_missing_gateway_key_is_an_error_never_a_silent_success(self):
        client = _client()
        rel = _rotina(client, _Gateway(GatewayNaoConfigurado("Chave do Asaas não configurada.")))
        erros = rel[ROTINA_CARENCIA_EXPIRADA].erros
        assert erros and "Chave do Asaas não configurada." in erros[0]
        assert _row(client, "assinaturas", SUB_1)["gateway_cancelamento_pendente"] is True

    def test_no_free_plan_reports_and_applies_nothing(self):
        client = _client(planos=[_plano(PREMIUM, "Premium", 2700, 2)])
        rel = _rotina(client)[ROTINA_CARENCIA_EXPIRADA]
        assert rel.erros == [f"{SUB_1}: {PLANO_GRATUITO_AUSENTE}"]
        assert _row(client, "assinaturas", SUB_1)["estado"] == "carencia"
        assert _eventos(client) == []

    def test_member_already_on_another_plan_is_left_alone(self):
        outro = "77777777-7777-7777-7777-777777777777"
        client = _client(membro=_membro(plano_id=outro, status="ativo"))
        _rotina(client)
        assert _row(client, "assinaturas", SUB_1)["estado"] == "expirada"
        assert _row(client, "membros", MEMBRO_1)["plano_id"] == outro


class TestEndOfPaidPeriodAfterCancel:
    def test_member_moves_to_free_plan_when_paid_period_ends(self):
        client = _client(
            assinaturas=[_assinatura(estado="cancelada", carencia_ate=None, pago_ate=PASSADO)],
            membro=_membro(status="ativo"),
        )
        rel = _rotina(client)[ROTINA_FIM_DO_PERIODO]
        assert rel.alteradas == [f"{SUB_1}: membro → plano gratuito"]
        assert _row(client, "assinaturas", SUB_1)["estado"] == "cancelada"
        membro = _row(client, "membros", MEMBRO_1)
        assert membro["plano_id"] == GRATUITO and membro["status"] == "ativo"
        (evento,) = _eventos(client)
        assert evento["tipo"] == "plano"

        # idempotent: the next run finds the member already moved
        rel = _rotina(client)[ROTINA_FIM_DO_PERIODO]
        assert rel.alteradas == []
        assert len(_eventos(client)) == 1

    def test_member_keeps_plan_until_paid_period_ends(self):
        client = _client(
            assinaturas=[_assinatura(estado="cancelada", carencia_ate=None, pago_ate=FUTURO)],
            membro=_membro(status="ativo"),
        )
        rel = _rotina(client)[ROTINA_FIM_DO_PERIODO]
        assert rel.examinadas == 0
        assert _row(client, "membros", MEMBRO_1)["plano_id"] == PREMIUM


class TestAutomationsSwitch:
    def test_switched_off_skips_everything_and_writes_nothing(self):
        client = _client(automacoes=False)
        gateway = _Gateway()
        relatorios = asyncio.run(_service(client, gateway).executar_rotina())
        assert [r.nome for r in relatorios] == list(ROTINAS)
        assert all(r.pulado and r.examinadas == 0 for r in relatorios)
        assert _row(client, "assinaturas", SUB_1)["estado"] == "carencia"
        assert _row(client, "membros", MEMBRO_1)["plano_id"] == PREMIUM
        assert gateway.cancelados == [] and _eventos(client) == []


class TestSettings:
    def test_first_read_creates_the_default_row(self):
        client = MockSupabaseClient(schema="community")
        client.set_table_data("configuracoes_cobranca", [])
        service = CobrancaService(client, org_id=ORG_ID)
        assert service.obter_configuracoes() == {"dias_carencia": 5, "automacoes_ativas": True}
        assert len(client.table("configuracoes_cobranca").select("*").execute().data) == 1

    def test_save(self):
        client = MockSupabaseClient(schema="community")
        client.set_table_data("configuracoes_cobranca", [])
        service = CobrancaService(client, org_id=ORG_ID)
        saved = service.salvar_configuracoes(dias_carencia=7, automacoes_ativas=False)
        assert saved == {"dias_carencia": 7, "automacoes_ativas": False}
        assert service.obter_configuracoes() == saved


class TestStateMachineMapping:
    @pytest.mark.parametrize("atual,alvos", [
        ("iniciada", ("ativa",)),
        ("ativa", ("inadimplente", "carencia")),
        ("carencia", ("ativa",)),
        ("carencia", ("expirada",)),
        ("ativa", ("cancelada",)),
    ])
    def test_legal(self, atual, alvos):
        validar_transicao({"id": SUB_1, "estado": atual}, *alvos, now=NOW)

    @pytest.mark.parametrize("atual,alvo", [
        ("ativa", "carencia"),        # no ACTIVE → GRACE edge in the seed
        ("expirada", "ativa"),        # terminal
        ("cancelada", "cancelada"),
        ("pausada", "ativa"),         # outside the seed machine
    ])
    def test_illegal(self, atual, alvo):
        with pytest.raises(TransicaoIlegal):
            validar_transicao({"id": SUB_1, "estado": atual}, alvo, now=NOW)

    def test_cycle_math_clamps_month_end(self):
        assert somar_ciclo(date(2026, 1, 31), "mensal") == date(2026, 2, 28)
        assert somar_ciclo(date(2026, 12, 15), "mensal") == date(2027, 1, 15)
        assert somar_ciclo(date(2028, 2, 29), "anual") == date(2029, 2, 28)

    def test_free_plan_is_the_active_zero_price_with_lowest_ordem(self):
        client = MockSupabaseClient(schema="community")
        client.set_table_data("planos", [
            _plano("a", "Grátis antigo", 0, 5, ativo=False),
            _plano("b", "Grátis B", 0, 3),
            _plano(GRATUITO, "Gratuito", 0, 0),
            _plano(PREMIUM, "Premium", 2700, 0),
        ])
        assert plano_gratuito(client, ORG_ID)["id"] == GRATUITO


class _BrokenService:
    async def executar_rotina(self):
        raise RuntimeError("db down")


class TestScheduler:
    def test_job_runs_the_sweep_and_returns_the_reports(self):
        client = _client()
        result = asyncio.run(rotina_cobranca_job(_service(client)))
        assert [r["nome"] for r in result] == list(ROTINAS)
        assert _row(client, "assinaturas", SUB_1)["estado"] == "expirada"

    def test_job_failure_is_logged_and_returned_not_raised(self):
        assert asyncio.run(rotina_cobranca_job(_BrokenService())) == [{"erro": "db down"}]

    def test_configure_registers_the_hourly_job(self):
        from noctusai_lib.api.scheduler import scheduler

        configure()
        assert any(job.id == ROTINA_COBRANCA_JOB for job in scheduler.get_jobs())
