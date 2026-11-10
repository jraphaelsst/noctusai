"""`noctus.dev.supabase_request_budget` — the telemetry leg of the polling-budget rule.

WHY (2026-11-10). The Free-plan project was Fair-Use restricted (HTTP 402 on every call) after
~620k REST calls/day from our own pollers; nothing measured request volume, so the first signal was
the 402 (`KB § PATTERNS/backend/polling-request-budget.md`). These tests pin what decides whether the
owner is told in time: shape normalisation (the logs carry user ids / emails / phones — no raw value
may survive: LGPD), the threshold verdicts, the 402 path, and that an unmeasurable read is `unknown`,
never a green `ok` and never a red. Every network edge is the injected `LogsSource` seam (Fake here).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import supabase_request_budget as srb  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
UUID = "3f2b8c1e-9d4a-4e6b-8a7c-1234567890ab"
EMAIL = "maria.silva@example.com"
PHONE = "5511999998888"
NOW = "2026-11-10T12:00:00Z"
RAW_VALUES = (UUID, EMAIL, PHONE, "maria", "silva", "transcricao")


# ── normalisation: no raw value survives ─────────────────────────────────────
@pytest.mark.parametrize("search, expected", [
    (f"?id=eq.{UUID}", "id=eq.?"),
    (f"?id=in.({UUID},{UUID})", "id=in.(?)"),
    (f"?email=eq.{EMAIL}&select=*", "email=eq.?&select=*"),
    (f"?phone=eq.{PHONE}", "phone=eq.?"),
    ("?type=eq.transcricao&limit=5000&offset=1200", "limit=5000&offset=?&type=eq.?"),
    (f"?or=(email.eq.{EMAIL},id.eq.{UUID})", "or=(email.eq.?,id.eq.?)"),
    ("?nome=ilike.%25silva%25", "nome=ilike.?"),
    ("?order=created_at.desc&select=id,nome", "order=created_at.desc&select=id,nome"),
    (f"?id=not.in.({UUID})", "id=not.in.(?)"),
    ("", ""),
    (None, ""),
])
def test_normalize_search(search, expected):
    assert srb.normalize_search(search) == expected


def test_normalize_search_is_stable_regardless_of_param_order():
    assert srb.normalize_search("?b=eq.1&a=eq.2") == srb.normalize_search("?a=eq.9&b=eq.8")


@pytest.mark.parametrize("path", [
    f"/rest/v1/clientes/{UUID}",
    f"/auth/v1/admin/users/{UUID}",
    f"/storage/v1/object/sign/fotos/{UUID}/{PHONE}.jpg",
    f"/rest/v1/rpc/f/{EMAIL}",
])
def test_normalize_path_drops_ids_emails_and_storage_object_names(path):
    out = srb.normalize_path(path)
    for raw in (UUID, EMAIL, PHONE):
        assert raw not in out


def test_normalize_path_keeps_the_endpoint_identity():
    assert srb.normalize_path("/rest/v1/rpc/claim_next_job") == "/rest/v1/rpc/claim_next_job"
    assert srb.normalize_path("/rest/v1/jobs") == "/rest/v1/jobs"
    assert srb.normalize_path(f"/rest/v1/clientes/{UUID}") == "/rest/v1/clientes/?"


# F8: the path is an ALLOWLIST (/{rest|auth|storage|functions}/v1/<known first segment>), everything else `?`
@pytest.mark.parametrize("path, expected", [
    ("/storage/v1/render/image/public/fotos/joao_cpf_123456.jpg", "/storage/v1/render/image/public/?"),
    ("/storage/v1/object/sign/contratos/maria-silva-rg.pdf", "/storage/v1/object/sign/?"),
    ("/rest/v1/maria.silva", "/rest/v1/?"),
    ("/rest/v1/rpc/claim_next_job", "/rest/v1/rpc/claim_next_job"),
    ("/rest/v1/rpc/Maria.Silva", "/rest/v1/rpc/?"),
    ("/rest/v1/clientes/extra/maria", "/rest/v1/clientes/?"),
    ("/auth/v1/token", "/auth/v1/token"),
    ("/auth/v1/secret-thing-joao", "/auth/v1/?"),
    ("/auth/v1/admin/users/abc", "/auth/v1/admin/?"),
    ("/functions/v1/send-mail/joao", "/functions/v1/send-mail/?"),
    ("/some/other/maria", "/?"),
    ("/", "/"),
    ("", "/"),
])
def test_normalize_path_is_an_allowlist(path, expected):
    assert srb.normalize_path(path) == expected


def test_user_agent_family_never_carries_a_version_or_free_text():
    assert srb.ua_family("python-httpx/0.27.2") == "python-httpx"
    assert srb.ua_family("Mozilla/5.0 (Macintosh) AppleWebKit") == "browser"
    assert srb.ua_family("supabase-js/2.45.0 node") == "supabase-js"
    assert srb.ua_family("") == "unknown"
    assert srb.ua_family(None) == "unknown"


# ── verdicts ─────────────────────────────────────────────────────────────────
def _source(shape_rows, status_rows, usage=None, trip_shape_rows=None):
    """Rows default to our own servers' traffic (role service_role); anon rows say so explicitly."""
    status_rows = [{"role": "service_role", **r} for r in status_rows]
    return srb.FakeLogsSource(shape_rows=shape_rows, status_rows=status_rows, usage_rows=usage,
                              trip_shape_rows=trip_shape_rows)


