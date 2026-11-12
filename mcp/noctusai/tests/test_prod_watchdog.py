"""`noctus.dev.prod_watchdog` — the OFF-HOST prod liveness checker.

WHY (2026-10-11). The prod VPS hard-froze after a fleet deploy; host journald
and cron had silently stopped ~20h earlier while the sites kept serving. An
on-host check dies with the host. These tests pin the parts that decide whether
the owner gets told: classification thresholds, the N-consecutive rule (one
blip never alerts), dedupe + reminders + recovery, channel routing/fallbacks,
the SSH backoff that spares fail2ban, and a host-probe parser that must survive
garbage. Every network edge is an injected seam — no network, no monkeypatch.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import _public_edge as edge  # noqa: E402
from tools.noctus.dev import prod_watchdog as pw  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
WATCHDOG_DIR = REPO / "deploy" / "watchdog"
TH = pw.thresholds({})
HOUR = 3600.0

GOOD_HOST = {
    "journald_last_age_s": 5, "heartbeat_age_s": 60, "mem_available_mb": 4000,
    "swap_used_mb": 10, "load1": 0.5, "load5": 0.4, "ncpu": 2, "uptime_s": 999, "now": 1,
}


# ── fakes (seams, not patches) ───────────────────────────────────────────────
class Fetch:
    """URL-substring → status. Default 200 with a clean health body."""

    def __init__(self, fail: dict | None = None, hook: dict | None = None):
        self.fail = fail or {}
        self.hook = hook or {}
        self.calls: list[str] = []

    def __call__(self, url, timeout):
        self.calls.append(url)
        for needle, status in self.fail.items():
            if needle in url:
                return status, b"", ""
        body = {"status": "ok", "startup_hook_error": None}
        for needle, err in self.hook.items():
            if needle in url:
                body["startup_hook_error"] = err
        return 200, json.dumps(body).encode(), "application/json"


class Ssh:
    def __init__(self, result=(0, json.dumps(GOOD_HOST), "")):
        self.result = result
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.result


class Sender:
    def __init__(self, ok=True):
        self.ok = ok
        self.sent: list[tuple[str, str]] = []

    def __call__(self, subject, body):
        self.sent.append((subject, body))
        return self.ok, "fake"


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


ENV_ALL = {
    "RESEND_API_KEY": "x", "WATCHDOG_ALERT_EMAIL": "o@example.com",
    "WAHA_BASE_URL": "https://waha.example", "WAHA_API_KEY": "k", "WATCHDOG_ALERT_WHATSAPP": "5511999",
}


def _run(tmp_path, *, fetch=None, ssh=None, senders=None, clock=None, send=True, env=None,
         slugs=("core", "seed"), test_alert=False):
    if senders is None:
        senders = {"email": Sender(), "whatsapp": Sender()}
    return pw.run(
        tmp_path / "state.json", send=send, test_alert=test_alert,
        env=ENV_ALL if env is None else env, repo_root=REPO, slugs=list(slugs),
        fetcher=fetch or Fetch(), ssh_runner=ssh if ssh is not None else Ssh(),
        senders=senders, clock=clock or Clock(),
        budget_check=lambda: {"verdict": "ok", "ok": True},  # the budget leg has its own tests below
    )


# ── classification thresholds ────────────────────────────────────────────────
def _http_ok():
    return [{"slug": "core", "url": "https://noctusai.com/api/health", "status": 200,
             "latency_ms": 1, "ok": True, "startup_hook_error": None}]


@pytest.mark.parametrize("field,value,needle", [
    ("journald_last_age_s", 31 * 60, "journald"),
    ("journald_last_age_s", None, "journald"),
    ("heartbeat_age_s", 16 * 60, "heartbeat"),
    ("heartbeat_age_s", None, "heartbeat ausente"),
    ("mem_available_mb", 599, "MemAvailable"),
    ("swap_used_mb", 1025, "swap"),
    ("load1", 4.01, "load1"),
])
def test_each_host_threshold_degrades(field, value, needle):
    host = dict(GOOD_HOST, **{field: value})
    state, down, deg = pw.classify(_http_ok(), host, None, {}, TH)
    assert state == pw.DEGRADED and not down
    assert any(needle in r for r in deg), deg


@pytest.mark.parametrize("field,value", [
    ("journald_last_age_s", 30 * 60), ("heartbeat_age_s", 15 * 60),
    ("mem_available_mb", 600), ("swap_used_mb", 1024), ("load1", 4.0),
])
def test_values_at_the_threshold_are_still_up(field, value):
    host = dict(GOOD_HOST, **{field: value})
    assert pw.classify(_http_ok(), host, None, {}, TH)[0] == pw.UP


def test_thresholds_are_env_overridable_and_junk_is_loud():
    assert pw.thresholds({"WATCHDOG_MEM_AVAILABLE_MIN_MB": "900"})["WATCHDOG_MEM_AVAILABLE_MIN_MB"] == 900
    with pytest.raises(ValueError, match="WATCHDOG_SWAP_USED_MAX_MB"):
        pw.thresholds({"WATCHDOG_SWAP_USED_MAX_MB": "lots"})


def test_ssh_unreachable_alone_is_degraded_not_down():
    state, down, deg = pw.classify(_http_ok(), None, None, {"ssh": 2}, TH)
    assert state == pw.DEGRADED and not down and any("SSH" in r for r in deg)


def test_ssh_unreachable_plus_core_impaired_is_down():
    http = _http_ok()
    http[0]["startup_hook_error"] = "RuntimeError: boom"
    assert pw.classify(http, None, None, {"ssh": 2}, TH)[0] == pw.DOWN
    http = _http_ok()
    http[0].update(ok=False, status=530)
    assert pw.classify(http, None, None, {"ssh": 2, "http:core": 1}, TH)[0] == pw.DOWN


def test_startup_hook_error_on_any_product_degrades(tmp_path):
    rep = _run(tmp_path, fetch=Fetch(hook={"seed.": "ImportError: x"}))
    assert rep["state"] == pw.DEGRADED
    assert any("startup_hook_error" in r for r in rep["reasons"])


# ── consecutive counters: one blip never alerts ──────────────────────────────
def test_core_blip_does_not_alert_two_in_a_row_is_down(tmp_path):
    email = Sender()
    senders = {"email": email, "whatsapp": Sender()}
    rep1 = _run(tmp_path, fetch=Fetch(fail={"noctusai.com/": 530}), senders=senders)
    assert rep1["state"] == pw.UP and rep1["alert"]["due"] is None and not email.sent
    rep2 = _run(tmp_path, fetch=Fetch(fail={"noctusai.com/": 530}), senders=senders)
    assert rep2["state"] == pw.DOWN and rep2["alert"]["due"] == "down"
    assert len(email.sent) == 1 and "FORA DO AR" in email.sent[0][0]


def test_a_success_in_between_resets_the_counter(tmp_path):
    bad = Fetch(fail={"noctusai.com/": 0})
    _run(tmp_path, fetch=bad)
    _run(tmp_path, fetch=Fetch())
    assert _run(tmp_path, fetch=bad)["state"] == pw.UP


def test_non_core_product_failing_twice_is_degraded(tmp_path):
    bad = Fetch(fail={"seed.": 502})
    assert _run(tmp_path, fetch=bad)["state"] == pw.UP
    rep = _run(tmp_path, fetch=bad)
    assert rep["state"] == pw.DEGRADED and any(r.startswith("seed:") for r in rep["reasons"])


def test_ssh_needs_two_consecutive_failures(tmp_path):
    dead = Ssh((255, "", "ssh: connect to host 203.0.113.9 port 22: Connection timed out"))
    env = dict(ENV_ALL, NOCTUS_VPS_HOST="203.0.113.9")
    assert _run(tmp_path, ssh=dead, env=env)["state"] == pw.UP
    rep = _run(tmp_path, ssh=dead, env=env)
    assert rep["state"] == pw.DEGRADED
    # The host is a secret: never in the report detail, never in a message.
    assert "203.0.113.9" not in json.dumps(rep, default=str)


# ── dedupe, reminders, recovery ──────────────────────────────────────────────
def test_dedupe_reminder_and_recovery(tmp_path):
    clock = Clock()
    wa, email = Sender(), Sender()
    senders = {"email": email, "whatsapp": wa}
    bad_host = Ssh((0, json.dumps(dict(GOOD_HOST, heartbeat_age_s=None)), ""))

    rep = _run(tmp_path, ssh=bad_host, senders=senders, clock=clock)
    assert rep["alert"]["due"] == "degraded" and len(wa.sent) == 1 and not email.sent

    for _ in range(3):  # no repeats while nothing changes
        clock.t += 600
        assert _run(tmp_path, ssh=bad_host, senders=senders, clock=clock)["alert"]["due"] is None
    assert len(wa.sent) == 1

    clock.t += 6 * HOUR  # reminder after WATCHDOG_REMINDER_HOURS
    rep = _run(tmp_path, ssh=bad_host, senders=senders, clock=clock)
    assert rep["alert"]["due"] == "reminder" and "LEMBRETE" in wa.sent[-1][0]
    clock.t += 600
    assert _run(tmp_path, ssh=bad_host, senders=senders, clock=clock)["alert"]["due"] is None

    clock.t += 600  # recovery → both channels
    rep = _run(tmp_path, senders=senders, clock=clock)
    assert rep["state"] == pw.UP and rep["alert"]["due"] == "recovery"
    assert "RECUPERADO" in email.sent[-1][0] and "RECUPERADO" in wa.sent[-1][0]
    clock.t += 600
    assert _run(tmp_path, senders=senders, clock=clock)["alert"]["due"] is None


def test_undelivered_alert_is_retried_next_run_and_exits_nonzero(tmp_path):
    dead = {"email": Sender(ok=False), "whatsapp": Sender(ok=False)}
    bad_host = Ssh((0, json.dumps(dict(GOOD_HOST, mem_available_mb=100)), ""))
    rep = _run(tmp_path, ssh=bad_host, senders=dead)
    assert rep["exit_code"] == 1 and rep["alert"]["delivered"] is False
    good = {"email": Sender(), "whatsapp": Sender()}
    rep = _run(tmp_path, ssh=bad_host, senders=good)
    assert rep["alert"]["due"] == "degraded" and rep["alert"]["delivered"] and rep["exit_code"] == 0


def test_dry_run_sends_nothing_and_without_state_path_writes_nothing(tmp_path):
    email = Sender()
    rep = pw.run(None, env=ENV_ALL, repo_root=REPO, slugs=["core"],
                 fetcher=Fetch(fail={"noctusai.com": 0}), ssh_runner=None,
                 senders={"email": email}, clock=Clock())
    assert rep["send"] is False and rep["state_saved"] is None and not email.sent
    assert list(tmp_path.iterdir()) == []


# ── routing + fallbacks ──────────────────────────────────────────────────────
def test_degraded_falls_back_to_email_when_whatsapp_fails(tmp_path):
    wa, email = Sender(ok=False), Sender()
    bad_host = Ssh((0, json.dumps(dict(GOOD_HOST, swap_used_mb=2000)), ""))
    rep = _run(tmp_path, ssh=bad_host, senders={"email": email, "whatsapp": wa})
    assert len(wa.sent) == 1 and len(email.sent) == 1 and rep["alert"]["delivered"]


def test_degraded_uses_email_when_whatsapp_not_configured_and_says_so(tmp_path):
    email = Sender()
    env = {k: v for k, v in ENV_ALL.items() if not k.startswith("WA")}
    bad_host = Ssh((0, json.dumps(dict(GOOD_HOST, load1=9)), ""))
    rep = _run(tmp_path, ssh=bad_host, env=env, senders={"email": email})
    assert len(email.sent) == 1
    assert "NOT CONFIGURED" in rep["alert"]["channels"]["whatsapp"]["detail"]
    assert any("whatsapp NOT CONFIGURED" in w for w in rep["warnings"])


def test_down_goes_to_email_and_also_tries_whatsapp():
    wa, email = Sender(ok=False), Sender()
    res = pw.deliver("down", pw.DOWN, "s", "b", {"email": email, "whatsapp": wa}, pw.channel_config(ENV_ALL))
    assert len(email.sent) == 1 and len(wa.sent) == 1 and res["delivered"]


def test_no_channel_configured_is_red_in_send_mode(tmp_path):
    rep = _run(tmp_path, env={}, senders={})
    assert rep["exit_code"] == 1
    assert any("NO alert channel" in w for w in rep["warnings"])


def test_real_senders_only_exist_for_configured_channels():
    assert set(pw.make_senders(ENV_ALL)) == {"email", "whatsapp"}
    assert set(pw.make_senders({"RESEND_API_KEY": "x"})) == set()


def test_alert_posts_send_the_browser_user_agent():
    """Cloudflare rule 1010 (in front of Resend) 403s urllib's default UA."""
    import http.server
    import threading

    seen: dict = {}

    class _H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            seen["ua"] = self.headers.get("User-Agent")
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    ok, _ = pw._post_json(f"http://127.0.0.1:{srv.server_port}/", {}, {"X": "1"}, timeout=5)
    srv.server_close()
    assert ok and seen["ua"] == edge.BROWSER_UA


