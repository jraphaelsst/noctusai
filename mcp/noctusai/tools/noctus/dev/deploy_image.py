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
  5. SWAP-VERIFY — a healthy probe does NOT prove the swap landed (2026-08-13:
     a healthy OLD container, never actually recreated, would have satisfied
     every earlier step). Re-inspect the RUNNING container's own image id +
     baked revision label; refuse to report `deployed` if either doesn't
     verifiably match what was intended.
  6. ROLLBACK on health failure — retag the snapshot id back to `:<tag>` +
     `up -d` → production returns to the last-known-good image; re-probe to
     confirm.

DRY-RUN by default (read-only: reports the current image + the plan); pass
confirm=True to perform the swap (the 412-style production write gate). BY
CONSTRUCTION it only runs a safe docker allowlist — `inspect`/`image`/`tag`/`ps`
and `docker compose {pull,up}` — never `rmi`/`prune`/`down`/`rm`/`system`, so it
can neither delete the rollback image nor tear the fleet down (a colocated test
asserts no banned token is ever emitted).

IO is injectable (`run_remote`, `sleep`, `now`) so the colocated test drives
every path — planned / up_to_date / deployed / swap_unverified / rolled_back /
error — with zero real SSH and zero real waiting. `noctus.dev.deploy_verify`
is the sibling INDEPENDENT witness — callable standalone, with no dependency
on this tool having run at all (the exact property the 2026-08-13 incident
was missing: this tool timed out and disconnected mid-swap, and nothing but a
manual `docker inspect` caught it).
"""
from __future__ import annotations

import datetime as _dt
import re
import time as _time
import urllib.error
import urllib.request
from typing import Any, Callable

from ._vps_ssh import run_remote as _throttled_ssh

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
# Read-only git subcommands the PROD-PIN ancestry guard (below) may run on the
# VPS checkout — never reset/checkout/clean/push. Same allowlist shape as
# noctus.dev.release's `_git`, scoped to this tool's one read-only use.
_GIT_ALLOWED = frozenset({"fetch", "rev-parse", "merge-base"})
# Asserted-absent by the colocated safety test (defense in depth beyond the
# allowlists): the tool must never emit any of these, across BOTH the docker
# and the git command surfaces.
_BANNED_TOKENS = ("rmi", "prune", "system", "down", "kill", "volume", "stop",
                  "reset", "checkout", "restore", "clean")

DEFAULT_COMPOSE = "deploy/fleet/docker-compose.prod.yml"
DEFAULT_IMAGE_REPO = "ghcr.io/jraphaelsst"
DEFAULT_REPO_DIR = "/opt/noctus/noctusai"

# The OCI label build-and-push.sh bakes into every image (`git rev-parse HEAD`
# at build time) — how the PROD-PIN ancestry guard learns which commit a
# pulled `:latest` actually came from, since a floating tag carries no git
# identity on its own.
_REVISION_LABEL = "org.opencontainers.image.revision"

# Container health classes (Go-template returns Health.Status, else State.Status).
_GOOD = frozenset({"healthy", "running"})
_BAD = frozenset({"unhealthy", "exited", "dead"})


def _run_remote_default(ssh_host: str, cmd: list[str]) -> tuple[int, str, str]:
    # Routed through the shared throttled + circuit-broken SSH chokepoint so a
    # transient edge blip can never escalate into a fail2ban ban (`_vps_ssh`).
    return _throttled_ssh(ssh_host, cmd)


def _docker(runner, *args) -> tuple[int, str, str]:
    """Run a non-compose docker command — only if on the safe allowlist."""
    sub = args[0] if args else ""
    if sub not in _DOCKER_ALLOWED:
        raise ValueError(f"deploy_image: docker '{sub}' not on the safe allowlist {sorted(_DOCKER_ALLOWED)}")
    return runner(["docker", *args])


def _git(runner, repo_dir: str, *args) -> tuple[int, str, str]:
    """Run a read-only git subcommand against the VPS checkout at `repo_dir` —
    only if on the safe allowlist (fetch / rev-parse / merge-base). Used
    exclusively by the PROD-PIN ancestry guard; never reset/checkout/push."""
    sub = args[0] if args else ""
    if sub not in _GIT_ALLOWED:
        raise ValueError(f"deploy_image: git '{sub}' not on the safe allowlist {sorted(_GIT_ALLOWED)}")
    return runner(["git", "-C", repo_dir, *args])


def _image_revision(runner, image_ref: str) -> str | None:
    """The git sha baked into `image_ref`'s `org.opencontainers.image.revision`
    OCI label (set by build-and-push.sh at build time, per commit), or None
    when the label is absent/empty — e.g. an image built before this guard
    existed, or built by a path other than build-and-push.sh."""
    rc, out, _e = _docker(runner, "inspect", "-f",
                          f'{{{{ index .Config.Labels "{_REVISION_LABEL}" }}}}', image_ref)
    val = (out or "").strip()
    return val if rc == 0 and val and val != "<no value>" else None


def _prod_ancestor_check(runner, repo_dir: str, sha: str,
                         prod_ref: str = "origin/prod") -> tuple[bool | None, str]:
    """True/False whether `sha` is an ancestor of (or equal to) `prod_ref` on
    the VPS git checkout at `repo_dir`. Returns (None, detail) — UNVERIFIABLE,
    never a guess — when the fetch or the ref itself can't be resolved; the
    caller treats None the same as a hard refusal (fail-closed, no silent
    errors: 'couldn't check' is not 'checked and it's fine')."""
    rc_f, _of, err_f = _git(runner, repo_dir, "fetch", "origin", "--quiet")
    if rc_f != 0:
        return None, f"git fetch failed on the VPS checkout at {repo_dir}: {err_f.strip()}"
    rc_p, out_p, err_p = _git(runner, repo_dir, "rev-parse", "--verify", "--quiet", prod_ref)
    if rc_p != 0 or not out_p.strip():
        return None, f"cannot resolve '{prod_ref}' on the VPS checkout: {err_p.strip() or out_p.strip()}"
    rc_a, _oa, err_a = _git(runner, repo_dir, "merge-base", "--is-ancestor", sha, prod_ref)
    if rc_a not in (0, 1):
        return None, f"'git merge-base --is-ancestor {sha} {prod_ref}' errored unexpectedly (rc={rc_a}): {err_a.strip()}"
    is_ancestor = rc_a == 0
    return is_ancestor, (
        f"{sha[:12]} is {'an ancestor of' if is_ancestor else 'NOT an ancestor of'} {prod_ref}"
    )


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
    repo_dir: str = DEFAULT_REPO_DIR,
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
    skip_ancestry_check: bool = False,
) -> dict[str, Any]:
    """Atomic image redeploy of `product` with C2 rollback. Dry-run unless
    `confirm`. After a successful recreate, restarts noctus-tunnel so
    cloudflared re-resolves its origin connection (leg a). When
    `edge_hostname` is provided, also curls the public hostname with a
    browser UA to confirm CF-edge reachability (leg b).

    PROD-PIN ancestry guard (2026-07-20): when `tag == 'latest'` and
    `source == 'pull'`, a `:latest` pull is a floating GHCR tag that moves on
    every `main` push — independent of the `prod` promote-gate
    (KB § GUIDES/production-deploy.md § 2b). Before recreating the container,
    this reads the pulled image's `org.opencontainers.image.revision` OCI
    label (baked by build-and-push.sh) and REFUSES to deploy — fail-closed,
    container untouched — unless that commit is a verified ancestor of
    `origin/prod` on the VPS checkout. An unlabeled image or an unresolvable
    `origin/prod` also refuses (unverifiable ≠ safe). Pass
    `skip_ancestry_check=True` to override deliberately (e.g. a pinned
    `tag=<sha>` deploy never needs it — the tag itself already IS the
    verifiable identity; source='local' also skips it — a build-on-VPS image
    is a deliberate human action taken right there on the box).

    SWAP-VERIFY (2026-08-13): a healthy probe alone never proves the swap
    landed — the 2026-08-13 incident was a healthy OLD container that
    `compose up -d` silently never recreated. After a healthy probe, this
    re-inspects the RUNNING container's own image id + baked revision label
    (not the pulled image/tag) and REFUSES to report `deployed` — status
    `swap_unverified`, no auto-rollback (an unverified swap could equally be
    a transient inspect glitch on a genuinely-landed container; guessing at
    a correction here would be exactly the bug this guards against) — unless
    both verifiably match what was intended. `noctus.dev.deploy_verify` is
    the independent, standalone check for the same ground truth.

    status ∈ {planned, up_to_date, deployed, swap_unverified, rolled_back, error}.
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

    # ── PROD-PIN ancestry guard — only the risky floating-tag pull path.
    #    A pinned tag=<sha> deploy already carries verifiable identity in the
    #    tag itself; source='local' is a deliberate on-box human action. ──
    if tag == "latest" and source == "pull" and not skip_ancestry_check:
        revision = _image_revision(runner, f"{image}:{tag}")
        if not revision:
            return {**base, "status": "error", "exit_code": 1, "new_image_id": new_image_id,
                    "reason": (
                        f"PROD-PIN GUARD: pulled '{image}:{tag}' carries no "
                        f"'{_REVISION_LABEL}' OCI label (image predates the guard, or "
                        "was built by a path other than build-and-push.sh) — cannot "
                        "verify its source commit is an ancestor of origin/prod. "
                        "REFUSING (fail-closed): a floating :latest can carry an "
                        "un-promoted main tip (KB § GUIDES/production-deploy.md § 2b). "
                        "Deploy a verified tag=<sha> instead, or pass "
                        "skip_ancestry_check=True to override deliberately. Container "
                        "untouched."
                    )}
        is_ancestor, detail = _prod_ancestor_check(runner, repo_dir, revision)
        if is_ancestor is None:
            return {**base, "status": "error", "exit_code": 1, "new_image_id": new_image_id,
                    "source_revision": revision,
                    "reason": f"PROD-PIN GUARD: ancestry unverifiable ({detail}) — REFUSING "
                              "(fail-closed; 'couldn't check' is not 'checked and it's fine'). "
                              "Container untouched. Pass skip_ancestry_check=True to override "
                              "deliberately."}
        if not is_ancestor:
            return {**base, "status": "error", "exit_code": 1, "new_image_id": new_image_id,
                    "source_revision": revision,
                    "reason": (
                        f"PROD-PIN GUARD: refusing to deploy — {detail}. The pulled "
                        f"':latest' image (commit {revision[:12]}) was built from a "
                        "commit not yet promoted to origin/prod — deploying it would be "
                        "exactly the 2026-07-16 PROD-PIN HOLE (KB § "
                        "GUIDES/production-deploy.md § 2b). Promote it first "
                        "(noctus.dev.release stage='promote'), or pass "
                        "skip_ancestry_check=True to override deliberately. Container "
                        "untouched."
                    )}
        base["source_revision"] = revision

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
        # ── SWAP-VERIFY (2026-08-13 phantom-deploy guard) — a HEALTHY probe
        #    only proves *some* container answers on that port; it does NOT
        #    prove the swap actually happened. The 2026-08-13 incident: the
        #    OLD container was healthy and "Up 2 days" — `compose up -d` had
        #    silently never recreated it, and this exact code path was about
        #    to return status='deployed' anyway. Re-inspect the RUNNING
        #    container (not the pulled image) for its actual id + its own
        #    baked revision label — the only two things that prove a
        #    recreate landed. `_image_revision` on a container name reads
        #    `.Config.Labels` off the CONTAINER's own inspect, same as it
        #    does for an image ref. ──
        rc_ri, running_image_id, _e_ri = _docker(runner, "inspect", "-f", "{{.Image}}", container)
        running_image_id = running_image_id.strip()
        landed_revision = _image_revision(runner, container)
        intended_revision = base.get("source_revision") or _image_revision(runner, f"{image}:{tag}")
        swap_landed = running_image_id == new_image_id
        revision_landed = intended_revision is None or landed_revision == intended_revision
        if not (swap_landed and revision_landed):
            # REFUSE to report success on an unverified swap (no silent
            # errors) — and do NOT auto-rollback: we cannot tell "the swap
            # silently no-op'd" from "a transient inspect glitch just
            # misread a genuinely-landed container", so guessing at a
            # corrective action here would be exactly as unsafe as the bug
            # this guards against. Report every observed fact and name the
            # independent witness that resolves it.
            return {
                **base, "status": "swap_unverified", "exit_code": 1,
                "new_image_id": new_image_id, "health": health, "health_states": states,
                "running_image_id": running_image_id, "landed_revision": landed_revision,
                "intended_revision": intended_revision,
                "reason": (
                    f"`compose up -d --force-recreate {product}` returned success and "
                    f"the health probe reports healthy, but the RUNNING container does "
                    f"not verifiably match what was deployed "
                    f"(running_image_id={running_image_id[:19]!r} vs "
                    f"intended={new_image_id[:19]!r}; landed_revision="
                    f"{(landed_revision or 'none')[:12]!r} vs intended_revision="
                    f"{(intended_revision or 'none')[:12]!r}). This is the exact "
                    "2026-08-13 phantom-deploy shape: a healthy container that is NOT "
                    "the one just deployed. REFUSING to report 'deployed'. Do NOT "
                    "assume this is safe or broken — run `noctus.dev.deploy_verify` "
                    "(independent of this call) to get ground truth, then decide "
                    "manually whether to retry the recreate or investigate."
                ),
            }
        base["running_image_id"] = running_image_id
        base["landed_revision"] = landed_revision
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
            "ps + compose pull/up) — never rmi/prune/down/rm. PROD-PIN ancestry guard "
            "(2026-07-20): a tag='latest' + source='pull' deploy REFUSES (fail-closed, "
            "container untouched) unless the pulled image's baked git revision is a "
            "verified ancestor of origin/prod — closes the hole where a floating "
            ":latest can carry an un-promoted main tip; pass skip_ancestry_check=True "
            "to override deliberately. SWAP-VERIFY (2026-08-13): a healthy probe alone "
            "never proves the swap landed — after a healthy probe this re-inspects the "
            "RUNNING container's own image id + revision label (not the pulled tag) and "
            "REFUSES status='deployed' (returns 'swap_unverified' instead, no "
            "auto-rollback) unless both verifiably match. status: planned | up_to_date | "
            "deployed | swap_unverified | rolled_back | error. Independent standalone "
            "witness for the same ground truth: noctus.dev.deploy_verify. See "
            "KB § GUIDES/production-deploy.md § 2a (C2)."
        ),
    )
    def _deploy_image(
        product: str,
        confirm: bool = False,
        tag: str = "latest",
        source: str = "pull",
        ssh_host: str = "noctus-vps",
        skip_ancestry_check: bool = False,
    ) -> dict:
        return deploy_image(product, ssh_host=ssh_host, tag=tag, source=source, confirm=confirm,
                            skip_ancestry_check=skip_ancestry_check)


__all__ = ["deploy_image", "_poll_health", "_restart_tunnel", "_curl_edge", "_image_revision",
          "_prod_ancestor_check", "_git", "_DOCKER_ALLOWED", "_COMPOSE_ALLOWED", "_GIT_ALLOWED",
          "_BANNED_TOKENS", "_TUNNEL_CONTAINER", "register"]
