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
`personal: true`), the VPS's own checkout must declare the IDENTICAL policy (same hash as the one the human confirmed),
and the VPS's rendered compose must stamp `noctus.line.personal=true` on core AND edge and keep the core off noctus-net.

Threat model (one paragraph, also in KB § CONTEXT/INTEGRATIONS/whatsapp.md § 6a). The adversary is NOT a hostile
operator -- whoever has a shell on this laptop or root on the VPS can pair a number without this tool. It is a
WELL-MEANING AGENT UNDER PRESSURE: a session that wants the task done and reads "the owner does it by hand" as an
obstacle. What such a session cannot produce by accident is an interactive human at a terminal: so the path refuses
unless stdin AND stdout are TTYs and /dev/tty opens, refuses inside an agent harness (env CLAUDECODE or any
CLAUDE_CODE_*, and -- best effort -- any `claude` binary in the parent process chain; an unreadable chain refuses),
and then requires the human to TYPE the line name and the literal word CONFIRMO on /dev/tty (never stdin, so nothing
piped and no flag can pre-answer it). There is no second factor and there will not be one (owner decision: no
OTP/2FA, ever). Every attempt -- refused or done -- appends a row to the `waha-owner-hand.ndjson` ledger (who = git
user.email + OS user, when, line, policy hash, action, host, outcome; never a phone number). Residual risk the owner
accepted (D49, reminder 15): VPS root/automation can read the session files until NOC-REMEDIATE[personal-core-host-exec-authz]
is built.

