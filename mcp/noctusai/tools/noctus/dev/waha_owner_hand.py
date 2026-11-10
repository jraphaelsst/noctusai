"""The OWNER-BY-HAND path for a `personal: true` WAHA line (owner decision D49, 2026-11-10). CLI ONLY.

`noctus.dev.waha_instance` refuses to provision/apply a personal line for every caller (PERSONAL_REFUSAL). This module
is the one way the OWNER does that step himself, from his own terminal:

    python mcp/noctusai/cli.py --waha-instance-owner-hand apply <line>      # core -> provision -> edge
    python mcp/noctusai/cli.py --waha-instance-owner-hand provision <line>  # session config only (core already up)

It is deliberately NOT an MCP tool: it has no `register()`, `tools/noctus/dev/__init__.py` never imports it, and a test
asserts its name is absent from the registered tool set. It runs exactly what `provision` / `apply` run for that ONE
line, with every other check unchanged (tighten-only vs the VPS checkout and the running session, policy read-back,
foreign webhooks dropped, edge-before-QR order), plus checks of its own: the line must be the strict shadow shape
(`send: disabled`, `mark_online: false`, `full_sync: false`, `edge_deny_writes: true`, `dashboard: false`,
`personal: true`); the policy hash the human confirms covers the policy fields AND the rendered core + edge compose
service blocks, and the VPS's own checkout (its `waha-instances.yml` and its `compose.waha.yml`) must give the
IDENTICAL hash; the VPS compose must stamp `noctus.line.personal=true` on core AND edge and keep the core off noctus-net.

Threat model (also in KB § CONTEXT/INTEGRATIONS/whatsapp.md § 6a). The risk is a WELL-MEANING AGENT UNDER PRESSURE --
a session that reads "the owner does it by hand" as an obstacle -- not a hostile operator (whoever has a shell here or
root on the VPS can pair a number without this tool). What such a session cannot produce by accident is a human at a
real terminal window, so:

* the parent process chain is an ALLOWLIST: walked to launchd (pid 1), it must contain a known terminal emulator
  (TERMINAL_ALLOWLIST -- data) and nothing from CHAIN_DENYLIST (pty/reparent wrappers, `claude`, IDE extension hosts /
  language servers) anywhere; a chain that cannot be read, or reaches launchd with no emulator, is refused. This is what
  stops `env -i ... script -q /dev/null <cmd> < answers` from a reparented subshell, `expect`, `tmux new -d` +
  `send-keys`;
* stdin AND stdout are TTYs, /dev/tty opens, no CLAUDECODE / CLAUDE_CODE_* in the env;
* the human TYPES the line name and CONFIRMO on /dev/tty (never stdin; no flag can pre-answer it);
* the `confirmed` audit row is written (or spooled AND read back, its id shown on the terminal) BEFORE anything touches
  the VPS; the grant `waha_instance` accepts is bound to line + policy hash + host + a secret nonce whose DIGEST is in
  that row, is honoured only while that row is < 5 minutes old, and is single-use (the outcome row consumes it).

No second factor, ever (owner decision). What this control does NOT stop (documented residuals, KB § 6a): in-process
Python that deliberately reaches into this module's private state; a process that types into a real terminal window
(osascript / accessibility APIs); an agent hosted in an allowlisted IDE's own terminal; VPS root/automation reading the
session files until NOC-REMEDIATE[personal-core-host-exec-authz] is built.
"""
from __future__ import annotations

import base64
import datetime as _dt
import getpass
import hashlib
import json
import os
import re
import secrets
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import waha_instance as wi

LEDGER_NAME = "waha-owner-hand.ndjson"
LEDGER_REL = Path("project-history") / LEDGER_NAME
ACTIONS = ("provision", "apply")
CONFIRM_WORD = "CONFIRMO"
COMMAND = "python mcp/noctusai/cli.py --waha-instance-owner-hand {action} {name}"
GRANT_TTL_S = 300
_HARNESS_ENV_EXACT = ("CLAUDECODE",)
_HARNESS_ENV_PREFIX = "CLAUDE_CODE_"
_MAX_HOPS = 64

