"""The OWNER-BY-HAND path for a `personal: true` WAHA line (owner decision D49, 2026-11-10). CLI ONLY.

Since 2026-11-12 (owner decision superseding D49, option (b)) an AGENT may also provision/apply a personal line through
`noctus.dev.waha_instance`: it runs the SAME `personal_line_checks` below, writes an `agent_started` audit row (who,
line, host, policy hash) to this module's ledger BEFORE touching the VPS, and an outcome row after; the owner's phone
scanning the QR stays the human consent step, and `remove` of a personal line stays refused for agents. This module
remains the alternative where the OWNER does the step himself, from a macOS Terminal.app window (Aplicativos ›
Utilitários), from the primary checkout:

    PATH=/usr/bin:/bin:/usr/sbin:/sbin:$PATH mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py \
        --waha-instance-owner-hand apply <line>       # core -> provision -> edge  (`provision`: session config only)

It is deliberately NOT an MCP tool: it has no `register()`, `tools/noctus/dev/__init__.py` never imports it, and a test
asserts its name is absent from the registered tool set. It runs exactly what `provision` / `apply` run for that ONE
line, with every other check unchanged (tighten-only vs the VPS checkout and the running session, policy read-back,
foreign webhooks dropped, edge-before-QR order), plus checks of its own: the line must be the strict shadow shape
(`send: disabled`, `mark_online: false`, `full_sync: false`, `edge_deny_writes: true`, `dashboard: false`,
`personal: true`); the policy hash the human confirms covers the policy fields AND the rendered core + edge compose
service blocks, and the VPS's own checkout (its `waha-instances.yml` and its `compose.waha.yml`) must give the
IDENTICAL hash; the VPS compose must stamp `noctus.line.personal=true` on core AND edge and keep the core off noctus-net.

Threat model (also in KB § CONTEXT/INTEGRATIONS/whatsapp.md § 6a). Under D49 the risk was a WELL-MEANING AGENT UNDER
PRESSURE reading "the owner does it by hand" as an obstacle. Since 2026-11-12 agents are no longer refused for
provision/apply (the owner chose it); what bounds them is the shared shape/hash/label checks + the audit row, and the
pairing itself still needs the owner's phone. This path's own gate (below) keeps its meaning only for THIS path: a grant
it mints proves a human at a real terminal window typed the confirmation, so:

* the parent process chain is read from the KERNEL, in-process (sysctl KERN_PROC + libproc: parent pid, start time,
  real executable image) -- never argv (a process sets its own: `exec -a`), never `ps` or any tool resolved through
  PATH; every process must have started at or after its parent (a reused pid refuses). STRUCTURALLY: only the system
  shells and `/usr/bin/login` (SHELL_IMAGES, by path) may sit between this process and the nearest other ancestor,
  which must be the pinned Terminal.app (EMULATORS -- data; Terminal ONLY: an IDE-hosted agent runs in the same signed
  pty host as the owner's IDE terminal): its image at the pinned path, the RUNNING pid satisfying `anchor apple and
  identifier "com.apple.Terminal"` (`/usr/bin/codesign --verify -R`), started by launchd as a LaunchServices-registered
  app (`/usr/bin/lsappinfo`). Anything unreadable refuses;
* no CLAUDECODE / CLAUDE_CODE_*, no PYTHONPATH / PYTHONSTARTUP / PYTHONHOME / PYTHONUSERBASE / PYTHONINSPECT / DYLD_*,
  and PATH starts with /usr/bin:/bin (git and ssh, which libraries resolve through PATH, are then the system ones);
  stdin AND stdout are TTYs and /dev/tty opens;
* no process other than this one and its own shell/login chain has our tty as its controlling terminal (a TIOCSTI typist
  or second reader), checked before every prompt, and the input queue is flushed (tcflush) before every prompt;
* the human TYPES the line name and CONFIRMO on /dev/tty (never stdin; no flag can pre-answer it);
* the `confirmed` audit row is written (or spooled AND read back, its id shown on the terminal) BEFORE anything touches
  the VPS; the grant `waha_instance` accepts is bound to line + policy hash + host + a secret nonce whose DIGEST is in
  that row, is honoured only while that row is < 5 minutes old, and is single-use (the outcome row consumes it).

A test IO runs the whole call in the TEST owner-hand scope: `_vps_ssh.run_remote` then refuses every command, so a
test-marked runner that forwards THROUGH it reaches nothing (one that spawns /usr/bin/ssh itself reaches the VPS -- no
capability beyond the plain ssh of the residuals below). Inside any owner-hand call ssh and git run by absolute system
path; outside it every other caller is unchanged.

No second factor, ever (owner decision). This client-side gate guards only the SANCTIONED path; it is not the control on
the personal line. Documented residuals (KB § 6a): (a) code running as this uid acts on the personal line with no grant
and NO audit row -- `_vps_ssh.run_remote("noctus-vps", "... docker compose -f compose.waha.yml up -d --no-deps
waha-<n>-core")` with an empty scope, patching `_owner_allows` then calling `_apply`, or plain `ssh noctus-vps` from any
shell; and a row minted through a patched gate cannot be told apart from the owner's. Only
NOC-REMEDIATE[personal-core-host-exec-authz] on the VPS closes this (an SSH forced command or a docker authz plugin
refusing `compose up/create/start` of `noctus.line.personal=true` services under the automation key); (b) a process that
DRIVES a real Terminal window (`open -a Terminal x.command`, AppleScript `do script`, accessibility keystrokes --
NOC-REMEDIATE[owner-hand-accessibility-injection]); (c) code planted into what the owner's command loads (venv
`site-packages/*.pth`, `sitecustomize`, `pyvenv.cfg` home, `~/.zshrc`) runs inside the genuine Terminal session before
any check and cannot be detected in-process; `~/.ssh/config` (ProxyCommand, Host remap) decides where ssh connects;
(d) VPS root/automation reading the session files until NOC-REMEDIATE[personal-core-host-exec-authz] is built.
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
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import waha_instance as wi

LEDGER_NAME = "waha-owner-hand.ndjson"
LEDGER_REL = Path("project-history") / LEDGER_NAME
ACTIONS = ("provision", "apply")
CONFIRM_WORD = "CONFIRMO"
COMMAND = ("PATH=/usr/bin:/bin:/usr/sbin:/sbin:$PATH mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py "
           "--waha-instance-owner-hand {action} {name}")
GRANT_TTL_S = 300
_HARNESS_ENV_EXACT = ("CLAUDECODE",)
_HARNESS_ENV_PREFIX = "CLAUDE_CODE_"
_MAX_HOPS = 64

#: The only images allowed between this process and its terminal emulator, by exact path (never a name, never argv).
SHELL_IMAGES: tuple[str, ...] = ("/bin/zsh", "/bin/bash", "/bin/sh", "/usr/bin/login")
#: The pinned terminal: macOS Terminal.app ONLY (tech-lead decision 2026-11-10, surfaced to the owner). IDE terminals were
#: removed: an agent hosted in the IDE (its `sendText`, a `tasks.json` task) runs in the SAME signed pty-host helper as the
#: owner's integrated terminal, so no image or signature check can tell them apart. The owner may ask to re-add his IDE
#: as an ACCEPTED risk (a row here with its pinned helper + app requirement; the gate already supports `app`).
#: `entry_images` = the process that is the shell's parent chain head (Terminal runs `/usr/bin/login`, then the shell);
#: its RUNNING pid must satisfy `entry_requirement`; `app: None` = the entry IS the app, which must be launchd's child and
#: LaunchServices-registered as `bundle_id`.
EMULATORS: tuple[dict, ...] = (
    {"label": "macOS Terminal", "bundle_id": "com.apple.Terminal",
     "entry_images": ("/System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal",),
     "entry_requirement": 'anchor apple and identifier "com.apple.Terminal"', "app": None},
)
OPEN_TERMINAL = "Abra o Terminal.app (Aplicativos › Utilitários) e rode o comando lá."
#: Variables that make the interpreter (or the loader) run code the owner did not type.
_INJECTION_ENV = ("PYTHONPATH", "PYTHONSTARTUP", "PYTHONHOME", "PYTHONUSERBASE", "PYTHONINSPECT",
                  # /usr/bin/git is the xcrun shim: these pick which toolchain (and so which git) it runs
                  "DEVELOPER_DIR", "SDKROOT", "TOOLCHAINS")
#: Any GIT_* (GIT_DIR, GIT_SSH_COMMAND, GIT_CONFIG_*, GIT_EXEC_PATH...) can redirect where the audit row is written.
_INJECTION_ENV_PREFIXES = ("DYLD_", "GIT_")
#: PATH must START with this: a tool any library resolves through PATH (git for the ledger, ssh) is then the system one.
_SAFE_PATH_PREFIX = "/usr/bin:/bin"
#: A test IO may target only this host (RFC 2606 `.invalid`: it can never resolve), so the seam cannot reach the VPS.
TEST_HOST = "noc-test.invalid"

# NOC-REMEDIATE[owner-hand-accessibility-injection]: a process that DRIVES a real, pinned Terminal window passes the
# chain check by design of what it can see: (1) a LaunchServices launch (`open -a Terminal x.command`, no TCC prompt) of
# a script that runs this command; (2) AppleScript `do script` / System Events `keystroke`, CGEventPost, accessibility
# APIs typing the answers -- these need an Automation or Accessibility TCC grant ALREADY held by the agent's host app
# (both prompt the owner the first time); (3) TIOCSTI from a process holding our tty. Built here: input is flushed
# (tcflush TCIFLUSH) before every prompt, and any process other than this one and its own shell/login chain that has our
# tty as its controlling terminal refuses (sysctl KERN_PROC_TTY). Still open: (1) and (2). Cheap next check: refuse
# while any app other than Terminal holds Accessibility or Automation rights, and when Terminal's launch came from a
# `.command` document. Design constraint: reading TCC.db needs Full Disk Access for the process doing it; without it a
# fail-closed check would refuse EVERY run, so the design must either ask the owner to grant FDA to Terminal or treat
# "unreadable" as a warning with that decision named. (A `sitecustomize` refusal was considered and NOT built: this
# venv's interpreter loads one on every start, so it would refuse every run while catching only accidents.)
# Not a blocker for D49 (the owner accepted the host residual) — 2026-11-10

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
    test: bool = False  # minted under a test IO: only ever honoured for TEST_HOST, a temp ledger and the fake store
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
    if _store_problem(grant.test, grant.host, grant.ledger_root):
        return False  # a production grant needs the real store; a test grant, the test host + temp ledger + fake store
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


_BUNDLE_RX = re.compile(r'bundleID="([^"]+)"')
_LIBPROC = "/usr/lib/libproc.dylib"
_LIBC = "/usr/lib/libc.dylib"
_CODESIGN = "/usr/bin/codesign"
_LSAPPINFO = "/usr/bin/lsappinfo"
_GIT = "/usr/bin/git"
_NODEV = 0xFFFFFFFF
# struct kinfo_proc (sysctl KERN_PROC), arm64/x86_64 darwin: p_starttime {tv_sec int64 @0, tv_usec int32 @8}, p_pid @40,
# kp_eproc.e_ppid @560, e_tdev @572; size 648. Self-checked against proc_pidinfo(PROC_PIDT_SHORTBSDINFO) on every read: a
# layout mismatch reads as "unreadable" (refuse), never as a wrong answer.
_KP_SIZE, _KP_START, _KP_USEC, _KP_PID, _KP_PPID, _KP_TDEV = 648, 0, 8, 40, 560, 572
_CTL_KERN, _KERN_PROC, _KERN_PROC_PID, _KERN_PROC_TTY = 1, 14, 1, 4
_PROC_PIDT_SHORTBSDINFO, _SHORTBSD_SIZE = 13, 64


def _sysctl_procs(mib: tuple) -> "bytes | None":
    import ctypes

    try:
        libc = ctypes.CDLL(_LIBC, use_errno=True)
    except OSError:
        return None
    arr = (ctypes.c_int * len(mib))(*mib)
    size = ctypes.c_size_t(0)
    if libc.sysctl(arr, len(mib), None, ctypes.byref(size), None, ctypes.c_size_t(0)) != 0:
        return None
    buf = ctypes.create_string_buffer(size.value + 16 * _KP_SIZE)
    size = ctypes.c_size_t(len(buf))
    if libc.sysctl(arr, len(mib), buf, ctypes.byref(size), None, ctypes.c_size_t(0)) != 0:
        return None
    return buf.raw[:size.value]


def _short_ppid(pid: int) -> "int | None":
    """The kernel's parent pid (libproc PROC_PIDT_SHORTBSDINFO: readable for every pid, root-owned ones included)."""
    import ctypes
    import struct

    try:
        lib = ctypes.CDLL(_LIBPROC, use_errno=True)
    except OSError:
        return None
    buf = ctypes.create_string_buffer(_SHORTBSD_SIZE)
    n = lib.proc_pidinfo(ctypes.c_int(pid), ctypes.c_int(_PROC_PIDT_SHORTBSDINFO), ctypes.c_uint64(0), buf,
                         ctypes.c_int(_SHORTBSD_SIZE))
    if n != _SHORTBSD_SIZE or struct.unpack_from("<I", buf.raw, 0)[0] != pid:
        return None
    return struct.unpack_from("<I", buf.raw, 4)[0]


