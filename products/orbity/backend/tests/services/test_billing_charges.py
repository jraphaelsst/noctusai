"""Gateway charges for contract receivables: the plan, the contracts-billing seam, the worker.

Fakes (``FakeCheckoutGateway`` / ``FakeHostedCheckout`` / ``FakeChargeOperations``) and ``MockSupabaseClient`` only -- no
patching. The properties pinned here are the ones that lose money when they break: no double charge on a retry, a stuck
row is recovered, an honest ``skipped`` when no gateway is configured, a kept charge survives a contract termination, a
cancelled charge is cancelled at the gateway too.
"""
from datetime import date, datetime, timezone

import pytest
from noctusai_lib.domain.commerce.gateway import FakeCheckoutGateway
from noctusai_lib.domain.contracts import FakeContractsBilling
from noctusai_lib.integrations.payments.checkout import FakeHostedCheckout
from noctusai_lib.integrations.payments.errors import PaymentGatewayError
from noctusai_lib.integrations.payments.types import Money
from noctusai_lib.testing import MockSupabaseClient

from app.services import billing_charges as bc

ORG = "00000000-0000-0000-0000-000000000abc"
CLIENT = "c1000000-0000-4000-8000-000000000001"
CONTRACT = "d1000000-0000-4000-8000-000000000001"
ENTRY = "e1000000-0000-4000-8000-000000000001"
TODAY = date(2026, 10, 16)


def _client(**over):
    base = {"id": CLIENT, "org_id": ORG, "name": "Acme", "legal_name": "Acme Comércio LTDA", "document": "11222333000181",
            "email": "fin@acme.com", "active": True, "default_billing_type": "boleto", "billing_automation_enabled": True}
    base.update(over)
    return base


def _entry(**over):
    base = {"id": ENTRY, "org_id": ORG, "direction": "receivable", "status": "open", "description": "Contrato — 10/2026",
            "amount_cents": 150_000, "settled_cents": 0, "due_date": "2026-10-20", "competence_month": "2026-10-01",
            "source": "contracts", "source_ref": f"{CONTRACT}:2026-10-20"}
    base.update(over)
    return base


def _charge(**over):
    base = {"id": "ch-1", "org_id": ORG, "entry_id": ENTRY, "client_id": CLIENT, "contract_id": CONTRACT, "gateway": "asaas",
            "billing_method": "boleto", "external_ref": f"orbity:{ENTRY}", "external_id": None, "invoice_url": None,
            "pix_payload": None, "generation_status": "generating", "generation_attempts": 1, "last_error": None,
            "preserved_after_deactivation": False, "gateway_cancel_status": None, "locked_at": "2026-10-16T12:00:00+00:00"}
    base.update(over)
    return base


def _db(*, client=None, entry=None, charge=None):
    db = MockSupabaseClient(schema="orbity")
    db.set_table_data("clients", [client or _client()])
    db.set_table_data("fin_entries", [entry or _entry()])
    db.set_table_data("billing_charges", [charge] if charge is not None else [])
    db.set_table_data("ctr_contracts", [{"id": CONTRACT, "org_id": ORG, "party_id": CLIENT, "party_name": "Acme Comércio LTDA"}])
    return db


def _row(db):
    return db.table("billing_charges")._data[0]


# ── the plan ────────────────────────────────────────────────────────────────────────────────────────────────