#: (label, regex on an ancestor's full command line). At least ONE ancestor must match. The terminal's pty host only --
#: an IDE's extension host ("Helper (Plugin)") is NOT a terminal and is on the denylist.
TERMINAL_ALLOWLIST: tuple[tuple[str, str], ...] = (
    ("macOS Terminal", r"/Terminal\.app/Contents/MacOS/Terminal(\s|$)"),
    ("iTerm2", r"/iTerm\.app/Contents/MacOS/(iTerm2|iTermServer-[\w.]+)(\s|$)"),
    ("Antigravity IDE", r"/Antigravity IDE Helper\.app/Contents/MacOS/Antigravity IDE Helper(\s|$)"),
    ("VS Code", r"/Code Helper\.app/Contents/MacOS/Code Helper(\s|$)"),
)
#: (label, regex). ANY ancestor matching ANY of these refuses, even under an allowed emulator.
CHAIN_DENYLIST: tuple[tuple[str, str], ...] = (
    ("script", r"(^|/)script(\s|$)"),
    ("expect", r"(^|/)expect(\s|$)"),
    ("tmux", r"(^|/)tmux(:|\s|$)"),
    ("screen", r"(?i)(^|/)screen(\s|$)"),
    ("nohup", r"(^|/)nohup(\s|$)"),
    ("setsid", r"(^|/)setsid(\s|$)"),
    ("unbuffer", r"(^|/)unbuffer(\s|$)"),
    ("socat", r"(^|/)socat(\s|$)"),
    ("python -c pty", r"(^|/)python[\d.]*\s.*-c.*\bpty\b"),
    ("claude", r"(^|/)claude(\s|$)|@anthropic-ai/claude-code|claude-code/cli"),
    ("IDE extension host / language server", r"language_server|Helper \(Plugin\)"),
)

_MINT = object()  # module-private: only `owner_hand` holds it when it builds a grant


def _b32(raw: bytes) -> str:
    """Lowercase base32 (digits 2-7 only): no long digit runs, so a hash can never trip the ledger PII guard (a hex
    digest can carry an 11-digit run that is a valid CPF, which would refuse that policy FOREVER)."""
    return base64.b32encode(raw).decode().rstrip("=").lower()


def _new_id() -> str:
    return _b32(secrets.token_bytes(10))


def _digest(nonce: str) -> str:
    return _b32(hashlib.sha256(("waha-owner-hand:" + nonce).encode()).digest())


@dataclass(frozen=True)
class OwnerHandGrant:
    """Permission for ONE personal line, ONE policy hash, ONE host, ONE use. Minted only by `owner_hand` after the gate
    and after its `confirmed` audit row (carrying `_digest(nonce)`, never the nonce) is durable."""

    line: str
    policy_hash: str
    host: str
    nonce: str = field(default="", repr=False)
    ledger_root: "str | None" = None
    fields_hash: str = ""
    _key: object = field(repr=False, compare=False, default=None)
    _state: dict = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self):
        if self._key is not _MINT:
            raise PermissionError("an OwnerHandGrant is minted only by waha_owner_hand.owner_hand after the human gate")


def compose_fingerprint(services: dict, name: str) -> dict:
    """The core + edge compose service blocks of a line (image, env, volumes, networks, labels, command...), as data."""
    return {svc: services.get(svc) for svc in (f"waha-{name}-core", f"waha-{name}")}


def policy_hash(inst: dict, compose: "dict | None" = None) -> str:
    """sha256 of every field that decides what a line may do (+ its rendered compose blocks when given)."""
    keys = ("name", "product", "session", "line_policy", "edge_deny_writes", "dashboard", "personal", "webhook_upstream")
    doc = {k: inst.get(k) for k in keys}
    if compose is not None:
        doc["compose"] = compose
    return _b32(hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).digest())


def _ledger_text(root: "str | Path | None") -> str:
    from ._ledger_store import open_ledger
    base = Path(root) if root else Path(wi.REPO_ROOT)
    return open_ledger(LEDGER_NAME, base / LEDGER_REL).read_text()


def _rows_for(text: str, digest: str) -> list[dict]:
    out = []
    for ln in text.splitlines():
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("grant_digest") == digest:
            out.append(r)
    return out


