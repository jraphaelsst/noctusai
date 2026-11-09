"""Owner-notification catalog: declarations, the Fake/Real gate, the fail-toward-warning posture."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.notification_catalog import (
    FakeNotificationGate,
    NotificationKind,
    SupabaseNotificationGate,
    UndeclaredNotificationKind,
    declare_kinds,
    declared_kinds,
    make_notification_gate,
    reset_declarations_for_tests,
    send_row,
    status_for,
)

P = "catalog-test-product"


def _kind(kind: str = "aviso", titulo: str = "Aviso") -> NotificationKind:
    return NotificationKind(kind=kind, titulo=titulo, descricao="O que chega.", gatilho="Quando dispara.")


@pytest.fixture(autouse=True)
def _clean():
    reset_declarations_for_tests(P)
    yield
    reset_declarations_for_tests(P)


class _Query:
    def __init__(self, db: "_Db", table: str):
        self.db, self.table, self.op, self.payload, self.filters = db, table, "select", None, []

    def select(self, *_a, **_k):
        self.op = "select"
        return self

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    def upsert(self, rows, on_conflict=None):
        self.op, self.payload = "upsert", rows
        return self

    def insert(self, row):
        self.op, self.payload = "insert", row
        return self

    def execute(self):
        self.db.calls.append((self.table, self.op, self.payload, list(self.filters)))
        if self.db.fail:
            raise RuntimeError("core down")

        class R:
            data = None

        r = R()
        if self.op == "select":
            r.data = [r_ for r_ in self.db.rows if all(r_.get(c) == v for c, v in self.filters)]
        return r


class _Db:
    def __init__(self, rows=None, fail=False):
        self.rows, self.fail, self.calls = rows or [], fail, []

    def table(self, name):
        return _Query(self, name)


def test_kind_validates_slug_texts_and_channels():
    with pytest.raises(ValueError):
        NotificationKind(kind="Bad-Kind", titulo="t", descricao="d", gatilho="g")
    with pytest.raises(ValueError):
        NotificationKind(kind="ok", titulo=" ", descricao="d", gatilho="g")
    with pytest.raises(ValueError):
        NotificationKind(kind="ok", titulo="t", descricao="d", gatilho="g", canais=("sms",))


def test_declaring_twice_same_is_noop_different_raises():
    declare_kinds(P, [_kind()])
    declare_kinds(P, [_kind()])
    assert [k.kind for k in declared_kinds(P)] == ["aviso"]
    with pytest.raises(ValueError):
        declare_kinds(P, [_kind(titulo="Outro título")])


def test_fake_gate_refuses_undeclared_kind_and_honours_switch():
    declare_kinds(P, [_kind()])
    gate = FakeNotificationGate(P, disabled={"aviso"})
    assert gate.allowed("aviso") is False
    with pytest.raises(UndeclaredNotificationKind):
        gate.allowed("nunca_declarado")
    gate.record("aviso", org_id=None, status="suppressed", recipients=1)
    assert gate.sends[0]["status"] == "suppressed"


def test_real_gate_registers_without_touching_enabled_and_reads_switch():
    declare_kinds(P, [_kind()])
    db = _Db(rows=[{"product": P, "kind": "aviso", "enabled": False}])
    gate = SupabaseNotificationGate(P, lambda: db)
    gate.register()
    upsert = next(c for c in db.calls if c[1] == "upsert")
    assert upsert[0] == "notification_kinds"
    assert "enabled" not in upsert[2][0]  # a redeploy never re-enables what the owner switched off
    assert gate.allowed("aviso") is False


def test_real_gate_unknown_row_defaults_on_and_caches_within_ttl():
    declare_kinds(P, [_kind()])
    db = _Db(rows=[])
    t = [0.0]
    gate = SupabaseNotificationGate(P, lambda: db, ttl_seconds=60, clock=lambda: t[0])
    assert gate.allowed("aviso") is True
    reads = sum(1 for c in db.calls if c[1] == "select")
    gate.allowed("aviso")
    assert sum(1 for c in db.calls if c[1] == "select") == reads
    t[0] = 61.0
    gate.allowed("aviso")
    assert sum(1 for c in db.calls if c[1] == "select") == reads + 1


def test_real_gate_fails_toward_warning_when_core_is_unreadable(caplog):
    declare_kinds(P, [_kind()])
    gate = SupabaseNotificationGate(P, lambda: _Db(fail=True))
    with caplog.at_level("ERROR"):
        assert gate.allowed("aviso") is True
        gate.record("aviso", status="sent", recipients=1, delivered=1)  # ledger failure never raises
    assert any("sending anyway" in r.message for r in caplog.records)


def test_send_row_and_status_for():
    assert status_for(recipients=0, delivered=0, failed=0) == "no_recipient"
    assert status_for(recipients=2, delivered=2, failed=0) == "sent"
    assert status_for(recipients=2, delivered=1, failed=1) == "partial"
    assert status_for(recipients=1, delivered=0, failed=1) == "failed"
    row = send_row(P, "aviso", org_id=None, status="failed", recipients=1, delivered=0, reason="x" * 999)
    assert len(row["reason"]) == 300
    with pytest.raises(ValueError):
        send_row(P, "aviso", org_id=None, status="weird", recipients=0, delivered=0, reason=None)


def test_factory_without_core_is_the_fake():
    assert isinstance(make_notification_gate(P, None), FakeNotificationGate)
