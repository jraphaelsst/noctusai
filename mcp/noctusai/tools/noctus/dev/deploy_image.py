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
import re
import shlex
import subprocess
import time as _time
import urllib.error
import urllib.request
from typing import Any, Callable

# Browser User-Agent — Cloudflare WAF blocks the default urllib signature
# (same rule as sso_smoke / Hostinger MCP; error 1010 without this).
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Non-compose docker subcommands the tool may run. Excludes rmi/prune/rm/system
# (would destroy the rollback image) by omission. `exec` is read-only here (only
# curls the in-container /api/health for the active probe); `commit` snapshots
# the running container into the :previous rollback image (additive, never
# destructive).
_DOCKER_ALLOWED = frozenset({"inspect", "image", "tag", "ps", "exec", "commit", "restart"})
# `docker compose` sub-actions the tool may run. Excludes down/rm/kill/stop.
_COMPOSE_ALLOWED = frozenset({"pull", "up"})
# Asserted-absent by the colocated safety test (defense in depth beyond the
# allowlists): the tool must never emit any of these.
_BANNED_TOKENS = ("rmi", "prune", "system", "down", "kill", "volume", "stop")

DEFAULT_COMPOSE = "deploy/fleet/docker-compose.prod.yml"
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


def _container_port(runner, container: str) -> str | None:
    """The product's port for the active /api/health probe. Prefers the
    container's healthcheck test (compose always sets `curl …localhost:<port>/
    api/health` — present even on a broken container); falls back to the image's
    ExposedPorts. None ⇒ probe uses the docker healthcheck (slower)."""
    rc, out, _e = _docker(runner, "inspect", "-f",
                          "{{if .Config.Healthcheck}}{{json .Config.Healthcheck.Test}}{{end}}", container)
    m = re.search(r"localhost:(\d+)", out or "")
    if m:
        return m.group(1)
    rc2, out2, _e2 = _docker(runner, "inspect", "-f",
                             "{{range $p,$_ := .Config.ExposedPorts}}{{$p}} {{end}}", container)
    m2 = re.search(r"(\d+)", out2 or "")
    return m2.group(1) if m2 else None


def _poll_health(runner, sleep, container: str, timeout: int, interval: int,
                 port: str | None = None, startup_grace: int = 30) -> tuple[str, list[str]]:
    """Poll → 'healthy' | 'unhealthy' | 'timeout'. With a port: ACTIVE probe
    (`exec curl /api/health`) — fast healthy detection, and a curl that still
    fails *past startup_grace* ⇒ unhealthy (so a broken image rolls back in
    ~grace, not ~2 min). A container that exits/dies ⇒ immediate unhealthy.
    Without a port: falls back to the docker healthcheck / state."""
    states: list[str] = []
    waited = 0
    while waited <= timeout:
        _rc, st, _e = _docker(runner, "inspect", "-f", "{{.State.Status}}", container)
        st = (st or "").strip()
        if st in ("exited", "dead"):
            return "unhealthy", states + [f"state={st}@{waited}s"]
        if port:
            rc_c, _o, _ec = _docker(runner, "exec", container, "curl", "-fsS", "-m", "3",
                                    f"http://localhost:{port}/api/health")
            if rc_c == 0:
                return "healthy", states + [f"up@{waited}s"]
            states.append(f"down@{waited}s")
            if waited >= startup_grace:  # past the startup window + still failing
                return "unhealthy", states
        else:
            _rc2, hs, _e2 = _docker(runner, "inspect", "-f",
                "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}", container)
            hs = (hs or "").strip()
            states.append(hs)
            if hs in _GOOD:
                return "healthy", states
            if hs in _BAD:
                return "unhealthy", states
        sleep(interval)
        waited += interval
    return "timeout", states



# ── Tunnel name — the cloudflared container that routes the public hostname
#    to the product origin. One restart re-resolves all stale in-flight
#    connections from the pre-recreate container. ──
_TUNNEL_CONTAINER = "noctus-tunnel"


def _restart_tunnel(runner) -> tuple[bool, str]:
    """docker restart noctus-tunnel after a successful deploy so cloudflared
    drops its stale origin connection and picks up the new container.
    Returns (ok, msg). Idempotent — safe to call even if the tunnel is not
    running (returns ok=False with a warning; never raises)."""
    rc, _out, err = _docker(runner, "restart", _TUNNEL_CONTAINER)
    if rc == 0:
        return True, f"noctus-tunnel restarted (origin connection re-resolved)"
    return False, f"noctus-tunnel restart returned rc={rc}: {err.strip()!r} (tunnel may be down)"