def _age_s(ts: str) -> float:
    try:
        then = _dt.datetime.fromisoformat(str(ts))
    except ValueError:
        return float("inf")
    if then.tzinfo is None:
        return float("inf")
    return (_dt.datetime.now(_dt.timezone.utc) - then).total_seconds()


def grant_covers(grant, inst: dict, host: str, vps_inst: "dict | None" = None) -> bool:
    """True only for a minted, unconsumed grant naming this line + host + policy, backed by its own fresh `confirmed`
    audit row. Any read failure is False (fail closed)."""
    if not isinstance(grant, OwnerHandGrant) or grant._key is not _MINT or not grant.nonce:
        return False
    if grant.line != inst.get("name") or grant.host != host:
        return False
    want = grant.fields_hash or grant.policy_hash
    if want != policy_hash(inst) or (vps_inst is not None and policy_hash(vps_inst) != want):
        return False
    try:
        rows = _rows_for(_ledger_text(grant.ledger_root), _digest(grant.nonce))
    except Exception:  # noqa: BLE001 - an unreadable ledger never covers (fail closed)
        return False
    if any(r.get("outcome") != "confirmed" for r in rows):
        return False  # consumed: the outcome row of its one use is already there
    ok = [r for r in rows if r.get("line") == grant.line and r.get("host") == grant.host
          and r.get("policy_hash") == grant.policy_hash]
    if not ok:
        return False
    if not grant._state.get("verified"):  # the 5-minute window applies to the first check of this action
        if min(_age_s(r.get("ts")) for r in ok) > GRANT_TTL_S:
            return False
        grant._state["verified"] = True
    return True


def shadow_shape_problems(inst: dict) -> list[str]:
    """The strict read-only shadow shape a personal line must have (anything else is refused, never loosened)."""
    pol = inst.get("line_policy") or {}
    want = {"send": "disabled", "mark_online": False, "full_sync": False}
    out = [f"line_policy.{k} must be {v!r}, is {pol.get(k)!r}" for k, v in want.items() if pol.get(k) != v]
    for k, v in (("personal", True), ("edge_deny_writes", True), ("dashboard", False)):
        if inst.get(k) is not v:
            out.append(f"{k} must be {v!r}, is {inst.get(k)!r}")
    return out


class _RealIO:
    """The process's real terminal, environment, parent chain, identity and remote runner."""

    def env(self) -> dict:
        return dict(os.environ)

    def isatty(self, fd: int) -> bool:
        return os.isatty(fd)

    def open_tty(self):
        return open("/dev/tty", "r+", encoding="utf-8")  # noqa: SIM115 - closed by the caller

    def parent_commands(self) -> "list[str] | None":
        """Command lines of every ancestor up to (not incl.) launchd, nearest first. None when the chain cannot be read
        or does not reach pid 1 within _MAX_HOPS."""
        out, pid = [], os.getppid()
        for _ in range(_MAX_HOPS):
            if pid <= 1:
                return out
            try:
                r = subprocess.run(["ps", "-o", "ppid=", "-o", "command=", "-p", str(pid)],
                                   capture_output=True, text=True, timeout=5, check=False)
            except (OSError, subprocess.SubprocessError):
                return None
            line = r.stdout.strip()
            if r.returncode != 0 or not line:
                return None
            ppid, _, cmd = line.partition(" ")
            out.append(cmd.strip())
            try:
                pid = int(ppid)
            except ValueError:
                return None
        return None

    def git_email(self) -> str:
        try:
            r = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True, timeout=5, check=False)
            return r.stdout.strip() or "unknown"
        except (OSError, subprocess.SubprocessError):
            return "unknown"

    def os_user(self) -> str:
        try:
            return getpass.getuser()
        except (OSError, KeyError):
            return "unknown"

    sh = None  # production: waha_instance's own runner, never overridable from here