The grant that lets `waha_instance` skip its personal refusal is minted here only after the gate passed, is bound to
line + policy hash + host, and is checked by identity of a module-private key. A Python caller that reaches into this
module's private key on purpose is out of scope (that is the adversary above, not the accident).
"""
from __future__ import annotations

import datetime as _dt
import getpass
import hashlib
import json
import os
import re
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
_HARNESS_ENV_EXACT = ("CLAUDECODE",)
_HARNESS_ENV_PREFIX = "CLAUDE_CODE_"
_CLAUDE_CMD = re.compile(r"(^|/)claude(\s|$)|@anthropic-ai/claude-code|claude-code/cli")
_MAX_HOPS = 64

_MINT = object()  # module-private: only `owner_hand` holds it when it builds a grant


@dataclass(frozen=True)
class OwnerHandGrant:
    """Permission for ONE personal line, ONE policy hash, ONE host. Built only by `owner_hand` after the human gate."""

    line: str
    policy_hash: str
    host: str
    _key: object = field(repr=False, compare=False, default=None)

    def __post_init__(self):
        if self._key is not _MINT:
            raise PermissionError("an OwnerHandGrant is minted only by waha_owner_hand.owner_hand after the human gate")


def policy_hash(inst: dict) -> str:
    """sha256 of every field that decides what a line may do (canonical JSON)."""
    keys = ("name", "product", "session", "line_policy", "edge_deny_writes", "dashboard", "personal", "webhook_upstream")
    doc = {k: inst.get(k) for k in keys}
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def grant_covers(grant, inst: dict, host: str, vps_inst: "dict | None" = None) -> bool:
    """True only for a minted grant naming this line + host whose hash equals this checkout's AND the VPS's policy."""
    if not isinstance(grant, OwnerHandGrant) or grant._key is not _MINT:
        return False
    if grant.line != inst.get("name") or grant.host != host or grant.policy_hash != policy_hash(inst):
        return False
    return vps_inst is None or policy_hash(vps_inst) == grant.policy_hash


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
        """Command lines of every ancestor process (nearest first); None when the chain cannot be read."""
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
        return out

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

    sh = None  # production uses waha_instance's own runner (no override)


def human_gate(io) -> "str | None":
    """None when an interactive human (not an agent harness) is at this terminal; else why not. Fail closed."""
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
    chain = io.parent_commands()
    if chain is None:
        return "the parent process chain cannot be read: refused (fail closed)"
    for cmd in chain:
        if _CLAUDE_CMD.search(cmd):
            return "a `claude` process is in the parent process chain: the owner runs this in his own terminal"
    return None


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _audit(root: Path, row: dict) -> dict:
    from ._ledger_store import append_rows
    try:
        return append_rows(LEDGER_NAME, root / LEDGER_REL, [row],
                           message=f"waha-owner-hand: {row['action']} {row['line']} {row['outcome']}")
    except Exception as exc:  # noqa: BLE001 - surfaced on the result, and the action is refused when it matters
        return {"ok": False, "status": "error", "error": f"{exc.__class__.__name__}: {exc}"}


def _audit_ok(res: dict) -> bool:
    return bool(res.get("ok")) or res.get("status") == "pending"  # pending = durably spooled, published next time


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
        f"  policy hash : {phash}\n\n"
    )


def _vps_compose_problems(name: str, host: str, sh) -> list[str]:
    """The VPS's rendered compose must label core AND edge personal and keep the core off noctus-net."""
    import yaml

    rc, text, err = sh(host, f"cat {wi.VPS_FLEET}/compose.waha.yml")
    if rc != 0:
        return [f"cannot read the VPS's compose.waha.yml ({err.strip()[-120:]})"]
    try:
        svcs = (yaml.safe_load(text) or {}).get("services") or {}
    except yaml.YAMLError as exc:
        return [f"the VPS's compose.waha.yml does not parse ({exc.__class__.__name__})"]
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
    return out


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

    `_test_io` is a TEST-ONLY injection point (terminal, env, parent chain, identity, remote runner). The CLI never
    passes it and it is not part of any tool schema; production code must never pass it."""
    io = _test_io or _RealIO()
    root = Path(repo_root) if repo_root else Path(wi.REPO_ROOT)
    who = {"git_email": io.git_email(), "os_user": io.os_user()}
    base = {"ts": _now(), "tool": "waha_owner_hand", "action": action, "line": name, "host": ssh_host, "who": who,
            "policy_hash": None}

    def refuse(why: str, **kw) -> dict:
        row = {**base, "outcome": "refused", "reason": why[:300]}
        aud = _audit(root, row)
        return {"ok": False, "action": action, "name": name, "status": "refused", "error": why, "audit": aud, **kw}

    if action not in ACTIONS:
        return refuse(f"unknown action {action!r} -- {'|'.join(ACTIONS)}")
    why = human_gate(io)
    if why:
        return refuse(why)
    try:
        spec = wi.load_spec(root)
        inst = wi._inst(spec, name)
    except ValueError as exc:
        return refuse(str(exc))
    phash = policy_hash(inst)
    base["policy_hash"] = phash
    bad = shadow_shape_problems(inst)
    if bad:
        return refuse("not a strict read-only personal line: " + "; ".join(bad))
    sh = io.sh or wi._sh
    vps_inst, vwhy = wi._vps_instance(name, ssh_host, sh)
    if vps_inst is None:
        return refuse(vwhy)
    if policy_hash(vps_inst) != phash:
        return refuse("the VPS's own waha-instances.yml declares a different policy for this line "
                      f"(VPS {policy_hash(vps_inst)[:12]} vs here {phash[:12]}): deploy_pull first, then re-run")
    bad = _vps_compose_problems(name, ssh_host, sh)
    if bad:
        return refuse("the VPS's rendered compose is not safe for a personal line: " + "; ".join(bad))

    try:
        tty = io.open_tty()
    except OSError as exc:
        return refuse(f"/dev/tty cannot be opened ({exc.__class__.__name__})")
    try:
        tty.write(_summary(inst, phash, ssh_host, action))
        typed = _ask(tty, "  Type the line name to continue: ")
        if typed != name:
            return refuse("the typed line name does not match: nothing was done")
        word = _ask(tty, f"  Type {CONFIRM_WORD} to {action} this personal line now: ")
        if word != CONFIRM_WORD:
            return refuse(f"{CONFIRM_WORD} was not typed: nothing was done")
    finally:
        tty.close()

    pre = _audit(root, {**base, "outcome": "confirmed"})
    if not _audit_ok(pre):
        return {"ok": False, "action": action, "name": name, "status": "refused", "audit": pre,
                "error": "the audit row could not be written: refused before touching the VPS (fail closed)"}
    grant = OwnerHandGrant(line=name, policy_hash=phash, host=ssh_host, _key=_MINT)
    kw = {"_test_sh": io.sh} if io.sh is not None else {}
    if action == "provision":
        res = wi._provision(spec, name, ssh_host, True, _owner_grant=grant, **kw)
    else:
        res = wi._apply(spec, name, ssh_host, True, _owner_grant=grant, **kw)
        if res.get("ok"):
            lab = _live_label_problems(name, ssh_host, sh)
            if lab:
                res = {**res, "ok": False, "status": "label_drift", "label_problems": lab}
    post = _audit(root, {**base, "ts": _now(), "outcome": str(res.get("status") or ("ok" if res.get("ok") else "error"))})
    return {**res, "owner_hand": True, "policy_hash": phash, "audit": {"confirmed": pre, "outcome": post}}


__all__ = ["owner_hand", "human_gate", "policy_hash", "grant_covers", "shadow_shape_problems", "OwnerHandGrant",
           "LEDGER_NAME", "COMMAND"]
