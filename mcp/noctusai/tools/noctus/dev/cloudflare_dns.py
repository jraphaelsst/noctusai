"""noctus.dev.cloudflare_dns — DNS for the tunnel's declared hostnames, agent-callable.

The claude.ai Cloudflare connector covers Workers/D1/KV/R2 only — no DNS — and
`deploy/tunnel/route-dns.sh` needs a host `cloudflared` the VPS does not have.
This tool closes the gap (the "five products had no DNS" incident, KB §
PATTERNS/devops/tunnel-ingress-source-of-truth.md).

  check  — read-only (default). Resolve every hostname in ingress.yml (plus
           optional `hosts`) over DNS-over-HTTPS; report present/missing.
  route  — create the proxied CNAME to the tunnel for the given hosts via
           cloudflared-in-docker on the VPS (zone-scoped cert.pem, never read
           or printed here). DRY-RUN unless confirm=True. Refuses hosts that
           ingress.yml does not declare (unless allow_undeclared) and hosts
           outside the zone. Idempotent ("already exists" is ok).
  list   — zone DNS records via the Cloudflare API; needs a token resolved by
           resolve_credential('cloudflare_api_token') (DB -> env
           CLOUDFLARE_API_TOKEN), else status 'not_configured' + instructions.

IO seams (injectable, Fake in tests): `resolver(host)->bool`, `ssh(host, cmd)->
(rc,out,err)`, `http_get(url, headers)->(status, json)`.
"""
from __future__ import annotations

import json
import re
import shlex
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from .tunnel_config import _resolve_root, _read_ingress
from ._vps_ssh import run_remote

TUNNEL_ID = "6e9ccdc5-4d99-4d5e-b9f9-1da2fe99f56c"
ZONE = "noctusai.com"
TUNNEL_DIR_DEFAULT = "/opt/noctus/noctusai/deploy/tunnel"
CLOUDFLARED_IMAGE = "cloudflare/cloudflared:latest"
_HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$")

NOT_CONFIGURED_HELP = (
    "No Cloudflare API token resolved. Create an API token (Zone:DNS:Read on "
    "noctusai.com) at https://dash.cloudflare.com/profile/api-tokens and store it "
    "as platform_settings['cloudflare_api_token'] or env CLOUDFLARE_API_TOKEN. "
    "check/route do not need it."
)


def in_zone(host: str) -> bool:
    return host == ZONE or host.endswith("." + ZONE)


def valid_host(host: str) -> bool:
    return bool(_HOST_RE.match(host)) and len(host) <= 253


def route_command(host: str, tunnel_dir: str = TUNNEL_DIR_DEFAULT) -> str:
    """The exact docker command (host validated, every token shell-quoted)."""
    if not valid_host(host):
        raise ValueError(f"invalid hostname {host!r}")
    parts = [
        "docker", "run", "--rm", "--user", "0",
        "-v", f"{tunnel_dir}:/etc/cloudflared:ro",
        CLOUDFLARED_IMAGE, "tunnel", "--origincert", "/etc/cloudflared/cert.pem",
        "route", "dns", TUNNEL_ID, host,
    ]
    return " ".join(shlex.quote(p) for p in parts)


def classify_route_output(rc: int, out: str, err: str) -> str:
    text = f"{out}\n{err}".lower()
    if "already exists" in text:
        return "exists"
    if rc == 0 and "added cname" in text:
        return "created"
    if rc == 0:
        return "created"
    return "error"


def missing_diff(hosts: list[str], present: dict[str, bool]) -> list[str]:
    return sorted(h for h in hosts if not present.get(h))


def doh_resolves(host: str) -> bool:
    """True iff the name has an A/AAAA/CNAME answer (proxied CNAMEs answer as A)."""
    for rtype in ("A", "AAAA", "CNAME"):
        url = "https://cloudflare-dns.com/dns-query?" + urllib.parse.urlencode(
            {"name": host, "type": rtype})
        req = urllib.request.Request(url, headers={"accept": "application/dns-json"})
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 - fixed https host
            data = json.loads(r.read().decode())
        if data.get("Status") == 0 and data.get("Answer"):
            return True
    return False