def chain_problem(chain: "list[str] | None") -> "str | None":
    """None when the ancestor chain has a known terminal emulator and no denied wrapper; else why not."""
    if chain is None:
        return "the parent process chain cannot be read up to launchd: refused (fail closed)"
    for cmd in chain:
        for label, rx in CHAIN_DENYLIST:
            if re.search(rx, cmd):
                return (f"`{label}` is in the parent process chain: the owner runs this directly in a terminal window "
                        "(no pty wrapper, multiplexer or agent)")
    if not any(re.search(rx, cmd) for cmd in chain for _, rx in TERMINAL_ALLOWLIST):
        names = ", ".join(lab for lab, _ in TERMINAL_ALLOWLIST)
        return f"no known terminal emulator in the parent process chain (allowed: {names}): refused"
    return None


def human_gate(io) -> "str | None":
    """None when an interactive human (not an agent harness) is at a real terminal window; else why not. Fail closed."""
    env = io.env()
    hits = sorted(k for k in env if k in _HARNESS_ENV_EXACT or k.startswith(_HARNESS_ENV_PREFIX))
    if hits:
        return f"running inside an agent harness (env {', '.join(hits)} present): the owner runs this in his own terminal"
    if not (io.isatty(0) and io.isatty(1)):
        return "stdin and stdout must both be a terminal (no pipes, no redirection): the owner runs this by hand"
    try:
        io.open_tty().close()
    except OSError as exc:
        return f"/dev/tty cannot be opened ({exc.__class__.__name__}): no controlling terminal"
    return chain_problem(io.parent_commands())


def _test_runner_problem(io) -> "str | None":
    """A test IO must carry its OWN runner, explicitly marked as a test fake -- never the real one -- and only inside a
    pytest test. This is what keeps the test seam from being a gate bypass that still reaches the VPS."""
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return "a test IO was passed outside a pytest test: refused (the CLI never passes one)"
    sh = getattr(io, "sh", None)
    if sh is None or sh is wi._sh or getattr(sh, "__noc_test_fake__", False) is not True:
        return ("a test IO must carry its own runner explicitly marked as a test fake (`__noc_test_fake__ = True`); "
                "the real remote runner is never reachable through it")
    return None


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _audit(root: Path, row: dict) -> dict:
    from ._ledger_store import append_rows
    try:
        return append_rows(LEDGER_NAME, root / LEDGER_REL, [row],
                           message=f"waha-owner-hand: {row['action']} {row['line']} {row['outcome']}")
    except Exception as exc:  # noqa: BLE001 - surfaced on the result; the action is refused when it matters
        return {"ok": False, "status": "error", "error": f"{exc.__class__.__name__}: {exc}"}


def _audit_durable(root: Path, res: dict, row_id: str) -> "str | None":
    """None when the row is durable: published/written, or SPOOLED and read back from the spool by its id."""
    if res.get("ok") and res.get("status") != "pending":
        return None
    if res.get("status") == "pending":
        try:
            text = _ledger_text(root)
        except Exception as exc:  # noqa: BLE001 - a failed read-back refuses
            return f"audit row {row_id} was spooled but could not be read back ({exc.__class__.__name__})"
        if any(f'"id": "{row_id}"' in ln or f'"id":"{row_id}"' in ln for ln in text.splitlines()):
            return None
        return f"audit row {row_id} was spooled but could not be read back from the spool"
    return f"the audit row could not be written ({res.get('error') or res.get('status')})"


def _ask(tty, prompt: str) -> str:
    tty.write(prompt)
    tty.flush()
    return (tty.readline() or "").strip()


def _summary(inst: dict, phash: str, host: str, action: str) -> str:
    pol = inst["line_policy"]
    return (
        "\n  PERSONAL WhatsApp line -- owner-by-hand (D49)\n"
        f"  action      : {action}\n"
        f"  line        : {inst['name']}   (product {inst['product']}, session {inst.get('session')})\n"
        f"  policy      : send={pol['send']}  markOnline={str(pol['mark_online']).lower()}  "
        f"fullSync={str(pol['full_sync']).lower()}  auto_repair={str(pol['auto_repair']).lower()}  "
        f"personal={str(inst.get('personal')).lower()}\n"
        f"  edge proxy  : waha-{inst['name']} (deny writes)  dashboard=off\n"
        f"  target host : {host}\n"
        f"  policy hash : {phash}   (policy + rendered core/edge compose; the VPS checkout matches)\n\n"
    )


