"""noctus.dev.deploy_image — atomic product-image redeploy with rollback (C2).

The §2a safety-net **C2**: a product-image deploy must never leave production on
a broken image. The live fleet runs GHCR-pulled images (`ghcr.io/jraphaelsst/
noctus-<slug>:<tag>`, compose project `noctusai-products-prod`) — the VPS never
builds; it `docker compose pull`s + `up -d`s (see the fleet README). This tool
wraps that update so it is atomic:

  1. SNAPSHOT — tag the currently-running image id as `:previous` (the pinned
     rollback target).
  2. PULL — `docker compose pull <product>` (the new image from GHCR). If the
     pulled image id == the running one, it's a no-op (status up_to_date).
  3. DEPLOY — `docker compose up -d <product>` (recreate on the new image).
  4. HEALTH-PROBE — poll the container health until healthy / unhealthy / timeout.
  5. ROLLBACK on failure — retag the snapshot id back to `:<tag>` + `up -d` →
     production returns to the last-known-good image; re-probe to confirm.

DRY-RUN by default (read-only: reports the current image + the plan); pass
confirm=True to perform the swap (the 412-style production write gate). BY
CONSTRUCTION it only runs a safe docker allowlist — `inspect`/`image`/`tag`/`ps`
and `docker compose {pull,up}` — never `rmi`/`prune`/`down`/`rm`/`system`, so it
can neither delete the rollback image nor tear the fleet down (a colocated test
asserts no banned token is ever emitted).

IO is injectable (`run_remote`, `sleep`, `now`) so the colocated test drives
every path — planned / up_to_date / deployed / rolled_back / error — with zero
real SSH and zero real waiting.
"""
from __future__ import annotations

import datetime as _dt
import shlex
import subprocess
import time as _time
from typing import Any, Callable

# Non-compose docker subcommands the tool may run. Excludes rmi/prune/rm/system
# (would destroy the rollback image) by omission.
_DOCKER_ALLOWED = frozenset({"inspect", "image", "tag", "ps"})
# `docker compose` sub-actions the tool may run. Excludes down/rm/kill/stop.
_COMPOSE_ALLOWED = frozenset({"pull", "up"})
# Asserted-absent by the colocated safety test (defense in depth beyond the
# allowlists): the tool must never emit any of these.
_BANNED_TOKENS = ("rmi", "prune", "system", "down", "kill", "volume", "stop")

DEFAULT_COMPOSE = "projects/production-deploy-migration/deploy/fleet/docker-compose.prod.yml"
DEFAULT_IMAGE_REPO = "ghcr.io/jraphaelsst"

# Container health classes (Go-template returns Health.Status, else State.Status).
_GOOD = frozenset({"healthy", "running"})
_BAD = frozenset({"unhealthy", "exited", "dead"})


def _run_remote_default(ssh_host: str, cmd: list[str]) -> tuple[int, str, str]:
    remote = " ".join(shlex.quote(c) for c in cmd)
    r = subprocess.run(["ssh", ssh_host, remote], capture_output=True, text=True)
    return r.returncode, (r.stdout or ""), (r.stderr or "")


def _docker(runner, *args) -> tuple[int, str, str]:
    """Run a non-compose docker command — only if on the safe allowlist."""
    sub = args[0] if args else ""
    if sub not in _DOCKER_ALLOWED:
        raise ValueError(f"deploy_image: docker '{sub}' not on the safe allowlist {sorted(_DOCKER_ALLOWED)}")
    return runner(["docker", *args])


def _compose(runner, compose_file: str, action: str, *rest) -> tuple[int, str, str]:
    """Run `docker compose -f <file> <action> ...` — only the safe actions."""
    if action not in _COMPOSE_ALLOWED:
        raise ValueError(f"deploy_image: compose '{action}' not on the safe allowlist {sorted(_COMPOSE_ALLOWED)}")
    return runner(["docker", "compose", "-f", compose_file, action, *rest])


def _poll_health(runner, sleep, container: str, timeout: int, interval: int) -> tuple[str, list[str]]:
    """Poll container health → 'healthy' | 'unhealthy' | 'timeout'. Uses
    Health.Status when a healthcheck exists, else falls back to State.Status."""
    tmpl = "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}"
    states: list[str] = []
    waited = 0
    while waited <= timeout:
        _rc, out, _e = _docker(runner, "inspect", "-f", tmpl, container)
        st = (out or "").strip()
        states.append(st)
        if st in _GOOD:
            return "healthy", states
        if st in _BAD:
            return "unhealthy", states
        sleep(interval)
        waited += interval
    return "timeout", states