class TestPlan:
    def test_a_boleto_client_with_automation_and_a_gateway_is_queued(self):
        plan = bc.plan_charge(_client(), gateway_ready=True)
        assert (plan.status, plan.method, plan.reason) == ("queued", "boleto", None)

    def test_pix_maps_to_pix(self):
        assert bc.plan_charge(_client(default_billing_type="PIX"), True).method == "pix"

    def test_no_gateway_is_an_honest_skip_with_the_reason(self):
        plan = bc.plan_charge(_client(), gateway_ready=False)
        assert plan.status == "skipped" and "não configurado" in plan.reason

    @pytest.mark.parametrize("kind", ["cartao", "transferencia", "", None])
    def test_a_method_that_is_not_gateway_shaped_is_skipped(self, kind):
        plan = bc.plan_charge(_client(default_billing_type=kind), True)
        assert plan.status == "skipped" and "não usa gateway" in plan.reason

    def test_automation_off_is_skipped(self):
        assert bc.plan_charge(_client(billing_automation_enabled=False), True).status == "skipped"

    def test_no_client_is_skipped(self):
        assert bc.plan_charge(None, True).status == "skipped"


def test_backoff_follows_the_upstream_schedule_and_caps():
    assert [bc.backoff_minutes(n) for n in range(1, 8)] == [0, 2, 10, 30, 120, 120, 120]


def test_the_contract_id_is_read_from_the_source_ref():
    assert bc.contract_id_of(f"{CONTRACT}:2026-10-20") == CONTRACT
    assert bc.contract_id_of(f"{CONTRACT.upper()}:i1:excess") == CONTRACT
    assert bc.contract_id_of("orbity-extra:abc") is None
    assert bc.contract_id_of(None) is None


# ── the contracts-billing seam ──────────────────────────────────────────────────────────────────────────────


class TestOrbityContractsBilling:
    def _billing(self, db, *, configured=True):
        return bc.OrbityContractsBilling(db, gateway=FakeCheckoutGateway(configured=configured), inner=FakeContractsBilling())

    def _book(self, billing):
        return billing.book_receivable(
            ORG, source_ref=f"{CONTRACT}:2026-10-20", description="Contrato — 10/2026", counterparty_name="Acme",
            counterparty_doc=None, amount_cents=150_000, competence_month=date(2026, 10, 1), due_date=date(2026, 10, 20))

    def test_booking_records_a_queued_charge_for_the_contracts_client(self):
        db = _db()
        entry_id = self._book(self._billing(db))
        row = _row(db)
        assert row["entry_id"] == entry_id and row["client_id"] == CLIENT and row["contract_id"] == CONTRACT
        assert row["generation_status"] == "queued" and row["billing_method"] == "boleto"
        assert row["external_ref"] == f"orbity:{entry_id}"

    def test_without_a_gateway_the_receivable_stays_plain_and_says_why(self):
        db = _db()
        self._book(self._billing(db, configured=False))
        row = _row(db)
        assert row["generation_status"] == "skipped" and "não configurado" in row["last_error"]
        assert row["gateway"] is None

    def test_rebooking_the_same_period_does_not_create_a_second_charge_row(self):
        db = _db()
        billing = self._billing(db)
        self._book(billing)
        self._book(billing)
        assert len(db.table("billing_charges")._data) == 1

    def test_a_kept_receivable_is_not_cancelled_by_a_contract_termination(self):
        inner = FakeContractsBilling()
        db = _db(charge=_charge(generation_status="generated", preserved_after_deactivation=True, external_id="pay_1"))
        billing = bc.OrbityContractsBilling(db, gateway=FakeCheckoutGateway(), inner=inner)
        inner.book_receivable(ORG, source_ref=f"{CONTRACT}:2026-10-20")
        # the finance lookup the wrapper does is by (contracts, source_ref) -> the entry above
        out = billing.cancel_receivable(ORG, source_ref=f"{CONTRACT}:2026-10-20")
        assert out == "kept_settled"
        assert inner.entries[(ORG, f"{CONTRACT}:2026-10-20")]["status"] == "open"
        assert _row(db)["gateway_cancel_status"] is None


def test_cancelling_a_charge_that_exists_at_the_gateway_queues_the_gateway_cancel():
    db = _db(charge=_charge(generation_status="generated", external_id="pay_1"))
    bc.mark_cancelled(bc.ChargeStore(db), ORG, _row(db))
    assert _row(db)["gateway_cancel_status"] == "pending"


