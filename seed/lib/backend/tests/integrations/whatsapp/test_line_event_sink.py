"""The persistent LineEventSink: boot with `send: disabled` works with it, refuses without it, refusals land as rows."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.sql_templates import whatsapp_line_events_table_sql
from noctusai_lib.integrations.whatsapp import (
    LineEvent, LinePolicyError, LineEventPersistenceError, LineWriteRefused, SupabaseLineEventSink,
    FakeLineEventSink, clear_line_policies, make_line_event_sink, parse_line_policy, register_line_policy,
    set_default_line_event_sink,
)
from noctusai_lib.integrations.whatsapp import line_policy as lp

DISABLED = {"send": "disabled", "mark_online": False, "full_sync": False, "auto_repair": False}


@pytest.fixture(autouse=True)
def _isolated():
    clear_line_policies()
    prior = lp.get_default_line_event_sink()
    yield
    set_default_line_event_sink(prior)
    clear_line_policies()


def test_disabled_line_refused_with_in_memory_sink():
    set_default_line_event_sink(lp.InMemoryLineEventSink())
    with pytest.raises(LinePolicyError, match="in-memory"):
        register_line_policy("http://waha-x:3000", parse_line_policy(DISABLED))


def test_disabled_line_boots_with_persistent_sink_and_refusal_lands_as_row():
    sink = make_line_event_sink(schema="assistant", use_fake=True)
    set_default_line_event_sink(sink)
    register_line_policy("http://waha-x:3000", parse_line_policy(DISABLED))
    ev = LineEvent("whatsapp.line.write_refused", "http://waha-x:3000", "POST /api/sendText", "send_disabled", DISABLED)
    sink.record(ev)
    row, = sink.rows
    assert (row["event"], row["op"], row["reason"], row["policy"]) == (ev.event, ev.op, ev.reason, DISABLED)


def test_persistence_failure_is_loud():
    sink = FakeLineEventSink(fail_with=RuntimeError("db down"))
    with pytest.raises(LineEventPersistenceError):
        sink.record(LineEvent("e", "l", "o", "r", {}))


class _Table:
    def __init__(self, log, fail):
        self.log, self.fail = log, fail

    def schema(self, s):
        self.log.append(("schema", s)); return self

    def table(self, t):
        self.log.append(("table", t)); return self

    def insert(self, row):
        self.log.append(("insert", row)); return self

    def execute(self):
        if self.fail:
            raise ConnectionError("boom")


def test_real_sink_inserts_into_the_schema_table_and_raises_on_failure(caplog):
    log: list = []
    sink = SupabaseLineEventSink(lambda: _Table(log, False), schema="assistant")
    sink.record(LineEvent("e", "l", "o", "r", {"send": "disabled"}))
    assert log[0] == ("schema", "assistant") and log[1] == ("table", "whatsapp_line_events") and log[2][1]["event"] == "e"
    bad = SupabaseLineEventSink(lambda: _Table([], True), schema="assistant")
    with pytest.raises(LineEventPersistenceError), caplog.at_level("CRITICAL"):
        bad.record(LineEvent("e", "l", "o", "r", {}))
    assert "NOT persisted" in caplog.text


def test_real_sink_needs_a_client_factory():
    with pytest.raises(ValueError):
        make_line_event_sink(schema="assistant")


def test_table_template_is_insert_only_service_only():
    sql = whatsapp_line_events_table_sql("assistant")
    assert "REVOKE UPDATE, DELETE, TRUNCATE" in sql and "GRANT SELECT, INSERT" in sql
    assert "BEFORE UPDATE OR DELETE" in sql and "tier:service" in sql