def _proc(pid: int) -> "tuple[int, float, int] | None":
    """(ppid, start time, controlling tty dev) from the kernel, in-process (no `ps`, nothing resolved through PATH)."""
    import struct

    raw = _sysctl_procs((_CTL_KERN, _KERN_PROC, _KERN_PROC_PID, pid))
    if not raw or len(raw) < _KP_SIZE or struct.unpack_from("<i", raw, _KP_PID)[0] != pid:
        return None
    ppid = struct.unpack_from("<i", raw, _KP_PPID)[0]
    if _short_ppid(pid) != ppid:  # layout self-check (and a second, independent kernel read)
        return None
    start = struct.unpack_from("<q", raw, _KP_START)[0] + struct.unpack_from("<i", raw, _KP_USEC)[0] / 1e6
    return ppid, start, struct.unpack_from("<I", raw, _KP_TDEV)[0]


def _tty_pids(tdev: int) -> "list[int] | None":
    """Every pid whose CONTROLLING terminal is `tdev` (sysctl KERN_PROC_TTY), whoever owns it."""
    import struct

    raw = _sysctl_procs((_CTL_KERN, _KERN_PROC, _KERN_PROC_TTY, tdev))
    if raw is None or len(raw) % _KP_SIZE:
        return None
    return [struct.unpack_from("<i", raw, i + _KP_PID)[0] for i in range(0, len(raw), _KP_SIZE)]


