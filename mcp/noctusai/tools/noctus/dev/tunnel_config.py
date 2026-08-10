"""noctus.dev.tunnel_config — make `deploy/tunnel/ingress.yml` actually canonical.

**The drift this closes** (found 2026-08-10 while publishing igig).
`deploy/tunnel/ingress.yml` opens with the words "SINGLE SOURCE OF TRUTH",
and `config.yml.template` says the `ingress:` block is "generated from
ingress.yml". Neither was mechanised. `compose.tunnel.yml` mounts **`./`**,
so the live config is whichever directory the tunnel happened to be brought
up from — on the VPS that was
`projects/production-deploy-migration/deploy/tunnel/`, a **gitignored,
deploy-local copy**. Editing the repo's `ingress.yml` therefore changed
nothing live, silently: adding igig's route to the canonical file left the
running tunnel unaware of it, and the route had to be hand-patched into the
deploy-local copy with `sed`.

That is the hand-maintained-list failure mode the fleet already has keepers
for (`KB § PATTERNS/devops/product-lockfile-and-slug-drift.md`) — a
"canonical" file that nothing derives from is a comment, not a contract.
`.gitignore` already ignores `**/tunnel/config.yml` and `**/tunnel/*.json`
"so a `git pull` can NEVER touch the live tunnel config by construction" —
i.e. the INTENDED home for the live config and credentials is the repo's
own `deploy/tunnel/`, with both files gitignored. The project-folder copy
was therefore not a deliberate design; it was the drift.

(One thing that looked like a bug and was not: the live config listed
`orbity.noctusai.com` after the comment declaring the catch-all must be
last. The catch-all `http_status:404` was still the final RULE, so routing
was correct — only the comment placement was off. Renumbering it is
cosmetic, and worth saying plainly rather than banking as a fix.)

**The fix.** `config.yml`'s `ingress:` block is now RENDERED from
`ingress.yml`, with the catch-all appended last by construction. The
environment-specific lines (`tunnel:` id, `credentials-file:`) are
preserved from the live file — they are secrets/identity, not routing, and
never belong in the repo.

  render — pure function: ingress.yml → the `ingress:` block. Testable
           offline; no SSH.
  check  — read the LIVE config over SSH and diff its hostname→service map
           against the rendered one. Read-only. This is the drift detector
           that did not exist.
  apply  — back up the live config, write the rendered one, restart the
           tunnel. Confirm-gated (production mutation).

KB § PATTERNS/devops/tunnel-ingress-source-of-truth.md.
"""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from workspace import resolve_caller_root

from ._vps_ssh import run_remote

#: Where the tunnel's live config lives on the VPS. Deliberately a constant
#: rather than a guess: `apply` must never write to an arbitrary path.
#: The repo's own deploy/tunnel/ — the intended home per .gitignore's
#: "a `git pull` can NEVER touch the live tunnel config" rule. Overridable
#: for a host that has not been migrated off the deploy-local copy.
LIVE_CONFIG_DEFAULT = "/opt/noctus/noctusai/deploy/tunnel/config.yml"
LEGACY_CONFIG_PATH = (
    "/opt/noctus/noctusai/projects/production-deploy-migration/deploy/tunnel/config.yml"
)
INGRESS_REL = "deploy/tunnel/ingress.yml"

#: cloudflared matches ingress rules top-to-bottom and REQUIRES a final
#: catch-all. Appended by the renderer so it can never drift down the file.
CATCH_ALL = "  - service: http_status:404"


def _resolve_root(repo_root: str | None, worktree_path: str | None) -> Path:
    if repo_root is not None:
        return Path(repo_root)
    if worktree_path:
        return Path(resolve_caller_root(worktree_path))
    return Path(REPO_ROOT)


def parse_ingress(text: str) -> list[dict]:
    """`ingress.yml` → ordered list of `{hostname, service}`.

    Raises ValueError on a shape the renderer cannot faithfully express —
    never silently drops a route, because a dropped route is an outage.
    """
    import yaml

    data = yaml.safe_load(text) or {}
    routes = data.get("routes")
    if not isinstance(routes, list) or not routes:
        raise ValueError("ingress.yml has no non-empty `routes:` list")
    out: list[dict] = []
    for i, r in enumerate(routes):
        if not isinstance(r, dict):
            raise ValueError(f"routes[{i}] is not a mapping")
        host = str(r.get("hostname") or "").strip()
        svc = str(r.get("service") or "").strip()
        if not host or not svc:
            raise ValueError(f"routes[{i}] missing hostname or service: {r!r}")
        out.append({"hostname": host, "service": svc})
    return out


