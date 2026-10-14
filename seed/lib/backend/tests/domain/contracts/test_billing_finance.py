"""The REAL seam: contracts book into the finance organ (mock PostgREST validated against `finance_migration`)."""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date

import pytest

from noctusai_lib.domain.contracts import (
    SupabaseContractsBilling, billing_run, contracts, handle_signature_webhook, make_contracts_billing, register_contracts_billing,
)
from noctusai_lib.domain.contracts import signature as sig
from noctusai_lib.domain.contracts._common import Scope
from noctusai_lib.domain.finance import _common as fin_common
from noctusai_lib.integrations.signature import make_signature_adapter
from noctusai_lib.integrations.signature.exceptions import WebhookInvalido

from .conftest import CFG, FIN_CFG, ORG_A, ORG_B, VALID_CPF, body, mk, mk_party

ON = date(2026, 11, 1)


@pytest.fixture
def real(db):
    return make_contracts_billing("supabase", db=db, finance_cfg=FIN_CFG)


def fin_rows(db, org=ORG_A):
    return fin_common.Scope(db, FIN_CFG, org).rows("entries")


def test_factory_builds_each_kind_and_refuses_unknown(db):
    assert isinstance(make_contracts_billing("supabase", db=db, finance_cfg=FIN_CFG), SupabaseContractsBilling)
    assert make_contracts_billing("noop").book_receivable(ORG_A) is None
    with pytest.raises(ValueError):
        make_contracts_billing("supabase")
    with pytest.raises(ValueError):
        make_contracts_billing("nope")  # type: ignore[arg-type]


def test_activation_creates_idempotent_receivables_with_source_contracts(db, s, real):
    p = mk_party(s)
    c = mk(s, party_id=p["id"], billing_model="installments", installments_count=3, amount_cents=100000, first_due_date="2026-11-10")
    contracts.activate_contract(s, c["id"], billing=real, on=ON)
    rows = sorted(fin_rows(db), key=lambda r: r["due_date"])
    assert [(r["source"], r["source_ref"], r["amount_cents"], r["direction"], r["status"]) for r in rows] == [
        ("contracts", f"{c['id']}:i1", 33333, "receivable", "open"),
        ("contracts", f"{c['id']}:i2", 33333, "receivable", "open"),
        ("contracts", f"{c['id']}:i3", 33334, "receivable", "open")]
    assert rows[0]["counterparty_name"] == "Ana Souza" and rows[0]["counterparty_doc"] == VALID_CPF
    assert rows[0]["competence_month"] == "2026-11-01"
    # re-running everything is a no-op in finance too
    billing_run.contracts_generate_billing(db, CFG, real, on=ON)
    assert len(fin_rows(db)) == 3


def test_recurring_uses_the_mensalidades_category_and_services_the_service_one(db, s, real):
    r = mk(s, title="Mensal")
    o = mk(s, title="Avulso", billing_model="one_time", first_due_date="2026-11-12")
    contracts.activate_contract(s, r["id"], billing=real, on=ON)
    contracts.activate_contract(s, o["id"], billing=real, on=ON)
    cats = {c["id"]: c["name"] for c in fin_common.Scope(db, FIN_CFG, ORG_A).rows("categories")}
    by_ref = {x["source_ref"]: cats.get(x["category_id"]) for x in fin_rows(db)}
    assert by_ref[f"{r['id']}:2026-11-10"] == "Mensalidades"
    assert by_ref[f"{o['id']}:one"] == "Serviços"


def test_termination_cancels_unsettled_future_receivables_in_finance(db, s, real):
    c = mk(s, billing_model="installments", installments_count=3, amount_cents=30000, first_due_date="2026-11-10", penalty_cents=500)
    contracts.activate_contract(s, c["id"], billing=real, on=ON)
    contracts.terminate_contract(s, c["id"], {"reason": "x", "effective_on": date(2026, 11, 15)}, billing=real, on=ON)
    status = {r["source_ref"].split(":", 1)[1]: r["status"] for r in fin_rows(db)}
    assert status["i1"] == "open" and status["i2"] == "cancelled" and status["i3"] == "cancelled"