def _proc_image(pid: int) -> "str | None":
    """The kernel's record of a process's executable path (libproc proc_pidpath); None when unreadable."""
    import ctypes

    try:
        lib = ctypes.CDLL(_LIBPROC, use_errno=True)
    except OSError:
        return None
    buf = ctypes.create_string_buffer(4096)  # PROC_PIDPATHINFO_MAXSIZE
    n = lib.proc_pidpath(ctypes.c_int(pid), buf, ctypes.c_uint32(4096))
    if n <= 0:
        return None
    try:
        return os.path.normpath(buf.value.decode("utf-8"))
    except UnicodeDecodeError:
        return None


class _RealIO:
    """The process's real terminal, environment, parent chain, identity and remote runner."""

    def platform(self) -> str:
        return sys.platform

    def env(self) -> dict:
        return dict(os.environ)

    def isatty(self, fd: int) -> bool:
        return os.isatty(fd)

    def open_tty(self):
        """/dev/tty as an unbuffered read+write text stream (a text `r+` open is refused on a pty: not seekable)."""
        import io as _io

        raw = open("/dev/tty", "r+b", buffering=0)  # noqa: SIM115 - closed by the caller through the wrapper
        return _io.TextIOWrapper(raw, encoding="utf-8", write_through=True, line_buffering=True)

    def self_proc(self) -> "tuple[int, float, int] | None":
        """(this pid, its start time, its controlling tty dev)."""
        me = _proc(os.getpid())
        return None if me is None else (os.getpid(), me[1], me[2])

    def ancestors(self) -> "list[tuple[int, str | None, float]] | None":
        """(pid, REAL executable image, start time) of every ancestor up to (not incl.) launchd, nearest first. Parent pid,
        start time and image all come from the kernel, in-process; each hop is read twice around the image read, so a
        pid that exits and is reused mid-walk reads as unreadable. None when the chain cannot be read or does not reach
        pid 1 within _MAX_HOPS."""
        out, pid = [], os.getppid()
        for _ in range(_MAX_HOPS):
            if pid <= 1:
                return out
            before = _proc(pid)
            image = _proc_image(pid)
            after = _proc(pid)
            if before is None or after is None or before[:2] != after[:2]:
                return None
            out.append((pid, image, before[1]))
            pid = before[0]
        return None

    def tty_pids(self, tdev: int) -> "list[int] | None":
        return _tty_pids(tdev)

    def signature_ok(self, pid: int, requirement: str) -> bool:
        """The RUNNING process satisfies the code-signing requirement (dynamic validity, not the file on disk)."""
        try:
            r = subprocess.run([_CODESIGN, "--verify", f"-R={requirement}", str(pid)],
                               capture_output=True, text=True, timeout=15, check=False)
        except (OSError, subprocess.SubprocessError):
            return False
        return r.returncode == 0

    def app_bundle(self, pid: int) -> "str | None":
        """The LaunchServices bundle id of the application with this pid; None when it is not a registered app."""
        try:
            asn = subprocess.run([_LSAPPINFO, "find", f"pid={pid}"], capture_output=True, text=True, timeout=5,
                                 check=False).stdout.strip()
            if not asn:
                return None
            info = subprocess.run([_LSAPPINFO, "info", "-only", "bundleid", asn], capture_output=True, text=True,
                                  timeout=5, check=False).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        m = _BUNDLE_RX.search(info)
        return m.group(1) if m else None

    def git_email(self) -> str:
        try:
            r = subprocess.run([_GIT, "config", "user.email"], capture_output=True, text=True, timeout=5, check=False)
            return r.stdout.strip() or "unknown"
        except (OSError, subprocess.SubprocessError):
            return "unknown"

    def os_user(self) -> str:
        try:
            return getpass.getuser()
        except (OSError, KeyError):
            return "unknown"

    sh = None  # production: waha_instance's own runner, never overridable from here


