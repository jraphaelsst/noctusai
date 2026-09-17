"""Unit tests for `WebhooksService` — contract §Webhooks, amendments
A1, A4, A5, A8, A11, A15.

Uses `noctusai_lib.integrations.payments.webhook_events.make_fake_gateway_event`
(the seed's dev/test seam — bypasses signature verification entirely,
never call it from a real route) + `noctusai_lib.domain.payments.
FakeEventInbox`. `_BrokenClient` is a from-scratch test double
substituting the DB I/O boundary (NOT a monkeypatch of this product's
own code) used ONLY to prove amendment A5's release-then-re-raise.
"""
import asyncio

from noctusai_lib.domain.payments import FakeEventInbox
from noctusai_lib.integrations.payments.webhook_events import make_fake_gateway_event
from noctusai_lib.testing import MockSupabaseClient

from app.services.webhooks_service import WebhooksService

ORG_ID = "11111111-1111-1111-1111-111111111111"
MEMBRO_1 = "22222222-2222-2222-2222-222222222222"
PLANO_1 = "33333333-3333-3333-3333-333333333333"
ASSINATURA_1 = "44444444-4444-4444-4444-444444444444"


def _membro_row(**over) -> dict:
    base = {
        "id": MEMBRO_1, "org_id": ORG_ID, "nome": "Ana", "email": "ana@x.com",
        "telefone": "+5511999999999", "status": "pendente", "plano_id": None,
        "origem": "checkout", "tags": [], "user_id": None, "observacoes": None,
        "entrou_em": None, "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _assinatura_row(**over) -> dict:
    base = {
        "id": ASSINATURA_1, "org_id": ORG_ID, "membro_id": MEMBRO_1, "plano_id": PLANO_1,
        "gateway": "stripe", "assinatura_externa_id": None, "cliente_externo_id": "cus_1",
        "estado": "iniciada", "metodo": "cartao", "ciclo": "mensal",
        "iniciada_em": "2026-01-01T00:00:00+00:00", "ativa_em": None, "cancelada_em": None,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _client(*, assinatura_rows=None, membro_rows=None, pagamento_rows=None) -> MockSupabaseClient:
    c = MockSupabaseClient()
    c.set_table_data("assinaturas", assinatura_rows if assinatura_rows is not None else [_assinatura_row()])
    c.set_table_data("membros", membro_rows if membro_rows is not None else [_membro_row()])
    c.set_table_data("pagamentos", pagamento_rows if pagamento_rows is not None else [])
    return c


def _run(coro):
    return asyncio.run(coro)


class _BrokenClient:
    """Wraps a real `MockSupabaseClient`, EXCEPT `.table(raise_on_table)`
    raises immediately — a from-scratch test double for the DB I/O
    boundary, used only to prove `WebhooksService.handle()` releases the
    inbox claim before re-raising (amendment A5)."""

    def __init__(self, inner: MockSupabaseClient, *, raise_on_table: str) -> None:
        self._inner = inner
        self._raise_on_table = raise_on_table

    def table(self, name: str):
        if name == self._raise_on_table:
            raise RuntimeError("simulated DB failure")
        return self._inner.table(name)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class TestAmendmentA1FirstPaymentActivation:
    def test_charge_paid_activates_first_payment(self):
        client = _client()
        service = WebhooksService(client, inbox=FakeEventInbox(), org_id=ORG_ID)
        event = make_fake_gateway_event(
            gateway="stripe", kind="charge_paid",
            external_reference=ASSINATURA_1, subscription_id_at_gateway="sub_1",
            charge_id_at_gateway="ch_1",
            raw={"data": {"object": {"amount_paid": 9900}}},
        )
        _run(service.handle(event))

        assinatura = client.table("assinaturas").select("*").eq(
            "id", ASSINATURA_1
        ).maybe_single().execute().data
        assert assinatura["estado"] == "ativa"
        assert assinatura["assinatura_externa_id"] == "sub_1"
        assert assinatura["ativa_em"] is not None

        membro = client.table("membros").select("*").eq(
            "id", MEMBRO_1
        ).maybe_single().execute().data
        assert membro["status"] == "ativo"
        assert membro["plano_id"] == PLANO_1
        assert membro["entrou_em"] is not None

        pagamentos = client.table("pagamentos").select("*").eq(
            "assinatura_id", ASSINATURA_1
        ).execute().data
        assert len(pagamentos) == 1
        assert pagamentos[0]["estado"] == "pago"
        assert pagamentos[0]["valor_centavos"] == 9900

    def test_charge_paid_for_unknown_assinatura_is_noop_200(self):
        client = _client()
        service = WebhooksService(client, inbox=FakeEventInbox(), org_id=ORG_ID)
        event = make_fake_gateway_event(
            gateway="stripe", kind="charge_paid",
            external_reference="does-not-exist", charge_id_at_gateway="ch_x",
        )
        _run(service.handle(event))  # must not raise


class TestAmendmentA4IllegalTransitions:
    def test_ordering_1_charge_paid_after_local_cancellation_is_noop(self):
        """A `charge_paid` arriving AFTER the local subscription is
        already `cancelada` records the payment but changes NO
        subscription/member status — never a silent re-activation."""
        client = _client(
            assinatura_rows=[_assinatura_row(
                estado="cancelada", assinatura_externa_id="sub_1",
                cancelada_em="2026-01-02T00:00:00+00:00",
            )],
        )
        service = WebhooksService(client, inbox=FakeEventInbox(), org_id=ORG_ID)
        event = make_fake_gateway_event(
            gateway="stripe", kind="charge_paid", external_reference=ASSINATURA_1,
            subscription_id_at_gateway="sub_1", charge_id_at_gateway="ch_2",
            raw={"data": {"object": {"amount_paid": 9900}}},
        )
        _run(service.handle(event))  # must not raise / never 5xx

        assinatura = client.table("assinaturas").select("*").eq(
            "id", ASSINATURA_1
        ).maybe_single().execute().data
        assert assinatura["estado"] == "cancelada"

        membro = client.table("membros").select("*").eq(
            "id", MEMBRO_1
        ).maybe_single().execute().data
        assert membro["status"] == "pendente"  # unchanged

        pagamentos = client.table("pagamentos").select("*").eq(
            "assinatura_id", ASSINATURA_1
        ).execute().data
        assert len(pagamentos) == 1
        assert pagamentos[0]["estado"] == "pago"  # still recorded

    def test_ordering_2_subscription_cancelled_then_late_charge_paid(self):
        """The OTHER ordering: `subscription_updated=cancelled` lands
        first (a legal ativa->cancelada move), then a late `charge_paid`
        arrives — the member must stay cancelled, never resurrected."""
        client = _client(
            assinatura_rows=[_assinatura_row(
                estado="ativa", assinatura_externa_id="sub_1",
                ativa_em="2026-01-01T00:00:00+00:00",
            )],
            membro_rows=[_membro_row(status="ativo", plano_id=PLANO_1)],
        )
        service = WebhooksService(client, inbox=FakeEventInbox(), org_id=ORG_ID)

        cancel_event = make_fake_gateway_event(
            gateway="stripe", kind="subscription_updated", external_reference=ASSINATURA_1,
            subscription_id_at_gateway="sub_1", subscription_status="canceled",
        )
        _run(service.handle(cancel_event))
        assinatura = client.table("assinaturas").select("*").eq(
            "id", ASSINATURA_1
        ).maybe_single().execute().data
        assert assinatura["estado"] == "cancelada"
        membro = client.table("membros").select("*").eq(
            "id", MEMBRO_1
        ).maybe_single().execute().data
        assert membro["status"] == "cancelado"

        late_paid_event = make_fake_gateway_event(
            gateway="stripe", kind="charge_paid", external_reference=ASSINATURA_1,
            subscription_id_at_gateway="sub_1", charge_id_at_gateway="ch_late",
            raw={"data": {"object": {"amount_paid": 9900}}},
        )
        _run(service.handle(late_paid_event))  # must not raise

        assinatura2 = client.table("assinaturas").select("*").eq(
            "id", ASSINATURA_1
        ).maybe_single().execute().data
        assert assinatura2["estado"] == "cancelada"
        membro2 = client.table("membros").select("*").eq(
            "id", MEMBRO_1
        ).maybe_single().execute().data
        assert membro2["status"] == "cancelado"  # never silently re-activated


class TestAmendmentA5ReleaseOnFailure:
    def test_handler_raising_after_claim_leaves_event_reclaimable(self):
        client = _BrokenClient(_client(), raise_on_table="membros")
        inbox = FakeEventInbox()
        service = WebhooksService(client, inbox=inbox, org_id=ORG_ID)
        event = make_fake_gateway_event(
            gateway="stripe", kind="charge_paid", external_reference=ASSINATURA_1,
            subscription_id_at_gateway="sub_1", charge_id_at_gateway="ch_1",
        )
        raised = False
        try:
            _run(service.handle(event))
        except RuntimeError:
            raised = True
        assert raised, "expected the simulated DB failure to propagate"

        # Re-claimable: a retry delivery of the SAME event is NOT
        # silently treated as a duplicate.
        assert inbox.claim(gateway="stripe", event_id=event.event_id) is True

    def test_duplicate_delivery_is_a_proven_noop(self):
        client = _client()
        inbox = FakeEventInbox()
        service = WebhooksService(client, inbox=inbox, org_id=ORG_ID)
        event = make_fake_gateway_event(
            gateway="stripe", kind="charge_paid", external_reference=ASSINATURA_1,
            subscription_id_at_gateway="sub_1", charge_id_at_gateway="ch_1",
        )
        _run(service.handle(event))
        pagamentos_after_first = client.table("pagamentos").select("*").execute().data
        assert len(pagamentos_after_first) == 1

        # Re-deliver the identical event — claim() now returns False.
        _run(service.handle(event))
        pagamentos_after_second = client.table("pagamentos").select("*").execute().data
        assert len(pagamentos_after_second) == 1  # unchanged — proven no-op


class TestAmendmentA8PausadaNeverWebhookDriven:
    def test_subscription_updated_never_moves_a_paused_subscription(self):
        client = _client(
            assinatura_rows=[_assinatura_row(estado="pausada", assinatura_externa_id="sub_1")],
        )
        service = WebhooksService(client, inbox=FakeEventInbox(), org_id=ORG_ID)
        event = make_fake_gateway_event(
            gateway="stripe", kind="subscription_updated", external_reference=ASSINATURA_1,
            subscription_id_at_gateway="sub_1", subscription_status="active",
        )
        _run(service.handle(event))
        assinatura = client.table("assinaturas").select("*").eq(
            "id", ASSINATURA_1
        ).maybe_single().execute().data
        assert assinatura["estado"] == "pausada"  # untouched


class TestAmendmentA11PixImageNulledOnPago:
    def test_pix_imagem_base64_nulled_once_pago(self):
        client = _client(
            assinatura_rows=[_assinatura_row(gateway="asaas", assinatura_externa_id="sub_asaas_1", metodo="pix")],
            pagamento_rows=[{
                "id": "pag-1", "org_id": ORG_ID, "assinatura_id": ASSINATURA_1,
                "membro_id": MEMBRO_1, "gateway": "asaas", "cobranca_externa_id": "pay_1",
                "valor_centavos": 9900, "metodo": "pix", "estado": "pendente",
                "pago_em": None, "vencimento": None, "url_fatura": "https://asaas.test/inv/pay_1",
                "pix_payload": "00020126...", "pix_imagem_base64": "base64-image-data",
                "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
            }],
        )
        service = WebhooksService(client, inbox=FakeEventInbox(), org_id=ORG_ID)
        event = make_fake_gateway_event(
            gateway="asaas", kind="charge_paid", external_reference=ASSINATURA_1,
            subscription_id_at_gateway="sub_asaas_1", charge_id_at_gateway="pay_1",
            raw={"payment": {"value": "99.00"}},
        )
        _run(service.handle(event))

        pagamento = client.table("pagamentos").select("*").eq(
            "id", "pag-1"
        ).maybe_single().execute().data
        assert pagamento["estado"] == "pago"
        assert pagamento["pix_imagem_base64"] is None


class TestChargeRefundedNoStatusChange:
    def test_charge_refunded_never_changes_member_or_subscription_status(self):
        client = _client(
            assinatura_rows=[_assinatura_row(estado="ativa", assinatura_externa_id="sub_1")],
            membro_rows=[_membro_row(status="ativo", plano_id=PLANO_1)],
        )
        service = WebhooksService(client, inbox=FakeEventInbox(), org_id=ORG_ID)
        event = make_fake_gateway_event(
            gateway="stripe", kind="charge_refunded", external_reference=ASSINATURA_1,
            subscription_id_at_gateway="sub_1", charge_id_at_gateway="ch_refund_1",
        )
        _run(service.handle(event))

        pagamentos = client.table("pagamentos").select("*").eq(
            "assinatura_id", ASSINATURA_1
        ).execute().data
        assert len(pagamentos) == 1
        assert pagamentos[0]["estado"] == "estornado"

        assinatura = client.table("assinaturas").select("*").eq(
            "id", ASSINATURA_1
        ).maybe_single().execute().data
        assert assinatura["estado"] == "ativa"  # unchanged — "a manager decides"

        membro = client.table("membros").select("*").eq(
            "id", MEMBRO_1
        ).maybe_single().execute().data
        assert membro["status"] == "ativo"  # unchanged