def render_ingress_block(routes: list[dict]) -> str:
    """The `ingress:` block, catch-all last BY CONSTRUCTION."""
    lines = ["ingress:"]
    for r in routes:
        lines.append(f"  - hostname: {r['hostname']}")
        lines.append(f"    service: {r['service']}")
    lines.append(CATCH_ALL)
    return "\n".join(lines) + "\n"


def render_config(live_config_text: str, routes: list[dict]) -> str:
    """Replace the live config's `ingress:` block with the rendered one,
    preserving every line above it (tunnel id, credentials-file, protocol,
    comments) verbatim — those are environment identity, not routing."""
    lines = live_config_text.splitlines()
    idx = next((i for i, l in enumerate(lines) if l.strip() == "ingress:"), None)
    if idx is None:
        raise ValueError("live config has no `ingress:` block to replace")
    head = "\n".join(lines[:idx]).rstrip("\n")
    return head + "\n\n" + render_ingress_block(routes)


def parse_config_hostmap(config_text: str) -> dict[str, str]:
    """Live `config.yml` → {hostname: service}. Ignores the catch-all."""
    import yaml

    data = yaml.safe_load(config_text) or {}
    rules = data.get("ingress") or []
    out: dict[str, str] = {}
    for r in rules:
        if not isinstance(r, dict):
            continue
        host = r.get("hostname")
        if host:
            out[str(host).strip()] = str(r.get("service") or "").strip()
    return out


def _read_ingress(root: Path) -> list[dict]:
    p = root / INGRESS_REL
    if not p.is_file():
        raise ValueError(f"{INGRESS_REL} not found under {root}")
    return parse_ingress(p.read_text(encoding="utf-8"))


def _fetch_live(ssh_host: str, live_path: str) -> str:
    rc, out, err = run_remote(ssh_host, f"cat {live_path}")
    if rc != 0:
        raise ValueError(f"could not read {live_path} (rc={rc}): {err.strip()}")
    return out


def _render(repo_root, worktree_path) -> dict:
    root = _resolve_root(repo_root, worktree_path)
    routes = _read_ingress(root)
    return {
        "ok": True,
        "action": "render",
        "route_count": len(routes),
        "ingress_block": render_ingress_block(routes),
    }


def _check(ssh_host: str, live_path: str, repo_root, worktree_path) -> dict:
    root = _resolve_root(repo_root, worktree_path)
    routes = _read_ingress(root)
    declared = {r["hostname"]: r["service"] for r in routes}
    live_text = _fetch_live(ssh_host, live_path)
    live = parse_config_hostmap(live_text)

    missing = sorted(set(declared) - set(live))          # in repo, not live
    extra = sorted(set(live) - set(declared))            # live, not in repo
    changed = sorted(h for h in set(declared) & set(live) if declared[h] != live[h])
    in_sync = not (missing or extra or changed)
    return {
        "ok": True,
        "action": "check",
        "in_sync": in_sync,
        "status": "in_sync" if in_sync else "drifted",
        "declared_count": len(declared),
        "live_count": len(live),
        "missing_from_live": missing,
        "extra_in_live": extra,
        "service_changed": {h: {"declared": declared[h], "live": live[h]} for h in changed},
        "live_path": live_path,
        "detail": (
            "live tunnel config matches deploy/tunnel/ingress.yml"
            if in_sync else
            "LIVE TUNNEL CONFIG HAS DRIFTED from deploy/tunnel/ingress.yml — "
            "run action='apply' confirm=True to re-derive it"
        ),
    }


