"""noctus.vps.exec — bounded diagnostic command exec on the VPS (host or in a container).

Closes the recurring "I can't see prod from here" gap (2026-07-08 sw.js debug):
- read a DEPLOYED container's files (`grep _is_service_worker /app/.../app.py`),
- curl the ORIGIN directly on VPS localhost, BYPASSING CloudFlare (settle
  origin-vs-edge header questions the tunnel otherwise hides),
- inspect an image's contents without a local Docker.

**Separate module from `vps.py` BY DESIGN.** `vps.py` bans `docker exec` /
arbitrary exec via `_BANNED_TOKENS` (a colocated test enforces it) — the
operate-layer stays exec-free. This module OWNS exec, with its own safety model:

  1. **HARD-DENY** — a destructive-token blocklist that ALWAYS refuses, even with
     `confirm=True` (rm -rf, mkfs, dd, shutdown, docker rm/rmi/kill/prune, …).
  2. **READ-ALLOWLIST** — when the command's leading binary is inherently
     read-only (cat/grep/ls/curl/…), it runs WITHOUT confirm.
  3. **CONFIRM-GATE** — anything else needs `confirm=True` (a production write).

All I/O routes through the throttled + circuit-broken SSH chokepoint
(`_vps_ssh.run_remote`) — same as every VPS tool — so it can't burst-connect the
edge into a fail2ban ban. IO is injectable (`run_remote`) for zero-SSH tests.
"""
from __future__ import annotations

import shlex
from typing import Any, Callable

from ._vps_ssh import run_remote as _throttled_ssh

DEFAULT_HOST = "noctus-vps"
_MAX_OUT = 20000  # cap each stream so a runaway `cat` can't flood the context

# Leading binaries that are inherently READ-ONLY → run without confirm.
_READ_BINARIES = frozenset({
    "cat", "grep", "egrep", "fgrep", "rg", "ls", "head", "tail", "wc", "stat",
    "find", "env", "printenv", "echo", "test", "file", "du", "df", "uname",
    "hostname", "date", "whoami", "pwd", "which", "readlink", "sort", "uniq",
    "cut", "tr", "jq", "xxd", "base64", "sed", "awk", "curl", "wget", "id",
    "getent", "dirname", "basename", "realpath", "md5sum", "sha256sum",
})
# `docker <sub>` is read-only only for these subcommands.
_DOCKER_READ_SUBCMDS = frozenset({
    "ps", "inspect", "images", "logs", "version", "info", "top", "port",
    "stats", "df", "history",
})

# Substrings that ALWAYS refuse — even with confirm=True. Destructive/irreversible
# or fleet-tearing. Matched against the raw command (lowercased).
_HARD_DENY = (
    "rm -rf", "rm -r ", "rm -fr", " rm /", "rm /", "mkfs", "dd if=", "dd of=",
    "> /dev/", "of=/dev/", "shutdown", "reboot", "halt", "poweroff", "init 0",
    "init 6", ":(){", "wipefs", "fdisk", "parted", "mv /", "truncate -s 0 /",
    "chmod -r 000", "chown -r", "docker rm", "docker rmi", "docker kill",
    "docker stop", "docker system prune", "docker volume rm", "docker network rm",
    "docker compose down", "docker-compose down", "crontab", "iptables -f",
    "ufw disable", "userdel", "passwd ", "> /etc/", ">/etc/",
)


def _err(msg: str, **extra) -> dict[str, Any]:
    return {"ok": False, "status": "error", "exit_code": 1, "error": msg, **extra}


def _runner(run_remote, ssh_host):
    return run_remote or (lambda cmd: _throttled_ssh(ssh_host, cmd))


def _leading_binary(command: str) -> str:
    """First real binary token, skipping `VAR=val` env prefixes."""
    try:
        toks = shlex.split(command)
    except ValueError:
        toks = command.split()
    for tok in toks:
        if "=" in tok and not tok.startswith("-") and tok.split("=", 1)[0].isidentifier():
            continue  # env-var assignment prefix (FOO=bar cmd)
        return tok
    return ""