def _emulator_for(image: str) -> "dict | None":
    for e in EMULATORS:
        if image in e["entry_images"]:
            return e
    return None


def _refused(why: str) -> str:
    return f"{why}. {OPEN_TERMINAL}"


def chain_problem(io) -> "str | None":
    """None when the nearest non-shell ancestor is the pinned, correctly signed Terminal.app started by launchd as a
    registered app, with only system shells / login in between, every process started after its parent; else why not.
    Judged on real images from the kernel, never argv, never a PATH-resolved tool."""
    me, chain = io.self_proc(), io.ancestors()
    if chain is None or me is None:
        return _refused("the parent process chain cannot be read up to launchd: refused (fail closed)")
    starts = [me[1]] + [c[2] for c in chain]
    if any(starts[k] < starts[k + 1] for k in range(len(starts) - 1)):
        return _refused("a process in the parent chain started before its parent (a reused pid): refused")
    i = 0
    while i < len(chain) and chain[i][1] in SHELL_IMAGES:
        i += 1
    if i == len(chain):
        return _refused("no terminal emulator above the shell (reached launchd)")
    pid, image, _ = chain[i]
    if not image:
        return _refused(f"the executable image of ancestor pid {pid} cannot be read: refused (fail closed)")
    emu = _emulator_for(image)
    if emu is None:
        return _refused(f"the shell's parent is `{image}`, not the pinned Terminal.app (no IDE terminal, pty wrapper, "
                        "multiplexer, interpreter or agent)")
    if not io.signature_ok(pid, emu["entry_requirement"]):
        return _refused(f"{emu['label']} (pid {pid}) does not satisfy its pinned code-signing requirement")
    if emu["app"] is not None:
        if i + 1 >= len(chain):
            return _refused(f"{emu['label']}'s terminal host has no app above it")
        i += 1
        pid, image, _ = chain[i]
        if image not in emu["app"]["images"]:
            return _refused(f"{emu['label']}'s terminal host was not started by the {emu['label']} app (`{image}`)")
        if not io.signature_ok(pid, emu["app"]["requirement"]):
            return _refused(f"the {emu['label']} app (pid {pid}) does not satisfy its pinned code-signing requirement")
    if i != len(chain) - 1:
        return _refused(f"{emu['label']} (pid {pid}) was not started by launchd (something launched it)")
    if io.app_bundle(pid) != emu["bundle_id"]:
        return _refused(f"{emu['label']} (pid {pid}) is not a registered {emu['bundle_id']} application")
    return None


