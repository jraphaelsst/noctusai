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

import re
import shlex
from typing import Any, Callable

from ._vps_ssh import run_remote as _throttled_ssh

DEFAULT_HOST = "noctus-vps"
_MAX_OUT = 20000  # cap each stream so a runaway `cat` can't flood the context

# Binaries that may run WITHOUT confirm, each with an ARGV-level flag allowlist (`_ARGV_POLICY` below): a binary is
# not "read-only" -- a binary invoked with these exact flags is. `env`, `find`, `awk`, `sed`, `xargs` are NOT here: they
# can launch other programs (`env sh`, `find -exec`, `awk system()`, `sed e`), so they need confirm like any write.
_READ_BINARIES = frozenset({
    "cat", "grep", "egrep", "fgrep", "rg", "ls", "head", "tail", "wc", "stat", "echo", "test", "file", "du", "df",
    "uname", "hostname", "date", "whoami", "pwd", "which", "readlink", "sort", "uniq", "cut", "tr", "jq", "xxd",
    "base64", "curl", "wget", "id", "getent", "dirname", "basename", "realpath", "md5sum", "sha256sum", "printenv",
})

#: per-binary allowed flags. short = single-letter flags (clusters like `-sS` are checked char by char), val_short = short
#: flags that TAKE a value, long = bare long flags, val_long = long flags that take a value. Anything else -> confirm.
_ARGV_POLICY: dict[str, dict[str, Any]] = {
    "cat": {"short": "nbsAETv"},
    "head": {"short": "qv", "val_short": "nc"}, "tail": {"short": "qv", "val_short": "nc"},
    "wc": {"short": "lwcmL"}, "stat": {"short": "L", "val_short": "c", "long": {"--dereference"}, "val_long": {"--format"}},
    "ls": {"short": "lahtrRdSAFi1sc", "long": {"--all", "--human-readable"}},
    "grep": {"short": "cilLnrRwxvsEFhHoqIazZ", "val_short": "ABCme", "val_long": {"--include", "--exclude", "--max-count"},
             "long": {"--count", "--ignore-case", "--line-number", "--recursive", "--files-with-matches",
                      "--invert-match", "--no-messages", "--extended-regexp", "--fixed-strings", "--quiet"}},
    "echo": {"short": "ne"}, "test": {"short": ""}, "file": {"short": "bi"},
    "du": {"short": "hsacx", "val_short": "d"}, "df": {"short": "hTi"}, "uname": {"short": "asrmnvpio"},
    "hostname": {"short": "fis"}, "date": {"short": "u", "val_short": "d"}, "whoami": {"short": ""}, "pwd": {"short": "LP"},
    "which": {"short": "a"}, "readlink": {"short": "fem"}, "sort": {"short": "nrubfhVc", "val_short": "kt"},
    "uniq": {"short": "cdui"}, "cut": {"short": "s", "val_short": "dfcb"}, "tr": {"short": "dsc"},
    "jq": {"short": "rcCSeMa", "long": {"--raw-output", "--compact-output", "--sort-keys"}},
    "xxd": {"short": "p", "val_short": "lcs"}, "base64": {"short": "d"}, "id": {"short": "unGg"},
    "getent": {"short": ""}, "dirname": {"short": ""}, "basename": {"short": "a", "val_short": "s"},
    "realpath": {"short": ""}, "md5sum": {"short": "b"}, "sha256sum": {"short": "b"}, "printenv": {"short": "0"},
    # HTTP clients: GET-only flags. NO -X/--request, -d/--data*, -F, -T, -K, -o/-O (write files), cookies, --json.
    "curl": {"short": "sSfLIivk46g", "val_short": "HmAeDw", "long": {"--compressed", "--head", "--insecure", "--silent",
             "--show-error", "--fail", "--location", "--verbose", "--include"},
             "val_long": {"--max-time", "--connect-timeout", "--header", "--user-agent", "--resolve", "--retry"}},
    "wget": {"short": "qSv", "val_short": "OTt", "long": {"--spider", "--quiet", "--no-check-certificate", "--server-response"},
             "val_long": {"--timeout", "--tries", "--header"}},
    "rg": {"short": "cilnIwxvsFhHoqz", "val_short": "ABCmeg", "long": {"--count", "--ignore-case", "--files-with-matches"}},
}


