"""Owner line: notify_owner outcomes, the Supabase recipient source TTL, the WAHA transport."""
from __future__ import annotations

import logging

import pytest

from noctusai_lib.domain.notification_catalog import (
    FakeNotificationGate,
    FakeOwnerLineTransport,
    FakeOwnerRecipientSource,
    NotificationKind,
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


def test_waha_transport_chat_id_and_error_propagation():
    calls = []

    class C:
        def send_text_sync(self, chat_id, text):
            calls.append((chat_id, text))

    WahaOwnerLineTransport(lambda: C()).send_text("+5511999990001", "oi")
    assert calls == [("5511999990001@c.us", "oi")]

    class Bad:
        def send_text_sync(self, *_a):
            raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        WahaOwnerLineTransport(lambda: Bad()).send_text("+5511999990001", "oi")
    with pytest.raises(ValueError):
        WahaOwnerLineTransport(lambda: C()).send_text("abc", "oi")


def test_make_owner_line_transport_presence():
    assert make_owner_line(lambda: _Db([]), None).transport is None
    assert make_owner_line(lambda: _Db([]), lambda: object()).transport is not None