def test_cancelling_a_charge_that_never_reached_the_gateway_stops_it_being_generated():
    db = _db(charge=_charge(generation_status="queued"))
    bc.mark_cancelled(bc.ChargeStore(db), ORG, _row(db))
    assert _row(db)["generation_status"] == "skipped" and _row(db)["gateway_cancel_status"] is None


# ── the worker ──────────────────────────────────────────────────────────────────────────────────────────────


def _gateway(checkout=None, configured=True):
    return FakeCheckoutGateway(configured=configured, checkout=checkout or FakeHostedCheckout())


class TestProcessOne:
    def test_generates_the_charge_with_the_idempotency_reference_and_the_legal_name(self):
        db = _db(charge=_charge())
        gw = _gateway()
        out = bc.process_one(db, gw, _row(db), today=TODAY)
        assert out["status"] == "generated"
        (_, req), = [c for c in gw.checkout.calls if c[0] == "create_checkout"]
        assert req.external_reference == f"orbity:{ENTRY}"        # ALWAYS sent
        assert req.reuse_existing is True                         # ... and the gateway is asked to reuse a live charge
        assert req.name == "Acme Comércio LTDA"                   # the Razão Social is what goes to the gateway
        assert req.tax_id == "11222333000181" and req.price == Money(150_000)
        assert req.due_date == date(2026, 10, 20) and req.billing_method == "boleto"
        row = _row(db)
        assert row["generation_status"] == "generated" and row["external_id"] and row["invoice_url"]
        assert row["locked_at"] is None and row["last_error"] is None

    def test_a_past_due_date_is_clamped_to_today(self):
        db = _db(entry=_entry(due_date="2026-09-01"), charge=_charge())
        gw = _gateway()
        bc.process_one(db, gw, _row(db), today=TODAY)
        assert gw.checkout.calls[-1][1].due_date == TODAY

    def test_pix_stores_the_copy_and_paste_payload(self):
        db = _db(client=_client(default_billing_type="pix"), charge=_charge(billing_method="pix"))
        bc.process_one(db, _gateway(), _row(db), today=TODAY)
        assert _row(db)["pix_payload"]

    def test_a_retry_after_a_lost_response_never_creates_a_second_charge(self):
        class LosesTheFirstResponse(FakeHostedCheckout):
            lost = False

            def create_checkout(self, request):
                session = super().create_checkout(request)
                if not self.lost:
                    self.lost = True
                    raise PaymentGatewayError("asaas", "timeout calling /payments", retryable=True)
                return session

        checkout = LosesTheFirstResponse()
        db = _db(charge=_charge())
        gw = _gateway(checkout)
        first = bc.process_one(db, gw, _row(db), today=TODAY)
        assert first["status"] == "retrying" and _row(db)["next_attempt_at"] and "timeout" in _row(db)["last_error"]
        # the worker claims it again (reserve flips it back to 'generating', attempts + 1)
        _row(db).update(generation_status="generating", generation_attempts=2)
        second = bc.process_one(db, gw, _row(db), today=TODAY)
        assert second["status"] == "generated"
        assert len(checkout.sessions) == 1, "the retry must reuse the charge the gateway already created"

    def test_a_transient_failure_retries_with_backoff_then_fails_when_attempts_are_spent(self):
        class Down(FakeHostedCheckout):
            def create_checkout(self, request):
                raise PaymentGatewayError("asaas", "HTTP 503", retryable=True)

        db = _db(charge=_charge(generation_attempts=2))
        out = bc.process_one(db, _gateway(Down()), _row(db), today=TODAY)
        assert out["status"] == "retrying"
        assert datetime.fromisoformat(_row(db)["next_attempt_at"]) > datetime.now(timezone.utc)
        _row(db).update(generation_status="generating", generation_attempts=bc.MAX_ATTEMPTS)
        assert bc.process_one(db, _gateway(Down()), _row(db), today=TODAY)["status"] == "failed"
        assert _row(db)["next_attempt_at"] is None and "503" in _row(db)["last_error"]

    def test_a_permanent_gateway_refusal_fails_at_once_with_the_gateways_message(self):
        class Refuses(FakeHostedCheckout):
            def create_checkout(self, request):
                raise PaymentGatewayError("asaas", "CPF/CNPJ inválido", status=400, retryable=False)

        db = _db(charge=_charge())
        assert bc.process_one(db, _gateway(Refuses()), _row(db), today=TODAY)["status"] == "failed"
        assert _row(db)["last_error"] == "CPF/CNPJ inválido"

    @pytest.mark.parametrize("over,needle", [
        ({"document": None}, "CPF/CNPJ"), ({"email": ""}, "e-mail"), ({"legal_name": " "}, "Razão Social"),
    ])
    def test_a_client_missing_what_the_gateway_needs_fails_without_calling_it(self, over, needle):
        db = _db(client=_client(**over), charge=_charge())
        gw = _gateway()
        out = bc.process_one(db, gw, _row(db), today=TODAY)
        assert out["status"] == "failed" and needle in _row(db)["last_error"]
        assert gw.checkout.calls == []

    def test_an_org_without_credentials_is_skipped_not_failed(self):
        db = _db(charge=_charge())
        out = bc.process_one(db, _gateway(configured=False), _row(db), today=TODAY)
        assert out["status"] == "skipped" and "não configurado" in _row(db)["last_error"]

    def test_a_receivable_that_is_no_longer_open_is_skipped_without_calling_the_gateway(self):
        db = _db(entry=_entry(status="cancelled"), charge=_charge())
        gw = _gateway()
        assert bc.process_one(db, gw, _row(db), today=TODAY)["status"] == "skipped"
        assert gw.checkout.calls == []

    def test_a_charge_that_already_has_a_gateway_id_is_not_created_again(self):
        db = _db(charge=_charge(external_id="pay_old"))
        gw = _gateway()
        out = bc.process_one(db, gw, _row(db), today=TODAY)
        assert out == {"entry_id": ENTRY, "status": "generated", "external_id": "pay_old"}
        assert gw.checkout.calls == []

    def test_a_receivable_cancelled_while_the_gateway_call_was_in_flight_queues_the_gateway_cancel(self):
        class CancelsMidFlight(FakeHostedCheckout):
            def create_checkout(self, request):
                db.table("fin_entries")._data[0]["status"] = "cancelled"
                return super().create_checkout(request)

        db = _db(charge=_charge())
        bc.process_one(db, _gateway(CancelsMidFlight()), _row(db), today=TODAY)
        assert _row(db)["generation_status"] == "generated" and _row(db)["gateway_cancel_status"] == "pending"

    def test_a_partially_paid_receivable_charges_only_what_is_left(self):
        db = _db(entry=_entry(status="partial", settled_cents=50_000), charge=_charge())
        gw = _gateway()
        bc.process_one(db, gw, _row(db), today=TODAY)
        assert gw.checkout.calls[-1][1].price == Money(100_000)


