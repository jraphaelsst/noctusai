"""Owner line: notify_owner outcomes, the Supabase recipient source TTL, the WAHA transport."""
from __future__ import annotations

import logging

import pytest

from noctusai_lib.domain.notification_catalog import (
    FakeNotificationGate,
    FakeOwnerLineTransport,
    FakeOwnerRecipientSource,
    NotificationKind,
    OwnerLineNumberMismatch,
    OwnerLineNumberUnknown,
    OwnerRecipient,
    SupabaseOwnerRecipientSource,
    UndeclaredNotificationKind,
    WahaOwnerLineTransport,
    configure_owner_line,
    declare_kinds,
    make_owner_line,
    notify_owner,
    reset_declarations_for_tests,
)

P = "owner-line-test-product"
R1, R2 = OwnerRecipient("+5511999990001", "A"), OwnerRecipient("+5511999990002")


@pytest.fixture(autouse=True)
def _clean():
    reset_declarations_for_tests(P)
    declare_kinds(P, [NotificationKind(kind="aviso", titulo="Aviso", descricao="d", gatilho="g")])
    configure_owner_line()
    yield
    reset_declarations_for_tests(P)
    configure_owner_line()


def _send(gate, recipients, transport, **kw):
    return notify_owner(P, "aviso", "oi", gate=gate, recipients=recipients, transport=transport, **kw)


def test_switched_off_suppressed_and_nothing_sent():
    gate, tr = FakeNotificationGate(P, disabled={"aviso"}), FakeOwnerLineTransport()
    d = _send(gate, FakeOwnerRecipientSource([R1]), tr)
    assert d.status == "suppressed" and tr.sent == []
    assert gate.sends[-1]["status"] == "suppressed"


def test_no_recipients():
    gate = FakeNotificationGate(P)
    d = _send(gate, FakeOwnerRecipientSource([]), FakeOwnerLineTransport())
    assert (d.status, d.recipients, d.reason) == ("no_recipient", 0, "nenhum destinatário do dono configurado")
    assert gate.sends[-1]["status"] == "no_recipient"


def test_transportless_failed_and_error_logged(caplog):
    gate = FakeNotificationGate(P)
    with caplog.at_level(logging.ERROR):
        d = _send(gate, FakeOwnerRecipientSource([R1]), None)
    assert (d.status, d.reason, d.delivered) == ("failed", "linha_noc_nao_configurada", 0)
    assert f"seed.owner_line.nao_configurada product={P} kind=aviso" in caplog.text
    assert gate.sends[-1]["reason"] == "linha_noc_nao_configurada"


def test_all_some_none_delivered():
    src = FakeOwnerRecipientSource([R1, R2])
    gate = FakeNotificationGate(P)
    tr = FakeOwnerLineTransport()
    assert _send(gate, src, tr, org_id="o1").status == "sent"
    assert [n for n, _ in tr.sent] == [R1.numero, R2.numero]
    part = _send(gate, src, FakeOwnerLineTransport(fail_numbers={R2.numero}))
    assert (part.status, part.delivered, part.recipients) == ("partial", 1, 2)
    none = _send(gate, src, FakeOwnerLineTransport(fail_numbers={R1.numero, R2.numero}))
    assert (none.status, none.delivered) == ("failed", 0)
    for d in (part, none):
        assert "oi" not in d.reason and R1.numero not in d.reason and len(d.reason) <= 300
    assert [s["status"] for s in gate.sends] == ["sent", "partial", "failed"]


def test_undeclared_kind_raises():
    with pytest.raises(UndeclaredNotificationKind):
        notify_owner(P, "nope", "x", gate=FakeNotificationGate(P), recipients=FakeOwnerRecipientSource([R1]),
                     transport=FakeOwnerLineTransport())


def test_unreadable_recipients_failed_not_raised():
    class Boom:
        def active(self):
            raise RuntimeError("core down")

    d = _send(FakeNotificationGate(P), Boom(), FakeOwnerLineTransport())
    assert d.status == "failed"


def test_defaults_use_configured_line():
    tr = FakeOwnerLineTransport()
    configure_owner_line(recipients=FakeOwnerRecipientSource([R1]), transport=tr)
    assert notify_owner(P, "aviso", "oi", gate=FakeNotificationGate(P)).status == "sent"
    assert tr.sent == [(R1.numero, "oi")]


class _Q:
    def __init__(self, db):
        self.db = db

    def select(self, *_a):
        return self

    def eq(self, *_a):
        return self

    def order(self, *_a):
        return self

    def execute(self):
        self.db.reads += 1

        class _R:
            data = self.db.rows

        return _R()


