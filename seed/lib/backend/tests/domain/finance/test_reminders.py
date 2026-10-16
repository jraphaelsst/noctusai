"""Billing reminders: selection by offset/timezone, dedup-first sending, retries, opt-outs, hooks, loud failures."""
from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
import pytest

from noctusai_lib.domain.finance import entries
from noctusai_lib.domain.finance._common import Scope
from noctusai_lib.domain.finance.errors import FinanceError
from noctusai_lib.domain.finance.reminders import (
    DEFAULT_RULES,
    FakeReminderChannel,
    MAX_ATTEMPTS,
    ReminderContact,
    ReminderPorts,
    ReminderSendError,
    WhatsAppReminderChannel,
    create_rule,
    delete_rule,
    ensure_default_rules,
    list_log,
    list_rules,
    make_reminder_channel,
    make_waha_client_resolver,
    normalize_br_phone,
    preview_reminders,
    register_billing_reminders,
    render,
    run_reminders_all,
    run_reminders_for_org,
    set_receivable_opt_out,
    update_settings,
    validate_template,
)
from noctusai_lib.domain.finance.reminders import service as svc
from noctusai_lib.integrations.rate_limit import VirtualClock
from noctusai_lib.integrations.whatsapp.client import WahaClient

from .conftest import CFG, ORG_A, ORG_B, mk_entry

TODAY = date(2026, 10, 20)


def contact_for(_s, entry):
    return ReminderContact(
        nome="Maria", phone="11999998888", razao_social="Maria Silva LTDA", nome_fantasia="Studio Maria",
        link_pagamento=f"https://pay/{entry['id']}", pix_copia_cola="PIXCODE",
    )


class Env:
    def __init__(self, s):
        self.s = s
        self.channel = FakeReminderChannel()
        self.ports = ReminderPorts(channels={"whatsapp": self.channel}, resolve_contact=contact_for, clock=VirtualClock())

    def run(self, on=TODAY):
        return run_reminders_for_org(self.s, self.ports, on=on)


@pytest.fixture
def env(s):
    update_settings(s, {"enabled": True})
    ensure_default_rules(s)
    return Env(s)


@pytest.fixture
def mk(s):
    def _mk(offset_from_today, **over):
        due = date.fromordinal(TODAY.toordinal() + offset_from_today).isoformat()
        return mk_entry(s, due_date=due, **over)
    return _mk


# ── rules / templates ──────────────────────────────────────────────────────


def test_default_rules_are_idempotent(s):
    ensure_default_rules(s)
    ensure_default_rules(s)
    assert [r["offset_days"] for r in list_rules(s)] == [o for o, _ in DEFAULT_RULES]


def test_rule_validation(s):
    with pytest.raises(FinanceError):
        create_rule(s, {"offset_days": 999, "template": "x"})
    with pytest.raises(FinanceError) as e:
        create_rule(s, {"offset_days": 1, "template": "Oi {inexistente}"})
    assert e.value.code == "variavel_desconhecida"
    create_rule(s, {"offset_days": 1, "template": "Oi {nome}"})
    with pytest.raises(FinanceError) as e:
        create_rule(s, {"offset_days": 1, "template": "Outra"})
    assert e.value.code == "regra_duplicada"


def test_rules_are_org_scoped(s, s_b):
    ensure_default_rules(s)
    assert list_rules(s_b) == []


def test_render_all_variables_and_empty_link_line_dropped():
    out = render("{nome}|{razao_social}|{nome_fantasia}|{valor}|{vencimento}|{dias_atraso}\n{link_pagamento}\nfim",
                 {"nome": "A", "razao_social": "B", "nome_fantasia": "C", "valor": "R$ 1,00", "vencimento": "01/01/2026",
                  "dias_atraso": "3", "link_pagamento": "", "pix_copia_cola": ""})
    assert out == "A|B|C|R$ 1,00|01/01/2026|3\nfim"