def _http_get(url: str, headers: dict) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = {}
        return e.code, body


def _ssh(host: str, cmd: str) -> tuple[int, str, str]:
    return run_remote(host, cmd)


def _resolve_token() -> str:
    import os
    try:
        from noctusai_lib.config.credentials import configure_credentials, resolve_credential
        from settings import get_settings

        s = get_settings()
        if s.supabase_url and s.supabase_service_role_key:
            configure_credentials(
                supabase_url=s.supabase_url,
                supabase_anon_key=s.supabase_anon_key or "",
                supabase_service_role_key=s.supabase_service_role_key,
            )
        tok = resolve_credential("cloudflare_api_token")
        if tok:
            return tok
    except Exception:  # degrade to env; absence is reported as not_configured
        pass
    return os.environ.get("CLOUDFLARE_API_TOKEN", "")


def _declared(root: Path) -> list[str]:
    return [r["hostname"] for r in _read_ingress(root)]


def _check(hosts, root, resolver) -> dict:
    declared = _declared(root)
    targets = list(dict.fromkeys(declared + list(hosts or [])))
    present: dict[str, bool] = {}
    errors: dict[str, str] = {}
    for h in targets:
        try:
            present[h] = bool(resolver(h))
        except Exception as e:  # unmeasurable is not "missing"
            errors[h] = f"{type(e).__name__}: {e}"
    missing = missing_diff([h for h in targets if h not in errors], present)
    status = "unverified" if errors else ("missing" if missing else "in_sync")
    return {
        "ok": not errors, "action": "check", "status": status,
        "checked": len(targets), "present": sorted(h for h, v in present.items() if v),
        "missing": missing, "errors": errors,
    }


def _route(hosts, all_missing, allow_undeclared, confirm, root, ssh_host,
           tunnel_dir, resolver, ssh) -> dict:
    declared = set(_declared(root))
    hosts = list(hosts or [])
    if all_missing:
        chk = _check([], root, resolver)
        if chk["status"] == "unverified":
            return {"ok": False, "action": "route", "status": "error",
                    "error": f"cannot resolve all_missing, DNS lookups failed: {chk['errors']}"}
        hosts += chk["missing"]
    hosts = list(dict.fromkeys(hosts))
    if not hosts:
        return {"ok": True, "action": "route", "status": "noop",
                "detail": "no hosts given (or none missing)", "results": {}}
    refused = {}
    for h in hosts:
        if not valid_host(h):
            refused[h] = "invalid hostname"
        elif not in_zone(h):
            refused[h] = f"outside zone {ZONE}"
        elif h not in declared and not allow_undeclared:
            refused[h] = "not declared in deploy/tunnel/ingress.yml (allow_undeclared=True to override)"
    if refused:
        return {"ok": False, "action": "route", "status": "refused", "refused": refused}
    cmds = {h: route_command(h, tunnel_dir) for h in hosts}
    if not confirm:
        return {"ok": True, "action": "route", "status": "planned",
                "commands": cmds, "note": "DRY RUN — pass confirm=True to create the CNAMEs"}
    results = {}
    for h, cmd in cmds.items():
        rc, out, err = ssh(ssh_host, cmd)
        results[h] = {"result": classify_route_output(rc, out, err), "rc": rc,
                      "detail": (out.strip() or err.strip())[-300:]}
    bad = [h for h, r in results.items() if r["result"] == "error"]
    return {"ok": not bad, "action": "route",
            "status": "error" if bad else "routed", "results": results}