class TestProcessCharges:
    def test_the_batch_claims_through_the_reserve_rpc_and_drains_the_gateway_cancels(self):
        db = _db(charge=_charge())
        db.set_rpc_data("billing_reserve_charges", [_charge()])
        out = bc.process_charges(db, _gateway(), today=TODAY)
        name, params = db.rpc_calls[0]
        assert name == "billing_reserve_charges" and params["p_stale_minutes"] == bc.STALE_MINUTES
        assert out["reserved"] == 1 and out["generated"] == 1 and out["gateway_cancel"] == {"done": 0, "failed": 0, "pending": 0}

    def test_one_crashing_row_does_not_strand_the_rest(self):
        db = _db(charge=_charge())
        db.set_rpc_data("billing_reserve_charges", [{"id": "x", "org_id": ORG, "entry_id": "missing", "generation_attempts": 1}, _charge()])

        class Boom(FakeHostedCheckout):
            pass

        out = bc.process_charges(db, _gateway(Boom()), today=TODAY)
        assert out["reserved"] == 2 and out["generated"] == 1 and out["skipped"] == 1


class TestGatewayCancel:
    def _pending(self):
        return _db(charge=_charge(generation_status="generated", external_id="pay_1", gateway_cancel_status="pending"))

    def test_cancels_at_the_gateway_and_marks_done(self):
        db, gw = self._pending(), _gateway()
        gw.charges.add_charge("pay_1", amount=Money(150_000), status="pending")
        assert bc.cancel_pending_at_gateway(db, gw) == {"done": 1, "failed": 0, "pending": 0}
        assert gw.charges.charges["pay_1"].status == "cancelled" and _row(db)["gateway_cancel_status"] == "done"

    def test_an_already_paid_charge_is_reported_not_swallowed(self):
        db, gw = self._pending(), _gateway()
        gw.charges.add_charge("pay_1", amount=Money(150_000), status="received")
        out = bc.cancel_pending_at_gateway(db, gw)
        assert out["failed"] == 1 and _row(db)["gateway_cancel_status"] == "failed"
        assert "já foi paga" in _row(db)["gateway_cancel_error"]

    def test_a_gateway_that_lost_the_charge_counts_as_cancelled(self):
        db, gw = self._pending(), _gateway()  # pay_1 unknown to the fake => resource_missing
        assert bc.cancel_pending_at_gateway(db, gw)["done"] == 1

    def test_no_credentials_leaves_it_pending_with_a_message(self):
        db = self._pending()
        out = bc.cancel_pending_at_gateway(db, _gateway(configured=False))
        assert out["pending"] == 1 and _row(db)["gateway_cancel_status"] == "pending" and _row(db)["gateway_cancel_error"]

    def test_is_scoped_to_the_given_org(self):
        db, gw = self._pending(), _gateway()
        assert bc.cancel_pending_at_gateway(db, gw, org_id="another-org") == {"done": 0, "failed": 0, "pending": 0}


