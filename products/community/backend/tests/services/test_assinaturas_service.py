"""Unit tests for `AssinaturasService.cancelar` — amendment A14 (cancel
is ordered and never swallowed).

`FakePaymentGateway` injected via constructor DI (`gateway_factory=`) —
the seam `assinaturas_router.py`'s default wiring can't exercise without
a real Stripe/Asaas subscription actually existing in the Fake's own
bookkeeping.
"""
import asyncio

from noctusai_lib.integrations.payments import FakePaymentGateway
from noctusai_lib.integrations.payments.types import Money, SubscriptionRequest
from noctusai_lib.testing import MockSupabaseClient

from app.services.assinaturas_service import AssinaturasService, AssinaturasServiceError

ORG_ID = "11111111-1111-1111-1111-111111111111"
MEMBRO_1 = "22222222-2222-2222-2222-222222222222"
PLANO_1 = "33333333-3333-3333-3333-333333333333"
ASSINATURA_1 = "44444444-4444-4444-4444-444444444444"


def _run(coro):
    return asyncio.run(coro)


def _membro_row(**over) -> dict:
    base = {
        "id": MEMBRO_1, "org_id": ORG_ID, "nome": "Ana", "email": "ana@x.com",
        "telefone": "+5511999999999", "status": "ativo", "plano_id": PLANO_1,
        "origem": "checkout", "tags": [], "user_id": None, "observacoes": None,
        "entrou_em": "2026-01-01T00:00:00+00:00",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _assinatura_row(**over) -> dict:
    base = {
        "id": ASSINATURA_1, "org_id": ORG_ID, "membro_id": MEMBRO_1, "plano_id": PLANO_1,
        "gateway": "stripe", "assinatura_externa_id": None, "cliente_externo_id": None,
        "estado": "ativa", "metodo": "cartao", "ciclo": "mensal",
        "iniciada_em": "2026-01-01T00:00:00+00:00", "ativa_em": "2026-01-01T00:00:00+00:00",
        "cancelada_em": None,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _client(*, assinatura_rows=None, membro_rows=None) -> MockSupabaseClient:
    c = MockSupabaseClient()
    c.set_table_data("assinaturas", assinatura_rows if assinatura_rows is not None else [_assinatura_row()])
    c.set_table_data("membros", membro_rows if membro_rows is not None else [_membro_row()])
    return c


class TestCancelHappyPath:
    def test_cancels_at_gateway_then_locally(self):
        fake_gateway = FakePaymentGateway()
        customer = fake_gateway.ensure_customer(external_reference=MEMBRO_1, email="ana@x.com", name="Ana")
        subscription = fake_gateway.create_subscription(SubscriptionRequest(
            external_reference=ASSINATURA_1, customer_id_at_gateway=customer.id_at_gateway,
            price=Money(9900, "BRL"),
        ))
        client = _client(assinatura_rows=[_assinatura_row(assinatura_externa_id=subscription.id_at_gateway)])
        service = AssinaturasService(client, org_id=ORG_ID, gateway_factory=lambda gw: fake_gateway)

        result = _run(service.cancelar(assinatura_id=ASSINATURA_1, motivo="pediu"))
        assert result["estado"] == "cancelada"

        membro = client.table("membros").select("*").eq("id", MEMBRO_1).maybe_single().execute().data
        assert membro["status"] == "cancelado"


class TestAmendmentA14GatewayFailure:
    def test_gateway_cancel_failure_returns_502_and_changes_nothing_locally(self):
        client = _client()
        broken_gateway = FakePaymentGateway()
        # never registered "sub-does-not-exist" with this Fake instance
        # -> cancel_subscription raises PaymentGatewayError, mirroring a
        # real gateway rejecting an unknown id.
        client.table("assinaturas").update(
            {"assinatura_externa_id": "sub-does-not-exist"}
        ).eq("id", ASSINATURA_1).execute()
        service = AssinaturasService(client, org_id=ORG_ID, gateway_factory=lambda gw: broken_gateway)

        try:
            _run(service.cancelar(assinatura_id=ASSINATURA_1, motivo="pediu"))
            assert False, "expected AssinaturasServiceError"
        except AssinaturasServiceError as exc:
            assert exc.status_code == 502

        assinatura = client.table("assinaturas").select("*").eq(
            "id", ASSINATURA_1
        ).maybe_single().execute().data
        assert assinatura["estado"] == "ativa"  # unchanged — never swallowed

        membro = client.table("membros").select("*").eq("id", MEMBRO_1).maybe_single().execute().data
        assert membro["status"] == "ativo"  # unchanged


class TestCancelNotFound:
    def test_unknown_assinatura_404(self):
        client = _client()
        service = AssinaturasService(client, org_id=ORG_ID)
        try:
            _run(service.cancelar(assinatura_id="does-not-exist", motivo="x"))
            assert False
        except AssinaturasServiceError as exc:
            assert exc.status_code == 404