def _eval(source, **kw):
    kw.setdefault("now", NOW)
    kw.setdefault("window_hours", 1.0)
    return srb.evaluate(source, **kw)


def test_quiet_traffic_is_ok():
    rep = _eval(_source(
        [{"m": "GET", "p": "/rest/v1/clientes", "s": "?select=*", "calls": 120}],
        [{"ua": "python-httpx/0.27", "status": 200, "calls": 120}],
    ))
    assert rep["verdict"] == "ok" and rep["total_calls"] == 120
    assert rep["projected_per_day"] == 120 * 24
    assert rep["offenders"] == []


def test_projected_total_over_warn_is_warn():
    # 5,000/h -> 120k/day: over 100k warn, under 250k critical; no single shape is hot
    rep = _eval(_source(
        [{"m": "GET", "p": f"/rest/v1/t{i}", "s": "", "calls": 250} for i in range(20)],
        [{"ua": "python-httpx/0.27", "status": 200, "calls": 5000}],
    ))
    assert rep["verdict"] == "warn"
    assert [o["reason"] for o in rep["offenders"]] == ["total_projected"]


def test_projected_total_over_critical_is_critical():
    rep = _eval(_source(
        [{"m": "GET", "p": "/rest/v1/a", "s": "?select=*", "calls": 100}],
        [{"ua": "python-httpx/0.27", "status": 200, "calls": 11_000}],  # 264k/day
    ))
    assert rep["verdict"] == "critical"


def test_one_hot_shape_is_warn_then_critical_and_values_collapse_into_one_shape():
    # the incident: the same query with a different value each tick is ONE shape
    rows = [{"m": "GET", "p": "/rest/v1/jobs", "s": f"?type=eq.transcricao&id=eq.{UUID[:-2]}{i:02d}", "calls": 10}
            for i in range(80)]  # 800/h -> 19.2k/day -> warn
    rep = _eval(_source(rows, [{"ua": "python-httpx/0.27", "status": 200, "calls": 800}]))
    assert rep["verdict"] == "warn"
    top = rep["top_shapes"][0]
    assert top["calls"] == 800 and top["shape"] == "GET /rest/v1/jobs ?id=eq.?&type=eq.?"
    rows = [{"m": "POST", "p": "/rest/v1/rpc/claim_next_job", "s": "", "calls": 2200}]  # 52.8k/day
    rep = _eval(_source(rows, [{"ua": "python-httpx/0.27", "status": 200, "calls": 2200}]))
    assert rep["verdict"] == "critical"
    assert rep["offenders"][0]["shape"] == "POST /rest/v1/rpc/claim_next_job"