class _Db:
    def __init__(self, rows):
        self.rows, self.reads = rows, 0

    def table(self, name):
        assert name == "notification_owner_recipients"
        return _Q(self)


def test_supabase_source_ttl_cache():
    db, now = _Db([{"numero": "+5511999990001", "nome": "A"}]), [0.0]
    src = SupabaseOwnerRecipientSource(lambda: db, ttl_seconds=60, clock=lambda: now[0])
    assert src.active() == [OwnerRecipient("+5511999990001", "A")]
    src.active()
    assert db.reads == 1
    now[0] = 61.0
    db.rows = []
    assert src.active() == [] and db.reads == 2


EXPECTED = "+5511999990099"


def _waha(factory, me="5511999990099@c.us"):
    return WahaOwnerLineTransport(factory, expected_numero=EXPECTED, me_fetch=lambda: me)


def test_waha_transport_sends_to_phone_and_propagates_errors():
    calls = []

    class C:
        def send_text_to_phone_sync(self, phone, text):
            calls.append((phone, text))

    _waha(lambda: C()).send_text("+5511999990001", "oi")
    assert calls == [("+5511999990001", "oi")]

    class Bad:
        def send_text_to_phone_sync(self, *_a):
            raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        _waha(lambda: Bad()).send_text("+5511999990001", "oi")
    with pytest.raises(ValueError):
        _waha(lambda: C()).send_text("abc", "oi")
    assert len(calls) == 1


def test_not_installed_default_fails_loudly(caplog):
    gate = FakeNotificationGate(P)
    with caplog.at_level(logging.ERROR):
        d = notify_owner(P, "aviso", "oi", gate=gate)
    assert (d.status, d.reason) == ("failed", "linha_noc_nao_instalada")
    assert f"seed.owner_line.nao_instalada product={P} kind=aviso" in caplog.text
    assert gate.sends[-1]["reason"] == "linha_noc_nao_instalada"
    # switch off still wins over "not installed"
    off = FakeNotificationGate(P, disabled={"aviso"})
    assert notify_owner(P, "aviso", "oi", gate=off).status == "suppressed"


def test_make_owner_line_without_core_client_fails_not_fakes():
    line = make_owner_line(None, lambda: object())
    configure_owner_line(recipients=line.recipients, transport=line.transport)
    gate = FakeNotificationGate(P)
    d = notify_owner(P, "aviso", "oi", gate=gate)
    assert d.status == "failed" and d.status != "no_recipient"


def test_make_owner_line_transport_presence():
    assert make_owner_line(lambda: _Db([]), None).transport is None
    ok = make_owner_line(lambda: _Db([]), lambda: object(), expected_numero=EXPECTED, me_fetch=lambda: "x")
    assert ok.transport is not None


def test_waha_url_without_expected_number_has_no_transport(caplog):
    with caplog.at_level(logging.ERROR):
        line = make_owner_line(lambda: _Db([]), lambda: object())
    assert line.transport is None
    configure_owner_line(recipients=FakeOwnerRecipientSource([R1]), transport=line.transport,
                         transport_reason=line.transport_reason)
    gate = FakeNotificationGate(P)
    d = notify_owner(P, "aviso", "oi", gate=gate)
    assert (d.status, d.reason) == ("failed", "linha_noc_numero_nao_declarado")


def test_matching_paired_number_sends_and_is_cached():
    calls, fetches = [], []

    class C:
        def send_text_to_phone_sync(self, phone, text):
            calls.append(phone)

    t = WahaOwnerLineTransport(lambda: C(), expected_numero=EXPECTED,
                               me_fetch=lambda: fetches.append(1) or "5511999990099@c.us")
    t.send_text(R1.numero, "a")
    t.send_text(R2.numero, "b")
    assert len(calls) == 2 and len(fetches) == 1


@pytest.mark.parametrize("me", ["5511888880000@c.us", None, ""])
def test_divergent_or_unknown_paired_number_sends_nothing(me):
    calls = []

    class C:
        def send_text_to_phone_sync(self, phone, text):
            calls.append(phone)

    t = WahaOwnerLineTransport(lambda: C(), expected_numero=EXPECTED, me_fetch=lambda: me)
    d = notify_owner(P, "aviso", "oi", gate=FakeNotificationGate(P), recipients=FakeOwnerRecipientSource([R1]),
                     transport=t)
    assert (d.status, d.reason) == ("failed", "1 de 1 falharam: linha_noc_numero_divergente")
    assert calls == []