def tty_problem(io) -> "str | None":
    """None when nothing but this process and its own shell/login chain has our terminal as ITS controlling terminal
    (what a TIOCSTI typist or a second reader of the line would need); else why not. Fail closed."""
    me, chain = io.self_proc(), io.ancestors()
    if me is None or chain is None:
        return _refused("this process's terminal or parent chain cannot be read")
    if me[2] in (_NODEV, 0):
        return _refused("this process has no controlling terminal")
    holders = io.tty_pids(me[2])
    if holders is None or me[0] not in holders:
        return _refused("the processes on this terminal cannot be listed: refused (fail closed)")
    allowed = {me[0]} | {pid for pid, image, _ in chain if image in SHELL_IMAGES}
    extra = sorted(set(holders) - allowed)
    if extra:
        return _refused(f"other processes share this terminal (pids {', '.join(map(str, extra[:8]))}): close them, or "
                        "use a fresh Terminal window")
    return None


def human_gate(io) -> "str | None":
    """None when an interactive human (not an agent harness) is at a real Terminal.app window; else why not. Fail closed."""
    if io.platform() != "darwin":
        # the chain/tty checks read the macOS kernel (sysctl KERN_PROC, libproc, codesign): elsewhere they cannot run
        return _refused(f"this command runs only on the owner's Mac (platform is {io.platform()!r}, not 'darwin')")
    env = io.env()
    hits = sorted(k for k in env if k in _HARNESS_ENV_EXACT or k.startswith(_HARNESS_ENV_PREFIX))
    if hits:
        return _refused(f"running inside an agent harness (env {', '.join(hits)} present)")
    inject = sorted(k for k in env if k in _INJECTION_ENV or k.startswith(_INJECTION_ENV_PREFIXES))
    if inject:
        return _refused(f"code-injection variables are set ({', '.join(inject)}): unset them")
    path = env.get("PATH", "")
    if not (path == _SAFE_PATH_PREFIX or path.startswith(_SAFE_PATH_PREFIX + ":")):
        return _refused(f"PATH must start with {_SAFE_PATH_PREFIX} (nothing ahead of the system tools); run: "
                        + COMMAND.format(action="<apply|provision>", name="<line>"))
    if not (io.isatty(0) and io.isatty(1)):
        return _refused("stdin and stdout must both be a terminal (no pipes, no redirection)")
    try:
        io.open_tty().close()
    except OSError as exc:
        return _refused(f"/dev/tty cannot be opened ({exc.__class__.__name__}): no controlling terminal")
    return chain_problem(io) or tty_problem(io)


