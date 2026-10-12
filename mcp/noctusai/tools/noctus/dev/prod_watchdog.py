"""`noctus.dev.prod_watchdog` — OFF-HOST liveness checker for the prod VPS.

WHY (2026-10-11). At ~01:17Z the prod VPS (8 GB RAM, 2 vCPU) hard-froze right
after a fleet deploy: no ping, no SSH, Cloudflare 530 on every site, until the
owner rebooted it by hand. Host journald and cron/sysstat had silently stopped
~20h EARLIER while the sites kept serving. Any on-host check would have died
with the host and said nothing. This runs somewhere else (GitHub Actions, every
10 min) and reads an on-host heartbeat over ONE restricted SSH call.

LEGS
  • http_probe — core + every slug in `deploy/fleet/build-scope.txt`:
    GET https://<host>/api/health (browser UA — CF WAF 1010), plus `/` for core.
    0 (connection error), 52x/530 or any non-2xx = failure. Records status,
    latency and the seed health field `startup_hook_error`.
  • host_probe — exactly ONE ssh connection per run to a FORCED-COMMAND key
    (`deploy/watchdog/host-probe.sh`), which prints one JSON line. Parsed
    defensively; an SSH backoff schedule spares fail2ban (maxretry=5/600s).

CLASSIFY → up | degraded | down (thresholds: module constants, env-overridable)
  DOWN      core HTTP failing N=2 consecutive runs; or SSH unreachable N runs
            AND core impaired (failing this run, or startup_hook_error).
  DEGRADED  SSH unreachable N runs (alone) · journald last entry > 30 min ·
            heartbeat > 15 min or missing · MemAvailable < 600 MB · swap used
            > 1024 MB · load1 > 2×ncpu · a non-core product failing N runs ·
            any startup_hook_error · unreadable host-probe output.
  A single blip never alerts: every failure-type reason needs N consecutive runs.

ALERTING (dedupe state machine over a JSON state file)
  Alert only when the classified state differs from the last state the owner
  was SUCCESSFULLY told about (incl. recovery → up), plus a reminder every
  WATCHDOG_REMINDER_HOURS (6) while not up. Routing: DOWN → email (+ WhatsApp
  best-effort) · DEGRADED → WhatsApp, else email · RECOVERY → both. A missing
  channel is reported loudly; with `send=True` and NO channel configured, or an
  alert that reached no channel, the run exits non-zero (the workflow goes red).
  WAHA runs ON the VPS, so WhatsApp is only ever available while the host is up.

🔴 STDLIB ONLY. The CI job runs this under a bare python with no pip install
(`cd mcp/noctusai && python -m tools.noctus.dev.prod_watchdog`). Every network
edge (HTTP fetcher, SSH runner, senders, clock, env) is an injectable seam, so
tests need no network and no monkeypatching.

Depth: `KB § PATTERNS/devops/prod-watchdog.md`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from . import _public_edge as _edge

# ── thresholds (module constants; each overridable by the env var named) ─────
DEFAULTS: dict[str, float] = {
    "WATCHDOG_JOURNALD_MAX_AGE_S": 30 * 60,
    "WATCHDOG_HEARTBEAT_MAX_AGE_S": 15 * 60,
    "WATCHDOG_MEM_AVAILABLE_MIN_MB": 600,
    "WATCHDOG_SWAP_USED_MAX_MB": 1024,
    "WATCHDOG_LOAD_PER_CPU_MAX": 2.0,
    #: consecutive failed runs before a failure counts (never alert on one blip)
    "WATCHDOG_CONSECUTIVE": 2,
    #: after this many consecutive SSH failures, start skipping runs
    "WATCHDOG_SSH_BACKOFF_AFTER": 3,
    #: never go longer than "attempt every Nth run" (10-min cron → 1h)
    "WATCHDOG_SSH_BACKOFF_MAX_EVERY": 6,
    "WATCHDOG_REMINDER_HOURS": 6,
    "WATCHDOG_HTTP_TIMEOUT_S": 20,
}

UP, DEGRADED, DOWN = "up", "degraded", "down"
STATE_VERSION = 1
CORE = "core"
RESEND_URL = "https://api.resend.com/emails"
EMAIL_FROM = "NoctusAI <noreply@noctusai.com>"
HOST_PROBE_FIELDS = (
    "journald_last_age_s", "heartbeat_age_s", "mem_available_mb", "swap_used_mb",
    "load1", "load5", "ncpu", "uptime_s", "now",
)
#: ssh's own exit status for "could not connect / authenticate".
SSH_CONNECT_FAILURE_RC = 255

Fetcher = Callable[[str, float], "tuple[int, bytes, str]"]
SshRunner = Callable[[], "tuple[int, str, str]"]
Sender = Callable[[str, str], "tuple[bool, str]"]


# ── config ───────────────────────────────────────────────────────────────────
def thresholds(env: Mapping[str, str]) -> dict[str, float]:
    """DEFAULTS overlaid with env. A non-numeric override is a loud error."""
    out = dict(DEFAULTS)
    for name in DEFAULTS:
        raw = (env.get(name) or "").strip()
        if raw:
            try:
                out[name] = float(raw)
            except ValueError as exc:
                raise ValueError(f"{name}={raw!r} is not a number") from exc
    return out


def default_roster(repo_root: Path) -> list[str]:
    """`core` + every slug in build-scope.txt (core first, rest sorted)."""
    slugs = set(_edge.read_slug_file(Path(repo_root) / _edge.BUILD_SCOPE_RELPATH))
    slugs.discard(CORE)
    return [CORE] + sorted(slugs)


def _repo_root() -> Path:
    # `workspace` is stdlib-only (verified by test_module_imports_under_bare_stdlib).
    from workspace import get_noctusai_home

    return Path(get_noctusai_home())


# ── http leg ─────────────────────────────────────────────────────────────────
def _probe_url(slug: str, url: str, fetcher: Fetcher, timeout: float) -> dict:
    t0 = time.monotonic()
    status, body, _ctype = fetcher(url, timeout)
    latency_ms = int((time.monotonic() - t0) * 1000)
    hook_err = None
    if body:
        try:
            parsed = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            parsed = None
        if isinstance(parsed, dict) and parsed.get("startup_hook_error"):
            hook_err = str(parsed["startup_hook_error"])[:200]
    return {
        "slug": slug, "url": url, "status": status, "latency_ms": latency_ms,
        "ok": 200 <= status < 300, "startup_hook_error": hook_err,
    }


def http_probe(slugs: list[str], repo_root: Path, fetcher: Fetcher, timeout: float) -> list[dict]:
    """GET /api/health per slug (and `/` for core). One dict per URL."""
    out = []
    for slug in slugs:
        base = f"https://{_edge.public_hostname(slug, repo_root)}"
        out.append(_probe_url(slug, base + "/api/health", fetcher, timeout))
        if slug == CORE:
            out.append(_probe_url(slug, base + "/", fetcher, timeout))
    return out


# ── host leg ─────────────────────────────────────────────────────────────────
def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def parse_host_probe(text: str) -> tuple[Optional[dict], Optional[str]]:
    """The LAST stdout line that is a JSON object → `(metrics, None)`.

    Every known field is coerced to float-or-None (a string number is
    accepted, junk becomes None). Garbage / empty → `(None, why)`.
    """
    for line in reversed((text or "").strip().splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return {k: _num(obj.get(k)) for k in HOST_PROBE_FIELDS}, None
    return None, "host-probe produced no JSON object line" if (text or "").strip() else "host-probe output empty"


def backoff_every(consecutive_failures: int, th: Mapping[str, float]) -> int:
    """Attempt SSH every Nth run: 1 below K failures, then 2, 3, … capped."""
    k = int(th["WATCHDOG_SSH_BACKOFF_AFTER"])
    cap = max(1, int(th["WATCHDOG_SSH_BACKOFF_MAX_EVERY"]))
    if consecutive_failures < k:
        return 1
    return min(2 + (consecutive_failures - k), cap)


def should_attempt_ssh(ssh_state: Mapping[str, Any], th: Mapping[str, float]) -> bool:
    every = backoff_every(int(ssh_state.get("consecutive_failures", 0)), th)
    return int(ssh_state.get("skipped_since_attempt", 0)) + 1 >= every


def make_ssh_runner(env: Mapping[str, str]) -> Optional[SshRunner]:
    """Real SSH runner from env, or None when the leg is not configured.

    Needs `NOCTUS_VPS_HOST` + `WATCHDOG_SSH_KEY_FILE` (the workflow writes the
    restricted key there). Host-key pinning follows deploy-prod.yml: keyscan
    with 3 tries into a private known_hosts, then `StrictHostKeyChecking=yes`.
    Keyscan is a pre-auth handshake (no auth attempt → not a fail2ban strike);
    the ssh call itself is the run's ONE authenticated connection.
    """
    host = (env.get("NOCTUS_VPS_HOST") or "").strip()
    key = (env.get("WATCHDOG_SSH_KEY_FILE") or "").strip()
    if not host or not key or not Path(key).is_file():
        return None

    def _run() -> tuple[int, str, str]:
        kh = Path(tempfile.mkdtemp(prefix="watchdog-kh-")) / "known_hosts"
        for attempt in range(3):
            try:
                r = subprocess.run(["ssh-keyscan", "-H", host], capture_output=True, text=True, timeout=30)
                if r.stdout.strip():
                    kh.write_text(r.stdout, encoding="utf-8")
                    break
            except (OSError, subprocess.TimeoutExpired):
                pass
            if attempt < 2:
                time.sleep(5)
        if not kh.exists():
            return SSH_CONNECT_FAILURE_RC, "", "ssh-keyscan produced no host key after 3 tries"
        try:
            r = subprocess.run(
                ["ssh", "-i", key,
                 "-o", "StrictHostKeyChecking=yes",
                 "-o", f"UserKnownHostsFile={kh}",
                 "-o", "ConnectTimeout=20",
                 "-o", "BatchMode=yes",
                 f"root@{host}", "probe"],
                capture_output=True, text=True, timeout=60,
            )
        except subprocess.TimeoutExpired:
            return SSH_CONNECT_FAILURE_RC, "", "ssh timed out after 60s"
        except OSError as exc:
            return SSH_CONNECT_FAILURE_RC, "", f"ssh could not start: {exc}"
        return r.returncode, r.stdout, r.stderr

    return _run


# ── senders ──────────────────────────────────────────────────────────────────
def _post_json(url: str, payload: dict, headers: dict, timeout: float = 20) -> tuple[bool, str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, f"unreachable ({type(exc).__name__})"


def channel_config(env: Mapping[str, str]) -> dict[str, dict]:
    """Per channel: configured? and which env NAMES are missing (never values)."""
    def _missing(names):
        return [n for n in names if not (env.get(n) or "").strip()]
    return {
        "email": {"missing": _missing(["RESEND_API_KEY", "WATCHDOG_ALERT_EMAIL"])},
        "whatsapp": {"missing": _missing(["WAHA_BASE_URL", "WAHA_API_KEY", "WATCHDOG_ALERT_WHATSAPP"])},
    }


def make_senders(env: Mapping[str, str]) -> dict[str, Sender]:
    """Real senders for every CONFIGURED channel (stdlib urllib only)."""
    cfg = channel_config(env)
    senders: dict[str, Sender] = {}
    if not cfg["email"]["missing"]:
        def _email(subject: str, body: str) -> tuple[bool, str]:
            return _post_json(
                RESEND_URL,
                {"from": EMAIL_FROM, "to": [env["WATCHDOG_ALERT_EMAIL"].strip()],
                 "subject": subject, "text": body},
                {"Authorization": f"Bearer {env['RESEND_API_KEY'].strip()}"},
            )
        senders["email"] = _email
    if not cfg["whatsapp"]["missing"]:
        def _whatsapp(subject: str, body: str) -> tuple[bool, str]:
            digits = re.sub(r"\D", "", env["WATCHDOG_ALERT_WHATSAPP"])
            return _post_json(
                env["WAHA_BASE_URL"].strip().rstrip("/") + "/api/sendText",
                {"session": (env.get("WAHA_SESSION") or "").strip() or "default",
                 "chatId": f"{digits}@c.us", "text": f"{subject}\n\n{body}"},
                {"X-Api-Key": env["WAHA_API_KEY"].strip()},
            )
        senders["whatsapp"] = _whatsapp
    return senders


# ── state ────────────────────────────────────────────────────────────────────
def fresh_state() -> dict:
    return {
        "version": STATE_VERSION, "state": UP, "since": None,
        "alerted_state": UP, "last_alert_at": None,
        "counters": {}, "ssh": {"consecutive_failures": 0, "skipped_since_attempt": 0},
        "last_run_at": None,
    }


def load_state(path: Optional[Path]) -> tuple[dict, Optional[str]]:
    """`(state, warning)`. Missing → fresh; corrupt → fresh + a LOUD warning."""
    if path is None or not path.exists():
        return fresh_state(), None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return fresh_state(), f"state file {path} unreadable ({exc}) — started from a fresh state"
    if not isinstance(data, dict) or data.get("version") != STATE_VERSION:
        return fresh_state(), f"state file {path} has an unknown shape — started from a fresh state"
    st = fresh_state()
    st.update(data)
    return st, None


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _bump(counters: dict, key: str, failed: bool) -> int:
    counters[key] = int(counters.get(key, 0)) + 1 if failed else 0
    return counters[key]


# ── classification ───────────────────────────────────────────────────────────
def classify(http: list[dict], host: Optional[dict], host_error: Optional[str],
             counters: Mapping[str, int], th: Mapping[str, float]) -> tuple[str, list[str], list[str]]:
    """`(state, down_reasons, degraded_reasons)` from this run + counters.

    `counters` are already updated for this run: `http:<slug>` and `ssh` hold
    consecutive failed runs. `host` is this run's parsed host-probe (None when
    the SSH leg did not produce one this run).
    """
    n = int(th["WATCHDOG_CONSECUTIVE"])
    down: list[str] = []
    deg: list[str] = []

    by_slug: dict[str, list[dict]] = {}
    for r in http:
        by_slug.setdefault(r["slug"], []).append(r)

    def _fail_detail(rows: list[dict]) -> str:
        return ", ".join(
            f"{r['url'].split('://', 1)[-1].split('/', 1)[-1] or '/'}→"
            f"{r['status'] or 'sem conexão'}" for r in rows if not r["ok"]
        )

    core_rows = by_slug.get(CORE, [])
    core_fails_now = any(not r["ok"] for r in core_rows)
    core_hook = any(r["startup_hook_error"] for r in core_rows)
    core_count = int(counters.get(f"http:{CORE}", 0))
    ssh_count = int(counters.get("ssh", 0))

    if core_count >= n:
        down.append(f"core: HTTP falhou em {core_count} execuções seguidas ({_fail_detail(core_rows)})")
    if ssh_count >= n and (core_fails_now or core_hook):
        down.append(f"SSH inacessível há {ssh_count} execuções E o core está comprometido")
    if ssh_count >= n and not down:
        deg.append(f"SSH inacessível há {ssh_count} execuções seguidas (HTTP ok)")

    for slug, rows in sorted(by_slug.items()):
        c = int(counters.get(f"http:{slug}", 0))
        if slug != CORE and c >= n:
            deg.append(f"{slug}: HTTP falhou em {c} execuções seguidas ({_fail_detail(rows)})")
        for r in rows:
            if r["startup_hook_error"]:
                deg.append(f"{slug}: startup_hook_error = {r['startup_hook_error']}")

    if host_error:
        deg.append(f"host-probe ilegível: {host_error}")
    if host is not None:
        j = host.get("journald_last_age_s")
        if j is None:
            deg.append("journald: nenhuma entrada legível (journald parado?)")
        elif j > th["WATCHDOG_JOURNALD_MAX_AGE_S"]:
            deg.append(f"journald: última entrada há {int(j // 60)} min")
        hb = host.get("heartbeat_age_s")
        if hb is None:
            deg.append("heartbeat ausente (/var/lib/noctus/heartbeat)")
        elif hb > th["WATCHDOG_HEARTBEAT_MAX_AGE_S"]:
            deg.append(f"heartbeat há {int(hb // 60)} min (timer systemd parado?)")
        mem = host.get("mem_available_mb")
        if mem is None:
            deg.append("MemAvailable ilegível no host-probe")
        elif mem < th["WATCHDOG_MEM_AVAILABLE_MIN_MB"]:
            deg.append(f"MemAvailable baixa: {int(mem)} MB")
        swap = host.get("swap_used_mb")
        if swap is not None and swap > th["WATCHDOG_SWAP_USED_MAX_MB"]:
            deg.append(f"swap em uso: {int(swap)} MB")
        load1, ncpu = host.get("load1"), host.get("ncpu")
        if load1 is None or not ncpu:
            deg.append("load/ncpu ilegível no host-probe")
        elif load1 > th["WATCHDOG_LOAD_PER_CPU_MAX"] * ncpu:
            deg.append(f"load1 {load1:.2f} > {th['WATCHDOG_LOAD_PER_CPU_MAX']:g}×{int(ncpu)} CPUs")

    state = DOWN if down else (DEGRADED if deg else UP)
    return state, down, deg


# ── alert decision + routing ─────────────────────────────────────────────────
def decide_alert(state: dict, new: str, now: float, th: Mapping[str, float]) -> Optional[str]:
    """`"down" | "degraded" | "recovery" | "reminder" | None`."""
    alerted = state.get("alerted_state", UP)
    if new != alerted:
        return "recovery" if new == UP else new
    last = state.get("last_alert_at")
    if new != UP and last is not None and now - float(last) >= th["WATCHDOG_REMINDER_HOURS"] * 3600:
        return "reminder"
    return None


def route(kind: str, new: str) -> tuple[list[str], list[str]]:
    """`(primary, also)` channel order. Primary are tried in order until one
    succeeds (fallback); `also` are always attempted, best-effort."""
    effective = new if kind == "reminder" else kind
    if effective == DOWN:
        return ["email"], ["whatsapp"]
    if effective == DEGRADED:
        return ["whatsapp", "email"], []
    if effective in ("recovery", "test"):
        return ["email", "whatsapp"], ["email", "whatsapp"]
    return ["email"], []


_TITLES = {
    DOWN: "FORA DO AR", DEGRADED: "DEGRADADO", "recovery": "RECUPERADO",
    "test": "TESTE de alerta",
}


def _fmt_ts(ts: Optional[float]) -> str:
    if ts is None:
        return "?"
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ts))


def compose_message(kind: str, new: str, reasons: list[str], since: Optional[float],
                    now: float) -> tuple[str, str]:
    """Short pt-BR `(subject, body)`. Never includes a host/IP/secret."""
    if kind == "reminder":
        title = f"LEMBRETE: ainda {_TITLES.get(new, new)}"
    else:
        title = _TITLES.get(kind, kind)
    subject = f"[NoctusAI prod] {title}"
    lines = [f"NoctusAI prod — {title}"]
    if kind == "test":
        lines.append("Mensagem de teste do prod-watchdog: este canal de alerta funciona.")
    elif kind == "recovery":
        lines.append("Tudo normal de novo: HTTP e host respondendo dentro dos limites.")
    else:
        if since is not None:
            mins = int((now - since) // 60)
            lines.append(f"Desde: {_fmt_ts(since)} (há {mins} min)")
        lines.append("Motivos:")
        lines.extend(f"- {r}" for r in reasons[:12])
        if len(reasons) > 12:
            lines.append(f"- … e mais {len(reasons) - 12}")
    lines.append(f"Verificado em {_fmt_ts(now)} pelo prod-watchdog (GitHub Actions).")
    return subject, "\n".join(lines)


def deliver(kind: str, new: str, subject: str, body: str,
            senders: Mapping[str, Sender], cfg: Mapping[str, dict]) -> dict:
    """Send per routing; returns per-channel results + `delivered`."""
    primary, also = route(kind, new)
    results: dict[str, dict] = {}

    def _try(ch: str) -> bool:
        if ch in results:
            return results[ch].get("ok", False)
        fn = senders.get(ch)
        if fn is None:
            missing = cfg.get(ch, {}).get("missing") or []
            results[ch] = {"ok": False, "detail": "NOT CONFIGURED — missing " + (", ".join(missing) or "sender")}
            return False
        try:
            ok, detail = fn(subject, body)
        except Exception as exc:  # a sender bug must surface, not abort the run
            ok, detail = False, f"sender raised {type(exc).__name__}: {exc}"
        results[ch] = {"ok": bool(ok), "detail": detail}
        return bool(ok)

    for ch in primary:
        if _try(ch) and kind not in ("recovery", "test"):
            break
    for ch in also:
        _try(ch)
    return {"kind": kind, "subject": subject, "channels": results,
            "delivered": any(r.get("ok") for r in results.values())}


# ── entry point ──────────────────────────────────────────────────────────────
def run(
    state_path: Optional[Path] = None,
    *,
    send: bool = False,
    test_alert: bool = False,
    env: Optional[Mapping[str, str]] = None,
    repo_root: Optional[Path] = None,
    slugs: Optional[list[str]] = None,
    fetcher: Optional[Fetcher] = None,
    ssh_runner: Any = "auto",
    senders: Optional[Mapping[str, Sender]] = None,
    clock: Callable[[], float] = time.time,
) -> dict:
    """One watchdog pass. Returns the report; `report["exit_code"]` is the verdict.

    `send=False` (default) is a DRY probe: nothing is sent, and the state file is
    only written when `state_path` is given (counters advance; the alert
    bookkeeping does not, since nothing was delivered). `ssh_runner="auto"`
    builds the real runner from env; pass None to declare the leg unconfigured.
    """
    env = os.environ if env is None else env
    th = thresholds(env)
    root = Path(repo_root) if repo_root is not None else _repo_root()
    roster = slugs if slugs is not None else default_roster(root)
    fetch = fetcher or _edge.fetch
    runner = make_ssh_runner(env) if ssh_runner == "auto" else ssh_runner
    cfg = channel_config(env)
    snd = make_senders(env) if senders is None else dict(senders)
    for ch in cfg:
        cfg[ch]["configured"] = ch in snd
    now = clock()
    warnings: list[str] = []

    state, warn = load_state(Path(state_path) if state_path else None)
    if warn:
        warnings.append(warn)
    counters = state["counters"] = dict(state.get("counters") or {})
    ssh_state = state["ssh"] = dict(state.get("ssh") or {})

    # http leg
    http = http_probe(roster, root, fetch, th["WATCHDOG_HTTP_TIMEOUT_S"])
    for slug in roster:
        _bump(counters, f"http:{slug}", any(not r["ok"] for r in http if r["slug"] == slug))

    # host leg — at most ONE ssh connection
    host = host_error = None
    if runner is None:
        ssh_leg = {"status": "not_configured",
                   "detail": "NOCTUS_VPS_HOST / WATCHDOG_SSH_KEY_FILE unset — SSH leg skipped, HTTP + alerting still run"}
        warnings.append(ssh_leg["detail"])
        # No measurement ≠ a failure: an unconfigured leg must not keep a stale
        # "SSH unreachable" count alive (or a stale backoff) forever.
        counters["ssh"] = 0
        ssh_state.update(consecutive_failures=0, skipped_since_attempt=0)
    elif not should_attempt_ssh(ssh_state, th):
        ssh_state["skipped_since_attempt"] = int(ssh_state.get("skipped_since_attempt", 0)) + 1
        ssh_leg = {"status": "backoff",
                   "detail": (f"skipped: {ssh_state.get('consecutive_failures', 0)} consecutive failures, "
                              f"attempting every {backoff_every(int(ssh_state.get('consecutive_failures', 0)), th)} runs")}
    else:
        ssh_state["skipped_since_attempt"] = 0
        rc, out, err = runner()
        host_val = (env.get("NOCTUS_VPS_HOST") or "").strip()
        err_clean = (err or "").strip()[-300:]
        if host_val:
            err_clean = err_clean.replace(host_val, "<host>")
        if rc == SSH_CONNECT_FAILURE_RC:
            ssh_state["consecutive_failures"] = int(ssh_state.get("consecutive_failures", 0)) + 1
            _bump(counters, "ssh", True)
            ssh_leg = {"status": "unreachable", "rc": rc, "detail": err_clean}
        else:
            ssh_state["consecutive_failures"] = 0
            _bump(counters, "ssh", False)
            host, host_error = parse_host_probe(out)
            if rc != 0 and host is None:
                host_error = f"forced command exited {rc}: {err_clean or host_error}"
            ssh_leg = {"status": "ok" if host else "probe_error", "rc": rc, "detail": host_error or ""}

    new, down_r, deg_r = classify(http, host, host_error, counters, th)
    reasons = down_r + deg_r
    prev = state.get("state", UP)
    if new != prev or state.get("since") is None:
        state["since"] = now
    state["state"] = new
    state["last_run_at"] = now
    state["reasons"] = reasons

    kind = decide_alert(state, new, now, th)
    alert: dict[str, Any] = {"due": kind}
    exit_code = 0
    any_channel = any(c["configured"] for c in cfg.values())
    for ch, c in cfg.items():
        if not c["configured"]:
            warnings.append(f"alert channel {ch} NOT CONFIGURED — missing {', '.join(c['missing']) or 'sender'}")

    if kind:
        subject, body = compose_message(kind, new, reasons, state.get("since"), now)
        alert.update({"subject": subject, "body": body})
        if send:
            res = deliver(kind, new, subject, body, snd, cfg)
            alert.update(res)
            if res["delivered"]:
                state["alerted_state"] = new
                state["last_alert_at"] = now
            else:
                exit_code = 1
                warnings.append(f"alert {kind} reached NO channel — will retry next run")
        else:
            alert["dry_run"] = True

    test: Optional[dict] = None
    if test_alert:
        t_subject, t_body = compose_message("test", new, [], None, now)
        if send:
            test = deliver("test", new, t_subject, t_body, snd, cfg)
            if any(cfg[ch]["configured"] and not test["channels"].get(ch, {}).get("ok") for ch in cfg):
                exit_code = 1
                warnings.append("test alert failed on at least one configured channel")
        else:
            test = {"dry_run": True, "subject": t_subject, "body": t_body}

    if send and not any_channel:
        exit_code = 1
        warnings.append("NO alert channel configured — the watchdog cannot tell anyone; failing the run")

    saved = None
    if state_path:
        save_state(Path(state_path), state)
        saved = str(state_path)

    return {
        "state": new, "previous_state": prev, "since": state.get("since"),
        "reasons": reasons, "down_reasons": down_r, "degraded_reasons": deg_r,
        "http": http, "ssh": ssh_leg, "host": host, "counters": counters,
        "alert": alert, "test_alert": test, "channels": cfg,
        "warnings": warnings, "send": send, "state_saved": saved, "exit_code": exit_code,
    }


def format_report(rep: dict) -> str:
    lines = [f"prod-watchdog: {rep['state'].upper()} (anterior: {rep['previous_state']})"]
    for r in rep["http"]:
        mark = "ok " if r["ok"] else "FAIL"
        hook = f"  startup_hook_error={r['startup_hook_error']}" if r["startup_hook_error"] else ""
        lines.append(f"  [{mark}] {r['url']:<52} {r['status'] or 'conn-err'} {r['latency_ms']}ms{hook}")
    lines.append(f"  ssh: {rep['ssh']['status']} {rep['ssh'].get('detail') or ''}".rstrip())
    if rep["host"]:
        lines.append("  host: " + ", ".join(f"{k}={v:g}" if v is not None else f"{k}=null"
                                            for k, v in rep["host"].items()))
    for r in rep["reasons"]:
        lines.append(f"  - {r}")
    a = rep["alert"]
    if a.get("due"):
        verb = "would send" if a.get("dry_run") else ("delivered" if a.get("delivered") else "NOT delivered")
        lines.append(f"  alert {a['due']}: {verb} — {a.get('subject')}")
        for ch, res in (a.get("channels") or {}).items():
            lines.append(f"    {ch}: {'ok' if res.get('ok') else 'FAIL'} {res.get('detail', '')}")
    else:
        lines.append("  alert: none due (dedupe)")
    t = rep.get("test_alert")
    if t:
        for ch, res in (t.get("channels") or {}).items():
            lines.append(f"  test {ch}: {'ok' if res.get('ok') else 'FAIL'} {res.get('detail', '')}")
        if t.get("dry_run"):
            lines.append("  test alert: dry run (pass --send)")
    for w in rep["warnings"]:
        lines.append(f"  WARNING: {w}")
    if rep["state_saved"]:
        lines.append(f"  state saved: {rep['state_saved']}")
    lines.append(f"  exit {rep['exit_code']}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="prod_watchdog", description=__doc__.split("\n", 1)[0])
    p.add_argument("--state", type=Path, default=None, help="JSON state file (omit = stateless dry probe)")
    p.add_argument("--send", action="store_true", help="send real alerts (default: dry run)")
    p.add_argument("--test-alert", action="store_true", help="also push a TEST message through every configured channel")
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    a = p.parse_args(argv)
    try:
        rep = run(a.state, send=a.send, test_alert=a.test_alert)
    except ValueError as exc:
        print(f"prod-watchdog: config error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(rep, indent=2, default=str) if a.json else format_report(rep))
    return int(rep["exit_code"])


def register(server) -> None:
    @server.tool(
        name="noctus.dev.prod_watchdog",
        description=(
            "OFF-HOST prod liveness check (the CI job runs it every 10 min; born from the "
            "2026-10-11 VPS freeze where on-host journald had died ~20h earlier). HTTP: "
            "/api/health for core + every slug in deploy/fleet/build-scope.txt (browser UA), "
            "plus core `/`; SSH: ONE call to a restricted forced-command key printing host "
            "metrics (journald age, heartbeat age, MemAvailable, swap, load) — skipped when "
            "NOCTUS_VPS_HOST/WATCHDOG_SSH_KEY_FILE are unset. Classifies up|degraded|down "
            "(down needs 2 consecutive failed runs). Default is a DRY probe: prints the "
            "report, sends nothing, touches state only when state_path is given. send=True "
            "sends real alerts (Resend email / WAHA WhatsApp) with dedupe + reminders. "
            "KB § PATTERNS/devops/prod-watchdog.md."
        ),
    )
    def _prod_watchdog(state_path: Optional[str] = None, send: bool = False,
                       send_test_alert: bool = False) -> dict:
        return run(Path(state_path) if state_path else None, send=send, test_alert=send_test_alert)


__all__ = [
    "DEFAULTS", "backoff_every", "channel_config", "classify", "compose_message",
    "decide_alert", "default_roster", "deliver", "http_probe", "load_state", "main",
    "make_senders", "make_ssh_runner", "parse_host_probe", "register", "route", "run",
    "save_state", "should_attempt_ssh", "thresholds",
]

if __name__ == "__main__":
    sys.exit(main())