def _is_read_only(command: str) -> bool:
    """True when the command's leading binary is inherently read-only."""
    bin_ = _leading_binary(command)
    if bin_ == "docker":
        try:
            toks = shlex.split(command)
        except ValueError:
            toks = command.split()
        # docker [global flags] <subcmd>; find the first non-flag after 'docker'
        after = [t for t in toks[1:] if not t.startswith("-")]
        sub = after[0] if after else ""
        if sub == "system":
            return len(after) > 1 and after[1] == "df"
        return sub in _DOCKER_READ_SUBCMDS
    return bin_ in _READ_BINARIES


def _hard_denied(command: str) -> str | None:
    low = command.lower()
    for tok in _HARD_DENY:
        if tok in low:
            return tok
    return None


def exec_cmd(
    command: str,
    container: str | None = None,
    confirm: bool = False,
    ssh_host: str = DEFAULT_HOST,
    run_remote: Callable | None = None,
) -> dict[str, Any]:
    """Run ``command`` on the VPS host, or inside ``container`` (docker exec).

    Read-only commands run freely; a destructive-token blocklist always refuses;
    everything else needs ``confirm=True``. Returns
    ``{ok,status,exit_code,stdout,stderr,command,container}``.
    """
    if not command or not command.strip():
        return _err("command required")

    denied = _hard_denied(command)
    if denied is not None:
        return {
            "ok": False, "status": "refused", "exit_code": 1,
            "error": (f"command contains a hard-denied token {denied!r} — this "
                      "tool refuses destructive/fleet-tearing ops even with "
                      "confirm=True. Use the dedicated tool (deploy_image / "
                      "vps.recreate / vps.prune) or run it by hand."),
        }

    read_only = _is_read_only(command)
    if not read_only and not confirm:
        return {
            "ok": False, "status": "needs_confirm", "exit_code": 1,
            "message": (f"'{_leading_binary(command)}' is not on the read-only "
                        "allowlist — this may mutate the VPS/container. Pass "
                        "confirm=True to proceed."),
        }

    inner = command
    if container:
        # Run inside the container. `sh -lc` so pipes/globs/redirection work.
        remote = f"docker exec {shlex.quote(container)} sh -lc {shlex.quote(inner)}"
    else:
        remote = f"sh -lc {shlex.quote(inner)}"

    run = _runner(run_remote, ssh_host)
    rc, out, err = run(remote)
    return {
        "ok": rc == 0,
        "status": "ok" if rc == 0 else "nonzero_exit",
        "exit_code": rc,
        "stdout": (out or "")[:_MAX_OUT],
        "stderr": (err or "")[:_MAX_OUT],
        "command": command,
        "container": container,
        "read_only": read_only,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.vps.exec",
        description=(
            "Run a BOUNDED diagnostic command on the VPS host, or inside a "
            "container (container=<name> → docker exec). Read-only commands "
            "(cat/grep/ls/curl/stat/find/docker inspect|ps|logs|images/…) run "
            "freely; a destructive blocklist (rm -rf/mkfs/dd/docker rm|rmi|kill|"
            "down|prune/shutdown/…) ALWAYS refuses; anything else needs "
            "confirm=True. Use it to read deployed container files, curl the "
            "ORIGIN on VPS localhost (bypassing CloudFlare), or inspect an image. "
            "Routes through the throttled+circuit-broken SSH."
        ),
    )
    def _exec(command: str, container: str | None = None, confirm: bool = False,
              ssh_host: str = DEFAULT_HOST) -> dict:
        return exec_cmd(command, container=container, confirm=confirm, ssh_host=ssh_host)


__all__ = ["exec_cmd", "register", "_HARD_DENY", "_READ_BINARIES", "_is_read_only",
           "_hard_denied"]