def test_test_alert_goes_through_every_configured_channel(tmp_path):
    wa, email = Sender(), Sender()
    rep = _run(tmp_path, senders={"email": email, "whatsapp": wa}, test_alert=True)
    assert "TESTE" in email.sent[0][0] and "TESTE" in wa.sent[0][0] and rep["exit_code"] == 0
    rep = _run(tmp_path, senders={"email": email, "whatsapp": Sender(ok=False)}, test_alert=True)
    assert rep["exit_code"] == 1


def test_message_is_ptbr_with_reasons_and_timestamp():
    subj, body = pw.compose_message("down", pw.DOWN, ["core: HTTP falhou"], 1_800_000_000.0, 1_800_001_200.0)
    assert subj == "[NoctusAI prod] FORA DO AR"
    assert "Motivos:" in body and "- core: HTTP falhou" in body and "há 20 min" in body and "UTC" in body


# ── SSH backoff ──────────────────────────────────────────────────────────────
def test_backoff_schedule():
    assert [pw.backoff_every(f, TH) for f in range(0, 10)] == [1, 1, 1, 2, 3, 4, 5, 6, 6, 6]


def test_backoff_skips_runs_and_never_more_than_one_connection(tmp_path):
    dead = Ssh((255, "", "timeout"))
    attempted = []
    for _ in range(10):
        before = dead.calls
        rep = _run(tmp_path, ssh=dead)
        assert dead.calls - before <= 1
        attempted.append(rep["ssh"]["status"])
    # failures 1-3 every run, then every 2nd, then every 3rd …
    assert attempted == ["unreachable"] * 3 + ["backoff", "unreachable", "backoff", "backoff",
                                               "unreachable", "backoff", "backoff"]
    # still DEGRADED while backing off (the count is not forgotten)
    assert rep["state"] == pw.DEGRADED