def test_send_failure_log_never_carries_the_number(caplog):
    class Leaky:
        def send_text(self, numero, texto):
            raise RuntimeError(f"number {numero} is not on WhatsApp")

    with caplog.at_level(logging.DEBUG):
        d = _send(FakeNotificationGate(P), FakeOwnerRecipientSource([R1]), Leaky())
    assert d.status == "failed"
    import re
    for rec in caplog.records:
        text = rec.getMessage() + (rec.exc_text or "") + str(rec.exc_info)
        assert not re.search(r"\+?\d{10,15}", text), text
    assert any("0001" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("expected,me,sends", [
    ("+5511999990099", "551199990099@c.us", True),    # declared with the 9, paired without it
    ("+551199990099", "5511999990099@c.us", True),    # declared without, paired with
    ("+5511999990099", "5511999990098@c.us", False),  # differs in a non-9 digit
    ("+5511999990099", "551199990098@c.us", False),
    ("+14155550123", "14155550123@c.us", True),       # foreign: exact digits
    ("+14155550123", "14155550124@c.us", False),
])
def test_paired_number_match_uses_br_variants(expected, me, sends):
    calls = []

    class C:
        def send_text_to_phone_sync(self, phone, text):
            calls.append(phone)

    t = WahaOwnerLineTransport(lambda: C(), expected_numero=expected, me_fetch=lambda: me)
    if sends:
        t.send_text(R1.numero, "oi")
        assert calls == [R1.numero]
    else:
        with pytest.raises(OwnerLineNumberMismatch):
            t.send_text(R1.numero, "oi")
        assert calls == []


class _Ok:
    def __init__(self):
        self.calls = []

    def send_text_to_phone_sync(self, phone, text):
        self.calls.append(phone)


def test_device_suffixed_me_id_matches():
    """WAHA docs (waha.devlike.pro, GET /api/sessions/{session}/me) show ``{"id": "11111111111@c.us", "pushName":
    ..., "reachoutTimelock": null, "messageCapping": null}`` and return null when the session is stopped; the docs
    do not mention ``:<device>`` or ``@lid`` forms (newer engines emit them), so both are parsed defensively."""
    c = _Ok()
    WahaOwnerLineTransport(lambda: c, expected_numero=EXPECTED, me_fetch=lambda: "5511999990099:12@c.us"
                           ).send_text(R1.numero, "oi")
    assert c.calls == [R1.numero]


def test_lid_me_id_fails_closed_unknown(caplog):
    c = _Ok()
    t = WahaOwnerLineTransport(lambda: c, expected_numero=EXPECTED, me_fetch=lambda: "123456789012345@lid")
    with caplog.at_level(logging.ERROR):
        d = notify_owner(P, "aviso", "oi", gate=FakeNotificationGate(P),
                         recipients=FakeOwnerRecipientSource([R1]), transport=t)
    assert d.reason == "1 de 1 falharam: linha_noc_numero_desconhecido" and c.calls == []
    assert "linha_noc_numero_desconhecido" in caplog.text
    assert issubclass(OwnerLineNumberUnknown, Exception)


def test_verification_expires_after_15_minutes_and_refetches():
    now, fetches, c = [0.0], [], _Ok()
    t = WahaOwnerLineTransport(lambda: c, expected_numero=EXPECTED, clock=lambda: now[0],
                               me_fetch=lambda: fetches.append(1) or "5511999990099@c.us")
    t.send_text(R1.numero, "a")
    now[0] = 899.0
    t.send_text(R1.numero, "b")
    assert len(fetches) == 1
    now[0] = 901.0
    t.send_text(R1.numero, "c")
    assert len(fetches) == 2


def test_repair_to_another_number_is_caught_after_expiry():
    now, me, c = [0.0], ["5511999990099@c.us"], _Ok()
    t = WahaOwnerLineTransport(lambda: c, expected_numero=EXPECTED, clock=lambda: now[0], me_fetch=lambda: me[0])
    t.send_text(R1.numero, "a")
    me[0], now[0] = "5511888880000@c.us", 1000.0
    with pytest.raises(OwnerLineNumberMismatch):
        t.send_text(R1.numero, "b")


def test_send_failure_drops_the_verification_cache():
    fetches = []

    class Flaky:
        n = 0

        def send_text_to_phone_sync(self, phone, text):
            Flaky.n += 1
            if Flaky.n == 1:
                raise ConnectionError("down")

    t = WahaOwnerLineTransport(lambda: Flaky(), expected_numero=EXPECTED,
                               me_fetch=lambda: fetches.append(1) or "5511999990099@c.us")
    with pytest.raises(ConnectionError):
        t.send_text(R1.numero, "a")
    t.send_text(R1.numero, "b")
    assert len(fetches) == 2
