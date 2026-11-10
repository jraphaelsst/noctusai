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
REDIS_ACL_CONTAINER = "noctus-redis-acl"

Probe = Callable[[list[str]], tuple[int, str, str]]


def plan(probe: Probe, base_compose: str, product: str, mode: str = "auto") -> dict:
    """-> {'files': [extra -f paths], 'error': str|None, 'mode': ..., 'listed': bool}.

    `probe` runs a command on the deploy host (list form); `base_compose` is the base file's path there.
    """
    if mode == "off":
        return {"files": [], "error": None, "mode": "off", "listed": False}
    if mode != "auto":
        return {"files": [], "error": f"redis-auth mode must be 'auto' or 'off', got {mode!r}", "mode": mode, "listed": False}
    fleet_dir = posixpath.dirname(base_compose)
    override = posixpath.join(fleet_dir, OVERRIDE_NAME)
    rc, _o, err = probe(["test", "-f", override])
    if rc == 1:
        return {"files": [], "error": None, "mode": "auto", "listed": False}
    if rc != 0:
        return {"files": [], "mode": "auto", "listed": False,
                "error": f"redis-auth override probe failed (rc={rc}: {(err or '').strip()[:120]}) - refusing: "
                         "an unverifiable override must not be treated as absent"}
    rc, _o, err = probe(["grep", "-q", f"^  {product}:$", override])
    if rc == 1:
        return {"files": [override], "error": None, "mode": "auto", "listed": False}
    if rc != 0:
        return {"files": [], "mode": "auto", "listed": False,
                "error": f"redis-auth override read failed (rc={rc}) - refusing"}
    env_file = posixpath.join(fleet_dir, ENV_DIR, f"{product}.env")
    rc, _o, _e = probe(["test", "-s", env_file])
    if rc != 0:
        return {"files": [override], "mode": "auto", "listed": True,
                "error": f"{override} lists {product} but its generated env file {env_file} is missing/empty "
                         f"(rc={rc}). Render it first: python mcp/noctusai/cli.py --redis-acl render --redis-acl-write. "
                         "Refusing to recreate: this service would silently fall back to the unauthenticated Redis."}
    rc, out, _e = probe(["docker", "inspect", "-f", "{{.State.Running}}", REDIS_ACL_CONTAINER])
    if rc != 0 or out.strip() != "true":
        return {"files": [override], "mode": "auto", "listed": True,
                "error": f"{override} lists {product} but {REDIS_ACL_CONTAINER} is not running - refusing: the "
                         "recreated service would point at a Redis that is not there (step 2 of the rollout first)."}
    return {"files": [override], "error": None, "mode": "auto", "listed": True}


def compose_cmd(base_compose: str, extra_files: list[str], *rest: str) -> list[str]:
    cmd = ["docker", "compose", "-f", base_compose]
    for f in extra_files:
        cmd += ["-f", f]
    return cmd + list(rest)