def test_ssh_not_configured_is_reported_and_clears_stale_counts(tmp_path):
    dead = Ssh((255, "", "x"))
    _run(tmp_path, ssh=dead)
    _run(tmp_path, ssh=dead)
    rep = pw.run(tmp_path / "state.json", send=True, env=ENV_ALL, repo_root=REPO, slugs=["core"],
                 fetcher=Fetch(), ssh_runner=None, senders={"email": Sender(), "whatsapp": Sender()},
                 clock=Clock())
    assert rep["ssh"]["status"] == "not_configured" and rep["state"] == pw.UP
    assert pw.make_ssh_runner({}) is None


# ── host-probe parser robustness ─────────────────────────────────────────────
@pytest.mark.parametrize("text", ["", "   \n", "garbage", "{not json", "[1,2]", "null"])
def test_parser_rejects_garbage(text):
    metrics, err = pw.parse_host_probe(text)
    assert metrics is None and err


def test_parser_tolerates_nulls_strings_junk_and_motd():
    text = 'Welcome to Ubuntu\n{"journald_last_age_s": null, "mem_available_mb": "512", "load1": "x", "ncpu": true}\n'
    m, err = pw.parse_host_probe(text)
    assert err is None
    assert m["journald_last_age_s"] is None and m["mem_available_mb"] == 512.0
    assert m["load1"] is None and m["ncpu"] is None and m["swap_used_mb"] is None


def test_unparseable_probe_with_a_live_connection_is_degraded_not_unreachable(tmp_path):
    rep = _run(tmp_path, ssh=Ssh((0, "oops", "")))
    assert rep["ssh"]["status"] == "probe_error" and rep["counters"]["ssh"] == 0
    assert rep["state"] == pw.DEGRADED


def test_host_probe_script_emits_parseable_json_even_off_linux():
    out = subprocess.run(["bash", str(WATCHDOG_DIR / "host-probe.sh")],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0
    m, err = pw.parse_host_probe(out.stdout)
    assert err is None and m["now"] and set(m) == set(pw.HOST_PROBE_FIELDS)


# ── roster + hostname resolution against the REAL files ──────────────────────
def test_roster_is_core_plus_build_scope():
    roster = pw.default_roster(REPO)
    scope = edge.read_slug_file(REPO / edge.BUILD_SCOPE_RELPATH)
    assert roster[0] == "core" and set(roster) == set(scope) | {"core"}
    assert roster.count("core") == 1


def test_ingress_parser_matches_yaml_on_the_real_file():
    yaml = pytest.importorskip("yaml")
    text = (REPO / edge.INGRESS_RELPATH).read_text(encoding="utf-8")
    want = [{"hostname": str(r["hostname"]), "service": str(r["service"])}
            for r in yaml.safe_load(text)["routes"]]
    got = [{"hostname": r["hostname"], "service": r["service"]} for r in edge.ingress_routes(text)]
    assert got == want


def test_public_hostname_resolves_real_routes():
    assert edge.public_hostname("core", REPO) == "noctusai.com"
    assert edge.public_hostname("social-wiring", REPO) == "social.noctusai.com"
    assert edge.public_hostname("no-such-product", REPO) == "no-such-product.noctusai.com"


def test_http_probe_hits_health_for_all_and_root_for_core(tmp_path):
    f = Fetch()
    pw.http_probe(["core", "seed"], REPO, f, 5)
    assert f.calls == ["https://noctusai.com/api/health", "https://noctusai.com/",
                       "https://seed.noctusai.com/api/health"]


# ── stdlib-only + wiring ─────────────────────────────────────────────────────
def test_module_imports_under_bare_stdlib():
    """CI runs the watchdog with NO pip install. Import it in a fresh `-I -S`
    interpreter (no site-packages) and prove nothing non-stdlib loaded."""
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]);"
        "from tools.noctus.dev import prod_watchdog as pw;"
        "print(pw.default_roster(pw._repo_root())[0])"
    )
    out = subprocess.run([sys.executable, "-I", "-S", "-c", code, str(REPO / "mcp" / "noctusai")],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "core"


def test_registered_and_cli_wired():
    init = (REPO / "mcp/noctusai/tools/noctus/dev/__init__.py").read_text()
    cli = (REPO / "mcp/noctusai/cli.py").read_text()
    assert "prod_watchdog.register(server)" in init
    assert "--prod-watchdog" in cli and "prod_watchdog" in cli


def test_shell_scripts_parse_and_installer_refuses_bad_args(tmp_path):
    for name in ("host-probe.sh", "install-heartbeat.sh"):
        assert subprocess.run(["bash", "-n", str(WATCHDOG_DIR / name)]).returncode == 0
    bad = subprocess.run(["bash", str(WATCHDOG_DIR / "install-heartbeat.sh"), "--bogus"],
                         capture_output=True, text=True)
    assert bad.returncode == 2
    junk = tmp_path / "k.pub"
    junk.write_text('restrict,command="x" ssh-ed25519 AAAA\n')
    r = subprocess.run(["bash", str(WATCHDOG_DIR / "install-heartbeat.sh"), "--check",
                        "--watchdog-pubkey", str(junk)], capture_output=True, text=True)
    assert r.returncode == 2 and "not an OpenSSH public key" in r.stderr


def test_installer_check_mode_changes_nothing(tmp_path):
    pub = tmp_path / "k.pub"
    pub.write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleExampleExample test\n")
    ak = tmp_path / "authorized_keys"
    r = subprocess.run(
        ["bash", str(WATCHDOG_DIR / "install-heartbeat.sh"), "--check", "--watchdog-pubkey", str(pub)],
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "NOCTUS_SYSTEMD_DIR": str(tmp_path),
             "NOCTUS_AUTHORIZED_KEYS": str(ak)},
    )
    assert r.returncode == 0, r.stderr
    assert "NOT INSTALLED" in r.stdout and "watchdog key: NOT in" in r.stdout
    assert sorted(p.name for p in tmp_path.iterdir()) == ["k.pub"]


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="systemd-analyze not available (macOS)")
def test_units_verify(tmp_path):
    for name in ("noctus-heartbeat.service", "noctus-heartbeat.timer"):
        shutil.copy(WATCHDOG_DIR / name, tmp_path / name)
    r = subprocess.run(["systemd-analyze", "verify", str(tmp_path / "noctus-heartbeat.timer")],
                       capture_output=True, text=True)
    assert "noctus-heartbeat" not in r.stderr or r.returncode == 0, r.stderr