# ── manual actions ──────────────────────────────────────────────────────────────────────────────────────────


class TestRequeue:
    def test_a_failed_charge_goes_back_to_the_queue_once_the_blocker_is_fixed(self):
        db = _db(charge=_charge(generation_status="failed", generation_attempts=5, last_error="Cliente sem CPF/CNPJ"))
        bc.requeue_charge(db, ORG, ENTRY, _gateway())
        row = _row(db)
        assert row["generation_status"] == "queued" and row["generation_attempts"] == 0 and row["last_error"] is None

    def test_it_refuses_when_no_gateway_is_configured(self):
        db = _db(charge=_charge(generation_status="skipped"))
        with pytest.raises(bc.BillingError) as exc:
            bc.requeue_charge(db, ORG, ENTRY, _gateway(configured=False))
        assert exc.value.status == 409 and "não configurado" in exc.value.message

    def test_it_refuses_a_charge_that_already_exists_at_the_gateway(self):
        db = _db(charge=_charge(generation_status="generated"))
        with pytest.raises(bc.BillingError) as exc:
            bc.requeue_charge(db, ORG, ENTRY, _gateway())
        assert exc.value.code == "cobranca_ja_gerada"

    def test_it_refuses_a_receivable_that_is_not_open(self):
        db = _db(entry=_entry(status="paid"), charge=_charge(generation_status="skipped"))
        with pytest.raises(bc.BillingError) as exc:
            bc.requeue_charge(db, ORG, ENTRY, _gateway())
        assert exc.value.code == "recebivel_nao_aberto"

    def test_unknown_charge_is_404(self):
        with pytest.raises(bc.BillingError) as exc:
            bc.requeue_charge(_db(), ORG, ENTRY, _gateway())
        assert exc.value.status == 404