def _vps_compose(name: str, host: str, sh) -> "tuple[dict | None, list[str]]":
    """(services of the VPS's compose.waha.yml, problems): core AND edge labelled personal, core off noctus-net."""
    import yaml

    rc, text, err = sh(host, f"cat {wi.VPS_FLEET}/compose.waha.yml")
    if rc != 0:
        return None, [f"cannot read the VPS's compose.waha.yml ({err.strip()[-120:]})"]
    try:
        svcs = (yaml.safe_load(text) or {}).get("services") or {}
    except yaml.YAMLError as exc:
        return None, [f"the VPS's compose.waha.yml does not parse ({exc.__class__.__name__})"]
    out = []
    for svc in (f"waha-{name}-core", f"waha-{name}"):
        s = svcs.get(svc)
        if not isinstance(s, dict):
            out.append(f"service {svc} missing from the VPS compose (an edge line has core + edge)")
            continue
        if str((s.get("labels") or {}).get("noctus.line.personal")) != "true":
            out.append(f"service {svc} lacks the label noctus.line.personal=true on the VPS")
    core_nets = (svcs.get(f"waha-{name}-core") or {}).get("networks") or []
    if "noctus-net" in core_nets:
        out.append(f"waha-{name}-core is on noctus-net on the VPS (the core must be reachable only through its edge)")
    return svcs, out


def _live_label_problems(name: str, host: str, sh) -> list[str]:
    out, fmt = [], shlex.quote('{{index .Config.Labels "noctus.line.personal"}}')
    for c in (f"noctus-waha-{name}-core", f"noctus-waha-{name}"):
        rc, val, _ = sh(host, f"docker inspect -f {fmt} {c}")
        if rc != 0 or val.strip() != "true":
            out.append(f"{c} is not running with the label noctus.line.personal=true")
    return out