# ── supabase request-budget leg + fleet breaker (telemetry for the polling-budget rule) ──
def _budget(verdict, **extra):
    base = {"ok": verdict != "unknown", "verdict": verdict, "reasons": [f"synthetic {verdict}"],
            "projected_per_day": 300000, "total_calls": 12500, "status_402": 0, "window_hours": 1.0,
            "trip": verdict == "critical", "signature_pin": "off", "trip_402_immediate": extra.get("status_402", 0) >= 100, "reasons_public": [f"public {verdict}: projected 300000/day"],
            "top_shapes": [{"shape": "POST /rest/v1/rpc/claim_next_job", "calls": 9, "projected_per_day": 216}]}
    base.update(extra)
    return lambda: dict(base)


class Tripper:
    def __init__(self, ok=True):
        self.ok, self.payloads = ok, []

    def __call__(self, payload):
        self.payloads.append(payload)
        if not self.ok:
            return False, "rc=255: down"
        return True, "tripped" if len(self.payloads) == 1 else "already tripped"


def _brun(tmp_path, check, tripper, *, send=True, rearmed=False, senders=None):
    return pw.run(tmp_path / "b.json", send=send, env=ENV_ALL, repo_root=REPO, slugs=["core"],
                  fetcher=Fetch(), ssh_runner=Ssh(), clock=Clock(),
                  senders=senders if senders is not None else {"email": Sender(), "whatsapp": Sender()},
                  budget_check=check, breaker_tripper=tripper, breaker_rearmed=rearmed)


def test_critical_trips_after_n_runs_with_the_exact_payload_and_alerts_once(tmp_path):
    t, wa, em = Tripper(), Sender(), Sender()
    senders = {"email": em, "whatsapp": wa}
    first = _brun(tmp_path, _budget("critical"), t, senders=senders)
    assert t.payloads == [] and first["breaker"]["status"] == "armed" and first["state"] == pw.UP
    second = _brun(tmp_path, _budget("critical"), t, senders=senders)
    assert len(t.payloads) == 1 and second["breaker"]["status"] == "tripped"
    pl = t.payloads[0]
    assert set(pl) == {"reason", "rate", "window", "tripped_at", "by"} and pl["by"] == "offhost-watchdog"
    assert pl["rate"] == 300000 and pl["window"] == "1h"
    assert second["alert"]["due"] == "breaker" and second["state"] == pw.DEGRADED
    assert any("DISJUNTOR" in s for s, _ in wa.sent) and len(em.sent) == 1  # WhatsApp + email, one each
    # third run: still critical: the (idempotent, NX) trip is re-asserted, but NO second alert (dedupe)
    third = _brun(tmp_path, _budget("critical"), t, senders=senders)
    assert len(t.payloads) == 2 and third["alert"]["due"] is None and third["state"] == pw.DEGRADED


def test_a_402_wave_trips_immediately_but_a_lone_402_needs_consecutive_runs(tmp_path):
    t = Tripper()
    rep = _brun(tmp_path / "wave", _budget("critical", status_402=500), t)
    assert len(t.payloads) == 1 and rep["breaker"]["status"] == "tripped"
    t2 = Tripper()
    first = _brun(tmp_path / "one", _budget("critical", status_402=1), t2)
    assert t2.payloads == [] and first["breaker"]["status"] == "armed"
    _brun(tmp_path / "one", _budget("critical", status_402=1), t2)
    assert len(t2.payloads) == 1


def test_sticky_breaker_reminds_and_never_auto_rearms(tmp_path):
    t, em = Tripper(), Sender()
    senders = {"email": em, "whatsapp": Sender()}
    _brun(tmp_path, _budget("critical", status_402=500), t, senders=senders)
    # traffic is back to ok (workers stopped) but the breaker is STILL tripped -> still DEGRADED
    for _ in range(3):
        rep = _brun(tmp_path, _budget("ok"), t, senders=senders)
        assert rep["state"] == pw.DEGRADED and rep["breaker"]["status"] == "tripped"
    assert len(t.payloads) == 1  # verdict ok: nothing to re-assert


def test_rearm_ack_clears_the_sticky_alert_and_the_next_critical_trips_again(tmp_path):
    t = Tripper()
    _brun(tmp_path, _budget("critical", status_402=500), t)
    rep = _brun(tmp_path, _budget("ok"), t, rearmed=True)
    assert rep["state"] == pw.UP and rep["breaker"]["status"] == "armed"
    _brun(tmp_path, _budget("critical", status_402=500), t)
    assert len(t.payloads) == 2


def test_failed_trip_is_degraded_loud_and_retried(tmp_path):
    t = Tripper(ok=False)
    rep = _brun(tmp_path, _budget("critical", status_402=500), t)
    assert rep["breaker"]["status"] == "trip_failed" and rep["state"] == pw.DEGRADED
    assert any("FALHOU" in r for r in rep["degraded_reasons"])
    t.ok = True
    rep = _brun(tmp_path, _budget("critical", status_402=500), t)
    assert rep["breaker"]["status"] == "tripped" and len(t.payloads) == 2


def test_critical_without_a_configured_tripper_still_alerts_and_says_it_could_not_trip(tmp_path):
    rep = _brun(tmp_path, _budget("critical", status_402=500), None)
    assert rep["breaker"]["status"] == "not_configured" and rep["state"] == pw.DEGRADED
    assert any("NÃO pôde" in r for r in rep["degraded_reasons"])


def test_dry_run_never_trips(tmp_path):
    t = Tripper()
    rep = _brun(tmp_path, _budget("critical", status_402=500), t, send=False)
    assert t.payloads == [] and rep["breaker"]["status"] == "dry_run_would_trip"


