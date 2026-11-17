"""`tools/noctus/dev/_http.py` -- the whole-call bound + bounded retry on every outbound HTTP call.

Real sockets, no stand-ins for our own code: a local HTTP server in a thread that accepts and never
responds (or dribbles, or answers 5xx) proves the deadline fires, the retry is bounded, a lost write is
never blindly re-sent, and `migrate_product` returns `ledger_record_failed` instead of hanging (the
2026-11-16 incident: 45 min on one CLOSE_WAIT socket)."""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "seed" / "lib" / "backend"))

from tools.noctus.dev import _http  # noqa: E402
from tools.noctus.dev.migrate_product import SupabaseMgmtExecutor, migrate_product  # noqa: E402
from tests.test_migrate_product import (  # noqa: E402
    _clean_git_runner,
    _live_catalog_fn,
    _make_migration_files,
    _make_products_dir,
)


class _Server:
    """Local HTTP server. `mode`: hang | dribble | ok | 503 | 404 | flaky (first request hangs, then ok).
    `hang_if` (optional): a body substring -- only requests carrying it hang, the rest answer `[]`."""

    def __init__(self, mode: str, hang_if: str | None = None) -> None:
        self.mode = mode
        self.hang_if = hang_if
        self.hits = 0
        self.release = threading.Event()
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: D401 -- silence
                pass

            def _serve(self):
                outer.hits += 1
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n).decode() if n else ""
                mode = outer.mode
                if outer.hang_if is not None:
                    mode = "hang" if outer.hang_if in body else "ok"
                if mode == "flaky":
                    mode = "hang" if outer.hits == 1 else "ok"
                if mode == "hang":
                    outer.release.wait(30)
                    return
                if mode == "dribble":
                    self.send_response(200)
                    self.send_header("Content-Length", "100000")
                    self.end_headers()
                    while not outer.release.is_set():
                        try:
                            self.wfile.write(b"x")
                            self.wfile.flush()
                        except OSError:
                            return
                        time.sleep(0.1)
                    return
                code = {"503": 503, "404": 404}.get(mode, 200)
                payload = b"[]"
                self.send_response(code)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = _serve

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.release.set()
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    made: list[_Server] = []

    def make(mode: str, hang_if: str | None = None) -> _Server:
        s = _Server(mode, hang_if)
        made.append(s)
        return s

    yield make
    for s in made:
        s.close()


@pytest.fixture
def event_log(tmp_path, monkeypatch):
    path = tmp_path / "guard-events.ndjson"
    monkeypatch.setenv("NOCTUS_GUARD_EVENT_LOG", str(path))
    return path


def _noop_sleep(_s):
    return None


class TestDeadlineIsTotal:
    def test_server_that_never_responds_is_released_at_the_deadline(self, server, event_log):
        s = server("hang")
        t0 = time.monotonic()
        with pytest.raises(_http.HttpDeadlineExceeded):
            _http.urlopen_read(s.url, call_site="t.hang", retries=0, read=30, total=0.5)
        assert time.monotonic() - t0 < 5

    def test_dribbling_peer_cannot_reset_the_bound(self, server, event_log):
        """The incident class: a per-socket read timeout (1s here) is reset by every byte; the TOTAL deadline is not."""
        s = server("dribble")
        t0 = time.monotonic()
        with pytest.raises(TimeoutError):
            _http.urlopen_read(s.url, call_site="t.dribble", retries=0, read=1, total=0.6)
        assert time.monotonic() - t0 < 5

    def test_deadline_exceeded_is_a_timeout_error(self):
        assert issubclass(_http.HttpDeadlineExceeded, TimeoutError)

    def test_ok_response_is_returned(self, server):
        r = _http.urlopen_read(server("ok").url, call_site="t.ok", retries=0)
        assert r.status == 200 and r.body == b"[]"


class TestRetryIsBounded:
    def test_one_retry_on_timeout_then_gives_up(self, server, event_log):
        s = server("hang")
        with pytest.raises(_http.HttpDeadlineExceeded):
            _http.urlopen_read(s.url, call_site="t.retry", total=0.3, read=30, sleep=_noop_sleep)
        assert s.hits == 2  # the first try + exactly ONE retry

    def test_non_idempotent_write_is_not_resent_after_a_lost_response(self, server, event_log):
        s = server("hang")
        req = urllib.request.Request(s.url, data=b"{}", method="POST")
        with pytest.raises(_http.HttpDeadlineExceeded):
            _http.urlopen_read(req, call_site="t.write", idempotent=False, total=0.3, read=30, sleep=_noop_sleep)
        assert s.hits == 1

    def test_flaky_peer_succeeds_on_the_retry(self, server, event_log):
        s = server("flaky")
        r = _http.urlopen_read(s.url, call_site="t.flaky", total=0.4, read=30, sleep=_noop_sleep)
        assert r.status == 200 and s.hits == 2

    def test_5xx_is_retried_once_then_surfaces(self, server, event_log):
        s = server("503")
        with pytest.raises(urllib.error.HTTPError) as ei:
            _http.urlopen_read(s.url, call_site="t.5xx", sleep=_noop_sleep)
        assert ei.value.code == 503 and s.hits == 2

    def test_4xx_is_never_retried(self, server, event_log):
        s = server("404")
        with pytest.raises(urllib.error.HTTPError) as ei:
            _http.urlopen_read(s.url, call_site="t.4xx", sleep=_noop_sleep)
        assert ei.value.code == 404 and s.hits == 1

    def test_probe_with_retries_zero_never_retries(self, server, event_log):
        s = server("503")
        with pytest.raises(urllib.error.HTTPError):
            _http.urlopen_read(s.url, call_site="t.probe", retries=0)
        assert s.hits == 1


