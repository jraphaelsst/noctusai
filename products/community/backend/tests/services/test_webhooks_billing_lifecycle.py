"""Ninho Vazio billing lifecycle — webhook rows of
projects/ninho-vazio/CONTRACT.md §Billing lifecycle (Asaas).

Runs on `MockSupabaseClient(schema="community")` — schema validation ON, so
every column this slice reads or writes is checked against the migrations
(013 included). Events come from the seed's `make_fake_gateway_event` (the
test seam that skips signature verification) except where the seed parser's
own Asaas mapping is the thing under test.
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import pytest
from noctusai_lib.domain.payments import FakeEventInbox
from noctusai_lib.integrations.payments.webhook_events import (
    make_fake_gateway_event,
    parse_webhook_event,
)
from noctusai_lib.testing import MockSupabaseClient
from postgrest.exceptions import APIError

from app.services.webhooks_service import (
    EVENTO_PAGAMENTO_APOS_ENCERRAMENTO,
    WebhooksService,
)

ORG_ID = "11111111-1111-1111-1111-111111111111"
MEMBRO_1 = "22222222-2222-2222-2222-222222222222"
PLANO_PREMIUM = "33333333-3333-3333-3333-333333333333"
ASSINATURA_1 = "44444444-4444-4444-4444-444444444444"
SUB_ASAAS = "sub_asaas_1"

NOW = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)


def _clock():
    return NOW


def _membro(**over) -> dict:
    base = {
        "id": MEMBRO_1, "org_id": ORG_ID, "nome": "Ana", "email": "ana@x.com",
        "telefone": None, "status": "pendente", "plano_id": None, "origem": "checkout",
        "tags": [], "user_id": None, "observacoes": None, "entrou_em": None,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _assinatura(**over) -> dict:
    base = {
        "id": ASSINATURA_1, "org_id": ORG_ID, "membro_id": MEMBRO_1, "plano_id": PLANO_PREMIUM,
        "gateway": "asaas", "assinatura_externa_id": SUB_ASAAS, "cliente_externo_id": "cus_1",
        "estado": "iniciada", "metodo": "pix", "ciclo": "mensal",
        "iniciada_em": "2026-09-01T00:00:00+00:00", "ativa_em": None, "cancelada_em": None,
        "inadimplente_desde": None, "carencia_ate": None, "pago_ate": None,
        "proxima_cobranca": None, "expirada_em": None, "cancelamento_solicitado_por": None,
        "cancelamento_motivo": None, "gateway_cancelamento_pendente": False,
        "created_at": "2026-09-01T00:00:00+00:00", "updated_at": "2026-09-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _client(*, assinatura=None, membro=None, pagamentos=None, config=None) -> MockSupabaseClient:
    c = MockSupabaseClient(schema="community")
    c.set_table_data("assinaturas", [assinatura or _assinatura()])
    c.set_table_data("membros", [membro or _membro()])
    c.set_table_data("pagamentos", pagamentos or [])
    c.set_table_data("lancamentos", [])
    c.set_table_data("membro_eventos", [])
    c.set_table_data("configuracoes_cobranca", config or [])
    return c


def _service(client, inbox=None) -> WebhooksService:
    return WebhooksService(client, inbox=inbox or FakeEventInbox(), org_id=ORG_ID, clock=_clock)


def _asaas(kind, *, event_id=None, charge="pay_1", value=27.0, due="2026-10-05") -> object:
    return make_fake_gateway_event(
        gateway="asaas", kind=kind, event_id=event_id or f"evt_{kind}_{charge}",
        subscription_id_at_gateway=SUB_ASAAS, charge_id_at_gateway=charge,
        raw={"payment": {"id": charge, "value": value, "dueDate": due, "subscription": SUB_ASAAS}},
    )


def _run(coro):
    return asyncio.run(coro)


def _row(client, table, **eq) -> dict:
    q = client.table(table).select("*")
    for k, v in eq.items():
        q = q.eq(k, v)
    return q.maybe_single().execute().data


def _rows(client, table) -> list[dict]:
    return client.table(table).select("*").execute().data or []


class TestSeedMapsAsaasOverdueToTheGracePath:
    def test_payment_overdue_parses_as_charge_failed(self):
        body = json.dumps({
            "event": "PAYMENT_OVERDUE",
            "payment": {"id": "pay_9", "subscription": SUB_ASAAS, "status": "OVERDUE",
                        "dueDate": "2026-10-05", "value": 27.0},
        }).encode()
        event = parse_webhook_event(
            body, {"asaas-access-token": "tok"}, gateway="asaas", asaas_webhook_token="tok",
        )
        assert event.kind == "charge_failed"
        assert event.subscription_id_at_gateway == SUB_ASAAS


class TestChargePaid:
    def test_first_payment_activates_with_paid_through_dates_and_books_cash(self):
        client = _client()
        _run(_service(client).handle(_asaas("charge_paid")))

        sub = _row(client, "assinaturas", id=ASSINATURA_1)
        assert sub["estado"] == "ativa"
        assert sub["proxima_cobranca"] == "2026-11-05"
        # 2026-11-05 00:00 America/Sao_Paulo, stored in UTC
        assert sub["pago_ate"] == "2026-11-05T03:00:00+00:00"
        assert sub["ativa_em"] == NOW.isoformat()
        assert sub["inadimplente_desde"] is None and sub["carencia_ate"] is None

        membro = _row(client, "membros", id=MEMBRO_1)
        assert membro["status"] == "ativo"
        assert membro["plano_id"] == PLANO_PREMIUM

        pagamento = _rows(client, "pagamentos")[0]
        assert pagamento["estado"] == "pago"
        assert pagamento["valor_centavos"] == 2700

        (lanc,) = _rows(client, "lancamentos")
        assert lanc["tipo"] == "entrada"
        assert lanc["origem"] == "pagamento"
        assert lanc["categoria"] == "assinatura"
        assert lanc["valor_centavos"] == 2700
        assert lanc["pagamento_id"] == pagamento["id"]
        assert lanc["membro_id"] == MEMBRO_1

        (evento,) = _rows(client, "membro_eventos")
        assert evento["tipo"] == "pagamento"
        assert evento["dados"]["pagamento_id"] == pagamento["id"]

    def test_renewal_on_active_sub_advances_dates_keeps_ativa_em(self):
        client = _client(assinatura=_assinatura(
            estado="ativa", ativa_em="2026-09-05T12:00:00+00:00",
            pago_ate="2026-10-05T03:00:00+00:00", proxima_cobranca="2026-10-05",
        ), membro=_membro(status="ativo", plano_id=PLANO_PREMIUM))
        _run(_service(client).handle(_asaas("charge_paid", charge="pay_2")))

        sub = _row(client, "assinaturas", id=ASSINATURA_1)
        assert sub["estado"] == "ativa"
        assert sub["ativa_em"] == "2026-09-05T12:00:00+00:00"
        assert sub["proxima_cobranca"] == "2026-11-05"
        assert len(_rows(client, "lancamentos")) == 1

    def test_late_webhook_for_older_charge_never_moves_paid_through_back(self):
        client = _client(assinatura=_assinatura(
            estado="ativa", pago_ate="2026-12-05T03:00:00+00:00", proxima_cobranca="2026-12-05",
        ))
        _run(_service(client).handle(_asaas("charge_paid", charge="pay_old", due="2026-10-05")))
        sub = _row(client, "assinaturas", id=ASSINATURA_1)
        assert sub["pago_ate"] == "2026-12-05T03:00:00+00:00"
        assert sub["proxima_cobranca"] == "2026-12-05"

    def test_payment_during_grace_reactivates(self):
        client = _client(
            assinatura=_assinatura(
                estado="carencia", inadimplente_desde="2026-10-05T12:00:00+00:00",
                carencia_ate="2026-10-10T12:00:00+00:00",
            ),
            membro=_membro(status="atrasado", plano_id=PLANO_PREMIUM),
        )
        _run(_service(client).handle(_asaas("charge_paid")))

        sub = _row(client, "assinaturas", id=ASSINATURA_1)
        assert sub["estado"] == "ativa"
        assert sub["inadimplente_desde"] is None
        assert sub["carencia_ate"] is None
        assert _row(client, "membros", id=MEMBRO_1)["status"] == "ativo"

    def test_confirmed_then_received_for_same_charge_books_one_lancamento(self):
        """Asaas fires PAYMENT_CONFIRMED and PAYMENT_RECEIVED for one card
        charge — two event ids, so the inbox lets both through."""
        client = _client()
        service = _service(client)
        _run(service.handle(_asaas("charge_paid", event_id="evt_confirmed")))
        _run(service.handle(_asaas("charge_paid", event_id="evt_received")))

        assert len(_rows(client, "pagamentos")) == 1
        assert len(_rows(client, "lancamentos")) == 1
        assert [e["tipo"] for e in _rows(client, "membro_eventos")] == ["pagamento"]

    def test_exact_replay_is_deduped_by_the_inbox(self):
        client = _client()
        inbox = FakeEventInbox()
        _run(_service(client, inbox).handle(_asaas("charge_paid")))
        _run(_service(client, inbox).handle(_asaas("charge_paid")))
        assert len(_rows(client, "lancamentos")) == 1

    @pytest.mark.parametrize("estado", ["expirada", "cancelada"])
    def test_payment_after_end_is_stored_and_booked_but_never_reactivates(self, estado):
        client = _client(
            assinatura=_assinatura(estado=estado),
            membro=_membro(status="ativo", plano_id="free-plan"),
        )
        _run(_service(client).handle(_asaas("charge_paid")))

        assert _row(client, "assinaturas", id=ASSINATURA_1)["estado"] == estado
        membro = _row(client, "membros", id=MEMBRO_1)
        assert membro["plano_id"] == "free-plan"
        assert _rows(client, "pagamentos")[0]["estado"] == "pago"
        assert len(_rows(client, "lancamentos")) == 1
        (evento,) = _rows(client, "membro_eventos")
        assert evento["tipo"] == "sistema"
        assert evento["descricao"] == EVENTO_PAGAMENTO_APOS_ENCERRAMENTO


class TestChargeFailedGrace:
    def test_overdue_on_active_moves_to_grace_keeping_access(self):
        client = _client(
            assinatura=_assinatura(estado="ativa"),
            membro=_membro(status="ativo", plano_id=PLANO_PREMIUM),
        )
        _run(_service(client).handle(_asaas("charge_failed")))

        sub = _row(client, "assinaturas", id=ASSINATURA_1)
        assert sub["estado"] == "carencia"
        assert sub["inadimplente_desde"] == NOW.isoformat()
        assert sub["carencia_ate"] == (NOW + timedelta(days=5)).isoformat()
        membro = _row(client, "membros", id=MEMBRO_1)
        assert membro["status"] == "atrasado"
        assert membro["plano_id"] == PLANO_PREMIUM  # access KEPT
        (evento,) = _rows(client, "membro_eventos")
        assert evento["tipo"] == "assinatura"
        # settings row created on first read with the default grace
        assert _rows(client, "configuracoes_cobranca")[0]["dias_carencia"] == 5

    def test_grace_length_comes_from_settings(self):
        client = _client(
            assinatura=_assinatura(estado="ativa"),
            config=[{"org_id": ORG_ID, "dias_carencia": 10, "automacoes_ativas": True}],
        )
        _run(_service(client).handle(_asaas("charge_failed")))
        sub = _row(client, "assinaturas", id=ASSINATURA_1)
        assert sub["carencia_ate"] == (NOW + timedelta(days=10)).isoformat()

    def test_second_failure_keeps_the_first_inadimplente_desde(self):
        first = "2026-10-01T12:00:00+00:00"
        client = _client(assinatura=_assinatura(
            estado="carencia", inadimplente_desde=first, carencia_ate="2026-10-06T12:00:00+00:00",
        ))
        _run(_service(client).handle(_asaas("charge_failed", charge="pay_2")))
        sub = _row(client, "assinaturas", id=ASSINATURA_1)
        assert sub["inadimplente_desde"] == first
        assert sub["carencia_ate"] == "2026-10-06T12:00:00+00:00"

    def test_legacy_inadimplente_row_enters_grace(self):
        client = _client(assinatura=_assinatura(estado="inadimplente"))
        _run(_service(client).handle(_asaas("charge_failed")))
        assert _row(client, "assinaturas", id=ASSINATURA_1)["estado"] == "carencia"

    def test_illegal_move_is_logged_and_not_applied(self, caplog):
        """INCOMPLETE → PAST_DUE is not a seed edge: a first charge that
        never succeeded gets no grace."""
        client = _client(assinatura=_assinatura(estado="iniciada"))
        with caplog.at_level(logging.ERROR, logger="app.services.webhooks_service"):
            _run(_service(client).handle(_asaas("charge_failed")))
        assert _row(client, "assinaturas", id=ASSINATURA_1)["estado"] == "iniciada"
        assert _row(client, "membros", id=MEMBRO_1)["status"] == "pendente"
        assert any("transição ilegal iniciada → inadimplente" in r.getMessage() for r in caplog.records)
        # the failed charge itself is still recorded
        assert _rows(client, "pagamentos")[0]["estado"] == "falhou"

    def test_stale_overdue_after_payment_is_ignored(self):
        client = _client(
            assinatura=_assinatura(estado="ativa"),
            pagamentos=[{
                "id": "55555555-5555-5555-5555-555555555555", "org_id": ORG_ID,
                "assinatura_id": ASSINATURA_1, "membro_id": MEMBRO_1, "gateway": "asaas",
                "cobranca_externa_id": "pay_1", "valor_centavos": 2700, "metodo": "pix",
                "estado": "pago", "pago_em": "2026-10-05T12:00:00+00:00", "vencimento": None,
                "url_fatura": None, "pix_payload": None, "pix_imagem_base64": None,
                "created_at": "2026-10-05T12:00:00+00:00", "updated_at": "2026-10-05T12:00:00+00:00",
            }],
        )
        _run(_service(client).handle(_asaas("charge_failed")))
        assert _row(client, "assinaturas", id=ASSINATURA_1)["estado"] == "ativa"
        assert _rows(client, "pagamentos")[0]["estado"] == "pago"


class TestChargeRefunded:
    def test_refund_books_one_saida_and_leaves_status_alone(self):
        client = _client(
            assinatura=_assinatura(estado="ativa"),
            membro=_membro(status="ativo", plano_id=PLANO_PREMIUM),
        )
        service = _service(client)
        _run(service.handle(_asaas("charge_paid")))
        _run(service.handle(_asaas("charge_refunded", event_id="evt_refund_1")))
        _run(service.handle(_asaas("charge_refunded", event_id="evt_refund_2")))

        pagamento = _rows(client, "pagamentos")[0]
        assert pagamento["estado"] == "estornado"
        lancs = _rows(client, "lancamentos")
        saidas = [lanc for lanc in lancs if lanc["tipo"] == "saida"]
        assert len(lancs) == 2 and len(saidas) == 1
        assert saidas[0]["origem"] == "estorno"
        assert saidas[0]["categoria"] == "estorno"
        assert saidas[0]["estorno_de"] == pagamento["id"]
        assert saidas[0]["pagamento_id"] is None
        assert _row(client, "assinaturas", id=ASSINATURA_1)["estado"] == "ativa"
        assert _row(client, "membros", id=MEMBRO_1)["status"] == "ativo"
        assert [e["tipo"] for e in _rows(client, "membro_eventos")] == ["pagamento", "pagamento"]


class _UniqueRaceClient:
    """From-scratch DB-boundary double: `lancamentos` reads see nothing and
    inserts raise the given Postgres error — what a concurrent delivery that
    booked the same charge between our read and our write looks like."""

    def __init__(self, inner: MockSupabaseClient, *, code: str) -> None:
        self._inner = inner
        self._code = code

    def table(self, name):
        if name == "lancamentos":
            return _RaisingLancamentos(self._code)
        return self._inner.table(name)


class _RaisingLancamentos:
    def __init__(self, code):
        self._code = code
        self._inserting = False

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def insert(self, _row):
        self._inserting = True
        return self

    def execute(self):
        if not self._inserting:
            return type("R", (), {"data": []})()
        raise APIError({"code": self._code, "message": "simulated", "details": "", "hint": ""})


class TestLancamentoUniqueConflict:
    def test_unique_violation_is_handled_as_already_booked(self):
        inner = _client()
        client = _UniqueRaceClient(inner, code="23505")
        _run(WebhooksService(client, inbox=FakeEventInbox(), org_id=ORG_ID, clock=_clock).handle(
            _asaas("charge_paid")
        ))
        assert _row(inner, "assinaturas", id=ASSINATURA_1)["estado"] == "ativa"

    def test_any_other_database_error_propagates_and_releases_the_claim(self):
        inner = _client()
        inbox = FakeEventInbox()
        client = _UniqueRaceClient(inner, code="23503")
        event = _asaas("charge_paid")
        with pytest.raises(APIError):
            _run(WebhooksService(client, inbox=inbox, org_id=ORG_ID, clock=_clock).handle(event))
        assert inbox.claim(gateway=event.gateway, event_id=event.event_id) is True
