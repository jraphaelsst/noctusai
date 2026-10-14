"""Invoices: mapping, refs, jobs (retry/dedupe/poll), private copy, cancel + refusal, hooks."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.commerce import invoices as inv
from noctusai_lib.domain.commerce.errors import CommerceError
from noctusai_lib.domain.jobs import Worker
from noctusai_lib.integrations.invoices import FakeInvoiceProvider, InvoiceKind, InvoiceProviderError

from .conftest import ORG_A, ORG_B
from .fiscal_harness import CFG, FH, fh, fiscal_schema_cache, run, seed_fiscal_org, seed_paid_order  # noqa: F401


class FlakyProvider(FakeInvoiceProvider):
    """A Fake whose `issue` fails retryably `fail_times` times (subclass, not a patched instance)."""

    def __init__(self, fail_times: int = 1, **kw):
        super().__init__(**kw)
        self.fail_times, self.calls = fail_times, 0

    def issue(self, request):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise InvoiceProviderError("fake", "boom", code="timeout", retryable=True)
        return super().issue(request)


def handlers(fh: FH, **kw):
    return inv.make_invoice_job_handlers(
        CFG, get_db=lambda: fh.db, make_provider=lambda org: fh.provider, get_storage=lambda: fh.storage,
        get_jobs=lambda: fh.jobs, get_mailer=lambda: fh.mailer, **kw,
    )


def worker(fh: FH, **kw) -> Worker:
    return Worker(fh.jobs, worker_id="w", handlers=handlers(fh), retry_policy=inv.INVOICE_RETRY_POLICY, **kw)


def drain(fh: FH) -> int:
    n = 0
    while run(worker(fh).run_once()):
        n += 1
        assert n < 50
    return n


def rows(fh, order):
    return inv.list_invoices(fh.db, ORG_A, order["id"])


class TestMapping:
    def test_service_goes_nfse_goods_goes_nfe_rights_and_none_go_nowhere(self, fh):
        seed_fiscal_org(fh, treatment={"service": "service_nfse", "physical": "goods_nfe", "digital": "rights_receipt", "print_on_demand": "none"})
        for ptype, kind in (("service", "nfse"), ("physical", "nfe"), ("digital", None), ("print_on_demand", None)):
            order = seed_paid_order(fh, product_type=ptype)
            made = inv.register_invoices(fh.db, ORG_A, order)
            assert [r["kind"] for r in made] == ([kind] if kind else []), ptype

    def test_product_override_beats_profile_mapping(self, fh):
        seed_fiscal_org(fh, treatment={"service": "service_nfse"})
        order = seed_paid_order(fh, product_type="service")
        item = fh.db.table("commerce_order_items").select("*").eq("order_id", order["id"]).execute().data[0]
        fh.db.table("commerce_products").update({"tax_treatment_override": "goods_nfe"}).eq("id", item["product_id"]).execute()
        assert [r["kind"] for r in inv.register_invoices(fh.db, ORG_A, order)] == ["nfe"]

    def test_ref_format_and_length(self, fh):
        seed_fiscal_org(fh)
        order = seed_paid_order(fh)
        (row,) = inv.register_invoices(fh.db, ORG_A, order)
        assert row["ref"] == f"{ORG_A.replace('-', '')[:8]}-{order['id']}-nfse-1" and len(row["ref"]) <= 64 and row["status"] == "processing"

    def test_register_is_idempotent_one_per_kind(self, fh):
        seed_fiscal_org(fh)
        order = seed_paid_order(fh)
        assert len(inv.register_invoices(fh.db, ORG_A, order)) == 1
        assert inv.register_invoices(fh.db, ORG_A, order) == []
        assert len(rows(fh, order)) == 1


class TestAutoIssue:
    def test_off_by_default_nothing_is_enqueued(self, fh):
        seed_fiscal_org(fh, auto=False)
        order = seed_paid_order(fh)
        assert run(inv.on_order_paid(fh.db, order, jobs=fh.jobs)) == []
        assert drain(fh) == 0

    def test_on_order_paid_issues_authorizes_and_copies_privately(self, fh):
        seed_fiscal_org(fh)
        order = seed_paid_order(fh)
        (row,) = run(inv.on_order_paid(fh.db, order, jobs=fh.jobs))
        assert drain(fh) == 1
        done = inv.get_invoice(fh.db, ORG_A, row["id"])
        assert done["status"] == "authorized" and done["number"] and done["issued_at"] and done["provider"] == "fake"
        assert done["pdf_path"] == f"{ORG_A}/invoices/{row['id']}.pdf" and done["xml_path"].endswith(".xml")
        blob = run(fh.storage.get(bucket=CFG.bucket, key=done["pdf_path"]))
        assert blob is not None and blob.data == b"%PDF-fake"
        assert "https://" not in repr({k: done[k] for k in ("pdf_path", "xml_path")})  # private keys, never public URLs
        assert fh.provider.endpoints[row["ref"]] == "/v2/nfsen"  # simples -> Nacional

    def test_same_order_twice_enqueues_one_job(self, fh):
        seed_fiscal_org(fh)
        order = seed_paid_order(fh)
        run(inv.on_order_paid(fh.db, order, jobs=fh.jobs))
        run(inv.on_order_paid(fh.db, order, jobs=fh.jobs))
        run(inv.enqueue_pending_invoices(fh.db, fh.jobs))
        assert drain(fh) == 1

    def test_dedupe_key_is_the_ref(self, fh):
        seed_fiscal_org(fh)
        (row,) = run(inv.on_order_paid(fh.db, seed_paid_order(fh), jobs=fh.jobs))
        job = next(iter(fh.jobs._jobs.values()))
        assert job.dedupe_key == row["ref"] and job.type == inv.ISSUE_JOB

    def test_sync_half_registers_without_enqueue_and_sweep_recovers(self, fh):
        seed_fiscal_org(fh)
        order = seed_paid_order(fh)
        assert len(inv.register_on_order_paid(fh.db, order)) == 1 and drain(fh) == 0
        assert run(inv.enqueue_pending_invoices(fh.db, fh.jobs)) == 1
        assert drain(fh) == 1 and rows(fh, order)[0]["status"] == "authorized"

    def test_discount_is_allocated_to_the_invoice_total(self, fh):
        seed_fiscal_org(fh)
        order = seed_paid_order(fh, discount=2500)
        (row,) = inv.register_invoices(fh.db, ORG_A, order)
        profile = inv.get_profile(fh.db, ORG_A)
        req = inv.build_request(fh.db, ORG_A, order, row, profile, "co")
        assert req.total_cents == 7500 and req.taker.doc and req.items[0].total_cents == 7500


class TestRetriesAndFailures:
    def test_retryable_provider_error_is_retried_with_backoff_then_succeeds(self, fh):
        fh.provider = FlakyProvider(fail_times=1)
        seed_fiscal_org(fh)
        (row,) = run(inv.on_order_paid(fh.db, seed_paid_order(fh), jobs=fh.jobs))
        assert run(worker(fh).run_once()) and inv.get_invoice(fh.db, ORG_A, row["id"])["status"] == "processing"
        job = next(iter(fh.jobs._jobs.values()))
        assert job.retry_count == 1 and job.scheduled_for is not None  # backoff applied
        from dataclasses import replace
        fh.jobs._jobs[job.id] = replace(job, scheduled_for=None)
        assert run(worker(fh).run_once())
        assert inv.get_invoice(fh.db, ORG_A, row["id"])["status"] == "authorized"

    def test_last_attempt_marks_error_alerts_and_dead_letters(self, fh):
        fh.provider = FlakyProvider(fail_times=10_000)
        seed_fiscal_org(fh)
        (row,) = run(inv.on_order_paid(fh.db, seed_paid_order(fh), jobs=fh.jobs))
        from dataclasses import replace
        for _ in range(inv.INVOICE_RETRY_POLICY.max_retries + 1):
            job = next(iter(fh.jobs._jobs.values()))
            fh.jobs._jobs[job.id] = replace(job, scheduled_for=None)
            run(worker(fh).run_once())
        final = inv.get_invoice(fh.db, ORG_A, row["id"])
        assert final["status"] == "error" and final["rejection"]["code"] == "falhas_repetidas"
        assert next(iter(fh.jobs._jobs.values())).status.value == "dead_letter"
        assert len(fh.mailer.sent) == 1

    def test_provider_rejection_records_reasons_and_alerts_no_retry(self, fh):
        seed_fiscal_org(fh)
        (row,) = run(inv.on_order_paid(fh.db, seed_paid_order(fh), jobs=fh.jobs))
        fh.provider.script_rejection(row["ref"], ["CPF do tomador invalido"])
        drain(fh)
        done = inv.get_invoice(fh.db, ORG_A, row["id"])
        assert done["status"] == "rejected" and done["rejection"]["reasons"] == ["CPF do tomador invalido"]
        assert next(iter(fh.jobs._jobs.values())).retry_count == 0
        (mail,) = fh.mailer.sent
        assert mail.to == ["contato@loja.test"] and row["ref"] in mail.text

    def test_non_retryable_refusal_is_rejection_not_retry(self, fh):
        seed_fiscal_org(fh, cert=False, auto=False)
        fh.db.table("commerce_store_profiles").update({"auto_issue_invoices": True}).eq("org_id", ORG_A).execute()
        (row,) = run(inv.on_order_paid(fh.db, seed_paid_order(fh), jobs=fh.jobs))
        drain(fh)  # the Fake refuses: no certificate on file
        done = inv.get_invoice(fh.db, ORG_A, row["id"])
        assert done["status"] == "rejected" and done["rejection"]["code"] == "certificado_ausente"

    def test_buyer_without_document_is_a_rejection_before_any_provider_call(self, fh):
        seed_fiscal_org(fh)
        (row,) = run(inv.on_order_paid(fh.db, seed_paid_order(fh, doc=None), jobs=fh.jobs))
        drain(fh)
        assert inv.get_invoice(fh.db, ORG_A, row["id"])["rejection"]["code"] == "dados_incompletos" and not fh.provider._docs

    def test_processing_polls_until_authorized(self, fh):
        seed_fiscal_org(fh)
        fh.provider._auto_authorize = False
        (row,) = run(inv.on_order_paid(fh.db, seed_paid_order(fh), jobs=fh.jobs))
        run(worker(fh).run_once())
        job = next(iter(fh.jobs._jobs.values()))
        assert job.retry_count == 0 and job.status.value == "pending" and job.scheduled_for is not None  # rescheduled, not failed
        fh.provider.authorize(InvoiceKind.NFSE, row["ref"])
        from dataclasses import replace
        fh.jobs._jobs[job.id] = replace(job, scheduled_for=None)
        run(worker(fh).run_once())
        assert inv.get_invoice(fh.db, ORG_A, row["id"])["status"] == "authorized"

    def test_staff_can_retry_a_rejected_one_under_a_new_ref(self, fh):
        seed_fiscal_org(fh)
        order = seed_paid_order(fh)
        (first,) = run(inv.on_order_paid(fh.db, order, jobs=fh.jobs))
        fh.provider.script_rejection(first["ref"], ["x"])
        drain(fh)
        again = run(inv.issue_for_staff(fh.db, ORG_A, order["id"], InvoiceKind.NFSE, jobs=fh.jobs))
        assert again["seq"] == 2 and again["ref"].endswith("-nfse-2") and again["ref"] != first["ref"]
        drain(fh)
        assert inv.get_invoice(fh.db, ORG_A, again["id"])["status"] == "authorized"

    def test_staff_issue_guards(self, fh):
        seed_fiscal_org(fh, auto=False)
        unpaid = seed_paid_order(fh, status="pending_payment")
        with pytest.raises(CommerceError) as e:
            run(inv.issue_for_staff(fh.db, ORG_A, unpaid["id"], InvoiceKind.NFSE, jobs=fh.jobs))
        assert e.value.code == "pedido_nao_pago"
        paid = seed_paid_order(fh)
        with pytest.raises(CommerceError) as e:
            run(inv.issue_for_staff(fh.db, ORG_A, paid["id"], InvoiceKind.NFE, jobs=fh.jobs))
        assert e.value.code == "tipo_nota_invalido"
        run(inv.issue_for_staff(fh.db, ORG_A, paid["id"], InvoiceKind.NFSE, jobs=fh.jobs))
        with pytest.raises(CommerceError) as e:
            run(inv.issue_for_staff(fh.db, ORG_A, paid["id"], InvoiceKind.NFSE, jobs=fh.jobs))
        assert e.value.code == "nota_ja_emitida"


class TestCancel:
    def _authorized(self, fh):
        seed_fiscal_org(fh)
        order = seed_paid_order(fh)
        (row,) = run(inv.on_order_paid(fh.db, order, jobs=fh.jobs))
        drain(fh)
        return order, row

    def test_reason_must_have_15_chars(self, fh):
        _, row = self._authorized(fh)
        with pytest.raises(CommerceError) as e:
            run(inv.request_cancel(fh.db, ORG_A, row["id"], "curto demais", jobs=fh.jobs))
        assert e.value.code == "justificativa_curta" and e.value.status_code == 422

    def test_cancel_job_cancels_and_keeps_the_copies(self, fh):
        _, row = self._authorized(fh)
        req = run(inv.request_cancel(fh.db, ORG_A, row["id"], "Pedido estornado a pedido do cliente", jobs=fh.jobs))
        assert req["status"] == "authorized" and req["cancel_requested_at"]
        drain(fh)
        done = inv.get_invoice(fh.db, ORG_A, row["id"])
        assert done["status"] == "cancelled" and done["cancelled_at"] and done["pdf_path"]

    def test_cancel_is_idempotent_one_job(self, fh):
        _, row = self._authorized(fh)
        for _ in range(2):
            run(inv.request_cancel(fh.db, ORG_A, row["id"], "Pedido estornado a pedido do cliente", jobs=fh.jobs))
        cancels = [j for j in fh.jobs._jobs.values() if j.type == inv.CANCEL_JOB]
        assert len(cancels) == 1 and cancels[0].dedupe_key == f"{row['ref']}:cancel"

    def test_window_refusal_records_rejection_alerts_and_stays_authorized(self, fh):
        _, row = self._authorized(fh)
        fh.provider.script_cancel_refusal(row["ref"], ["prazo de cancelamento expirado"])
        run(inv.request_cancel(fh.db, ORG_A, row["id"], "Pedido estornado a pedido do cliente", jobs=fh.jobs))
        fh.mailer.sent.clear()
        drain(fh)
        done = inv.get_invoice(fh.db, ORG_A, row["id"])
        assert done["status"] == "authorized"
        assert done["rejection"]["op"] == "cancel" and done["rejection"]["reasons"] == ["prazo de cancelamento expirado"]
        assert len(fh.mailer.sent) == 1 and "cancelamento" in fh.mailer.sent[0].text

    def test_only_authorized_can_be_cancelled(self, fh):
        seed_fiscal_org(fh)
        (row,) = run(inv.on_order_paid(fh.db, seed_paid_order(fh), jobs=fh.jobs))  # still processing
        with pytest.raises(CommerceError) as e:
            run(inv.request_cancel(fh.db, ORG_A, row["id"], "Pedido estornado a pedido do cliente", jobs=fh.jobs))
        assert e.value.code == "nota_nao_cancelavel"

    def test_on_order_revoked_enqueues_cancels_even_without_auto_issue(self, fh):
        order, row = self._authorized(fh)
        fh.db.table("commerce_store_profiles").update({"auto_issue_invoices": False}).eq("org_id", ORG_A).execute()
        out = run(inv.on_order_revoked(fh.db, order, jobs=fh.jobs))
        assert [o["id"] for o in out] == [row["id"]]
        drain(fh)
        assert inv.get_invoice(fh.db, ORG_A, row["id"])["status"] == "cancelled"

    def test_invoice_authorized_after_the_order_was_refunded_is_cancelled(self, fh):
        seed_fiscal_org(fh)
        fh.provider._auto_authorize = False
        order = seed_paid_order(fh)
        (row,) = run(inv.on_order_paid(fh.db, order, jobs=fh.jobs))
        run(worker(fh).run_once())  # processing, rescheduled
        fh.db.table("commerce_orders").update({"status": "refunded"}).eq("id", order["id"]).execute()
        fh.provider.authorize(InvoiceKind.NFSE, row["ref"])
        from dataclasses import replace
        job = next(j for j in fh.jobs._jobs.values() if j.type == inv.ISSUE_JOB)
        fh.jobs._jobs[job.id] = replace(job, scheduled_for=None)
        drain(fh)
        assert inv.get_invoice(fh.db, ORG_A, row["id"])["status"] == "cancelled"


def test_org_isolation_of_invoice_reads(fh):
    seed_fiscal_org(fh)
    (row,) = inv.register_invoices(fh.db, ORG_A, seed_paid_order(fh))
    with pytest.raises(Exception):
        inv.get_invoice(fh.db, ORG_B, row["id"])
    assert inv.get_invoice_by_ref(fh.db, ORG_B, row["ref"]) is None


def test_fake_provider_satisfies_the_protocol_used_here():
    from noctusai_lib.integrations.invoices import InvoiceProvider
    assert isinstance(FakeInvoiceProvider(), InvoiceProvider)