def test_warn_alerts_after_n_runs_but_never_trips(tmp_path):
    t = Tripper()
    first = _brun(tmp_path, _budget("warn", projected_per_day=120000), t)
    assert first["state"] == pw.UP
    second = _brun(tmp_path, _budget("warn", projected_per_day=120000), t)
    assert second["state"] == pw.DEGRADED and t.payloads == []
    assert any("ATENÇÃO" in r for r in second["degraded_reasons"])


def test_unknown_and_unconfigured_never_alert_and_never_trip(tmp_path):
    for check in (_budget("unknown", error="HTTP 503"), None):
        t = Tripper()
        for _ in range(3):
            rep = pw.run(
                tmp_path / f"u{id(check)}.json", send=True, env=ENV_ALL, repo_root=REPO, slugs=["core"],
                fetcher=Fetch(), ssh_runner=Ssh(), clock=Clock(),
                senders={"email": Sender(), "whatsapp": Sender()}, budget_check=check, breaker_tripper=t)
        assert rep["state"] == pw.UP and t.payloads == []


def test_auto_budget_without_a_token_is_not_configured_and_makes_no_call():
    rep = pw.run(None, env=ENV_ALL, repo_root=REPO, slugs=["core"], fetcher=Fetch(), ssh_runner=Ssh(),
                 senders={"email": Sender()})
    assert rep["budget"]["status"] == "not_configured"


def test_a_raising_check_is_unknown_not_a_crash(tmp_path):
    def boom():
        raise RuntimeError("secret-token-xyz")

    rep = _brun(tmp_path, boom, Tripper())
    assert rep["budget"]["verdict"] == "unknown" and "secret-token-xyz" not in repr(rep)


def test_breaker_tripper_needs_host_and_its_own_key(tmp_path):
    assert pw.make_breaker_tripper({}) is None
    key = tmp_path / "k"
    key.write_text("x")
    assert pw.make_breaker_tripper({"NOCTUS_VPS_HOST": "h", "WATCHDOG_BREAKER_KEY_FILE": str(key)}) is not None
    # the read-only probe key alone must never enable the write
    assert pw.make_breaker_tripper({"NOCTUS_VPS_HOST": "h", "WATCHDOG_SSH_KEY_FILE": str(key)}) is None


# ── deploy/watchdog/breaker-trip.sh: the forced command, run for real with a fake docker ──
def _fake_docker(tmp_path, *, preexisting=False):
    store = tmp_path / "redis.json"
    if preexisting:
        store.write_text("FIRST")
    d = tmp_path / "bin"
    d.mkdir()
    (d / "docker").write_text(f"""#!/usr/bin/env bash
# docker exec <c> redis-cli SETNX <key> <val> | EXISTS <key>
shift 3
cmd="$1"; key="$2"
if [[ "$cmd" == "SETNX" ]]; then
  [[ "$key" == "noctus:breaker:fleet" ]] || exit 9
  if [[ -e "{store}" ]]; then echo 0; else printf '%s' "$3" > "{store}"; echo 1; fi
elif [[ "$cmd" == "EXISTS" ]]; then [[ -e "{store}" ]] && echo 1 || echo 0
else exit 9; fi
""")
    (d / "docker").chmod(0o755)
    return d, store


needs_timeout = pytest.mark.skipif(shutil.which('timeout') is None, reason='coreutils timeout missing (the VPS has it)')


def _trip(tmp_path, payload, **kw):
    import os as _os
    d, store = _fake_docker(tmp_path, **kw)
    r = subprocess.run(["bash", str(WATCHDOG_DIR / "breaker-trip.sh")], input=payload, capture_output=True, text=True,
                       env={**_os.environ, "PATH": f"{d}:{_os.environ['PATH']}"}, timeout=30)
    return r, store


GOOD = {"reason": "critical", "rate": 300000, "window": "1h", "tripped_at": "2026-11-10T12:00:00Z", "by": "offhost-watchdog"}


@needs_timeout
def test_breaker_script_sets_only_the_canonical_key_and_never_overwrites(tmp_path):
    r, store = _trip(tmp_path, json.dumps(GOOD))
    assert r.returncode == 0 and json.loads(r.stdout) == {"tripped": True, "already": False}
    assert json.loads(store.read_text()) == GOOD
    d = tmp_path / "bin"
    import os as _os
    r2 = subprocess.run(["bash", str(WATCHDOG_DIR / "breaker-trip.sh")], input=json.dumps(dict(GOOD, reason="LATER")),
                        capture_output=True, text=True, env={**_os.environ, "PATH": f"{d}:{_os.environ['PATH']}"}, timeout=30)
    assert json.loads(r2.stdout) == {"tripped": False, "already": True}
    assert json.loads(store.read_text())["reason"] == "critical"


@pytest.mark.parametrize("bad", [
    "not json", "[]", json.dumps({**GOOD, "by": "someone"}), json.dumps({k: v for k, v in GOOD.items() if k != "rate"}),
    json.dumps({**GOOD, "extra": 1}), json.dumps({**GOOD, "reason": "x" * 301}), json.dumps({**GOOD, "reason": "a\nb"}),
    json.dumps({**GOOD, "rate": True}), json.dumps({**GOOD, "window": ""}),
])
@needs_timeout
def test_breaker_script_refuses_anything_but_the_exact_shape(tmp_path, bad):
    r, store = _trip(tmp_path, bad)
    assert r.returncode == 2 and not store.exists()


def test_breaker_script_parses_and_installer_docs_name_the_key_line():
    assert subprocess.run(["bash", "-n", str(WATCHDOG_DIR / "breaker-trip.sh")]).returncode == 0
    assert (WATCHDOG_DIR / "breaker-trip.sh").stat().st_mode & 0o111
    kb = (REPO / "KNOWLEDGE-BASE/CONTEXT/PATTERNS/devops/prod-watchdog.md").read_text()
    assert 'command="sudo /opt/noctus/noctusai/deploy/watchdog/breaker-trip.sh"' in kb
    assert (WATCHDOG_DIR / "noctus-breaker.sudoers").read_text().count("breaker-trip.sh") >= 1


# ── F6: re-trip after a re-arm; reconcile the state with the REAL key via the host probe ──
def _host(**kw):
    return (0, json.dumps({**GOOD_HOST, **kw}), "")


def _brun_host(tmp_path, check, tripper, host_extra, *, send=True):
    return pw.run(tmp_path / "h.json", send=send, env=ENV_ALL, repo_root=REPO, slugs=["core"],
                  fetcher=Fetch(), ssh_runner=Ssh(_host(**host_extra)), clock=Clock(),
                  senders={"email": Sender(), "whatsapp": Sender()}, budget_check=check, breaker_tripper=tripper)