def test_validate_template_rejects_blank():
    with pytest.raises(FinanceError):
        validate_template("   ")


# ── selection ──────────────────────────────────────────────────────────────


def test_selects_exactly_the_offset_days(env, mk):
    before3, today, late1, late7, other = mk(3), mk(0), mk(-1), mk(-7), mk(10)
    plan = preview_reminders(env.s, env.ports, on=TODAY)
    got = {p.entry_id: p.offset_days for p in plan.planned}
    assert got == {before3["id"]: -3, today["id"]: 0, late1["id"]: 1, late7["id"]: 7}
    assert other["id"] not in got


def test_preview_writes_nothing_and_renders_values(env, mk):
    e = mk(-7, amount_cents=123456)
    plan = preview_reminders(env.s, env.ports, on=TODAY)
    p = plan.planned[0]
    assert "R$ 1.234,56" in p.text and "7 dias de atraso" in p.text and f"https://pay/{e['id']}" in p.text
    assert env.s.rows("reminder_log") == [] and env.channel.sent == []


def test_skips_paid_cancelled_and_partial_uses_remaining(env, mk):
    paid, cancelled = mk(0), mk(0)
    env.s.tbl("entries").update({"status": "paid", "settled_cents": 10000}).eq("id", paid["id"]).execute()
    env.s.tbl("entries").update({"status": "cancelled"}).eq("id", cancelled["id"]).execute()
    partial = mk(0)
    env.s.tbl("entries").update({"status": "partial", "settled_cents": 4000}).eq("id", partial["id"]).execute()
    plan = preview_reminders(env.s, env.ports, on=TODAY)
    assert [p.entry_id for p in plan.planned] == [partial["id"]]
    assert "R$ 60,00" in plan.planned[0].text


def test_payables_are_never_dunned(env, mk):
    mk(0, direction="payable")
    assert preview_reminders(env.s, env.ports, on=TODAY).planned == []


def test_opt_out_and_host_veto_are_skipped_with_reasons(env, mk):
    opted, vetoed, ok = mk(0), mk(0), mk(0)
    set_receivable_opt_out(env.s, opted["id"], True)
    env.ports.skip_reason = lambda _s, entry: "preserved" if entry["id"] == vetoed["id"] else None
    plan = preview_reminders(env.s, env.ports, on=TODAY)
    assert [p.entry_id for p in plan.planned] == [ok["id"]]
    assert {x.entry_id: x.reason for x in plan.skipped} == {opted["id"]: "receivable_opt_out", vetoed["id"]: "blocked_by_host"}


def test_no_contact_and_no_phone_are_skipped(env, mk):
    mk(0)
    env.ports.resolve_contact = lambda _s, _e: None
    assert preview_reminders(env.s, env.ports, on=TODAY).skipped[0].reason == "no_contact"
    env.ports.resolve_contact = lambda _s, _e: ReminderContact(nome="X")
    assert preview_reminders(env.s, env.ports, on=TODAY).skipped[0].reason == "no_address_for_channel"


def test_rule_without_registered_channel_is_a_loud_skip(env, mk):
    mk(0)
    env.ports.channels.clear()
    plan = preview_reminders(env.s, env.ports, on=TODAY)
    assert plan.planned == [] and plan.skipped[0].reason == "no_channel_configured"


def test_org_disabled_or_no_settings_sends_nothing(s, mk):
    ensure_default_rules(s)
    e = Env(s)
    mk(0)
    assert e.run()["planned"] == 0  # no settings row => OFF
    update_settings(s, {"enabled": False})
    assert e.run()["planned"] == 0 and e.channel.sent == []


def test_disabled_rule_is_not_used(env, mk):
    mk(0)
    for r in list_rules(env.s):
        env.s.tbl("reminder_rules").update({"enabled": False}).eq("id", r["id"]).execute()
    assert preview_reminders(env.s, env.ports, on=TODAY).planned == []