def _under_temp(root: "str | Path | None") -> bool:
    import tempfile

    if not root:
        return False
    try:
        r, t = Path(root).resolve(), Path(tempfile.gettempdir()).resolve()
    except OSError:
        return False
    return r == t or t in r.parents


def _store_problem(test: bool, host: str, root: "str | Path | None") -> "str | None":
    """Production: the audit ledger is the real store. Test: the fake store, a ledger root under the temp dir and the
    reserved TEST_HOST -- so neither a test seam nor a test grant can ever audit to, or act on, anything real."""
    from ._ledger_store import MODE_FAKE, MODE_GIT, store_mode

    try:
        mode = store_mode()
    except ValueError as exc:
        return str(exc)
    if not test:
        if mode != MODE_GIT:
            return "the audit ledger must be the real store (origin/ledgers); NOCTUS_LEDGER_STORE=fake is test-only"
        return None
    if mode != MODE_FAKE:
        return "a test IO needs the fake ledger store (NOCTUS_LEDGER_STORE=fake): refused"
    if host != TEST_HOST:
        return f"a test IO may only target the reserved host {TEST_HOST}, not {host!r}: refused"
    if not _under_temp(root):
        return "a test IO needs its ledger root under the temp dir: refused"
    return None


def _test_runner_problem(io, host: str, root: "str | Path | None") -> "str | None":
    """A test IO must carry its OWN runner, explicitly marked as a test fake -- never the real one -- only inside a
    pytest test, on the fake store, a temp ledger root and TEST_HOST. This keeps the test seam from being a gate bypass
    that still reaches the VPS or the real ledger."""
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return "a test IO was passed outside a pytest test: refused (the CLI never passes one)"
    sh = getattr(io, "sh", None)
    if sh is None or sh is wi._sh or getattr(sh, "__noc_test_fake__", False) is not True:
        return ("a test IO must carry its own runner explicitly marked as a test fake (`__noc_test_fake__ = True`); "
                "the real remote runner is never reachable through it")
    return _store_problem(True, host, root)


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


def _audit_notice(row_id: str, res: dict) -> str:
    """What the owner sees about the `confirmed` row: its id, and whether it is published or only spooled."""
    state = ("spooled (not yet published to origin/ledgers; the next ledger publish carries it)"
             if res.get("status") == "pending" else "written")
    return f"\n  audit row {row_id} {state}\n\n"


