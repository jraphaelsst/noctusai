"""User-scoped clients: JWT goes straight to PostgREST (RLS still sees the user),
no second Auth `get_user`, no refresh Timer thread, and every client shares ONE
HTTP/1.1 keep-alive pool. KB § PATTERNS/backend/request-path-latency.md
"""
from __future__ import annotations

import http.server
import json
import threading

import httpx
import pytest

from noctusai_lib.integrations import http_pool
from noctusai_lib.integrations.database import make_supabase_client

KEY = "a" * 40 + "." + "b" * 40 + "." + "c" * 20
USER_JWT = "hdr." + "p" * 30 + ".sig"


class _Recorder:
    """A MockTransport handler that records what the wire would have carried."""

    def __init__(self):
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json=[{"id": 1}])


@pytest.fixture
def wire(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(http_pool, "shared_transport", lambda: httpx.MockTransport(rec))
    return rec


def _user_client(schema="orbity"):
    return make_supabase_client("https://x.supabase.co", KEY, KEY, schema=schema, access_token=USER_JWT)


class TestUserClientCarriesTheJwtWithoutASession:
    def test_postgrest_request_carries_the_users_bearer_and_schema(self, wire):
        """RLS reads `Authorization: Bearer <jwt>` + the schema profile."""
        _user_client().table("leads").select("*").execute()
        req = wire.requests[-1]
        assert req.headers["authorization"] == f"Bearer {USER_JWT}"
        assert req.headers["apikey"] == KEY  # the anon key, never the service role's
        assert req.headers["accept-profile"] == "orbity"

    def test_storage_also_carries_the_users_bearer(self, wire):
        c = _user_client()
        assert c.storage.session.headers["authorization"] == f"Bearer {USER_JWT}"

    def test_no_auth_get_user_call_and_no_gotrue_session(self, wire):
        c = _user_client()
        c.table("leads").select("*").execute()
        assert not [r for r in wire.requests if "/auth/v1/" in str(r.url)], "set_session's extra get_user is back"
        assert c.auth.get_session() is None

    def test_no_refresh_timer_thread_is_started(self, wire):
        before = threading.active_count()
        clients = [_user_client() for _ in range(5)]
        assert threading.active_count() == before
        assert all(getattr(c.auth, "_refresh_token_timer", None) is None for c in clients)

    def test_service_role_client_uses_the_service_key_and_is_not_a_user_client(self, wire):
        c = make_supabase_client("https://x.supabase.co", "anon." + "z" * 20 + "." + "z" * 10, KEY, schema="orbity")
        c.table("t").select("*").execute()
        assert wire.requests[-1].headers["authorization"] == f"Bearer {KEY}"

    def test_two_users_do_not_share_headers(self, wire):
        a = make_supabase_client("https://x.supabase.co", KEY, KEY, access_token="h.AAAA.s")
        b = make_supabase_client("https://x.supabase.co", KEY, KEY, access_token="h.BBBB.s")
        a.table("t").select("*").execute()
        b.table("t").select("*").execute()
        assert [r.headers["authorization"] for r in wire.requests] == ["Bearer h.AAAA.s", "Bearer h.BBBB.s"]


class TestPoolIsShared:
    def test_every_client_rides_one_transport(self):
        http_pool.reset_shared_transport()
        a, b = _user_client(), make_supabase_client("https://x.supabase.co", KEY, KEY)
        assert a.postgrest.session._transport is b.postgrest.session._transport is http_pool.shared_transport()
        assert a.storage.session._transport is http_pool.shared_transport()

    def test_closing_one_client_does_not_close_the_pool(self):
        http_pool.reset_shared_transport()
        a, b = _user_client(), _user_client()
        a.postgrest.session.close()
        a.storage.session.close()
        assert b.postgrest.session._transport is http_pool.shared_transport()
        assert b.postgrest.session.is_closed is False

    def test_http2_is_off_on_the_shared_transport(self):
        assert http_pool.shared_transport()._inner._pool._http2 is False

    def test_kill_switch_reverts_to_private_http1_clients(self, monkeypatch):
        monkeypatch.setenv("NOCTUS_HTTP_POOL", "0")
        c = _user_client()
        assert c.postgrest.session._transport is not http_pool.shared_transport()
        assert c.postgrest.session.headers["authorization"] == f"Bearer {USER_JWT}"


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive

    def do_GET(self):  # noqa: N802
        # postgrest sends `{}` as the body of a GET; a real server drains it by
        # Content-Length — leaving it unread corrupts the next request on the
        # kept-alive connection (that is a test-server artifact, not a pool bug).
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        body = json.dumps([{"id": 1}]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        self.do_GET()

    def log_message(self, *a):
        return


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    # The default listen backlog (5) is smaller than the 8 threads that open
    # their first connection at once — macOS RESETS the overflow
    # (ConnectError Errno 54), a flake of this fake server, not of the pool.
    request_queue_size = 64

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.connections = 0

    def get_request(self):
        conn = super().get_request()
        self.connections += 1
        return conn


class TestLiveKeepAliveAndThreads:
    """Real sockets: 40 requests from 40 DIFFERENT clients across 8 threads reuse a
    handful of connections (the old behaviour was one TCP+TLS handshake each)."""

    def test_connections_are_reused_across_clients_and_threads(self):
        http_pool.reset_shared_transport()
        srv = _Server(("127.0.0.1", 0), _Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        errors, ok = [], []

        def worker(n):
            try:
                for i in range(5):
                    c = make_supabase_client(url, KEY, KEY, schema="s", access_token=f"h.{n}{i}.s")
                    assert c.table("t").select("*").execute().data == [{"id": 1}]
                    ok.append(1)
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        srv.shutdown()
        assert errors == [] and len(ok) == 40
        # <= concurrency (8) plus slack; a handshake per request would be 40.
        assert srv.connections <= 12, srv.connections
