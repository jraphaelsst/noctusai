"""TimingTransport: per-request Supabase call timing (count, duration, new connection, service)."""
from __future__ import annotations

import httpx

from noctusai_lib.api import request_timing as rt
from noctusai_lib.integrations.http_pool import TimingTransport, service_of


class _Inner(httpx.BaseTransport):
    """Stands in for HTTPTransport; fires the trace events httpcore would."""

    def __init__(self, events=(), exc=None):
        self.events, self.exc = events, exc

    def handle_request(self, request):
        trace = request.extensions.get("trace")
        for name in self.events:
            trace(name, {})
        if self.exc:
            raise self.exc
        return httpx.Response(200, request=request)


def _stats():
    return rt._new_stats(1)


def _send(transport, url="https://x.supabase.co/rest/v1/t?id=eq.secret"):
    return transport.handle_request(httpx.Request("GET", url))


def test_counts_and_services_and_no_url_recorded():
    st = _stats()
    tok = rt._STATS.set(st)
    try:
        t = TimingTransport(_Inner())
        _send(t)
        _send(t, "https://x.supabase.co/auth/v1/user")
        _send(t, "https://x.supabase.co/functions/v1/f")
    finally:
        rt._STATS.reset(tok)
    assert st["db_n"] == 3 and st["db_new"] == 0 and st["db_conn_s"] == 0.0
    assert set(st["db_svc"]) == {"rest", "auth", "other"}
    assert st["db_max_s"] <= st["db_s"]
    assert "secret" not in repr(st)


def test_new_connection_detected_from_trace_events():
    st = _stats()
    tok = rt._STATS.set(st)
    try:
        t = TimingTransport(_Inner(["connection.connect_tcp.started", "connection.connect_tcp.complete",
                                    "connection.start_tls.started", "connection.start_tls.complete"]))
        _send(t)
        _send(TimingTransport(_Inner(["http11.send_request_headers.started"])))  # reused connection
    finally:
        rt._STATS.reset(tok)
    assert st["db_n"] == 2 and st["db_new"] == 1 and st["db_conn_s"] >= 0.0


def test_chains_existing_trace_callback():
    seen = []
    req = httpx.Request("GET", "https://x.supabase.co/storage/v1/o", extensions={"trace": lambda n, i: seen.append(n)})
    TimingTransport(_Inner(["connection.connect_tcp.started"])).handle_request(req)
    assert seen == ["connection.connect_tcp.started"]


def test_noop_outside_request_and_records_on_error():
    assert rt.current_stats() is None
    _send(TimingTransport(_Inner()))  # must not raise
    st = _stats()
    tok = rt._STATS.set(st)
    try:
        try:
            _send(TimingTransport(_Inner(exc=httpx.ConnectError("boom"))))
        except httpx.ConnectError:
            pass
    finally:
        rt._STATS.reset(tok)
    assert st["db_n"] == 1


def test_service_of():
    assert service_of(httpx.URL("https://h/rest/v1/x")) == "rest"
    assert service_of(httpx.URL("https://h/storage/v1/x")) == "storage"
    assert service_of(httpx.URL("https://h/")) == "other"


def test_header_and_log_fields_present_only_with_calls():
    st = _stats()
    assert "db;" not in rt.server_timing_value(5.0, st) and "db_n" not in rt.log_suffix(st)
    st.update(db_n=3, db_s=0.3, db_max_s=0.15, db_new=1, db_conn_s=0.05, db_svc={"rest": [3, 0.3]})
    h = rt.server_timing_value(5.0, st)
    assert 'db;dur=300.0;desc="3"' in h and "dbmax;dur=150.0" in h and 'dbconn;dur=50.0;desc="1"' in h
    assert " db_n=3 db_ms=300.0 db_max_ms=150.0 db_new=1 db_conn_ms=50.0 db_svc=rest:3:300.0" in rt.log_suffix(st)
