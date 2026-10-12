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