def _value_ok(binary: str, flag: str, value: str) -> bool:
    if binary == "curl" and flag == "-D":
        return value == "-"           # dump headers to stdout only, never to a file
    if binary == "curl" and flag == "-w":
        return "@" not in value        # `-w @file` reads a file
    if binary == "wget" and flag == "-O":
        return value == "-"           # stdout only
    return True


def _argv_ok(argv: list[str]) -> bool:
    pol = _ARGV_POLICY.get(argv[0] if argv else "")
    if pol is None:
        return False
    short, val_short = pol.get("short", ""), pol.get("val_short", "")
    longs, val_long = pol.get("long", set()), pol.get("val_long", set())
    i = 1
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            break
        if tok.startswith("--"):
            name, eq, val = tok.partition("=")
            if name in val_long:
                if not eq:
                    i += 1
            elif name not in longs:
                return False
        elif tok.startswith("-") and len(tok) > 1 and not tok[1:].isdigit():
            chars = tok[1:]
            for k, ch in enumerate(chars):
                if ch in val_short:
                    value = chars[k + 1:] if k < len(chars) - 1 else (argv[i + 1] if i + 1 < len(argv) else "")
                    if not _value_ok(argv[0], "-" + ch, value):
                        return False
                    if k == len(chars) - 1:
                        i += 1
                    break
                if ch not in short:
                    return False
        i += 1
    return True
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


#: A command line is "read-only" only when ONE simple command runs. Any shell metacharacter (`;` `&` `|` `$(` backtick,
#: newline, redirection) can chain a second, mutating command behind an allow-listed first word
#: (`echo; docker exec noctus-waha-x-core ...`), so its presence takes the command off the read-only path.
_SHELL_META = re.compile(r"[;&|`<>\n\r]|\$\(|\$\{")
#: curl/wget invoked in a way that is not a plain GET (a POST to a WAHA core would defeat the line policy).
_NON_GET_HTTP = re.compile(
    r"(?:^|\s)(?:-X\s*(?!GET\b|HEAD\b)\S+|--request(?:=|\s+)(?!GET\b|HEAD\b)\S+|-d\b|--data\S*|-F\b|--form\S*|"
    r"-T\b|--upload-file\b|--json\b|--post-data\S*|--post-file\S*|--method(?:=|\s+)(?!GET\b|HEAD\b)\S+|--body-\S+)",
)  # case-sensitive on purpose: `-D-` (dump headers) is a read, `-d` (data) is not
#: A WAHA core container (`waha-<n>-core` / `noctus-waha-<n>-core`) or ANY docker exec into a waha container: the
#: line-policy edge does not front these, so touching them is a production write that needs the confirm flow.
_WAHA_CORE = re.compile(r"waha-[a-z0-9-]*-core", re.IGNORECASE)
_DOCKER_EXEC_WAHA = re.compile(r"docker\s+(?:container\s+)?exec\b[^\n;|&]*\bwaha", re.IGNORECASE)
_IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_HEXID = re.compile(r"^[0-9a-f]{4,64}$")
_HOSTISH = re.compile(r"(?:://|@)([A-Za-z0-9][A-Za-z0-9._-]*)|\b([A-Za-z0-9][A-Za-z0-9._-]*):\d{2,5}\b")
#: Every container that is a WAHA: by NAME, by IMAGE ANCESTOR (devlikeapro/waha*, any tag) and by compose PROJECT label.
#: Rows: id, name, compose service, then per network IPv4, IPv6 and every network alias. `xargs -r` so "none" is rc 0 +
#: empty (a failure is rc != 0 -> fail closed).
_WAHA_INVENTORY = (
    "{ docker ps -aq --filter name=waha; "
    "for i in $(docker images -q --filter 'reference=devlikeapro/waha*' | sort -u); do docker ps -aq --filter ancestor=$i; done; "
    "docker ps -aq --filter label=com.docker.compose.project=noctus-waha; } | sort -u | xargs -r docker inspect "
    "--format '{{.Id}} {{.Name}} {{index .Config.Labels \"com.docker.compose.service\"}} "
    "{{if eq (index .Config.Labels \"noctus.line.personal\") \"true\"}}personal-line-label{{end}} "
    "{{range $k,$v := .NetworkSettings.Networks}}{{$v.IPAddress}} {{$v.GlobalIPv6Address}} {{range $v.Aliases}}{{.}} {{end}}{{end}}'"
)