def test_after_a_human_rearm_the_next_critical_trips_again_without_any_ack(tmp_path):
    t = Tripper()
    _brun_host(tmp_path, _budget("critical", status_402=500), t, {"breaker_tripped": 0})
    assert len(t.payloads) == 1
    # the key is GONE on the host (re-armed by a human): the sticky alert clears by itself ...
    rep = _brun_host(tmp_path, _budget("ok"), t, {"breaker_tripped": 0})
    assert rep["state"] == pw.UP and rep["breaker"]["status"] == "armed"
    # ... and the next critical trips again (the cache file never gets to veto it)
    rep = _brun_host(tmp_path, _budget("critical", status_402=500), t, {"breaker_tripped": 0})
    assert len(t.payloads) == 2 and rep["breaker"]["status"] == "tripped"


def test_a_key_found_set_on_the_host_is_adopted_and_alerted_once(tmp_path):
    t = Tripper()
    rep = _brun_host(tmp_path, _budget("ok"), t, {"breaker_tripped": 1})
    assert rep["breaker"]["status"] == "tripped" and rep["state"] == pw.DEGRADED and t.payloads == []
    again = _brun_host(tmp_path, _budget("ok"), t, {"breaker_tripped": 1})
    assert again["alert"]["due"] is None and again["state"] == pw.DEGRADED


def test_an_unreadable_host_signal_never_clears_a_sticky_breaker(tmp_path):
    t = Tripper()
    _brun_host(tmp_path, _budget("critical", status_402=500), t, {"breaker_tripped": 1})
    rep = _brun_host(tmp_path, _budget("ok"), t, {"breaker_tripped": None})
    assert rep["state"] == pw.DEGRADED


# ── F12: the probe reports whether our forced-command keys are really restricted ──
def test_unrestricted_forced_command_key_is_degraded():
    host = dict(GOOD_HOST, breaker_key_restricted=0)
    state, down, deg = pw.classify(_http_ok(), host, None, {}, TH)
    assert state == pw.DEGRADED and any("restrict" in r for r in deg)
    for fine in (1, None):
        assert pw.classify(_http_ok(), dict(GOOD_HOST, breaker_key_restricted=fine), None, {}, TH)[0] == pw.UP


def test_known_hosts_is_pinned_from_env_and_keyscan_is_never_run_when_pinned(tmp_path):
    calls = []

    def fake_run(args, **kw):
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, stdout="{}", stderr="")

    env = {"NOCTUS_VPS_KNOWN_HOSTS": "|1|abc|def ssh-ed25519 AAAAKEY"}
    rc, out, err = pw._ssh_once("h", "/k", "probe", env=env, run=fake_run, user="breaker", stdin_text="{}")
    assert rc == 0 and all(c[0] != "ssh-keyscan" for c in calls)
    ssh = calls[-1]
    assert "breaker@h" in ssh and "StrictHostKeyChecking=yes" in ssh
    kh = [a for a in ssh if a.startswith("UserKnownHostsFile=")][0].split("=", 1)[1]
    assert "AAAAKEY" in Path(kh).read_text()
    # unpinned: falls back to keyscan (and run() warns loudly)
    pw._ssh_once("h", "/k", "probe", env={}, run=fake_run, sleep=lambda s: None)
    assert any(c[0] == "ssh-keyscan" for c in calls)


# ── F8: a public run log carries counts and verdict only; shapes go to the email body alone ──
def test_report_and_state_carry_no_shapes_and_only_email_gets_them(tmp_path):
    wa, em = Sender(), Sender()
    rep = _brun(tmp_path, _budget("critical", status_402=500), Tripper(), senders={"email": em, "whatsapp": wa})
    blob = json.dumps(rep, default=str) + pw.format_report(rep) + (tmp_path / "b.json").read_text()
    assert "claim_next_job" not in blob
    assert rep["budget"]["verdict"] == "critical" and "top_shapes" not in rep["budget"]
    assert any("claim_next_job" in b for _, b in em.sent)
    assert not any("claim_next_job" in b for _, b in wa.sent)


# ── F1 end to end: an anonymous flood alerts at most, it never reaches the tripper ──
def test_anonymous_flood_through_the_real_evaluator_never_trips_the_fleet(tmp_path):
    from tools.noctus.dev import supabase_request_budget as srb

    flood = [{"ua": "curl/8", "status": 401, "role": "anon", "calls": 1500},
             {"ua": "curl/8", "status": 403, "role": "anon", "calls": 1500}]  # 3k/h

    def check():
        src = srb.FakeLogsSource(status_rows=flood, trip_shape_rows=[],
                                 shape_rows=[{"m": "GET", "p": "/rest/v1/clientes", "s": "", "calls": 3000}])
        return srb.supabase_request_budget(source=src, env={}, window_hours=1.0)

    t = Tripper()
    for _ in range(4):
        rep = _brun(tmp_path, check, t)
    assert t.payloads == [] and rep["breaker"]["status"] == "armed"
    assert rep["budget"]["verdict"] in ("ok", "warn")


# ── N4: a blind budget leg must not silently remove the protection ──
@pytest.mark.parametrize("blind", [_budget("unknown", error="HTTP 401"), None])
def test_consecutive_blind_runs_degrade_and_a_good_run_resets_it(tmp_path, blind):
    n = int(pw.DEFAULTS["WATCHDOG_BUDGET_BLIND_RUNS"])
    st = tmp_path / f"blind{id(blind)}.json"
    kw = dict(env=ENV_ALL, repo_root=REPO, slugs=["core"], fetcher=Fetch(), ssh_runner=Ssh(), clock=Clock(),
              senders={"email": Sender(), "whatsapp": Sender()}, breaker_tripper=Tripper())
    for _ in range(n - 1):
        assert pw.run(st, send=True, budget_check=blind, **kw)["state"] == pw.UP
    rep = pw.run(st, send=True, budget_check=blind, **kw)
    assert rep["state"] == pw.DEGRADED and any("SEM MEDIÇÃO" in r for r in rep["degraded_reasons"])
    rep = pw.run(st, send=True, budget_check=_budget("ok"), **kw)
    assert rep["state"] == pw.UP


# ── N9: the probe key's login user is configurable (unprivileged `probe` + sudoers), root stays the legacy default ──
def test_probe_user_is_configurable_and_defaults_to_the_legacy_root():
    assert pw._probe_user({}) == "root"
    assert pw._probe_user({"WATCHDOG_PROBE_USER": "probe"}) == "probe"
    assert pw._probe_user({"WATCHDOG_PROBE_USER": "  "}) == "root"


# ── N3/N6/N9: setup docs + sudoers carry the corrected, least-privilege shape ──
def test_setup_docs_and_sudoers_are_the_corrected_shape():
    kb = (REPO / "KNOWLEDGE-BASE/CONTEXT/PATTERNS/devops/prod-watchdog.md").read_text()
    assert "useradd -m -s /bin/sh breaker" in kb and "-s /usr/sbin/nologin" not in kb
    assert "verify" in kb and "environment" in kb.lower() and "host-probe.sh" in kb
    sud = (WATCHDOG_DIR / "noctus-breaker.sudoers").read_text()
    assert "Defaults!/opt/noctus/noctusai/deploy/watchdog/breaker-trip.sh env_reset" in sud
    assert 'probe ALL=(root) NOPASSWD: /opt/noctus/noctusai/deploy/watchdog/host-probe.sh ""' in sud