def test_a_402_wave_is_critical_even_when_volume_is_tiny():
    rep = _eval(_source(
        [{"m": "GET", "p": "/rest/v1/clientes", "s": "", "calls": 3}],
        [{"ua": "python-httpx/0.27", "status": 402, "calls": 100}],
    ))
    assert rep["verdict"] == "critical"
    assert rep["status_402"] == 100 and rep["restricted"] is True
    assert any(o["reason"] == "http_402" for o in rep["offenders"])


def test_4xx_counts_and_ua_families_are_reported():
    rep = _eval(_source(
        [{"m": "GET", "p": "/rest/v1/x", "s": "", "calls": 10}],
        [{"ua": "python-httpx/0.27", "status": 200, "calls": 6},
         {"ua": "Mozilla/5.0 x", "status": 401, "calls": 3},
         {"ua": "python-httpx/0.27", "status": 404, "calls": 1}],
    ))
    assert rep["status_4xx"] == 4 and rep["status_402"] == 0
    assert rep["by_user_agent"] == [{"family": "python-httpx", "calls": 7}, {"family": "browser", "calls": 3}]


def test_thresholds_are_configurable_from_env():
    th = srb.thresholds({"SUPABASE_BUDGET_WARN_TOTAL_PER_DAY": "1000", "SUPABASE_BUDGET_CRIT_TOTAL_PER_DAY": "5000"})
    rep = _eval(_source([{"m": "GET", "p": "/rest/v1/a", "s": "", "calls": 300}],
                        [{"ua": "x", "status": 200, "calls": 300}]), th=th)  # 7.2k/day
    assert rep["verdict"] == "critical"
    with pytest.raises(ValueError):
        srb.thresholds({"SUPABASE_BUDGET_WARN_TOTAL_PER_DAY": "lots"})


def test_no_raw_value_reaches_the_report():
    rep = _eval(_source(
        [{"m": "GET", "p": f"/rest/v1/clientes/{UUID}", "s": f"?email=eq.{EMAIL}&phone=eq.{PHONE}&or=(id.eq.{UUID})", "calls": 5000},
         {"m": "GET", "p": "/rest/v1/jobs", "s": "?type=eq.transcricao", "calls": 10}],
        [{"ua": f"python-httpx/{EMAIL}", "status": 402, "calls": 5010}],
    ))
    blob = repr(rep)
    for raw in RAW_VALUES:
        assert raw not in blob, raw


def test_window_is_capped_at_24h_and_validated():
    rep = _eval(_source([], [{"ua": "x", "status": 200, "calls": 1}]), window_hours=48)
    assert rep["window_hours"] == 24.0
    with pytest.raises(ValueError):
        _eval(_source([], []), window_hours=0)


def test_zero_traffic_in_window_is_ok_not_unknown():
    rep = _eval(_source([], []))
    assert rep["verdict"] == "ok" and rep["total_calls"] == 0


def test_unreadable_logs_are_unknown_never_ok_never_critical():
    rep = _eval(srb.FakeLogsSource(error=srb.LogsError("HTTP 503", transient=True)))
    assert rep["verdict"] == "unknown" and rep["ok"] is False
    assert "503" in rep["error"]


def test_usage_counts_are_included_when_available_and_optional():
    usage = [{"timestamp": "2026-11-10T11:00:00", "total_rest_requests": 100, "total_auth_requests": 5,
              "total_storage_requests": 1, "total_realtime_requests": 0}]
    rep = _eval(_source([], [{"ua": "x", "status": 200, "calls": 1}], usage=usage))
    assert rep["usage"]["available"] is True and rep["usage"]["rest_requests_24h"] == 100
    rep = _eval(_source([], [{"ua": "x", "status": 200, "calls": 1}], usage=[]))
    assert rep["usage"]["available"] is False
    assert "egress" in rep["usage"]["note"].lower()