def test_a_settled_receivable_is_kept_on_termination(db, s, real):
    c = mk(s, billing_model="installments", installments_count=2, amount_cents=20000, first_due_date="2026-12-10")
    contracts.activate_contract(s, c["id"], billing=real, on=ON)
    fs = fin_common.Scope(db, FIN_CFG, ORG_A)
    acct = fs.tbl("accounts").insert({"id": fin_common.new_id(), "org_id": ORG_A, "name": "Banco", "kind": "checking"}).execute().data[0]
    second = next(r for r in fin_rows(db) if r["source_ref"].endswith(":i2"))
    # a live (unreversed) settlement: finance refuses to cancel an entry that has one
    fs.tbl("settlements").insert({"id": fin_common.new_id(), "org_id": ORG_A, "entry_id": second["id"], "account_id": acct["id"],
                                  "kind": "payment", "settled_on": "2027-01-10", "amount_cents": 10000}).execute()
    contracts.terminate_contract(s, c["id"], {"reason": "x", "effective_on": date(2026, 11, 15)}, billing=real, on=ON)
    status = {r["source_ref"].split(":", 1)[1]: r["status"] for r in fin_rows(db)}
    assert status["i1"] == "cancelled" and status["i2"] == "open"  # never cancelled behind a settlement
    assert [b["period_key"] for b in billing_run.list_billings(s, c["id"])] == ["i2"]  # stays on the contract's books


def test_receivables_are_org_scoped(db, s, real):
    c = mk(s)
    contracts.activate_contract(s, c["id"], billing=real, on=ON)
    assert fin_rows(db, ORG_B) == []


def test_job_registration_uses_the_scheduler_seam_per_run(db, real):
    class FakeScheduler:
        def __init__(self):
            self.jobs = {}

        def register(self, job_id, fn, **kw):
            self.jobs[job_id] = (fn, kw)

    sch = FakeScheduler()
    got = register_contracts_billing(CFG, get_db=lambda: db, get_billing=lambda _db: real, scheduler=sch)
    assert got == "contracts_generate_billing" and sch.jobs[got][1] == {"hours": 24}
    s = Scope(db, CFG, ORG_A)
    c = mk(s, first_due_date="2026-11-10", start_date="2026-11-01")
    contracts.activate_contract(s, c["id"], billing=real, on=ON)
    asyncio.run(sch.jobs[got][0]())
    n = len(fin_rows(db))
    assert n >= 1 and len(fin_rows(db)) == n  # the job ran against the live db/billing and is idempotent


def test_webhook_handler_finds_the_contract_across_orgs_and_activates(db, real):
    s = Scope(db, CFG, ORG_A)
    adapter = make_signature_adapter()
    c = mk(s)
    sig.render_document(s, c["id"])
    sent = asyncio.run(sig.send_for_signature(s, adapter, c["id"], [{"name": "Ana", "email": "a@x.com", "cpf": VALID_CPF}]))
    ext = sent["signature_external_id"]

    def hook(status, signed=True):
        raw = json.dumps({"external_id": ext, "status": status}).encode()
        return raw, {"x-fake-signature": hashlib.sha256(raw).hexdigest() if signed else "bad"}

    with pytest.raises(WebhookInvalido):
        handle_signature_webhook(db, CFG, adapter, *hook("concluido", signed=False), billing=real)
    unknown = json.dumps({"external_id": "ghost", "status": "concluido"}).encode()
    assert handle_signature_webhook(db, CFG, adapter, unknown, {"x-fake-signature": hashlib.sha256(unknown).hexdigest()}) is None
    out = handle_signature_webhook(db, CFG, adapter, *hook("concluido"), billing=real)  # no org in the call: found by (provider, external_id)
    assert out["signature_status"] == "concluido" and out["status"] == "active" and out["org_id"] == ORG_A
    assert len(fin_rows(db)) >= 1
