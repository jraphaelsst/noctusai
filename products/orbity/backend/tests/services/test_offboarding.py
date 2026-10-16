"""Inactivating a client with kept charges: the decisions, the contracts, the gateway.

The atomic half (cancel / keep every open charge + the client row) is the ``offboard_client`` RPC -- proved on a real
Postgres by ``mcp/noctusai/tests/test_orbity_billing_migration_on_replay.py``. Here: the service around it.
"""
import pytest
from noctusai_lib.domain.commerce.gateway import FakeCheckoutGateway
from noctusai_lib.integrations.payments.types import Money
from noctusai_lib.testing import MockSupabaseClient

from app.services import offboarding as ob
from app.services.billing_charges import BillingError

ORG = "00000000-0000-0000-0000-000000000abc"
CLIENT = "c1000000-0000-4000-8000-000000000001"
CONTRACT = "d1000000-0000-4000-8000-000000000001"
E1, E2, E3 = ("e1000000-0000-4000-8000-00000000000%d" % n for n in (1, 2, 3))


def _entry(eid, status="open", due="2026-10-20", cents=100_000, settled=0):
    return {"id": eid, "org_id": ORG, "direction": "receivable", "status": status, "description": f"Mensalidade {eid[-1]}",
            "amount_cents": cents, "settled_cents": settled, "due_date": due, "competence_month": "2026-10-01"}


def _charge(eid, **over):
    base = {"id": f"ch-{eid[-1]}", "org_id": ORG, "entry_id": eid, "client_id": CLIENT, "contract_id": CONTRACT,
            "generation_status": "generated", "generation_attempts": 1, "external_id": None,
            "preserved_after_deactivation": False, "gateway_cancel_status": None, "created_at": "2026-10-01T00:00:00+00:00"}
    base.update(over)
    return base


def _db(*, entries=None, charges=None, contracts=None):
    db = MockSupabaseClient(schema="orbity")
    db.set_table_data("clients", [{"id": CLIENT, "org_id": ORG, "name": "Acme", "legal_name": "Acme LTDA", "active": True}])
    db.set_table_data("fin_entries", entries if entries is not None else [_entry(E1), _entry(E2, due="2026-09-05")])
    db.set_table_data("billing_charges", charges if charges is not None else [_charge(E1), _charge(E2)])
    db.set_table_data("ctr_contracts", contracts or [])
    db.set_rpc_data("offboard_client", {"cancelled": 1, "preserved": 1, "gateway_cancel_entry_ids": []})
    return db


def test_preview_lists_the_open_charges_oldest_first_and_the_live_contracts():
    db = _db(entries=[_entry(E1), _entry(E2, due="2026-09-05"), _entry(E3, status="paid")],
             charges=[_charge(E1), _charge(E2), _charge(E3)],
             contracts=[{"id": CONTRACT, "org_id": ORG, "party_id": CLIENT, "title": "Gestão", "status": "active"},
                        {"id": "x", "org_id": ORG, "party_id": CLIENT, "title": "Velho", "status": "terminated"}])
    out = ob.preview(db, ORG, CLIENT)
    assert [c["entry_id"] for c in out["charges"]] == [E2, E1]            # paid is not "open"
    assert out["charges"][0]["overdue"] is True
    assert [c["id"] for c in out["contracts"]] == [CONTRACT]              # terminated is not live
    assert out["client"] == {"id": CLIENT, "name": "Acme LTDA", "active": True}


def test_preview_hides_a_charge_already_kept_by_an_earlier_inactivation():
    db = _db(charges=[_charge(E1, preserved_after_deactivation=True), _charge(E2)])
    assert [c["entry_id"] for c in ob.preview(db, ORG, CLIENT)["charges"]] == [E2]


def test_preview_of_another_orgs_client_is_404():
    with pytest.raises(BillingError) as exc:
        ob.preview(_db(), "another-org", CLIENT)
    assert exc.value.status == 404


class TestDecisions:
    def test_every_open_charge_must_be_decided(self):
        with pytest.raises(BillingError) as exc:
            ob.offboard(_db(), FakeCheckoutGateway(), ORG, CLIENT, {E1: "cancel"})
        assert exc.value.status == 409 and exc.value.code == "cobrancas_em_aberto"

    def test_a_foreign_or_closed_charge_is_refused(self):
        with pytest.raises(BillingError) as exc:
            ob.offboard(_db(), FakeCheckoutGateway(), ORG, CLIENT, {E1: "cancel", E2: "cancel", E3: "cancel"})
        assert exc.value.code == "cobranca_invalida"

    def test_an_unknown_action_is_refused(self):
        with pytest.raises(BillingError) as exc:
            ob.offboard(_db(), FakeCheckoutGateway(), ORG, CLIENT, {E1: "cancel", E2: "maybe"})
        assert exc.value.code == "acao_invalida"

    def test_a_partially_paid_charge_cannot_be_cancelled_only_kept(self):
        db = _db(entries=[_entry(E1, status="partial", settled=30_000), _entry(E2)])
        with pytest.raises(BillingError) as exc:
            ob.offboard(db, FakeCheckoutGateway(), ORG, CLIENT, {E1: "cancel", E2: "cancel"})
        assert exc.value.code == "cobranca_parcialmente_paga"
        assert db.rpc_calls == []