def owner_hand(action: str, name: str, ssh_host: str = "noctus-vps", repo_root: "str | None" = None, *,
               _test_io=None) -> dict:
    """Run provision/apply for ONE personal line, only for an interactive human who typed the confirmation.

    `_test_io` is a TEST-ONLY injection point (terminal, env, parent chain, identity, remote runner). It is refused
    outside a pytest test and unless it carries its own explicitly test-marked fake runner (never the real one). The CLI
    never passes it and it is not part of any tool schema; production code must never pass it."""
    import yaml

    from ._ledger_store import MODE_GIT, store_mode

    io = _test_io or _RealIO()
    root = Path(repo_root) if repo_root else Path(wi.REPO_ROOT)
    who = {"git_email": io.git_email(), "os_user": io.os_user()}
    base = {"ts": _now(), "tool": "waha_owner_hand", "action": action, "line": name, "host": ssh_host, "who": who,
            "policy_hash": None}

    def refuse(why: str, **kw) -> dict:
        row = {**base, "id": _new_id(), "outcome": "refused", "reason": why[:300]}
        aud = _audit(root, row)
        return {"ok": False, "action": action, "name": name, "status": "refused", "error": why, "audit": aud, **kw}

    if action not in ACTIONS:
        return refuse(f"unknown action {action!r} -- {'|'.join(ACTIONS)}")
    if _test_io is not None:
        why = _test_runner_problem(_test_io)
        if why:
            return refuse(why)
    elif store_mode() != MODE_GIT:
        return refuse("the audit ledger must be the real store (origin/ledgers); NOCTUS_LEDGER_STORE=fake is test-only")
    why = human_gate(io)
    if why:
        return refuse(why)
    try:
        spec = wi.load_spec(root)
        inst = wi._inst(spec, name)
    except ValueError as exc:
        return refuse(str(exc))
    fields = policy_hash(inst)
    base["policy_hash"] = fields
    bad = shadow_shape_problems(inst)
    if bad:
        return refuse("not a strict read-only personal line: " + "; ".join(bad))
    sh = io.sh if _test_io is not None else wi._sh
    vps_inst, vwhy = wi._vps_instance(name, ssh_host, sh)
    if vps_inst is None:
        return refuse(vwhy)
    if policy_hash(vps_inst) != fields:
        return refuse("the VPS's own waha-instances.yml declares a different policy for this line "
                      f"(VPS {policy_hash(vps_inst)[:12]} vs here {fields[:12]}): deploy_pull first, then re-run")
    vps_svcs, bad = _vps_compose(name, ssh_host, sh)
    if bad:
        return refuse("the VPS's rendered compose is not safe for a personal line: " + "; ".join(bad))
    local_fp = compose_fingerprint((yaml.safe_load(wi.render_compose(spec)) or {}).get("services") or {}, name)
    vps_fp = compose_fingerprint(vps_svcs, name)
    phash, vhash = policy_hash(inst, local_fp), policy_hash(vps_inst, vps_fp)
    base["policy_hash"] = phash
    if phash != vhash:
        drift = sorted(s for s in local_fp if local_fp[s] != vps_fp.get(s))
        return refuse(f"the VPS's compose.waha.yml differs from this checkout's render for {', '.join(drift)} "
                      f"(VPS {vhash[:12]} vs here {phash[:12]}): render, merge and deploy_pull first, then re-run")

    try:
        tty = io.open_tty()
    except OSError as exc:
        return refuse(f"/dev/tty cannot be opened ({exc.__class__.__name__})")
    nonce = secrets.token_hex(32)
    row_id = _new_id()
    try:
        tty.write(_summary(inst, phash, ssh_host, action))
        typed = _ask(tty, "  Type the line name to continue: ")
        if typed != name:
            return refuse("the typed line name does not match: nothing was done")
        word = _ask(tty, f"  Type {CONFIRM_WORD} to {action} this personal line now: ")
        if word != CONFIRM_WORD:
            return refuse(f"{CONFIRM_WORD} was not typed: nothing was done")
        pre = _audit(root, {**base, "id": row_id, "ts": _now(), "outcome": "confirmed", "grant_digest": _digest(nonce)})
        why = _audit_durable(root, pre, row_id)
        if why:
            tty.write(f"\n  REFUSED: {why}\n")
            return {"ok": False, "action": action, "name": name, "status": "refused", "audit": pre,
                    "error": why + ": refused before touching the VPS (fail closed)"}
        state = "spooled (not yet published to origin/ledgers; the next ledger publish carries it)" \
            if pre.get("status") == "pending" else "written"
        tty.write(f"\n  audit row {row_id} {state}\n\n")
    finally:
        tty.close()

    if _test_io is not None and _test_runner_problem(_test_io):  # the minter re-checks: never a grant over the real runner
        return refuse("refused at mint: " + str(_test_runner_problem(_test_io)))
    grant = OwnerHandGrant(line=name, policy_hash=phash, host=ssh_host, nonce=nonce, ledger_root=str(root),
                           fields_hash=fields, _key=_MINT)
    if _test_io is not None and hasattr(_test_io, "observe_grant"):
        _test_io.observe_grant(grant)
    kw = {"_test_sh": sh} if _test_io is not None else {}
    res: dict = {"ok": False, "status": "error", "error": "the action did not complete"}
    try:
        if action == "provision":
            res = wi._provision(spec, name, ssh_host, True, _owner_grant=grant, **kw)
        else:
            res = wi._apply(spec, name, ssh_host, True, _owner_grant=grant, **kw)
            if res.get("ok"):
                lab = _live_label_problems(name, ssh_host, sh)
                if lab:
                    res = {**res, "ok": False, "status": "label_drift", "label_problems": lab}
    finally:  # the outcome row CONSUMES the grant (single use), whatever happened
        post = _audit(root, {**base, "id": _new_id(), "ts": _now(), "grant_digest": _digest(nonce),
                             "outcome": str(res.get("status") or ("ok" if res.get("ok") else "error"))})
    return {**res, "owner_hand": True, "policy_hash": phash, "audit_row_id": row_id,
            "audit": {"confirmed": pre, "outcome": post}}


__all__ = ["owner_hand", "human_gate", "chain_problem", "policy_hash", "compose_fingerprint", "grant_covers",
           "shadow_shape_problems", "OwnerHandGrant", "TERMINAL_ALLOWLIST", "CHAIN_DENYLIST", "LEDGER_NAME", "COMMAND"]