def _ask(tty, prompt: str) -> str:
    """Prompt on the tty and read one typed line. Anything already in the input queue (pre-typed, injected) is discarded
    first: only what is typed AFTER the prompt is shown counts."""
    import termios

    fileno = getattr(tty, "fileno", None)
    if fileno is not None:
        termios.tcflush(fileno(), termios.TCIFLUSH)
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


def personal_line_checks(spec: dict, inst: dict, name: str, host: str, sh) -> dict:
    """The checks EVERY personal-line provision/apply runs, whoever the caller (owner-hand or agent): the strict shadow
    shape; the VPS's own waha-instances.yml declaring the identical policy; its compose.waha.yml labelling core AND edge
    `noctus.line.personal=true` with the core off noctus-net; and its core + edge compose blocks hashing identical to
    this checkout's render. Returns {problem: str | None, fields, policy_hash (fields + compose, once known)}."""
    import yaml

    fields = policy_hash(inst)
    out: dict = {"problem": None, "fields": fields, "policy_hash": None}
    bad = shadow_shape_problems(inst)
    if bad:
        out["problem"] = "not a strict read-only personal line: " + "; ".join(bad)
        return out
    vps_inst, vwhy = wi._vps_instance(name, host, sh)
    if vps_inst is None:
        out["problem"] = vwhy
        return out
    if policy_hash(vps_inst) != fields:
        out["problem"] = ("the VPS's own waha-instances.yml declares a different policy for this line "
                          f"(VPS {policy_hash(vps_inst)[:12]} vs here {fields[:12]}): deploy_pull first, then re-run")
        return out
    vps_svcs, bad = _vps_compose(name, host, sh)
    if bad:
        out["problem"] = "the VPS's rendered compose is not safe for a personal line: " + "; ".join(bad)
        return out
    local_fp = compose_fingerprint((yaml.safe_load(wi.render_compose(spec)) or {}).get("services") or {}, name)
    vps_fp = compose_fingerprint(vps_svcs, name)
    phash, vhash = policy_hash(inst, local_fp), policy_hash(vps_inst, vps_fp)
    out["policy_hash"] = phash
    if phash != vhash:
        drift = sorted(s for s in local_fp if local_fp[s] != vps_fp.get(s))
        out["problem"] = (f"the VPS's compose.waha.yml differs from this checkout's render for {', '.join(drift)} "
                          f"(VPS {vhash[:12]} vs here {phash[:12]}): render, merge and deploy_pull first, then re-run")
    return out


# --- the AGENT path (D49 superseded 2026-11-12, owner decision; option (b)) ---------------------------------------------
#: An agent/tool caller of `noctus.dev.waha_instance` may provision/apply a personal line. It runs the SAME
#: `personal_line_checks` as the owner-hand path and writes an audit row (who, line, host, policy hash) to the same ledger
#: BEFORE anything touches the VPS (not durable => refused, fail closed), plus an outcome row after. Pairing stays human:
#: nothing here scans a QR or connects Google; the owner's phone scanning the QR is the consent step. `remove` of a
#: personal line stays refused for agents.
AGENT_STARTED = "agent_started"


def agent_store_problem(host: str, root: "str | Path", sh) -> "str | None":
    """Production: the audit ledger is the real store. Fake store: only inside pytest, with a runner explicitly marked as
    a test fake, the reserved TEST_HOST and a temp ledger root -- an agent run on the fake store reaches nothing real."""
    from ._ledger_store import MODE_FAKE, store_mode

    try:
        mode = store_mode()
    except ValueError as exc:
        return str(exc)
    if mode != MODE_FAKE:
        return _store_problem(False, host, root)
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return "the fake ledger store (NOCTUS_LEDGER_STORE=fake) is test-only: an agent personal-line run is refused"
    if sh is None or sh is wi._sh or getattr(sh, "__noc_test_fake__", False) is not True:
        return ("on the fake ledger store an agent personal-line run needs a runner explicitly marked as a test fake "
                "(`__noc_test_fake__ = True`): the real remote runner is never reachable from a test")
    return _store_problem(True, host, root)


def agent_who() -> dict:
    io = _RealIO()
    return {"git_email": io.git_email(), "os_user": io.os_user(),
            "session": os.environ.get("CLAUDE_CODE_SESSION_ID") or "unknown"}