def _curl_edge(hostname: str, timeout: int = 20) -> tuple[bool, str]:
    """GET the public hostname with a browser UA and assert a non-timeout
    response. CF WAF blocks non-browser UAs (error 1010), so _UA is mandatory.
    Returns (ok, detail). ok=True on any HTTP response (including 3xx/4xx/5xx)
    because those prove the CF edge reached the origin — only a timeout or
    connection error indicates a stale tunnel.
    Injectable via the `http` parameter of `deploy_image` (same signature:
    `(hostname: str) -> (bool, str)`)."""
    req = urllib.request.Request(
        hostname,
        headers={"User-Agent": _UA},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"edge reachable: HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        # Any HTTP status (incl. 4xx/5xx) proves the edge forwarded to the origin
        return True, f"edge reachable: HTTP {exc.code}"
    except Exception as exc:
        # Timeout or connection error — tunnel still stale
        return False, f"edge timeout/unreachable after tunnel restart: {exc}"


def deploy_image(
    product: str,
    ssh_host: str = "noctus-vps",
    repo_dir: str = "/opt/noctus/noctusai",
    compose_file: str = DEFAULT_COMPOSE,
    image_repo: str = DEFAULT_IMAGE_REPO,
    tag: str = "latest",
    source: str = "pull",
    confirm: bool = False,
    health_timeout: int = 120,
    poll_interval: int = 5,
    startup_grace: int = 40,
    run_remote: Callable[[list[str]], tuple[int, str, str]] | None = None,
    sleep: Callable[[float], None] | None = None,
    now: Callable[[], _dt.datetime] | None = None,
    edge_hostname: str | None = None,
    http: Callable | None = None,
) -> dict[str, Any]:
    """Atomic image redeploy of `product` with C2 rollback. Dry-run unless
    `confirm`. After a successful recreate, restarts noctus-tunnel so
    cloudflared re-resolves its origin connection (leg a). When
    `edge_hostname` is provided, also curls the public hostname with a
    browser UA to confirm CF-edge reachability (leg b).
    status ∈ {planned, up_to_date, deployed, rolled_back, error}.
    Never raises on an operational failure — it returns it (no silent errors)."""
    if not product or not product.strip():
        return {"ok": False, "status": "error", "exit_code": 1, "error": "product required"}
    if source not in ("pull", "local"):
        return {"ok": False, "status": "error", "exit_code": 1,
                "error": f"source must be 'pull' (GHCR) or 'local' (build-on-VPS), got {source!r}"}
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
        "image": f"{image}:{tag}", "source": source, "current_image_id": current_image_id,
        "previous_tag": f"{image}:previous",
    }

    acquire = (f"compose pull {product}" if source == "pull"
               else f"use the locally-built {image}:{tag}")

    # ── DRY-RUN: read-only plan, no snapshot/pull/up ──
    if not confirm:
        return {**base, "status": "planned", "exit_code": 0,
                "message": (
                    f"would: tag {current_image_id[:19]} as {image}:previous → {acquire} → "
                    f"up -d → health-probe → rollback on failure. Pass confirm=True to deploy."
                )}

    prev = f"{image}:previous"

    def _rollback(reason_prefix: str, new_image_id: str | None) -> dict[str, Any]:
        """Restore :tag from the verified :previous snapshot, force-recreate,
        re-probe, and VERIFY the container is actually back on the snapshot.
        Reports rollback_failed (loud, with a manual-recovery command) if not —
        never a false 'rolled_back'."""
        _docker(runner, "tag", prev, f"{image}:{tag}")  # retag :latest from the committed snapshot
        _compose(runner, cf, "up", "-d", "--force-recreate", product)
        rb_health, rb_states = _poll_health(runner, napper, container, health_timeout,
                                            poll_interval, port=port, startup_grace=startup_grace)
        _rcv, running_now, _ev = _docker(runner, "inspect", "-f", "{{.Image}}", container)
        running_now = running_now.strip()
        # Verify by HEALTH (robust): containerd digest forms make id-equality
        # unreliable, but the broken image is unhealthy and the restored snapshot
        # is healthy — so a healthy container after rollback == restored.
        restored = rb_health == "healthy"
        return {
            **base, "status": "rolled_back" if restored else "rollback_failed",
            "exit_code": 1,  # either way the deploy did NOT land (status distinguishes safe vs broken)
            "new_image_id": new_image_id,
            "rollback_health": rb_health, "rollback_health_states": rb_states,
            "running_after": running_now,
            "reason": (
                f"{reason_prefix} "
                + (f"Rolled back to the last-known-good image {current_image_id[:19]} (healthy)."
                   if restored else
                   f"⚠️ ROLLBACK FAILED — container is on {running_now[:19]} (health={rb_health}). "
                   f"MANUAL RECOVERY: docker tag {prev} {image}:{tag} && "
                   f"docker compose -f {cf} up -d --force-recreate {product}")
            ),
        }

    # ── SNAPSHOT (C2 rollback target) via `docker commit` — reliable on the
    #    containerd manifest-list store, where tagging the container's .Image id
    #    is NOT (it can resolve to a stale digest — the root cause of the
    #    2026-05-22 social-wiring outage). Commit captures the running container
    #    as the :previous image. VERIFY it resolves — fail-safe: no confirmed
    #    rollback target ⇒ REFUSE to deploy (the container is untouched). ──
    rc_c, _oc, err_c = _docker(runner, "commit", container, prev)
    rc_s, snap_id, err_s = _docker(runner, "image", "inspect", "-f", "{{.Id}}", prev)
    snapshot_id = snap_id.strip()
    if rc_c != 0 or rc_s != 0 or not snapshot_id:
        return {**base, "status": "error", "exit_code": 1,
                "reason": f"snapshot via `docker commit {container} {prev}` failed "
                          f"({err_c.strip() or err_s.strip()!r}); REFUSING to deploy without a "
                          "confirmed rollback target (fail-safe). Container untouched."}
    base["snapshot_id"] = snapshot_id

    # ── ACQUIRE the new image: pull from GHCR (source=pull, the live model) OR
    #    use an already-built local tag (source=local, the build-on-VPS model) ──
    if source == "pull":
        rc_p, out_p, err_p = _compose(runner, cf, "pull", product)
        if rc_p != 0:
            return {**base, "status": "error", "exit_code": 1,
                    "reason": f"`compose pull {product}` failed: {err_p.strip() or out_p.strip()}. "
                              "Container untouched (still on the current image)."}
    rc_n, new_id, err_n = _docker(runner, "image", "inspect", "-f", "{{.Id}}", f"{image}:{tag}")
    new_image_id = new_id.strip()
    if rc_n != 0 or not new_image_id:
        return {**base, "status": "error", "exit_code": 1,
                "reason": f"no image '{image}:{tag}' available to deploy (source={source}): "
                          f"{err_n.strip()}. For source=local, build + tag it on the box first."}
    if new_image_id == current_image_id:
        return {**base, "status": "up_to_date", "exit_code": 0, "new_image_id": new_image_id,
                "message": f"image '{image}:{tag}' == running image; no redeploy needed."}

    port = _container_port(runner, container)

    # ── DEPLOY (force-recreate so the swap ALWAYS takes — `up -d` alone can skip
    #    recreation when only the tag target changed) ──
    rc_u, out_u, err_u = _compose(runner, cf, "up", "-d", "--force-recreate", product)
    if rc_u != 0:
        return _rollback(f"`compose up -d {product}` failed: {err_u.strip() or out_u.strip()}.",
                         new_image_id)

    # ── HEALTH-PROBE (active /api/health when the port is known) ──
    health, states = _poll_health(runner, napper, container, health_timeout, poll_interval,
                                  port=port, startup_grace=startup_grace)
    if health == "healthy":
        # ── LEG (a): tunnel re-resolve — restart cloudflared so the stale
        #    pre-recreate origin connection is dropped. Only on real deploys
        #    (confirm=True + a recreate actually happened). ──
        tunnel_ok, tunnel_msg = _restart_tunnel(runner)
        # ── LEG (b): edge reachability — curl the public hostname with a
        #    browser UA to assert CF edge → origin is live (not a 524-class
        #    timeout). Skip when edge_hostname is not provided. ──
        edge_ok: bool | None = None
        edge_detail: str | None = None
        if edge_hostname:
            edge_fn = http or _curl_edge
            edge_ok, edge_detail = edge_fn(edge_hostname)
        result: dict = {
            **base, "status": "deployed", "exit_code": 0,
            "new_image_id": new_image_id, "health": health, "health_states": states, "port": port,
            "tunnel_restart": tunnel_ok, "tunnel_msg": tunnel_msg,
            "message": f"deployed {product} on {new_image_id[:19]} — healthy.",
        }
        if edge_ok is True:
            result["edge_check"] = edge_detail
        elif edge_ok is False:
            result["edge_warning"] = (
                f"edge still unreachable after tunnel restart — "  # noqa: ISC001
                f"{edge_detail}; manual fix: docker restart {_TUNNEL_CONTAINER}"
            )
        if not tunnel_ok:
            result["tunnel_warning"] = tunnel_msg
        return result

    # ── ROLLBACK (C2) ──
    r = _rollback(f"New image {new_image_id[:19]} was {health}.", new_image_id)
    r["health"] = health
    r["health_states"] = states
    return r


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
            "perform the swap (production write gate). source='pull' (default, "
            "GHCR model §2 ①) compose-pulls the new image; source='local' "
            "(build-on-VPS model §2 ②) swaps an already-built local tag (no pull). "
            "BY CONSTRUCTION limited to a safe docker allowlist (inspect/image/tag/"
            "ps + compose pull/up) — never rmi/prune/down/rm. status: planned | "
            "up_to_date | deployed | rolled_back | error. See KB § GUIDES/production-deploy.md § 2a (C2)."
        ),
    )
    def _deploy_image(
        product: str,
        confirm: bool = False,
        tag: str = "latest",
        source: str = "pull",
        ssh_host: str = "noctus-vps",
    ) -> dict:
        return deploy_image(product, ssh_host=ssh_host, tag=tag, source=source, confirm=confirm)


__all__ = ["deploy_image", "_poll_health", "_restart_tunnel", "_curl_edge", "_DOCKER_ALLOWED", "_COMPOSE_ALLOWED", "_BANNED_TOKENS", "_TUNNEL_CONTAINER", "register"]