# ── Real source: request shape, token never leaks ────────────────────────────
class _Resp:
    def __init__(self, body: bytes, status=200):
        self._b, self.status = body, status

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_real_source_builds_the_logs_request_and_hides_the_token():
    seen = {}

    def opener(req, timeout):
        seen["url"], seen["auth"] = req.full_url, req.get_header("Authorization")
        return _Resp(b'{"result":[{"calls":1}]}')

    src = srb.RealLogsSource(token="sbp_SECRET", project_ref="abcdefghijklmnopqrst", opener=opener)
    rows = src.query_logs("select 1", "2026-11-09T00:00:00Z", "2026-11-09T21:55:00Z")
    assert rows == [{"calls": 1}]
    assert "/v1/projects/abcdefghijklmnopqrst/analytics/endpoints/logs?" in seen["url"]
    assert "iso_timestamp_start=2026-11-09T00%3A00%3A00Z" in seen["url"]
    assert seen["auth"] == "Bearer sbp_SECRET"
    assert "sbp_SECRET" not in repr(src)


def test_real_source_http_error_never_echoes_the_token():
    import urllib.error

    def opener(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

    src = srb.RealLogsSource(token="sbp_SECRET", project_ref="abcdefghijklmnopqrst", opener=opener)
    with pytest.raises(srb.LogsError) as ei:
        src.query_logs("select 1", "a", "b")
    assert "403" in str(ei.value) and "sbp_SECRET" not in str(ei.value)


def test_make_source_without_a_token_is_none():
    assert srb.make_source({}) is None
    assert isinstance(srb.make_source({"SUPABASE_ACCESS_TOKEN": "t"}), srb.RealLogsSource)


def test_module_imports_under_bare_stdlib():
    """prod_watchdog runs in CI with no pip install and imports this module."""
    code = ("import sys; sys.path.insert(0, sys.argv[1]);"
            "from tools.noctus.dev import supabase_request_budget as m; print(m.DEFAULT_PROJECT_REF)")
    out = subprocess.run([sys.executable, "-I", "-S", "-c", code, str(REPO / "mcp" / "noctusai")],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr


def test_registered_and_cli_wired():
    init = (REPO / "mcp/noctusai/tools/noctus/dev/__init__.py").read_text()
    cli = (REPO / "mcp/noctusai/cli.py").read_text()
    assert "supabase_request_budget.register(server)" in init
    assert "--supabase-request-budget" in cli


# ── F1: only OUR servers' traffic can trip the breaker (anonymous floods must not) ──
def test_anonymous_junk_flood_never_trips_it_can_only_warn():
    anon = [{"ua": "curl/8", "status": 401, "role": "anon", "calls": 3000},
            {"ua": "curl/8", "status": 403, "role": "anon", "calls": 3000},
            {"ua": "curl/8", "status": 400, "role": "", "calls": 20_000}]
    rep = srb.evaluate(
        srb.FakeLogsSource(status_rows=anon, trip_shape_rows=[],
                           shape_rows=[{"m": "GET", "p": "/rest/v1/clientes", "s": "", "calls": 26_000}]),
        now=NOW, window_hours=1.0)
    assert rep["verdict"] == "warn" and rep["trip"] is False
    assert rep["total_calls"] == 26_000 and rep["eligible_calls"] == 0
    assert all(o["level"] != "critical" for o in rep["offenders"])


def test_an_anon_or_keyless_402_does_not_trip():
    rows = [{"ua": "x", "status": 402, "role": "anon", "calls": 50}, {"ua": "x", "status": 402, "role": "", "calls": 50}]
    rep = srb.evaluate(srb.FakeLogsSource(status_rows=rows, trip_shape_rows=[], shape_rows=[]), now=NOW)
    assert rep["verdict"] != "critical" and rep["trip"] is False and rep["status_402"] == 0
    assert rep["status_402_all"] == 100


def test_service_role_failures_and_errors_are_not_trip_traffic_but_service_role_402_is():
    rows = [{"ua": "python-httpx/0.27", "status": 500, "role": "service_role", "calls": 30_000}]
    rep = srb.evaluate(srb.FakeLogsSource(status_rows=rows, trip_shape_rows=[], shape_rows=[]), now=NOW)
    assert rep["trip"] is False and rep["eligible_calls"] == 0
    rows = [{"ua": "python-httpx/0.27", "status": 402, "role": "service_role", "calls": 100}]
    rep = srb.evaluate(srb.FakeLogsSource(status_rows=rows, trip_shape_rows=[], shape_rows=[]), now=NOW)
    assert rep["trip"] is True and rep["verdict"] == "critical" and rep["status_402"] == 100


def test_the_trip_queries_filter_on_the_service_role_claim_and_non_error_status():
    src = srb.FakeLogsSource(status_rows=[], shape_rows=[])
    srb.evaluate(src, now=NOW)
    sqls = [c[0] for c in src.calls]
    trip_sql = [q for q in sqls if "request.search" in q and "service_role" in q]
    assert trip_sql, sqls
    assert "request.sb.jwt.apikey.payload.role" in trip_sql[0]
    assert any("request.sb.jwt.apikey.payload.role" in q for q in sqls if "request.search" not in q)


def test_reports_carry_counts_only_reasons_for_public_logs():
    rep = _eval(_source([{"m": "POST", "p": "/rest/v1/rpc/claim_next_job", "s": "", "calls": 2200}],
                        [{"ua": "python-httpx/0.27", "status": 200, "calls": 2200}]))
    assert "claim_next_job" in " ".join(rep["reasons"])
    assert rep["reasons_public"] and "claim_next_job" not in " ".join(rep["reasons_public"])


# ── N1/N2/N5: the role claim is NOT a verified identity; only PostgREST-answered traffic can trip ──
@pytest.mark.parametrize("role, method, path, status, expected", [
    ("service_role", "GET", "/rest/v1/jobs", 200, True),
    ("service_role", "POST", "/rest/v1/rpc/claim_next_job", 201, True),
    ("service_role", "GET", "/rest/v1/jobs", 402, True),
    ("service_role", "OPTIONS", "/rest/v1/jobs", 204, False),      # CORS preflight answers before key-auth
    ("service_role", "OPTIONS", "/rest/v1/jobs", 402, False),
    ("service_role", "GET", "/auth/v1/verify", 302, False),         # forged-role 3xx before key-auth
    ("service_role", "GET", "/auth/v1/authorize", 302, False),
    ("service_role", "GET", "/functions/v1/x", 200, False),         # verify_jwt=false functions
    ("service_role", "GET", "/storage/v1/object/public/a/b", 200, False),
    ("service_role", "GET", "/rest/v1/jobs", 401, False),           # a forged JWT is rejected by PostgREST
    ("service_role", "GET", "/rest/v1/jobs", 500, False),
    ("anon", "GET", "/rest/v1/jobs", 200, False),
    ("", "GET", "/rest/v1/jobs", 200, False),
])
def test_trip_traffic_predicate(role, method, path, status, expected):
    assert srb.is_trip_traffic(role, method, path, status) is expected


def test_trip_sql_encodes_the_same_rule_for_shapes_and_the_ungrouped_aggregate():
    for sql in (srb.SQL_SHAPES_TRIP, srb.SQL_TRIP_AGG):
        assert "request.sb.jwt.apikey.payload.role" in sql and "'service_role'" in sql
        assert "startsWith(log_attributes['request.path'], '/rest/v1/')" in sql
        assert "log_attributes['request.method'] != 'OPTIONS'" in sql
    assert "countIf" in srb.SQL_TRIP_AGG
    # N5: the aggregate that decides the trip has NO user-agent / role grouping a spray could crowd out
    assert "group by" not in srb.SQL_TRIP_AGG.lower() and "user_agent" not in srb.SQL_TRIP_AGG


def test_forged_role_traffic_that_the_aggregate_excludes_never_trips_even_if_status_rows_look_big():
    # 5k/h of 'service_role' 2xx in the status rows (OPTIONS 204 / auth 302 / functions 200 in reality)
    big = [{"ua": "curl/8", "status": 200, "role": "service_role", "calls": 50_000}]
    rep = srb.evaluate(srb.FakeLogsSource(status_rows=big, trip_shape_rows=[], shape_rows=[],
                                          trip_agg_rows=[{"eligible": 0, "n402": 0}]), now=NOW)
    assert rep["trip"] is False and rep["verdict"] == "warn" and rep["eligible_calls"] == 0


def test_a_single_or_few_402s_never_trip_but_a_real_wave_does():
    def rep_for(n402):
        return srb.evaluate(srb.FakeLogsSource(
            status_rows=[{"ua": "x", "status": 402, "role": "service_role", "calls": n402}],
            trip_shape_rows=[], shape_rows=[], trip_agg_rows=[{"eligible": n402, "n402": n402}]), now=NOW)
    one = rep_for(1)
    assert one["trip"] is False and one["trip_402_immediate"] is False and one["verdict"] != "critical"
    assert rep_for(99)["trip"] is False
    wave = rep_for(srb.DEFAULTS["SUPABASE_BUDGET_MIN_402_TO_TRIP"])
    assert wave["trip"] is True and wave["trip_402_immediate"] is True


# ── signature pin (optional hardening of N1): the logged key signature prefix is something a forger cannot know ──
PIN = "Ab12_-xyz9"


@pytest.mark.parametrize("value, ok", [
    ("abcd", True), ("Ab12_-xyz9", True), ("A" * 16, True),
    ("abc", False), ("A" * 17, False), ("a b c d", False), ("ab'cd", False), ("ab;cd", False), ("", False), (None, False),
])
def test_signature_pin_validation(value, ok):
    assert srb.valid_sig_prefix(value) is ok


def test_pinned_sql_carries_the_clause_and_unpinned_sql_does_not():
    attr = "log_attributes['request.sb.jwt.apikey.payload.signature_prefix']"
    assert PIN not in srb.SQL_TRIP_AGG and "signature_prefix" not in srb.SQL_TRIP_AGG
    assert PIN not in srb.SQL_SHAPES_TRIP
    for sql in (srb.sql_trip_agg(PIN), srb.sql_shapes_trip(PIN)):
        assert f"{attr} = '{PIN}'" in sql and "startsWith(" in sql and "'OPTIONS'" in sql
    assert srb.sql_trip_agg(None) == srb.SQL_TRIP_AGG
    with pytest.raises(ValueError):
        srb.sql_trip_agg("x'; drop")


def test_predicate_with_a_pin_rejects_a_forged_signature():
    ok = lambda sig, pin=PIN: srb.is_trip_traffic("service_role", "GET", "/rest/v1/jobs", 200, sig=sig, pin=pin)
    assert ok(PIN) is True
    assert ok("WRONGPFX") is False and ok("") is False and ok(None) is False
    assert ok("WRONGPFX", pin=None) is True            # pin off: behaviour stays as before


def test_the_pin_reaches_the_query_but_never_any_public_output():
    src = srb.FakeLogsSource(status_rows=[{"ua": "x", "status": 200, "calls": 5}], shape_rows=[])
    rep = srb.evaluate(src, now=NOW, sig_pin=PIN)
    assert rep["signature_pin"] == "on" and PIN not in repr(rep)
    assert any(PIN in c[0] for c in src.calls)
    off = srb.evaluate(srb.FakeLogsSource(), now=NOW)
    assert off["signature_pin"] == "off"


def test_tool_core_reads_the_pin_from_env_and_rejects_a_bad_one_without_echoing_it():
    good = srb.supabase_request_budget(source=srb.FakeLogsSource(), env={"SUPABASE_SERVICE_SIG_PREFIX": PIN})
    assert good["signature_pin"] == "on" and PIN not in repr(good)
    bad = srb.supabase_request_budget(source=srb.FakeLogsSource(), env={"SUPABASE_SERVICE_SIG_PREFIX": "bad value!"})
    assert bad["ok"] is False and bad["status"] == "error" and "bad value" not in repr(bad)