def test_other_orgs_receivables_are_untouched(env, s_b, mk):
    mk_entry(s_b, due_date=TODAY.isoformat())
    assert preview_reminders(env.s, env.ports, on=TODAY).planned == []


def test_org_today_follows_the_org_timezone():
    utc_late = datetime(2026, 10, 21, 1, 30, tzinfo=timezone.utc)  # still the 20th in Sao Paulo
    assert svc.org_today({"timezone": "America/Sao_Paulo"}, now=utc_late) == date(2026, 10, 20)
    assert svc.org_today({"timezone": "Europe/Lisbon"}, now=utc_late) == date(2026, 10, 21)
    with pytest.raises(FinanceError):
        svc._tz("Mars/Olympus")


class FailingLogInsertDb:
    """A DB double (DI seam, not a patch) whose reminder_log INSERT raises `exc`; everything else is the real mock."""

    def __init__(self, inner, exc):
        self._inner, self._exc = inner, exc

    def table(self, name):
        table = self._inner.table(name)
        if name != CFG.table("reminder_log"):
            return table
        exc = self._exc

        class Failing:
            def insert(self, *a, **k):
                raise exc

            def __getattr__(self, attr):
                return getattr(table, attr)

        return Failing()

    def __getattr__(self, name):
        return getattr(self._inner, name)


# ── sending + dedup ────────────────────────────────────────────────────────


def test_sends_once_and_records_the_log(env, mk):
    e = mk(0)
    res = env.run()
    assert res["sent"] == 1 and res["errors"] == 0
    assert env.channel.sent[0]["to"] == "11999998888" and "Maria" in env.channel.sent[0]["text"]
    (row,) = env.s.rows("reminder_log")
    assert (row["entry_id"], row["status"], row["attempts"], row["cycle_date"]) == (e["id"], "sent", 1, TODAY.isoformat())
    assert row["provider_ref"] == "fake-1" and row["sent_at"]


def test_second_run_same_day_is_deduped(env, mk):
    mk(0)
    env.run()
    again = env.run()
    assert again["sent"] == 0 and again["deduped"] == 1 and len(env.channel.sent) == 1


def test_preview_flags_already_sent(env, mk):
    mk(0)
    env.run()
    assert preview_reminders(env.s, env.ports, on=TODAY).planned[0].already == "sent"


def test_dedup_claim_failure_is_loud_and_nothing_is_sent(env, mk, caplog):
    """The Orbity bug: the dedup insert failed unseen. Here: no claimed slot => no send, error counted + logged."""
    mk(0)
    s2 = Scope(FailingLogInsertDb(env.s.db, RuntimeError("null value in column agency_id violates not-null constraint")), CFG, ORG_A)
    with caplog.at_level("ERROR"):
        res = run_reminders_for_org(s2, env.ports, on=TODAY)
    assert res["errors"] == 1 and res["sent"] == 0 and env.channel.sent == []
    assert "aborted" in caplog.text


def test_unique_violation_on_claim_means_someone_else_holds_the_slot(env, mk):
    mk(0)

    class Dup(Exception):
        code = "23505"

    res = run_reminders_for_org(Scope(FailingLogInsertDb(env.s.db, Dup("duplicate key value violates unique constraint")), CFG, ORG_A), env.ports, on=TODAY)
    assert res["deduped"] == 1 and res["sent"] == 0 and env.channel.sent == []


def test_transient_error_is_retried_in_run(env, mk):
    mk(0)
    env.channel.fail_next = [ReminderSendError("http 503", transient=True)]
    res = env.run()
    assert res["sent"] == 1 and env.channel.calls == 2


def test_permanent_error_marks_failed_without_retry_or_later_resend(env, mk):
    mk(0)
    env.channel.fail_next = [ReminderSendError("telefone inválido", transient=False)]
    res = env.run()
    assert res["failed"] == 1 and env.channel.calls == 1
    (row,) = env.s.rows("reminder_log")
    assert row["status"] == "failed" and row["last_error"] == "telefone inválido"
    assert env.run()["sent"] == 0  # permanent => attempts exhausted, never re-sent
    assert env.channel.calls == 1