def test_workflow_scopes_secrets_to_their_steps_and_uses_an_environment():
    wf = (REPO / ".github/workflows/prod-watchdog.yml").read_text()
    job_env = wf.split("    env:\n", 1)[1].split("    steps:", 1)[0]
    for name in ("VPS_WATCHDOG_KEY", "RESEND_API_KEY", "WAHA_API_KEY", "SUPABASE_ACCESS_TOKEN", "BREAKER_KEY"):
        assert name not in job_env, name
    assert "environment: prod-watchdog" in wf


# ── N6/N-ACL: breaker-trip.sh + host-probe.sh speak both Redises (today's and the ACL one) ──
def _acl_docker(tmp_path):
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    log = tmp_path / "docker.log"
    store = tmp_path / "redis.json"
    (d / "docker").write_text(f"""#!/usr/bin/env bash
echo "ARGS: $*" >> "{log}"
echo "AUTH: ${{REDISCLI_AUTH:-}}" >> "{log}"
args=("$@"); i=0
while [[ "${{args[$i]}}" != "redis-cli" ]]; do i=$((i+1)); done
rest=("${{args[@]:$((i+1))}}")
while [[ "${{rest[0]:-}}" == --* ]]; do [[ "${{rest[0]}}" == "--user" ]] && rest=("${{rest[@]:2}}") || rest=("${{rest[@]:1}}"); done
cmd="${{rest[0]}}"
if [[ "$cmd" == "SETNX" ]]; then
  if [[ -e "{store}" ]]; then echo 0; else printf '%s' "${{rest[2]}}" > "{store}"; echo 1; fi
elif [[ "$cmd" == "EXISTS" ]]; then [[ -e "{store}" ]] && echo 1 || echo 0
else exit 9; fi
""")
    (d / "docker").chmod(0o755)
    return d, log, store


@needs_timeout
def test_breaker_script_uses_the_acl_redis_when_the_trip_credential_exists(tmp_path):
    import os as _os
    d, log, store = _acl_docker(tmp_path)
    pw_file = tmp_path / "trip.pass"
    pw_file.write_text("s3cr3t-trip-pass\n")
    env = {**_os.environ, "PATH": f"{d}:{_os.environ['PATH']}", "NOCTUS_REDIS_TRIP_PASS_FILE": str(pw_file)}
    r = subprocess.run(["bash", str(WATCHDOG_DIR / "breaker-trip.sh")], input=json.dumps(GOOD), capture_output=True,
                       text=True, env=env, timeout=30)
    assert r.returncode == 0 and json.loads(r.stdout) == {"tripped": True, "already": False}
    txt = log.read_text()
    assert "noctus-breaker-redis" in txt and "--user trip" in txt and "--no-auth-warning" in txt and "-e REDISCLI_AUTH" in txt
    assert "SETNX noctus:breaker:fleet" in txt and " SET " not in txt  # the trip user holds +setnx only
    assert "AUTH: s3cr3t-trip-pass" in txt                 # delivered through the environment ...
    assert not any("s3cr3t" in l for l in txt.splitlines() if l.startswith("ARGS:"))  # ... never on a command line


@needs_timeout
def test_breaker_script_verify_payload_is_read_only(tmp_path):
    import os as _os
    d, log, store = _acl_docker(tmp_path)
    env = {**_os.environ, "PATH": f"{d}:{_os.environ['PATH']}", "NOCTUS_REDIS_TRIP_PASS_FILE": str(tmp_path / "none")}
    r = subprocess.run(["bash", str(WATCHDOG_DIR / "breaker-trip.sh")], input='{"verify":true}', capture_output=True,
                       text=True, env=env, timeout=30)
    assert r.returncode == 0 and json.loads(r.stdout) == {"verify": True, "exists": 0}
    assert not store.exists() and "SETNX" not in log.read_text()


@needs_timeout
def test_legacy_path_uses_setnx_too_and_the_first_trip_stands(tmp_path):
    import os as _os
    d, store = _fake_docker(tmp_path)
    env = {**_os.environ, "PATH": f"{d}:{_os.environ['PATH']}", "NOCTUS_REDIS_TRIP_PASS_FILE": str(tmp_path / "absent")}
    run = lambda payload: subprocess.run(["bash", str(WATCHDOG_DIR / "breaker-trip.sh")], input=json.dumps(payload),
                                         capture_output=True, text=True, env=env, timeout=30)
    assert json.loads(run(GOOD).stdout) == {"tripped": True, "already": False}
    assert json.loads(run(dict(GOOD, reason="later")).stdout) == {"tripped": False, "already": True}
    assert json.loads(store.read_text())["reason"] == "critical"
    assert "SETNX" in (WATCHDOG_DIR / "breaker-trip.sh").read_text()


def test_breaker_script_is_hardened():
    txt = (WATCHDOG_DIR / "breaker-trip.sh").read_text()
    assert "\ncd /" in txt and "python3 -I -c" in txt


@needs_timeout
def test_host_probe_reads_the_breaker_key_from_the_acl_redis_too(tmp_path):
    import os as _os
    d, log, store = _acl_docker(tmp_path)
    store.write_text("x")
    pw_file = tmp_path / "trip.pass"
    pw_file.write_text("pp\n")
    env = {**_os.environ, "PATH": f"{d}:{_os.environ['PATH']}", "NOCTUS_REDIS_TRIP_PASS_FILE": str(pw_file)}
    out = subprocess.run(["bash", str(WATCHDOG_DIR / "host-probe.sh")], capture_output=True, text=True, env=env, timeout=60)
    assert json.loads(out.stdout.strip().splitlines()[-1])["breaker_tripped"] == 1
    assert "noctus-breaker-redis" in log.read_text() and "--user trip" in log.read_text()


# ── signature pin through the watchdog: reported as on/off, the value never leaves the process ──
def test_signature_pin_state_is_reported_but_its_value_never_reaches_report_state_or_alerts(tmp_path):
    from tools.noctus.dev import supabase_request_budget as srb

    pin = "Ab12_-xyz9"
    em = Sender()

    def check():
        return srb.supabase_request_budget(
            source=srb.FakeLogsSource(status_rows=[{"ua": "x", "status": 200, "calls": 9}], shape_rows=[]),
            env={"SUPABASE_SERVICE_SIG_PREFIX": pin})

    rep = _brun(tmp_path, check, Tripper(), senders={"email": em, "whatsapp": Sender()})
    blob = json.dumps(rep, default=str) + pw.format_report(rep) + (tmp_path / "b.json").read_text()
    assert pin not in blob and "signature pin: on" in pw.format_report(rep)
    off = _brun(tmp_path / "off", _budget("ok"), Tripper())
    assert "signature pin: off" in pw.format_report(off)