def _list(http_get) -> dict:
    token = _resolve_token_hook()
    if not token:
        return {"ok": False, "action": "list", "status": "not_configured",
                "instruction": NOT_CONFIGURED_HELP}
    hdr = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    code, body = http_get(f"https://api.cloudflare.com/client/v4/zones?name={ZONE}", hdr)
    zones = (body or {}).get("result") or []
    if code != 200 or not zones:
        return {"ok": False, "action": "list", "status": "error",
                "error": f"zone lookup failed (http {code})"}
    zid = zones[0]["id"]
    records, page = [], 1
    while True:
        code, body = http_get(
            f"https://api.cloudflare.com/client/v4/zones/{zid}/dns_records?per_page=100&page={page}", hdr)
        if code != 200:
            return {"ok": False, "action": "list", "status": "error",
                    "error": f"dns_records failed (http {code})"}
        records += [{"name": r.get("name"), "type": r.get("type"),
                     "content": r.get("content"), "proxied": r.get("proxied")}
                    for r in body.get("result") or []]
        if page >= ((body.get("result_info") or {}).get("total_pages") or 1):
            break
        page += 1
    return {"ok": True, "action": "list", "status": "listed",
            "count": len(records), "records": records}


#: token seam (tests replace the module attribute through the public setter)
_resolve_token_hook: Callable[[], str] = _resolve_token


def cloudflare_dns(
    action: str = "check",
    hosts: list[str] | None = None,
    all_missing: bool = False,
    allow_undeclared: bool = False,
    confirm: bool = False,
    ssh_host: str = "noctus-vps",
    tunnel_dir: str = TUNNEL_DIR_DEFAULT,
    repo_root: str | None = None,
    worktree_path: str | None = None,
    resolver: Callable[[str], bool] | None = None,
    ssh: Callable[[str, str], tuple[int, str, str]] | None = None,
    http_get: Callable[[str, dict], tuple[int, dict]] | None = None,
) -> dict:
    """DNS check / route / list for the tunnel's hostnames. See module doc."""
    resolver = resolver or doh_resolves
    ssh = ssh or _ssh
    http_get = http_get or _http_get
    try:
        if action == "list":
            return _list(http_get)
        root = _resolve_root(repo_root, worktree_path)
        if action == "check":
            return _check(hosts, root, resolver)
        if action == "route":
            return _route(hosts, all_missing, allow_undeclared, confirm, root,
                          ssh_host, tunnel_dir, resolver, ssh)
    except ValueError as e:
        return {"ok": False, "action": action, "status": "error", "error": str(e)}
    return {"ok": False, "action": action, "status": "error",
            "error": f"unknown action {action!r} — expected 'check', 'route' or 'list'"}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.cloudflare_dns",
        description=(
            "DNS for the cloudflared tunnel's hostnames (the claude.ai Cloudflare "
            "connector has no DNS). action='check' (default, read-only): resolve every "
            "hostname in deploy/tunnel/ingress.yml (+hosts) over DoH -> in_sync|missing. "
            "action='route' hosts=[...] or all_missing=True: DRY-RUN; confirm=True runs "
            "cloudflared-in-docker over the VPS SSH helper to create the CNAME to the "
            "tunnel; refuses hosts not in ingress.yml (unless allow_undeclared) or "
            "outside noctusai.com; idempotent. action='list': zone records via the "
            "Cloudflare API, needs cloudflare_api_token (else not_configured). "
            "KB § PATTERNS/devops/tunnel-ingress-source-of-truth.md."
        ),
    )
    def _cloudflare_dns(
        action: str = "check",
        hosts: list[str] | None = None,
        all_missing: bool = False,
        allow_undeclared: bool = False,
        confirm: bool = False,
        ssh_host: str = "noctus-vps",
        worktree_path: str = "",
    ) -> dict:
        return cloudflare_dns(
            action=action, hosts=hosts, all_missing=all_missing,
            allow_undeclared=allow_undeclared, confirm=confirm,
            ssh_host=ssh_host, worktree_path=worktree_path or None,
        )


__all__ = ["cloudflare_dns", "register", "route_command", "classify_route_output",
           "missing_diff", "in_zone", "valid_host"]