def _norm_tok(tok: str) -> str:
    """Lower-case; IP addresses canonicalised (IPv4-mapped IPv6 == the IPv4)."""
    import ipaddress

    t = tok.strip().lstrip("/").lower().rstrip(".")
    try:
        ip = ipaddress.ip_address(t.strip("[]").split("%", 1)[0])
    except ValueError:
        return t
    return str(getattr(ip, "ipv4_mapped", None) or ip)


def _waha_inventory(run) -> "list[set[str]] | None":
    """Per waha container: every identifying token (id, name, compose service, IPs, aliases). None = lookup failed."""
    try:
        rc, out, _err = run(_WAHA_INVENTORY)
    except Exception:  # noqa: BLE001 - an unreachable VPS is "unknown", which is closed
        return None
    if rc != 0:
        return None
    return [{_norm_tok(x) for x in line.split()} for line in (out or "").splitlines() if line.strip()]


def _candidate_targets(command: str, container: str | None) -> set[str]:
    """Tokens that could NAME a container without containing `waha`: a (short) id, an IP, or a host name."""
    toks = {t for t in re.split(r"[\s/:=,\"']+", command) if t}
    out = {t.lower() for t in toks if _HEXID.match(t.lower())}
    out |= {_norm_tok(ip) for ip in _IPV4.findall(command)}
    for m6 in re.finditer(r"\[([0-9A-Fa-f:.]+)\]", command):
        out.add(_norm_tok(m6.group(1)))
    for m in _HOSTISH.finditer(command):
        host = _norm_tok(m.group(1) or m.group(2) or "")
        if host and host not in ("localhost",):
            out.add(host)
    if container:
        out.add(_norm_tok(container))
    return out


def _row_matches(row: set[str], cands: set[str]) -> bool:
    ids = {x for x in row if _HEXID.match(x)}
    return any(c in row or (len(c) >= 4 and any(i.startswith(c) for i in ids)) for c in cands)


PERSONAL_LABEL_TOKEN = "personal-line-label"  # the inventory emits this for a container stamped noctus.line.personal=true


def _aliases_of(yml_text: str) -> set[str]:
    from .waha_instance import parse_instances

    out: set[str] = set()
    for inst in parse_instances(yml_text)["instances"]:
        if inst.get("personal"):
            n = inst["name"]
            out |= {f"waha-{n}", f"noctus-waha-{n}", f"waha-{n}-core", f"noctus-waha-{n}-core"}
    return out


def personal_aliases(repo_root=None) -> set[str]:
    """Names of `personal: true` lines in THIS checkout's waha-instances.yml. Raises when unreadable/unparseable."""
    from pathlib import Path

    from settings import REPO_ROOT

    from .waha_instance import DATA_REL

    return _aliases_of((Path(repo_root) if repo_root else Path(REPO_ROOT)).joinpath(DATA_REL).read_text(encoding="utf-8"))


def _vps_personal_aliases(run) -> set[str]:
    """Same, from the VPS's OWN checkout. Raises when it cannot be read."""
    from .waha_instance import VPS_FLEET

    rc, out, _err = run(f"cat {VPS_FLEET}/waha-instances.yml")
    if rc != 0:
        raise OSError("VPS waha-instances.yml unreadable")
    return _aliases_of(out)