def test_persistent_transient_failure_is_retried_by_next_days_until_exhausted(env, mk):
    mk(0)
    env.channel.fail_next = [ReminderSendError("503", transient=True)] * 50
    first = env.run()
    assert first["failed"] == 1
    (row,) = env.s.rows("reminder_log")
    assert row["status"] == "failed" and row["attempts"] == 1
    # tomorrow: the offset-0 rule's day was yesterday; the earlier-failure pass retries it (still failing)
    nxt = env.run(on=date.fromordinal(TODAY.toordinal() + 1))
    assert nxt["retried"] >= 1
    # let it succeed
    env.channel.fail_next.clear()
    env.run(on=date.fromordinal(TODAY.toordinal() + 2))
    rows = [r for r in env.s.rows("reminder_log") if r["offset_days"] == 0]
    assert rows[0]["status"] == "sent" and rows[0]["attempts"] <= MAX_ATTEMPTS


def test_failed_row_not_retried_after_the_window(env, mk):
    mk(0)
    env.channel.fail_next = [ReminderSendError("503", transient=True)] * 50
    env.run()
    env.channel.fail_next.clear()
    res = env.run(on=date.fromordinal(TODAY.toordinal() + 5))
    assert env.channel.sent == [] or all(m["text"] for m in env.channel.sent)
    (row,) = [r for r in env.s.rows("reminder_log") if r["offset_days"] == 0]
    assert row["status"] == "failed" and res["retried"] == 0


def test_pending_row_is_never_resent(env, mk):
    e = mk(0)
    rule = [r for r in list_rules(env.s) if r["offset_days"] == 0][0]
    env.s.tbl("reminder_log").insert({
        "id": "11111111-1111-4111-8111-111111111111", "org_id": ORG_A, "entry_id": e["id"], "rule_id": rule["id"],
        "channel": "whatsapp", "offset_days": 0, "cycle_date": TODAY.isoformat(), "status": "pending", "attempts": 1,
        "recipient": "x", "message": "m",
    }).execute()
    res = env.run()
    assert res["deduped"] == 1 and env.channel.sent == []


def test_log_listing_is_org_scoped(env, s_b, mk):
    mk(0)
    env.run()
    rows, total, _, _ = list_log(env.s)
    assert total == 1 and rows[0]["org_id"] == ORG_A
    assert list_log(s_b)[1] == 0


def test_delete_rule_without_history(s):
    r = create_rule(s, {"offset_days": 2, "template": "x"})
    delete_rule(s, r["id"])
    assert list_rules(s) == []


# ── job-level ──────────────────────────────────────────────────────────────


def test_run_all_covers_only_enabled_orgs_and_isolates_failures(s, s_b, mk):
    update_settings(s, {"enabled": True})
    ensure_default_rules(s)
    update_settings(s_b, {"enabled": False})
    ensure_default_rules(s_b)
    mk(0)
    mk_entry(s_b, due_date=TODAY.isoformat())
    env = Env(s)
    now = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)
    out = run_reminders_all(s.db, CFG, env.ports, now=now)
    assert out["orgs"] == 1 and out["sent"] == 1 and out["failed_orgs"] == 0
    assert all(m["org_id"] == ORG_A for m in env.channel.sent)


def test_register_job_uses_cron_and_swallows_errors():
    calls = {}

    class Sched:
        def register(self, name, fn, **kw):
            calls.update(name=name, fn=fn, kw=kw)

    jid = register_billing_reminders(CFG, get_db=lambda: (_ for _ in ()).throw(RuntimeError("db down")),
                                     ports=ReminderPorts(channels={}, resolve_contact=lambda *_: None), hour=9, scheduler=Sched())
    assert jid == "finance_billing_reminders" and calls["kw"]["cron"] == "0 9 * * *"
    import asyncio
    asyncio.run(calls["fn"]())  # logs the failure, does not raise
    with pytest.raises(ValueError):
        register_billing_reminders(CFG, get_db=lambda: None, ports=ReminderPorts(channels={}, resolve_contact=lambda *_: None), hour=25, scheduler=Sched())


