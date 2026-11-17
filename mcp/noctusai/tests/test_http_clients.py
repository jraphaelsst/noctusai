"""`_http.bounded_client` (httpx) + `_http.supabase_client` / `supabase_execute` (supabase-py): the TOTAL deadline on
the clients that `urlopen_read` does not cover. Real local sockets (hang / dribble / ok), no stand-ins for our own code."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "seed" / "lib" / "backend"))

from tools.noctus.dev import _http  # noqa: E402
from tests.test_http import event_log, server  # noqa: E402,F401  (fixtures)

_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.dummy-signature"  # supabase-py validates the key's SHAPE only


class TestBoundedClient:
    def test_dribbling_peer_cannot_reset_a_per_socket_read_timeout(self, server, event_log):
        """RED without the seam: the per-socket read timeout (30s) is reset by every byte; the total deadline is not."""
        s = server("dribble")
        t0 = time.monotonic()
        with _http.bounded_client(base_url=s.url, deadline_s=0.6, read=30, why="test dribble", call_site="t.bc") as c:
            with pytest.raises(httpx.HTTPError):  # an httpx error: existing `except httpx.HTTPError` handlers classify it
                c.request("GET", "/x")
        assert time.monotonic() - t0 < 5

    def test_hanging_peer_is_released_at_the_deadline(self, server, event_log):
        s = server("hang")
        t0 = time.monotonic()
        with _http.bounded_client(base_url=s.url, deadline_s=0.5, read=30, why="test hang", call_site="t.bc") as c:
            with pytest.raises(httpx.ReadTimeout):
                c.get("/x")
        assert time.monotonic() - t0 < 5

    def test_ok_response_and_verbs_pass_through(self, server):
        s = server("ok")
        with _http.bounded_client(base_url=s.url, deadline_s=10, why="test ok", call_site="t.bc") as c:
            assert c.get("/x").status_code == 200
            assert c.request("POST", "/x", json={"a": 1}).status_code == 200

    def test_http_errors_are_returned_not_raised(self, server):
        s = server("404")
        with _http.bounded_client(base_url=s.url, deadline_s=10, why="test 404", call_site="t.bc") as c:
            assert c.get("/x").status_code == 404

    def test_deadline_is_telemetry_with_site_and_reason(self, server, event_log):
        s = server("hang")
        with _http.bounded_client(base_url=s.url, deadline_s=0.3, read=30, why="batch sync", call_site="t.tele") as c:
            with pytest.raises(httpx.HTTPError):
                c.get("/x")
        blob = json.dumps([json.loads(line) for line in event_log.read_text().splitlines() if line.strip()])
        assert _http.EVENT_KIND in blob and "deadline_exceeded" in blob and "t.tele" in blob and "batch sync" in blob
        assert "127.0.0.1" in blob

    def test_why_is_mandatory_and_timeout_kwarg_is_refused(self):
        with pytest.raises(ValueError):
            _http.bounded_client(deadline_s=5, why=" ", call_site="t")
        with pytest.raises(TypeError):
            _http.bounded_client(deadline_s=5, why="x", call_site="t", timeout=5)
        with pytest.raises(ValueError):
            _http.bounded_client(deadline_s=0, why="x", call_site="t")


class TestSupabaseClient:
    def test_every_sub_client_gets_explicit_timeouts(self):
        c = _http.supabase_client("http://127.0.0.1:9", _JWT, call_site="t.sb", read=7.0)
        t = c.postgrest.session.timeout
        assert t.read == 7.0 and t.connect == _http.connect_timeout()

    def test_schema_is_forwarded(self):
        c = _http.supabase_client("http://127.0.0.1:9", _JWT, call_site="t.sb", schema="igig")
        assert c.postgrest.session.headers.get("accept-profile") == "igig"

    def test_slow_server_is_cut_by_the_explicit_read_timeout(self, server, event_log):
        s = server("hang")
        c = _http.supabase_client(s.url, _JWT, call_site="t.sb", read=0.5)
        t0 = time.monotonic()
        with pytest.raises(Exception) as ei:
            c.table("t").select("*").execute()
        assert "imeout" in type(ei.value).__name__ or "imeout" in str(ei.value)
        assert time.monotonic() - t0 < 10

    def test_dribbling_server_is_cut_by_the_total_deadline(self, server, event_log):
        s = server("dribble")
        c = _http.supabase_client(s.url, _JWT, call_site="t.sb", read=30)
        t0 = time.monotonic()
        with pytest.raises(_http.HttpDeadlineExceeded):
            _http.supabase_execute(c.table("t").select("*"), call_site="t.sbx", deadline_s=0.6)
        assert time.monotonic() - t0 < 5

    def test_supabase_execute_returns_data_when_healthy(self, server):
        s = server("ok")
        c = _http.supabase_client(s.url, _JWT, call_site="t.sb")
        assert _http.supabase_execute(c.table("t").select("*"), call_site="t.sbx", deadline_s=10).data == []
