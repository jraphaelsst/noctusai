"""Shared guard: every prod `docker compose` the toolkit runs must carry the Redis-auth override.

**The hazard (security review round 2, P1-1).** `deploy/fleet/compose.redis-auth.prod.yml` (rendered by
`noctus.dev.redis_acl`) is what moves a product onto the authenticated `noctus-redis-acl`. Tools that
recreate a service with only `-f docker-compose.prod.yml` (`deploy_image` deploy AND rollback,
`vps.recreate`, `ensure_product_url_roster`) silently put a locked product back on the old,
unauthenticated Redis (still running during the rollout) - no error, no log line.

Rule: when the override file exists beside the base compose file, EVERY compose call adds it as a
second `-f`. For a service the override lists, the generated per-service env file must exist and the
ACL'd Redis must be running, otherwise the call REFUSES loudly (never a quiet revert, never a service
booted without credentials). A probe that cannot be answered (ssh blip) also refuses: unknown is not "absent".
Escape hatch (explicit, returned in the payload): ``mode="off"``.

KB § PATTERNS/devops/redis-acl-lockdown.md
"""
from __future__ import annotations

import posixpath
from typing import Callable

OVERRIDE_NAME = "compose.redis-auth.prod.yml"
ENV_DIR = "redis-auth/env"
MARKER_REL = "redis-auth/cutover.services"
REDIS_ACL_CONTAINER = "noctus-redis-acl"
BREAKER_REDIS_CONTAINER = "noctus-breaker-redis"

Probe = Callable[[list[str]], tuple[int, str, str]]


def _listed(override_text: str) -> list[str]:
    """Services listed in the override (block between `services:` and top-level `networks:`)."""
    import re

    body = override_text.split("\nservices:\n", 1)[-1].split("\nnetworks:\n", 1)[0]
    return re.findall(r"^  ([a-z][a-z0-9\-]*):\s*$", body, flags=re.M)


def plan(probe: Probe, base_compose: str, product: str, mode: str = "auto") -> dict:
    """-> {'files': [extra -f paths], 'error': str|None, 'mode': ..., 'listed': bool, 'cut_over': [...]}.

    `probe` runs a command on the deploy host (list form); `base_compose` is the base file's path there.
    The override is HOST-LOCAL (rendered by `redis_acl render --services`), so "absent" is the normal state
    before a cutover and this guard is inert until the guardian deliberately renders it.
    """
    base = {"files": [], "error": None, "mode": mode, "listed": False, "cut_over": []}
    if mode == "off":
        return base
    if mode != "auto":
        return {**base, "error": f"redis-auth mode must be 'auto' or 'off', got {mode!r}"}
    fleet_dir = posixpath.dirname(base_compose)
    override = posixpath.join(fleet_dir, OVERRIDE_NAME)
    # DURABLE CUTOVER MARKER (`redis-auth/cutover.services`, written by `render --services`, cleared only by an
    # explicit empty `--services`): the override is a plain file and can be deleted/clobbered; without a second
    # record a lost override would make every recreate silently return a cut-over service to the old Redis.
    marker_path = posixpath.join(fleet_dir, MARKER_REL)
    rc_m, marker_text, err_m = probe(["cat", marker_path])
    if rc_m not in (0, 1):
        return {**base, "error": f"cutover marker probe failed (rc={rc_m}: {(err_m or '').strip()[:120]}) - refusing: "
                                 "an unverifiable marker must not be treated as absent"}
    marker = [x.strip() for x in (marker_text if rc_m == 0 else "").splitlines() if x.strip()]
    base = {**base, "marker": marker}
    rc, _o, err = probe(["test", "-f", override])
    if rc == 1:
        if marker:
            return {**base, "error": f"{marker_path} says {marker} are cut over to the authenticated Redis but "
                                     f"{override} is missing: refusing, a recreate would silently return them to the "
                                     "old Redis. Re-render: python mcp/noctusai/cli.py --redis-acl render "
                                     f"--redis-acl-write --redis-acl-services {','.join(marker)} (or clear the "
                                     "marker deliberately with --redis-acl-services '')."}
        return base
    if rc != 0:
        return {**base, "error": f"redis-auth override probe failed (rc={rc}: {(err or '').strip()[:120]}) - refusing: "
                                 "an unverifiable override must not be treated as absent"}
    rc, text, err = probe(["cat", override])
    if rc != 0:
        return {**base, "error": f"redis-auth override read failed (rc={rc}: {(err or '').strip()[:120]}) - refusing"}
    cut_over = _listed(text)
    unlisted = [x for x in marker if x not in cut_over]
    if unlisted:
        return {**base, "files": [override], "cut_over": cut_over, "listed": product in cut_over,
                "error": f"{marker_path} says {marker} are cut over but {override} lists only {cut_over} "
                         f"(missing {unlisted}): refusing, those services would silently return to the old Redis. "
                         "Re-render with the full list, or clear the marker deliberately with --redis-acl-services ''."}
    base = {**base, "files": [override], "cut_over": cut_over, "listed": product in cut_over}
    # EVERY listed service's generated env file must exist: compose resolves the whole project, so one missing file
    # breaks (or silently skips) a recreate of ANY service.
    missing = []
    for svc in cut_over:
        env_file = posixpath.join(fleet_dir, ENV_DIR, f"{svc}.env")
        rc, _o, _e = probe(["test", "-s", env_file])
        if rc != 0:
            missing.append(env_file)
    if missing:
        return {**base, "error": f"{override} lists {cut_over} but generated env file(s) {missing} are missing/empty. "
                                 "Render them first: python mcp/noctusai/cli.py --redis-acl render --redis-acl-write "
                                 f"--redis-acl-services {','.join(cut_over)}. Refusing to recreate: a service would "
                                 "silently fall back to the unauthenticated Redis."}
    if base["listed"]:
        for container in (REDIS_ACL_CONTAINER, BREAKER_REDIS_CONTAINER):
            rc, out, _e = probe(["docker", "inspect", "-f", "{{.State.Running}}", container])
            if rc != 0 or out.strip() != "true":
                return {**base, "error": f"{override} lists {product} but {container} is not running - refusing: the "
                                         "recreated service would point at a Redis that is not there (rollout step 2 first)."}
    return base


def compose_cmd(base_compose: str, extra_files: list[str], *rest: str) -> list[str]:
    cmd = ["docker", "compose", "-f", base_compose]
    for f in extra_files:
        cmd += ["-f", f]
    return cmd + list(rest)


def record_off(tool: str, product: str, files: list[str], record=None) -> bool:
    """`mode="off"` is a deliberate hole in the guard: leave a ledger row every time it is used (best effort,
    never raises; the caller reports `recorded` in the payload)."""
    try:
        if record is None:
            from . import auto_improvement

            record = auto_improvement.log_entry
        r = record(scope="broad", kind="finding", target="deploy/fleet/compose.redis-auth.prod.yml",
                   agent="devops-engineer",
                   description=(f"{tool}(redis_auth='off') used for {product}: the Redis-auth override was NOT added "
                                f"to the compose call (override files that would have applied: {files or 'none'}). "
                                "A recreate under this mode can return a cut-over service to the unauthenticated Redis."))
        return bool(r.get("ok", True)) if isinstance(r, dict) else True
    except Exception:  # noqa: BLE001 - audit trail must never break a deploy
        return False