# ── channels ───────────────────────────────────────────────────────────────


def test_normalize_phone():
    assert normalize_br_phone("(11) 99999-8888") == "5511999998888"
    assert normalize_br_phone("+55 11 99999-8888") == "5511999998888"
    with pytest.raises(ReminderSendError) as e:
        normalize_br_phone("123")
    assert not e.value.transient


def waha(handler):
    return WahaClient("http://waha", "k", "default", transport=httpx.MockTransport(handler))


def test_real_whatsapp_channel_sends_through_waha():
    seen = {}

    def handler(request):
        seen["body"] = request.read().decode()
        return httpx.Response(201, json={"id": {"_serialized": "true_5511@c.us_ABC"}})

    ch = WhatsAppReminderChannel(lambda org: waha(handler))
    r = ch.send(org_id=ORG_A, to="11999998888", text="oi")
    assert "5511999998888@c.us" in seen["body"] and r.provider_ref == "true_5511@c.us_ABC"


@pytest.mark.parametrize("status, transient", [(500, True), (429, True), (400, False), (404, False)])
def test_real_channel_classifies_http_errors(status, transient):
    ch = WhatsAppReminderChannel(lambda org: waha(lambda req: httpx.Response(status, json={})))
    with pytest.raises(ReminderSendError) as e:
        ch.send(org_id=ORG_A, to="11999998888", text="oi")
    assert e.value.transient is transient


def test_real_channel_transport_error_is_transient_and_no_line_is_permanent():
    def boom(request):
        raise httpx.ConnectError("down")

    with pytest.raises(ReminderSendError) as e:
        WhatsAppReminderChannel(lambda org: waha(boom)).send(org_id=ORG_A, to="11999998888", text="x")
    assert e.value.transient
    with pytest.raises(ReminderSendError) as e2:
        WhatsAppReminderChannel(lambda org: None).send(org_id=ORG_A, to="11999998888", text="x")
    assert not e2.value.transient


def test_factory():
    assert isinstance(make_reminder_channel("fake"), FakeReminderChannel)
    with pytest.raises(ValueError):
        make_reminder_channel("whatsapp")
    with pytest.raises(ValueError):
        make_reminder_channel("carrier-pigeon")
    assert isinstance(make_reminder_channel("whatsapp", resolve_client=lambda o: None), WhatsAppReminderChannel)


def test_line_resolver_prefers_billing_then_general():
    from types import SimpleNamespace as NS

    recs = [NS(id="00000000-0000-4000-8000-000000000001", extra={"purpose": "general"}),
            NS(id="00000000-0000-4000-8000-000000000002", extra={"purpose": "billing"})]

    class Store:
        def __init__(self, records):
            self.records = records

        def list_connections(self, *, org_id):
            return self.records

        def get_connection(self, *, connection_id, org_id, decrypt):
            return next(r for r in self.records if r.id == str(connection_id))

    built = lambda rec: rec.id  # noqa: E731
    org = ORG_A
    assert make_waha_client_resolver(Store(recs), client_factory=built)(org).endswith("2")
    assert make_waha_client_resolver(Store(recs[:1]), client_factory=built)(org).endswith("1")
    assert make_waha_client_resolver(Store([]), client_factory=built)(org) is None


def test_same_receivable_hits_distinct_rules_on_distinct_days(env, mk):
    mk(3)
    assert env.run(on=TODAY)["sent"] == 1                       # -3: three days before
    assert env.run(on=date.fromordinal(TODAY.toordinal() + 3))["sent"] == 1   # 0: on the day
    assert len(env.s.rows("reminder_log")) == 2