# ── N14: the report flags an unconfirmed environment protection, and never fails the run over it ──
def test_environment_protection_is_confirmed_or_flagged_never_fatal():
    def fetch(body, status=200):
        return lambda url, headers, timeout: (status, json.dumps(body).encode())

    env = {"GITHUB_REPOSITORY": "o/r", "WATCHDOG_GH_TOKEN": "SECRETTOK"}
    on = pw.environment_protection(env, fetch({"deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True}}))
    assert on["status"] == "restricted"
    off = pw.environment_protection(env, fetch({"deployment_branch_policy": None}))
    assert off["status"] == "off"
    assert pw.environment_protection(env, fetch({}, 403))["status"] == "unknown"
    assert pw.environment_protection({}, fetch({}))["status"] == "unknown"                       # no repo/token
    assert pw.environment_protection(env, lambda *a: (_ for _ in ()).throw(OSError("x")))["status"] == "unknown"
    assert "SECRETTOK" not in json.dumps([on, off])  # the token is never echoed


def test_run_reports_environment_protection_and_still_exits_zero(tmp_path):
    rep = pw.run(None, send=False, env=dict(ENV_ALL, GITHUB_REPOSITORY="o/r"), repo_root=REPO, slugs=["core"],
                 fetcher=Fetch(), ssh_runner=Ssh(), clock=Clock(), senders={"email": Sender()},
                 budget_check=lambda: {"verdict": "ok", "ok": True},
                 env_protection_check=lambda env: {"status": "unknown", "detail": "no token"})
    assert rep["environment_protection"]["status"] == "unknown" and rep["exit_code"] == 0
    assert any("environment protection" in w for w in rep["warnings"])


# ── N11/N12/N13/N10: shell hardening, run for real with fakes on PATH ──
def _fake_bin(tmp_path, scripts: dict):
    d = tmp_path / "fakebin"
    d.mkdir(parents=True, exist_ok=True)
    for name, body in scripts.items():
        (d / name).write_text("#!/usr/bin/env bash\n" + body)
        (d / name).chmod(0o755)
    return d


def test_probe_restriction_scan_covers_root_breaker_and_probe_homes_via_getent(tmp_path):
    import os as _os
    homes = {}
    for u in ("root", "breaker", "probe"):
        homes[u] = tmp_path / u
        (homes[u] / ".ssh").mkdir(parents=True)
    (homes["root"] / ".ssh/authorized_keys").write_text('restrict,command="x" ssh-ed25519 AAAA noctus-prod-watchdog\n')
    (homes["probe"] / ".ssh/authorized_keys").write_text("ssh-ed25519 AAAA noctus-prod-watchdog\n")  # NOT restricted
    cases = "\n".join(f'[[ "$2" == "{u}" ]] && echo "{u}:x:0:0::{h}:/bin/sh"' for u, h in homes.items())
    d = _fake_bin(tmp_path, {"getent": f'[[ "$1" == passwd ]] || exit 2\n{cases}\nexit 0\n'})
    env = {k: v for k, v in _os.environ.items() if k != "NOCTUS_AUTH_KEYS_FILES"}
    env["PATH"] = f"{d}:{env['PATH']}"
    out = subprocess.run(["bash", str(WATCHDOG_DIR / "host-probe.sh")], capture_output=True, text=True, env=env, timeout=60)
    assert json.loads(out.stdout.strip().splitlines()[-1])["breaker_key_restricted"] == 0


def test_installer_fails_up_front_for_a_missing_user_or_a_nologin_shell(tmp_path):
    import os as _os

    def run(id_rc, shell):
        d = _fake_bin(tmp_path / f"{id_rc}{shell.replace('/', '_')}", {
            "id": f'[[ "$1" == "-u" ]] && echo 0 && exit 0\nexit {id_rc}\n',
            "getent": f'echo "probe:x:1001:1001::{tmp_path}/home:{shell}"\n'})
        env = {**_os.environ, "PATH": f"{d}:{_os.environ['PATH']}", "NOCTUS_PROBE_USER": "probe"}
        return subprocess.run(["bash", str(WATCHDOG_DIR / "install-heartbeat.sh"), "--check"],
                              capture_output=True, text=True, env=env, timeout=30)

    gone = run(1, "/bin/sh")
    assert gone.returncode != 0 and "does not exist" in gone.stderr
    nol = run(0, "/usr/sbin/nologin")
    assert nol.returncode != 0 and "nologin" in nol.stderr
    txt = (WATCHDOG_DIR / "install-heartbeat.sh").read_text()
    assert "chown" in txt and not any("chown" in l and "|| true" in l for l in txt.splitlines())
    assert "root:root" in txt and "0644" in txt


@pytest.mark.parametrize("bad", ['{"reason":"r","rate":NaN,"window":"1h","tripped_at":"t","by":"offhost-watchdog"}',
                                 '{"reason":"r","rate":Infinity,"window":"1h","tripped_at":"t","by":"offhost-watchdog"}',
                                 '{"reason":"r","rate":-Infinity,"window":"1h","tripped_at":"t","by":"offhost-watchdog"}',
                                 '{"reason":"r","rate":1e999,"window":"1h","tripped_at":"t","by":"offhost-watchdog"}'])
def test_breaker_script_rejects_non_finite_numbers(tmp_path, bad):
    r, store = _trip(tmp_path, bad)
    assert r.returncode == 2 and not store.exists()
    assert "allow_nan=False" in (WATCHDOG_DIR / "breaker-trip.sh").read_text()


@needs_timeout
def test_host_probe_prefers_the_probe_credential_and_falls_back_to_trip(tmp_path):
    import os as _os
    d, log, store = _acl_docker(tmp_path)
    trip, probe = tmp_path / "trip.pass", tmp_path / "probe.pass"
    trip.write_text("tp\n")
    base = {**_os.environ, "PATH": f"{d}:{_os.environ['PATH']}", "NOCTUS_REDIS_TRIP_PASS_FILE": str(trip),
            "NOCTUS_REDIS_PROBE_PASS_FILE": str(probe)}
    subprocess.run(["bash", str(WATCHDOG_DIR / "host-probe.sh")], capture_output=True, text=True, env=base, timeout=60)
    assert "--user trip" in log.read_text() and "--user probe" not in log.read_text()
    log.unlink()
    probe.write_text("pp\n")
    subprocess.run(["bash", str(WATCHDOG_DIR / "host-probe.sh")], capture_output=True, text=True, env=base, timeout=60)
    txt = log.read_text()
    assert "--user probe" in txt and "AUTH: pp" in txt and "--user trip" not in txt