class TestOffboard:
    def test_sends_the_decisions_to_the_atomic_rpc_split_by_action(self):
        db = _db()
        out = ob.offboard(db, FakeCheckoutGateway(), ORG, CLIENT, {E1: "keep", E2: "cancel"})
        (name, params), = db.rpc_calls
        assert name == "offboard_client"
        assert params == {"p_org_id": ORG, "p_client_id": CLIENT, "p_cancel_entry_ids": [E2], "p_preserve_entry_ids": [E1]}
        assert out["client_id"] == CLIENT and out["contracts_failed"] == [] and out["contracts_terminated"] == []

    def test_a_client_with_no_open_charges_needs_no_decisions(self):
        db = _db(entries=[], charges=[])
        ob.offboard(db, FakeCheckoutGateway(), ORG, CLIENT, {})
        assert db.rpc_calls[0][1]["p_cancel_entry_ids"] == [] and db.rpc_calls[0][1]["p_preserve_entry_ids"] == []

    def test_the_live_contracts_are_terminated_through_the_seed_organ_with_the_waivers(self):
        contract = {"id": CONTRACT, "org_id": ORG, "party_id": CLIENT, "title": "Gestão", "status": "active", "billing_model": "recurring",
                    "amount_cents": 100_000, "frequency": "monthly", "due_day": 20, "first_due_date": "2026-01-20", "notice_days": 30,
                    "penalty_cents": 50_000, "penalty_bp": 1000, "version_n": 1, "next_period_on": "2026-11-20"}
        db = _db(entries=[], charges=[], contracts=[contract])
        out = ob.offboard(db, FakeCheckoutGateway(), ORG, CLIENT, {}, on=None)
        assert out["contracts_terminated"] == [CONTRACT] and out["contracts_failed"] == []
        row = db.table("ctr_contracts")._data[0]
        assert row["status"] == "terminated" and row["termination_reason"] == ob.TERMINATION_REASON
        assert not row.get("penalty_applied_cents"), "an agency-side inactivation waives the penalty"

    def test_a_contract_that_cannot_be_terminated_is_reported_and_the_gateway_work_still_runs(self):
        class VersionsDown(MockSupabaseClient):
            def table(self, name):
                if name == "ctr_contract_versions":
                    raise RuntimeError("versions table unavailable")
                return super().table(name)

        contract = {"id": CONTRACT, "org_id": ORG, "party_id": CLIENT, "title": "Gestão", "status": "active", "billing_model": "recurring",
                    "amount_cents": 100_000, "frequency": "monthly", "due_day": 20, "first_due_date": "2026-01-20", "version_n": 1}
        base = _db(entries=[], charges=[_charge(E3, external_id="pay_9", gateway_cancel_status="pending")], contracts=[contract])
        db = VersionsDown(schema="orbity")
        for t in ("clients", "fin_entries", "billing_charges", "ctr_contracts"):
            db.set_table_data(t, base.table(t)._data)
        db.set_rpc_data("offboard_client", {"cancelled": 0, "preserved": 0, "gateway_cancel_entry_ids": []})
        gw = FakeCheckoutGateway()
        gw.charges.add_charge("pay_9", amount=Money(100_000), status="pending")
        out = ob.offboard(db, gw, ORG, CLIENT, {})
        assert out["contracts_terminated"] == []
        (failed,) = out["contracts_failed"]
        assert failed["id"] == CONTRACT and "versions table unavailable" in failed["error"]
        assert gw.charges.charges["pay_9"].status == "cancelled", "a failed termination must not strand the gateway cancels"

    def test_cancelled_charges_are_cancelled_at_the_gateway_too(self):
        gw = FakeCheckoutGateway()
        gw.charges.add_charge("pay_77", amount=Money(100_000), status="pending")
        db = _db(charges=[_charge(E1, external_id="pay_77", gateway_cancel_status="pending"), _charge(E2)])
        out = ob.offboard(db, gw, ORG, CLIENT, {E1: "cancel", E2: "keep"})
        assert gw.charges.charges["pay_77"].status == "cancelled"
        assert out["gateway_cancelled"] == 1 and out["gateway_pending"] == 0

    @pytest.mark.parametrize("marker,status,code", [
        ("unresolved_charges", 409, "cobrancas_em_aberto"), ("charge_has_settlements", 409, "cobranca_parcialmente_paga"),
        ("charge_not_open_for_client", 422, "cobranca_invalida"), ("client_not_found", 404, "cliente_nao_encontrado"),
    ])
    def test_the_rpcs_refusals_become_their_http_errors(self, marker, status, code):
        class Refusing(MockSupabaseClient):
            def rpc(self, name, params=None):
                raise RuntimeError(f"P0001 {marker}")

        db = _db()
        refusing = Refusing(schema="orbity")
        for t in ("clients", "fin_entries", "billing_charges", "ctr_contracts"):
            refusing.set_table_data(t, db.table(t)._data)
        with pytest.raises(BillingError) as exc:
            ob.offboard(refusing, FakeCheckoutGateway(), ORG, CLIENT, {E1: "cancel", E2: "cancel"})
        assert (exc.value.status, exc.value.code) == (status, code)

    def test_an_unknown_rpc_failure_propagates(self):
        class Exploding(MockSupabaseClient):
            def rpc(self, name, params=None):
                raise RuntimeError("connection reset")

        db = _db()
        boom = Exploding(schema="orbity")
        for t in ("clients", "fin_entries", "billing_charges", "ctr_contracts"):
            boom.set_table_data(t, db.table(t)._data)
        with pytest.raises(RuntimeError):
            ob.offboard(boom, FakeCheckoutGateway(), ORG, CLIENT, {E1: "cancel", E2: "cancel"})