def _apply(ssh_host: str, live_path: str, repo_root, worktree_path, confirm: bool) -> dict:
    root = _resolve_root(repo_root, worktree_path)
    routes = _read_ingress(root)
    live_text = _fetch_live(ssh_host, live_path)
    rendered = render_config(live_text, routes)

    # Refuse to REMOVE a live hostname without an explicit declaration —
    # dropping a route is an outage, and must never be a silent side effect.
    live_hosts = set(parse_config_hostmap(live_text))
    declared_hosts = {r["hostname"] for r in routes}
    dropped = sorted(live_hosts - declared_hosts)
    if dropped:
        return {
            "ok": False,
            "action": "apply",
            "status": "blocked",
            "error": (
                f"REFUSED — applying would remove {len(dropped)} live hostname(s) "
                f"not declared in {INGRESS_REL}: {dropped}. Add them to the "
                "canonical file first (or remove them deliberately there)."
            ),
            "would_drop": dropped,
        }

    if not confirm:
        return {
            "ok": True,
            "action": "apply",
            "status": "planned",
            "live_path": live_path,
            "route_count": len(routes),
            "rendered_config": rendered,
            "note": "DRY RUN — pass confirm=True to write + restart the tunnel",
        }

    import base64
    payload = base64.b64encode(rendered.encode("utf-8")).decode("ascii")
    backup = f"{live_path}.bak-tunnelsync"
    cmd = (
        f"cp {live_path} {backup} && "
        f"echo {payload} | base64 -d > {live_path} && "
        f"echo WROTE && tail -3 {live_path}"
    )
    rc, out, err = run_remote(ssh_host, cmd)
    if rc != 0:
        return {
            "ok": False, "action": "apply", "status": "error",
            "error": f"write failed (rc={rc}): {err.strip()}",
        }
    r_rc, _r_out, r_err = run_remote(ssh_host, "docker restart noctus-tunnel")
    return {
        "ok": True,
        "action": "apply",
        "status": "applied",
        "live_path": live_path,
        "backup": backup,
        "route_count": len(routes),
        "tunnel_restarted": r_rc == 0,
        "restart_error": r_err.strip() if r_rc != 0 else None,
        "stdout": out.strip(),
    }


def tunnel_config(
    action: str = "check",
    ssh_host: str = "noctus-vps",
    live_path: str = LIVE_CONFIG_DEFAULT,
    repo_root: str | None = None,
    worktree_path: str | None = None,
    confirm: bool = False,
) -> dict:
    """Derive the cloudflared `ingress:` block from `deploy/tunnel/ingress.yml`.

    action='render' (offline) | 'check' (read-only drift diff vs the live
    VPS config) | 'apply' (backup + write + restart; confirm-gated).
    KB § PATTERNS/devops/tunnel-ingress-source-of-truth.md.
    """
    try:
        if action == "render":
            return _render(repo_root, worktree_path)
        if action == "check":
            return _check(ssh_host, live_path, repo_root, worktree_path)
        if action == "apply":
            return _apply(ssh_host, live_path, repo_root, worktree_path, confirm)
    except ValueError as e:
        return {"ok": False, "action": action, "status": "error", "error": str(e)}
    return {
        "ok": False,
        "action": action,
        "error": f"unknown action {action!r} — expected 'render', 'check' or 'apply'",
    }


# ── MCP registration ──────────────────────────────────────────────────────


def register(server) -> None:
    @server.tool(
        name="noctus.dev.tunnel_config",
        description=(
            "Make deploy/tunnel/ingress.yml genuinely canonical for the "
            "cloudflared tunnel. action='render' renders the ingress: block "
            "from ingress.yml offline (catch-all last by construction). "
            "action='check' reads the LIVE VPS config over SSH and diffs its "
            "hostname->service map against the repo's — the drift detector "
            "that did not exist when a 'single source of truth' file was not "
            "actually derived from. action='apply' confirm=True backs up, "
            "rewrites the live ingress block and restarts the tunnel; it "
            "REFUSES to drop a live hostname that ingress.yml does not "
            "declare. KB § PATTERNS/devops/tunnel-ingress-source-of-truth.md."
        ),
    )
    def _tunnel_config(
        action: str = "check",
        ssh_host: str = "noctus-vps",
        live_path: str = LIVE_CONFIG_DEFAULT,
        worktree_path: str = "",
        confirm: bool = False,
    ) -> dict:
        return tunnel_config(
            action=action,
            ssh_host=ssh_host,
            live_path=live_path,
            worktree_path=worktree_path or None,
            confirm=confirm,
        )


__all__ = ["tunnel_config", "register", "parse_ingress", "render_ingress_block",
           "render_config", "parse_config_hostmap"]