def deploy_image(
    product: str,
    ssh_host: str = "noctus-vps",
    repo_dir: str = "/opt/noctus/noctusai",
    compose_file: str = DEFAULT_COMPOSE,
    image_repo: str = DEFAULT_IMAGE_REPO,
    tag: str = "latest",
    confirm: bool = False,
    health_timeout: int = 150,
    poll_interval: int = 10,
    run_remote: Callable[[list[str]], tuple[int, str, str]] | None = None,
    sleep: Callable[[float], None] | None = None,
    now: Callable[[], _dt.datetime] | None = None,
) -> dict[str, Any]:
    """Atomic image redeploy of `product` with C2 rollback. Dry-run unless
    `confirm`. status ∈ {planned, up_to_date, deployed, rolled_back, error}.
    Never raises on an operational failure — it returns it (no silent errors)."""
    if not product or not product.strip():
        return {"ok": False, "status": "error", "exit_code": 1, "error": "product required"}
    runner = run_remote or (lambda cmd: _run_remote_default(ssh_host, cmd))
    napper = sleep or _time.sleep
    clock = now or _dt.datetime.utcnow
    container = f"noctus-{product}"
    image = f"{image_repo}/noctus-{product}"
    cf = f"{repo_dir}/{compose_file}"

    # ── PRE-FLIGHT (read-only): the running image id ──
    rc, cur, err = _docker(runner, "inspect", "-f", "{{.Image}}", container)
    if rc != 0 or not cur.strip():
        return {
            "ok": False, "status": "error", "exit_code": 1, "product": product,
            "error": f"container '{container}' not found/running on '{ssh_host}': "
                     f"{err.strip() or cur.strip()} — is the product deployed?",
        }
    current_image_id = cur.strip()

    base: dict[str, Any] = {
        "ok": True, "product": product, "container": container, "ssh_host": ssh_host,
        "image": f"{image}:{tag}", "current_image_id": current_image_id,
        "previous_tag": f"{image}:previous",
    }

    # ── DRY-RUN: read-only plan, no snapshot/pull/up ──
    if not confirm:
        return {**base, "status": "planned", "exit_code": 0,
                "message": (
                    f"would: tag {current_image_id[:19]} as {image}:previous → "
                    f"compose pull {product} → up -d → health-probe → rollback on failure. "
                    "Pass confirm=True to deploy."
                )}

    # ── SNAPSHOT (C2 rollback target) ──
    _docker(runner, "tag", current_image_id, f"{image}:previous")

    # ── PULL ──
    rc_p, out_p, err_p = _compose(runner, cf, "pull", product)
    if rc_p != 0:
        return {**base, "status": "error", "exit_code": 1,
                "reason": f"`compose pull {product}` failed: {err_p.strip() or out_p.strip()}. "
                          "Container untouched (still on the current image); snapshot tag is harmless."}
    rc_n, new_id, _e = _docker(runner, "image", "inspect", "-f", "{{.Id}}", f"{image}:{tag}")
    new_image_id = new_id.strip()
    if new_image_id and new_image_id == current_image_id:
        return {**base, "status": "up_to_date", "exit_code": 0, "new_image_id": new_image_id,
                "message": "pulled image == running image; no redeploy needed."}

    # ── DEPLOY (recreate on the new image) ──
    rc_u, out_u, err_u = _compose(runner, cf, "up", "-d", product)
    if rc_u != 0:
        # up failed before swapping — roll back defensively + report.
        _docker(runner, "tag", current_image_id, f"{image}:{tag}")
        _compose(runner, cf, "up", "-d", product)
        return {**base, "status": "rolled_back", "exit_code": 1, "new_image_id": new_image_id,
                "reason": f"`compose up -d {product}` failed: {err_u.strip() or out_u.strip()} — "
                          "restored the previous image."}

    # ── HEALTH-PROBE ──
    health, states = _poll_health(runner, napper, container, health_timeout, poll_interval)
    if health == "healthy":
        return {**base, "status": "deployed", "exit_code": 0,
                "new_image_id": new_image_id, "health": health, "health_states": states,
                "message": f"deployed {product} on {new_image_id[:19]} — healthy."}

    # ── ROLLBACK (C2) — restore the snapshot, recreate, re-probe ──
    _docker(runner, "tag", current_image_id, f"{image}:{tag}")
    _compose(runner, cf, "up", "-d", product)
    rb_health, rb_states = _poll_health(runner, napper, container, health_timeout, poll_interval)
    return {
        **base, "status": "rolled_back", "exit_code": 1,
        "new_image_id": new_image_id, "health": health, "health_states": states,
        "rollback_health": rb_health, "rollback_health_states": rb_states,
        "reason": (
            f"new image {new_image_id[:19]} was {health} after {health_timeout}s — "
            f"rolled back to {current_image_id[:19]} (now {rb_health}). "
            "Production is on the last-known-good image; investigate the new image before retrying."
        ),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.deploy_image",
        description=(
            "Atomic product-image redeploy with rollback — the §2a safety-net "
            "C2. For a deployed product (GHCR-pull model): snapshots the running "
            "image as :previous, `docker compose pull`s + `up -d`s the new image, "
            "health-probes the container, and ROLLS BACK to the snapshot on a "
            "health failure so prod is never left on a broken image. DRY-RUN by "
            "default (reports the current image + plan); pass confirm=True to "
            "perform the swap (production write gate). BY CONSTRUCTION limited to "
            "a safe docker allowlist (inspect/image/tag/ps + compose pull/up) — "
            "never rmi/prune/down/rm. status: planned | up_to_date | deployed | "
            "rolled_back | error. See KB § GUIDES/production-deploy.md § 2a (C2)."
        ),
    )
    def _deploy_image(
        product: str,
        confirm: bool = False,
        tag: str = "latest",
        ssh_host: str = "noctus-vps",
    ) -> dict:
        return deploy_image(product, ssh_host=ssh_host, tag=tag, confirm=confirm)


__all__ = ["deploy_image", "_poll_health", "_DOCKER_ALLOWED", "_COMPOSE_ALLOWED", "_BANNED_TOKENS", "register"]
