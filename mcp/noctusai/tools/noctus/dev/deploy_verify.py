"""noctus.dev.deploy_verify — the INDEPENDENT prod revision-drift witness.

The incident this closes (2026-08-13, real). A social-wiring promote looked
fully shipped: `release stage=bless` OK, `stage=promote` OK (prod tip ==
57807ada), `deploy_pull` OK. Then `deploy_image` **timed out without
returning**, and the MCP server disconnected before reporting anything. A
manual `docker inspect` — not any tool — was what caught it: the container
was still `org.opencontainers.image.revision=ecff5585`, "Up 2 days". The
swap had never happened. Two bug fixes were reported-adjacent to "shipped"
while prod served the old code for hours.

The structural hole is not "`deploy_image` has a bug" — it is that the ONLY
witness to whether a deploy landed was the deploying tool itself. When that
tool dies mid-flight, the system has NO independent answer to "what is prod
actually running?", because every branch-level signal (`prod` tip,
`deploy_pull`'s outcome) describes **git**, not the **running container**.

This tool is that independent answer. It has ZERO dependency on
`deploy_image` having run, succeeded, or even existed in this process —
it is composed entirely from read-only primitives (`noctus.vps.exec`'s
`docker inspect` / `docker exec … curl` allowlist) plus a LOCAL git
resolution of the `prod` branch tip (never a caller-supplied sha — a wrong
answer there would defeat the whole point). For every product it reports:

  • the RUNNING container's baked `org.opencontainers.image.revision` label
    (read directly off the container, not a tag — a tag can move without the
    container ever recreating, which is exactly what happened 2026-08-13);
  • the expected sha, resolved fresh from `origin/<prod_branch>` — never a
    parameter, so a caller cannot pass the wrong answer and get a green;
  • a per-product `drift: bool` (`None` only when the running image predates
    the revision-label guard and truly cannot be checked — reported loudly,
    never silently treated as OK);
  • container health + `startup_hook_error` (KB § PATTERNS/backend/
    startup-hook-must-not-be-fatal.md — a product whose lifespan hook failed
    still answers 200, so health alone is not the answer either).

Composes `noctus.vps.exec.exec_cmd` (the existing bounded read-only VPS
exec) rather than re-deriving SSH/allowlist plumbing — same reuse shape as
`release.py` composing `deploy_pull._rebuild_decision`. IO is injectable
(`run_remote`, threaded straight into `exec_cmd`, and `run_local` for the
git resolution) so the colocated test drives every path with zero real SSH
and zero real git.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from settings import REPO_ROOT
from workspace import resolve_caller_root

from . import vps_exec as _vps_exec

DEFAULT_HOST = "noctus-vps"
DEFAULT_COMPOSE = "deploy/fleet/docker-compose.prod.yml"

# The same OCI label build-and-push.sh bakes at build time (mirrors
# deploy_image._REVISION_LABEL — a plain string constant, not a functional
# dependency: this module never calls into deploy_image, by design).
_REVISION_LABEL = "org.opencontainers.image.revision"

_INSPECT_TEMPLATE = (
    "{{.State.Status}}|"
    "{{if .State.Health}}{{.State.Health.Status}}{{end}}|"
    f'{{{{ index .Config.Labels "{_REVISION_LABEL}" }}}}'
)


def _default_run_local(cmd: list[str]) -> tuple[int, str, str]:
    """Local git — resolving the prod tip is deliberately NOT an SSH op (it
    must work even when the VPS/SSH path is the thing that's broken)."""
    import subprocess

    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    return r.returncode, (r.stdout or ""), (r.stderr or "")


def _resolve_expected_sha(
    run_local: Callable[[list[str]], tuple[int, str, str]],
    remote: str, prod_branch: str,
) -> tuple[str | None, str]:
    """The prod branch tip, resolved FRESH — never a parameter (a caller
    passing the wrong answer would get a false green, defeating the point).
    Returns (sha_or_None, detail)."""
    rc_f, _o, err_f = run_local(["git", "fetch", remote, "--quiet"])
    if rc_f != 0:
        return None, f"git fetch {remote} failed: {err_f.strip()}"
    ref = f"{remote}/{prod_branch}"
    rc_r, out_r, err_r = run_local(["git", "rev-parse", "--verify", "--quiet", ref])
    sha = out_r.strip()
    if rc_r != 0 or not sha:
        return None, f"cannot resolve '{ref}': {err_r.strip() or 'unknown ref'}"
    return sha, f"resolved {ref} = {sha}"


def _load_compose_roster(root: Path, compose_file: str) -> tuple[list[dict[str, Any]], str | None]:
    """[{slug, container, port}] from the prod compose file's `services:`
    block — the same file `deploy_image`/`deploy_pull` treat as the prod
    shape's source of truth. Returns (roster, error_or_None). Lazy `yaml`
    import (only paid when the caller doesn't supply `products=`)."""
    import yaml

    path = root / compose_file
    if not path.exists():
        return [], f"compose file not found: {path}"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return [], f"could not parse {path}: {exc}"
    services = data.get("services") or {}
    if not isinstance(services, dict) or not services:
        return [], f"no services found in {path}"
    roster: list[dict[str, Any]] = []
    for slug in sorted(services):
        svc = services[slug] or {}
        container = svc.get("container_name") or f"noctus-{slug}"
        expose = svc.get("expose") or []
        port = None
        if expose:
            m = re.search(r"\d+", str(expose[0]))
            port = m.group(0) if m else None
        roster.append({"slug": slug, "container": container, "port": port})
    return roster, None


def _verify_one(
    entry: dict[str, Any],
    expected_sha: str,
    ssh_host: str,
    run_remote: Callable | None,
) -> dict[str, Any]:
    """Independent per-product read: running revision + health +
    startup_hook_error. Never raises — an unreachable probe is reported,
    not swallowed."""
    slug, container, port = entry["slug"], entry["container"], entry.get("port")
    out: dict[str, Any] = {
        "product": slug, "container": container, "port": port,
        "found": False, "state": None, "health": None,
        "revision": None, "expected_sha": expected_sha, "drift": None,
        "startup_hook_error": None, "health_probe": "skipped",
    }

    r_inspect = _vps_exec.exec_cmd(
        f"docker inspect -f '{_INSPECT_TEMPLATE}' {container}",
        ssh_host=ssh_host, run_remote=run_remote,
    )
    if not r_inspect["ok"]:
        out["note"] = (
            f"container '{container}' not found/inspectable on '{ssh_host}': "
            f"{(r_inspect.get('stderr') or '').strip()[:300]}"
        )
        out["drift"] = True  # expected: running the prod tip; it is not even up
        return out

    out["found"] = True
    parts = (r_inspect["stdout"].strip().split("|") + ["", "", ""])[:3]
    state, health, revision = (p.strip() for p in parts)
    out["state"] = state or None
    out["health"] = health or None
    revision = revision if revision and revision != "<no value>" else None
    out["revision"] = revision

    if revision is None:
        out["drift"] = None
        out["note"] = (
            "no org.opencontainers.image.revision label on the running "
            "container (image predates the revision guard, or was built by a "
            "path other than build-and-push.sh) — drift is UNVERIFIABLE, not "
            "assumed clean."
        )
    else:
        out["drift"] = revision != expected_sha

    # ── active health probe (in-container /api/health) — reuses the SAME
    #    exec_cmd allowlist noc-ship step 6 already calls by hand. ──
    if port:
        r_health = _vps_exec.exec_cmd(
            f"curl -fsS -m 3 http://localhost:{port}/api/health",
            container=container, ssh_host=ssh_host, run_remote=run_remote,
        )
        if r_health["ok"]:
            out["health_probe"] = "ok"
            try:
                body = json.loads(r_health["stdout"])
            except (ValueError, TypeError):
                body = {}
                out["health_probe"] = "ok_unparsed"
            out["startup_hook_error"] = body.get("startup_hook_error")
        else:
            out["health_probe"] = "unreachable"
            out["startup_hook_error"] = "unknown (probe unreachable)"
    else:
        out["health_probe"] = "skipped (no port resolved)"

    return out


def deploy_verify(
    products: list[str] | None = None,
    ssh_host: str = DEFAULT_HOST,
    compose_file: str = DEFAULT_COMPOSE,
    remote: str = "origin",
    prod_branch: str = "prod",
    run_remote: Callable[[list[str]], tuple[int, str, str]] | None = None,
    run_local: Callable[[list[str]], tuple[int, str, str]] | None = None,
    repo_root: str | None = None,
    worktree_path: str | None = None,
) -> dict[str, Any]:
    """Independent revision-drift verification — callable standalone with NO
    dependency on `deploy_image` having run. For every ACTIVE product (the
    prod compose roster, or an explicit `products=` override): running
    container revision vs the FRESHLY-resolved `prod` branch tip, health,
    and `startup_hook_error`.

    status ∈ {drift_detected, degraded, unverifiable, verified, error}.
    exit_code 0 ONLY for 'verified'. Never raises — every failure mode is a
    returned status, not an exception (no silent errors)."""
    local_runner = run_local or _default_run_local
    expected_sha, sha_detail = _resolve_expected_sha(local_runner, remote, prod_branch)
    if not expected_sha:
        return {
            "ok": False, "status": "error", "exit_code": 1,
            "error": f"cannot resolve the expected prod sha — {sha_detail}. "
                     "REFUSING to verify against an unknown target (fail-closed; "
                     "an unresolved expectation is not a passed check).",
        }

    if repo_root is not None:
        root = Path(repo_root)
    elif worktree_path:
        root = Path(resolve_caller_root(worktree_path))
    else:
        root = Path(REPO_ROOT)

    if products:
        # An explicit roster needs the compose file only for port lookup — a
        # miss there degrades to "no port" (health probe skipped), never a
        # hard failure (the caller already told us what to check).
        roster, _roster_note = _load_compose_roster(root, compose_file)
        by_slug = {r["slug"]: r for r in roster}
        entries = [by_slug.get(p, {"slug": p, "container": f"noctus-{p}", "port": None})
                   for p in products]
    else:
        entries, roster_error = _load_compose_roster(root, compose_file)
        if roster_error:
            return {"ok": False, "status": "error", "exit_code": 1,
                    "error": f"cannot resolve the product roster — {roster_error}"}

    results = [_verify_one(e, expected_sha, ssh_host, run_remote) for e in entries]

    drifted = [r["product"] for r in results if r["drift"] is True]
    unverifiable = [r["product"] for r in results if r["drift"] is None]
    degraded = [
        r["product"] for r in results
        if r["drift"] is False and (
            r["health"] == "unhealthy" or r["state"] not in (None, "running")
            or r["health_probe"] in ("unreachable",) or r.get("startup_hook_error")
        )
    ]

    if drifted:
        status, exit_code = "drift_detected", 1
    elif degraded:
        status, exit_code = "degraded", 1
    elif unverifiable:
        status, exit_code = "unverifiable", 1
    else:
        status, exit_code = "verified", 0

    return {
        "ok": True, "status": status, "exit_code": exit_code,
        "expected_sha": expected_sha, "ssh_host": ssh_host,
        "checked": len(results),
        "drifted": drifted, "degraded": degraded, "unverifiable": unverifiable,
        "products": results,
        "message": (
            f"{len(results)} product(s) checked against prod tip {expected_sha[:12]} — "
            f"{len(drifted)} drifted, {len(degraded)} degraded, "
            f"{len(unverifiable)} unverifiable."
        ),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.deploy_verify",
        description=(
            "The INDEPENDENT prod revision-drift witness (closes the 2026-08-13 "
            "phantom-deploy hole: deploy_image timed out mid-swap and nothing "
            "caught it but a manual docker inspect). For every ACTIVE product "
            "(prod compose roster, or an explicit products= list): reads the "
            "RUNNING container's org.opencontainers.image.revision label, "
            "resolves the expected sha FRESH from origin/<prod_branch> (never "
            "a parameter — a caller cannot pass the wrong answer and get a "
            "green), and reports a per-product drift:bool + health + "
            "startup_hook_error (a failed lifespan hook still serves 200). "
            "Callable standalone — ZERO dependency on deploy_image having run, "
            "succeeded, or even existed in this process; composes the existing "
            "noctus.vps.exec read-only allowlist over SSH. "
            "status: drift_detected | degraded | unverifiable | verified | "
            "error. exit_code 0 ONLY for 'verified'."
        ),
    )
    def _deploy_verify(
        products: list[str] | None = None,
        ssh_host: str = DEFAULT_HOST,
        prod_branch: str = "prod",
    ) -> dict:
        return deploy_verify(products=products, ssh_host=ssh_host, prod_branch=prod_branch)


__all__ = ["deploy_verify", "_load_compose_roster", "_resolve_expected_sha",
           "_verify_one", "_REVISION_LABEL", "register"]