class TestTelemetryAndConfig:
    def test_timeout_and_retry_are_recorded_as_events(self, server, event_log):
        s = server("hang")
        with pytest.raises(_http.HttpDeadlineExceeded):
            _http.urlopen_read(s.url, call_site="t.events", total=0.3, read=30, sleep=_noop_sleep)
        rows = [json.loads(line) for line in event_log.read_text().splitlines() if line.strip()]
        mine = [r for r in rows if "t.events" in json.dumps(r)]
        assert mine, rows
        blob = json.dumps(mine)
        assert _http.EVENT_KIND in blob and "deadline_exceeded" in blob and "retry_1" in blob
        assert "127.0.0.1" in blob  # host rides on the event

    def test_env_overrides_the_defaults(self, monkeypatch):
        monkeypatch.setenv("NOC_HTTP_CONNECT_TIMEOUT_S", "3")
        monkeypatch.setenv("NOC_HTTP_READ_TIMEOUT_S", "7")
        monkeypatch.setenv("NOC_HTTP_TOTAL_DEADLINE_S", "11")
        assert (_http.connect_timeout(), _http.read_timeout(), _http.total_deadline()) == (3.0, 7.0, 11.0)

    def test_garbage_env_falls_back_to_the_default(self, monkeypatch):
        monkeypatch.setenv("NOC_HTTP_READ_TIMEOUT_S", "nope")
        assert _http.read_timeout() == 60.0

    def test_module_is_stdlib_only_at_import_time(self):
        import ast

        tree = ast.parse(Path(_http.__file__).read_text())
        top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        mods = {(n.module or "").split(".")[0] if isinstance(n, ast.ImportFrom) else a.name.split(".")[0]
                for n in top for a in (n.names if isinstance(n, ast.Import) else [n])}
        assert "noctusai_lib" not in mods and "httpx" not in mods  # watchdogs run with no pip


class TestSupabaseExecutorIsBounded:
    def test_execute_returns_a_typed_failure_instead_of_hanging(self, server, event_log):
        s = server("hang")
        ex = SupabaseMgmtExecutor(access_token="t", project_ref="ref", retry_ambiguous=False,
                                  base_url=s.url, total_deadline=0.4, sleep=_noop_sleep)
        t0 = time.monotonic()
        out = ex.execute("SELECT 1")
        assert out["ok"] is False and out.get("transient") is True
        assert s.hits == 1  # a write-mode executor never re-sends a maybe-executed request
        assert time.monotonic() - t0 < 5


class TestMigrateProductAlwaysReachesItsLedgerStep:
    def test_ledger_record_that_hangs_returns_ledger_record_failed(self, tmp_path, server, event_log):
        s = server("ok", hang_if="INSERT INTO")  # DDL + reads answer; the ledger INSERT never does
        products = _make_products_dir(tmp_path)
        _make_migration_files(products, "orbity", [("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;")])
        ex = SupabaseMgmtExecutor(access_token="t", project_ref="ref", retry_ambiguous=False,
                                  base_url=s.url, total_deadline=0.4, sleep=_noop_sleep)

        def persister(product, files):
            return {"status": "recorded", "path": "/iso/migrations-applied.json", "error": None}

        t0 = time.monotonic()
        result = migrate_product("orbity", confirm=True, executor=ex, products_dir=products,
                                 git_runner=_clean_git_runner(), live_products_fn=_live_catalog_fn("orbity"),
                                 record_persister=persister)
        assert time.monotonic() - t0 < 30
        assert result["status"] == "ledger_record_failed"
        assert result["exit_code"] == 1
        assert result["applied"] == ["001_seed.sql"]
        assert result["ledger_unrecorded"] == ["001_seed.sql"]
        assert result["reason"]
        assert "noctus.dev.record_applied_migrations product=orbity" in result["record_command"]
        assert "001_seed.sql" in result["record_command"]
        assert result["record_command"] in result["error"]

    def test_a_lost_insert_response_is_settled_by_a_read_not_assumed(self, tmp_path):
        """The INSERT's response is lost, but a READ shows the row: that is NOT a ledger failure."""
        class LostInsertResponse:
            """The write lands server-side; only its response is lost."""

            def __init__(self):
                self.executed: list[str] = []
                self.landed = False

            def execute(self, sql):
                self.executed.append(sql)
                if "INSERT INTO" in sql:
                    self.landed = True
                    return {"ok": False, "rows": None, "error": "timed out", "transient": True}
                if sql.lstrip().startswith("SELECT filename"):
                    rows = [{"filename": "001_seed.sql"}] if self.landed else []
                    return {"ok": True, "rows": rows, "error": None}
                return {"ok": True, "rows": [], "error": None}

        products = _make_products_dir(tmp_path)
        _make_migration_files(products, "orbity", [("001_seed.sql", "CREATE SCHEMA IF NOT EXISTS orbity;")])
        ex = LostInsertResponse()
        result = migrate_product("orbity", confirm=True, executor=ex, products_dir=products,
                                 git_runner=_clean_git_runner(), live_products_fn=_live_catalog_fn("orbity"),
                                 record_persister=lambda p, f: {"status": "recorded", "path": None, "error": None})
        assert result["status"] == "applied" and result["applied"] == ["001_seed.sql"]
        assert sum("INSERT INTO" in q for q in ex.executed) == 1  # confirmed by the read: not re-sent