def agent_audit(root: "str | Path", action: str, name: str, host: str, phash: "str | None", outcome: str,
                run_id: str) -> "tuple[dict, str | None]":
    """Append one agent row; returns (result, why-not-durable | None)."""
    row_id = _new_id()
    row = {"ts": _now(), "id": row_id, "tool": "waha_instance", "caller": "agent", "run_id": run_id, "action": action,
           "line": name, "host": host, "who": agent_who(), "policy_hash": phash, "outcome": outcome}
    res = _audit(Path(root), row)
    return res, _audit_durable(Path(root), res, row_id)


def owner_hand(action: str, name: str, ssh_host: str = "noctus-vps", repo_root: "str | None" = None, *,
               _test_io=None) -> dict:
    """Run provision/apply for ONE personal line, only for an interactive human who typed the confirmation. Under a test
    IO the whole call runs in waha_instance's TEST owner-hand scope: its real remote runner refuses every command, so no
    wrapper a test IO carries can ever reach a real host."""
    token = wi._OWNER_HAND_SCOPE.set(wi.OWNER_HAND_TEST_SCOPE if _test_io is not None else wi.OWNER_HAND_LIVE_SCOPE)
    try:
        return _owner_hand(action, name, ssh_host, repo_root, _test_io=_test_io)
    finally:
        wi._OWNER_HAND_SCOPE.reset(token)


def _owner_hand(action: str, name: str, ssh_host: str, repo_root: "str | None", *, _test_io=None) -> dict:
    """Run provision/apply for ONE personal line, only for an interactive human who typed the confirmation.

    `_test_io` is a TEST-ONLY injection point (terminal, env, parent chain, identity, remote runner). It is refused
    outside a pytest test and unless it carries its own explicitly test-marked fake runner (never the real one). The CLI
    never passes it and it is not part of any tool schema; production code must never pass it."""
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
    why = (_test_runner_problem(_test_io, ssh_host, root) if _test_io is not None
           else _store_problem(False, ssh_host, root))
    if why:
        return refuse(why)
    why = human_gate(io)
    if why:
        return refuse(why)
    try:
        spec = wi.load_spec(root)
        inst = wi._inst(spec, name)
    except ValueError as exc:
        return refuse(str(exc))
    fields = policy_hash(inst)
    sh = io.sh if _test_io is not None else wi._sh
    chk = personal_line_checks(spec, inst, name, ssh_host, sh)
    base["policy_hash"] = chk["policy_hash"] or fields
    if chk["problem"]:
        return refuse(chk["problem"])
    phash = chk["policy_hash"]

    try:
        tty = io.open_tty()
    except OSError as exc:
        return refuse(f"/dev/tty cannot be opened ({exc.__class__.__name__})")
    nonce = secrets.token_hex(32)
    row_id = _new_id()
    try:
        tty.write(_summary(inst, phash, ssh_host, action))
        why = tty_problem(io)
        if why:
            return refuse(why)
        typed = _ask(tty, "  Type the line name to continue: ")
        if typed != name:
            return refuse("the typed line name does not match: nothing was done")
        why = tty_problem(io)
        if why:
            return refuse(why)
        word = _ask(tty, f"  Type {CONFIRM_WORD} to {action} this personal line now: ")
        if word != CONFIRM_WORD:
            return refuse(f"{CONFIRM_WORD} was not typed: nothing was done")
        pre = _audit(root, {**base, "id": row_id, "ts": _now(), "outcome": "confirmed", "grant_digest": _digest(nonce)})
        why = _audit_durable(root, pre, row_id)
        if why:
            tty.write(f"\n  REFUSED: {why}\n")
            return {"ok": False, "action": action, "name": name, "status": "refused", "audit": pre,
                    "error": why + ": refused before touching the VPS (fail closed)"}
        tty.write(_audit_notice(row_id, pre))
    finally:
        tty.close()

    # the minter re-checks the seam and the store: never a grant over the real runner, a real host or a swapped store
    why = (_test_runner_problem(_test_io, ssh_host, root) if _test_io is not None
           else _store_problem(False, ssh_host, root))
    if why:
        return refuse("refused at mint: " + why)
    grant = OwnerHandGrant(line=name, policy_hash=phash, host=ssh_host, nonce=nonce, ledger_root=str(root),
                           fields_hash=fields, test=_test_io is not None, _key=_MINT)
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
           "shadow_shape_problems", "OwnerHandGrant", "EMULATORS", "SHELL_IMAGES", "TEST_HOST", "LEDGER_NAME",
           "COMMAND"]