def targets_personal_core(command: str, container: str | None = None, run=None, repo_root=None) -> bool:
    """True when the command/container targets a container of a `personal: true` line. Refused with OR without confirm.

    A branch must never be able to LOOSEN this, so "personal" is the UNION of three sources: this checkout's yml, the
    VPS's own yml, and the LIVE container label `noctus.line.personal=true` (stamped at render). A flip to `personal:
    false` or a deleted line locally changes none of the other two. If ANY source cannot be read, every waha target is
    refused as if personal (fail closed)."""
    waha_names = {t for t in re.split(r"[\s/:=,\"']+", f"{command} {container or ''}".lower()) if "waha" in t}
    cands = _candidate_targets(command, container) | {_norm_tok(t) for t in waha_names}
    if not cands:
        return False
    aliases: set[str] = set()
    unreadable = False
    try:
        aliases |= personal_aliases(repo_root)
    except Exception:  # noqa: BLE001 - unreadable local declaration
        unreadable = True
    if run is not None:
        try:
            aliases |= _vps_personal_aliases(run)
        except Exception:  # noqa: BLE001 - unreadable VPS declaration
            unreadable = True
    low = f"{command} {container or ''}".lower()
    if any(re.search(rf"(?<![a-z0-9-]){re.escape(a)}(?![a-z0-9-])", low) for a in aliases):
        return True
    wahaish = bool(waha_names) or bool(_WAHA_CORE.search(command)) or bool(_DOCKER_EXEC_WAHA.search(command))
    if run is None:
        return unreadable and wahaish
    inv = _waha_inventory(run)
    if inv is None:
        return True                      # cannot see the live labels: fail closed
    hit = [row for row in inv if _row_matches(row, cands)]
    if any(PERSONAL_LABEL_TOKEN in row or row & aliases for row in hit):
        return True
    return unreadable and (wahaish or bool(hit))


def touches_waha_core(command: str, container: str | None = None, run=None) -> bool:
    """True when the command (or `container`) targets a WAHA container -- by name, or by id / IP / host name / alias when
    `run` is given and the target RESOLVES to a waha container. An unresolvable lookup fails CLOSED (True)."""
    if (_WAHA_CORE.search(command) or (container and "waha" in container.lower())
            or _DOCKER_EXEC_WAHA.search(command)):
        return True
    cands = _candidate_targets(command, container)
    if not cands or run is None:
        return False
    inv = _waha_inventory(run)
    if inv is None:
        return True
    return any(_row_matches(row, cands) for row in inv)


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
    """True when ONE simple command runs, its binary is allow-listed AND every flag is on that binary's allowlist (the
    parser is an ALLOWLIST at argv level, not a blocklist of known-bad flags)."""
    if _SHELL_META.search(command):
        return False
    try:
        toks = shlex.split(command)
    except ValueError:
        return False
    while toks and "=" in toks[0] and not toks[0].startswith("-") and toks[0].split("=", 1)[0].isidentifier():
        if toks[0].split("=", 1)[0].upper().startswith(("LD_", "DYLD_", "PATH", "BASH_", "SHELL", "IFS")):
            return False  # an env prefix that changes what runs is not harmless
        toks = toks[1:]
    if not toks:
        return False
    if toks[0] == "docker":
        after = [t for t in toks[1:] if not t.startswith("-")]
        flags = [t for t in toks[1:] if t.startswith("-")]
        if any(f.split("=", 1)[0] in ("-H", "--host", "--context", "--config", "--tls", "--tlsverify") for f in flags):
            return False
        sub = after[0] if after else ""
        if sub == "system":
            return len(after) > 1 and after[1] == "df"
        return sub in _DOCKER_READ_SUBCMDS
    return toks[0] in _READ_BINARIES and _argv_ok(toks)


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
    repo_root: str | None = None,
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

    run = _runner(run_remote, ssh_host)
    if targets_personal_core(command, container, run=run, repo_root=repo_root):
        return {
            "ok": False, "status": "refused", "exit_code": 1,
            "error": ("this targets a container of a `personal: true` WhatsApp line: refused with or without confirm -- "
                      "a personal number's core is touched by the owner by hand, never through this tool "
                      "(KB § INTEGRATIONS/whatsapp.md § 6a)."),
        }
    waha = touches_waha_core(command, container, run=run)
    read_only = _is_read_only(command) and not waha
    if waha and not confirm:
        return {
            "ok": False, "status": "needs_confirm", "exit_code": 1,
            "message": ("this touches a WAHA container (waha-<n>-core / docker exec into waha*): the line-policy edge "
                        "does not front it, so it can write to WhatsApp or change the session. It is never "
                        "read-only -- pass confirm=True only for a deliberate, owner-approved operation."),
        }
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


__all__ = ["exec_cmd", "touches_waha_core", "targets_personal_core", "personal_aliases", "register", "_HARD_DENY", "_READ_BINARIES", "_is_read_only",
           "_hard_denied"]
