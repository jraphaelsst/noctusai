"""Fleet container control — switch a product's container ON/OFF (start /
stop / restart) and read live status, from a control-plane host.

This is a **control-plane** domain primitive: a single product (Core) hosts an
admin "Fleet Control" panel, but the container-control logic itself is
product-agnostic — it operates the SAME docker host whether that's a developer's
laptop (local dev) or the production VPS (the Core container shares its host's
docker socket). Zero per-product code: every product is a uniform target named
``noctus-<slug>``.

**Security — this is RCE-adjacent.** The Real controller shells docker, so the
attack surface is the (verb, slug) pair. Both are validated against a HARD
ALLOWLIST *before* anything is shelled:

- ``verb`` ∈ {``start``, ``stop``, ``restart``} — nothing else (no ``rm`` /
  ``rmi`` / ``exec`` / ``down`` / ``run`` / arbitrary args).
- ``slug`` is a REGISTERED product (from ``parse_products_registry`` —
  ``start.sh``'s single source of truth) AND matches a strict charset
  ``[a-z0-9][a-z0-9-]*``.

The target container name is then *constructed* by the module as
``noctus-<slug>`` — the caller never supplies a raw container name or any free
text that reaches the command line. A colocated test asserts no banned token
can ever be emitted in the argv.

Shape: Protocol + Fake + Real + factory, mirroring
``KB § PATTERNS/seed-fake-real-adapter.md`` (this is IO-touching). The Real
controller takes an injected ``runner`` seam (``subprocess.run`` by default) so
tests assert the emitted argv with zero real docker.
"""
from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Callable, List, Optional, Protocol

from noctusai_lib.config.cors_registry import parse_products_registry

logger = logging.getLogger(__name__)

# ── Hard allowlist ─────────────────────────────────────────────────
# The ONLY verbs this module will ever shell. Anything else is rejected
# before reaching the command line. A colocated test asserts no destructive
# docker subcommand (rm/rmi/exec/down/run/kill/prune) is reachable.
ALLOWED_VERBS: tuple[str, ...] = ("start", "stop", "restart")

# Product container naming convention (matches docker-compose `container_name`).
CONTAINER_PREFIX = "noctus-"

# Strict slug charset — defence-in-depth alongside the registry membership
# check. Even a registered slug must look like a slug (no spaces, no shell
# metacharacters). Mirrors the cors_registry slug grammar.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Tokens the module must NEVER emit (asserted by the colocated test). The Real
# controller only ever runs `docker ps` (status) and `docker {start|stop|restart}
# noctus-<slug>` (actions) — none of these destroy an image, exec into a
# container, or tear the fleet down.
BANNED_TOKENS: tuple[str, ...] = (
    "rm", "rmi", "exec", "down", "run", "kill", "prune",
    "create", "cp", "commit", "build", "push", "pull", "login", "-v",
)


class FleetControlError(ValueError):
    """Raised when a (verb, slug) pair fails the hard allowlist.

    A ``ValueError`` subclass so callers (e.g. the Core router) can map it to a
    400/422 without importing this module's exact type.
    """


@dataclass(frozen=True)
class ContainerStatus:
    """Live status of a single product container."""

    slug: str
    container: str          # noctus-<slug>
    state: str              # "running" | "exited" | "absent" | <docker state>
    health: str             # "healthy" | "unhealthy" | "starting" | "" (none)
    running: bool

    def as_dict(self) -> dict:
        return {
            "slug": self.slug,
            "container": self.container,
            "state": self.state,
            "health": self.health,
            "running": self.running,
        }


@dataclass(frozen=True)
class ActResult:
    """Result of a start/stop/restart action."""

    slug: str
    container: str
    verb: str
    ok: bool
    message: str

    def as_dict(self) -> dict:
        return {
            "slug": self.slug,
            "container": self.container,
            "verb": self.verb,
            "ok": self.ok,
            "message": self.message,
        }


# ── Allowlist validation (shared by Real + any future controller) ──
def validate_action(slug: str, verb: str, registered_slugs: Optional[set[str]] = None) -> str:
    """Validate (slug, verb) against the hard allowlist and return the safe
    container name ``noctus-<slug>``.

    Raises :class:`FleetControlError` if the verb is not allowlisted, the slug
    fails the charset grammar, or the slug is not a registered product. This is
    the single chokepoint — both the Real controller and tests go through it, so
    the security invariant lives in exactly one place.

    Args:
        slug: product slug (must be registered AND match the slug grammar).
        verb: one of :data:`ALLOWED_VERBS`.
        registered_slugs: the set of valid product slugs. Defaults to the live
            registry (``parse_products_registry``). Injectable for tests.
    """
    if verb not in ALLOWED_VERBS:
        raise FleetControlError(
            f"verb {verb!r} is not allowed (allowed: {', '.join(ALLOWED_VERBS)})"
        )
    if not isinstance(slug, str) or not _SLUG_RE.match(slug):
        raise FleetControlError(f"slug {slug!r} is not a valid product slug")
    if registered_slugs is None:
        registered_slugs = {e["slug"] for e in parse_products_registry()}
    if slug not in registered_slugs:
        raise FleetControlError(
            f"slug {slug!r} is not a registered product"
        )
    return f"{CONTAINER_PREFIX}{slug}"


class ContainerController(Protocol):
    """Control-plane Protocol — read status + act on product containers."""

    def status(self) -> List[ContainerStatus]:  # type: ignore[empty-body]
        """Live status of every registered product container."""

    def act(self, slug: str, verb: str) -> ActResult:  # type: ignore[empty-body]
        """start / stop / restart the ``noctus-<slug>`` container."""


# ── Fake (tests + dev-without-socket) ──────────────────────────────
class FakeContainerController:
    """In-memory controller — no docker. Seeds a running/stopped state per
    registered slug and mutates it on ``act``. Used by tests and as the
    default when no real docker socket is present.

    Still routes ``act`` through :func:`validate_action`, so the allowlist
    is exercised even in the Fake (a stop/start of an unregistered slug or a
    bad verb raises exactly as the Real would).
    """

    def __init__(self, slugs: Optional[List[str]] = None,
                 registered_slugs: Optional[set[str]] = None):
        if slugs is None:
            slugs = [e["slug"] for e in parse_products_registry()]
        self._registered = registered_slugs if registered_slugs is not None else set(slugs)
        # default everyone "running, healthy" so the panel has content
        self._state: dict[str, dict] = {
            s: {"running": True, "state": "running", "health": "healthy"} for s in slugs
        }

    def status(self) -> List[ContainerStatus]:
        out: List[ContainerStatus] = []
        for slug, st in self._state.items():
            out.append(ContainerStatus(
                slug=slug,
                container=f"{CONTAINER_PREFIX}{slug}",
                state=st["state"],
                health=st["health"],
                running=st["running"],
            ))
        return out

    def act(self, slug: str, verb: str) -> ActResult:
        container = validate_action(slug, verb, registered_slugs=self._registered)
        st = self._state.setdefault(
            slug, {"running": False, "state": "exited", "health": ""}
        )
        if verb == "start":
            st.update(running=True, state="running", health="healthy")
        elif verb == "stop":
            st.update(running=False, state="exited", health="")
        elif verb == "restart":
            st.update(running=True, state="running", health="healthy")
        return ActResult(
            slug=slug, container=container, verb=verb, ok=True,
            message=f"{verb} {container} (fake)",
        )


# ── Real (shells docker against the host socket) ───────────────────
def _run_default(cmd: List[str]) -> tuple[int, str, str]:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, (r.stdout or ""), (r.stderr or "")


class DockerComposeController:
    """Real controller — operates the docker host the process can reach
    (the docker socket bind-mounted into the Core container, or the dev
    laptop's local docker).

    Status: ``docker ps -a --format '{{.Names}}\\t{{.State}}\\t{{.Status}}'``
    filtered to the ``noctus-`` prefix and joined back to the registered slug
    set (so an absent container shows ``state="absent"``).

    Actions: ``docker {start|stop|restart} noctus-<slug>`` — the verb + the
    constructed container name are the ONLY non-constant argv tokens, and both
    are validated by :func:`validate_action` before the call. The ``runner``
    seam (``subprocess.run`` by default) is injectable so tests assert the exact
    emitted argv with zero real docker.
    """

    def __init__(self, runner: Optional[Callable[[List[str]], tuple[int, str, str]]] = None,
                 registered_slugs: Optional[set[str]] = None):
        self._run = runner or _run_default
        self._registered = (
            registered_slugs if registered_slugs is not None
            else {e["slug"] for e in parse_products_registry()}
        )

    def _slug_of(self, container: str) -> Optional[str]:
        if not container.startswith(CONTAINER_PREFIX):
            return None
        slug = container[len(CONTAINER_PREFIX):]
        return slug if slug in self._registered else None

    def status(self) -> List[ContainerStatus]:
        rc, out, err = self._run([
            "docker", "ps", "-a", "--format",
            "{{.Names}}\t{{.State}}\t{{.Status}}",
        ])
        if rc != 0:
            logger.warning("fleet_control: docker ps failed (rc=%s): %s", rc, err.strip())
        seen: dict[str, ContainerStatus] = {}
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            name, state, status_text = parts[0], parts[1], parts[2]
            slug = self._slug_of(name)
            if slug is None:
                continue
            health = (
                "healthy" if "(healthy)" in status_text
                else "unhealthy" if "(unhealthy)" in status_text
                else "starting" if "(health: starting)" in status_text
                else ""
            )
            seen[slug] = ContainerStatus(
                slug=slug, container=name, state=state, health=health,
                running=(state == "running"),
            )
        # Registered products with no container at all → "absent".
        out_list: List[ContainerStatus] = []
        for slug in sorted(self._registered):
            if slug in seen:
                out_list.append(seen[slug])
            else:
                out_list.append(ContainerStatus(
                    slug=slug, container=f"{CONTAINER_PREFIX}{slug}",
                    state="absent", health="", running=False,
                ))
        return out_list

    def act(self, slug: str, verb: str) -> ActResult:
        # HARD ALLOWLIST — raises FleetControlError before any shelling.
        container = validate_action(slug, verb, registered_slugs=self._registered)
        rc, out, err = self._run(["docker", verb, container])
        if rc != 0:
            msg = (err or out).strip() or f"docker {verb} {container} failed"
            logger.warning("fleet_control: %s", msg)
            return ActResult(slug=slug, container=container, verb=verb, ok=False, message=msg)
        return ActResult(
            slug=slug, container=container, verb=verb, ok=True,
            message=f"{verb} {container} ok",
        )


# ── Factory ────────────────────────────────────────────────────────
def get_fleet_controller(
    *,
    use_real: Optional[bool] = None,
    runner: Optional[Callable[[List[str]], tuple[int, str, str]]] = None,
    registered_slugs: Optional[set[str]] = None,
) -> ContainerController:
    """Return the controller for this host.

    Resolution:
      - ``use_real=True``  → :class:`DockerComposeController` (shells docker).
      - ``use_real=False`` → :class:`FakeContainerController` (in-memory).
      - ``use_real=None``  → auto: Real iff the docker socket is present
        (``/var/run/docker.sock``), else Fake. This is the "dev laptop with
        docker vs. CI/test sandbox" switch; the Core container is given the
        socket explicitly (compose bind-mount) so it resolves Real on the VPS.

    A ``runner`` (injected) forces the Real controller regardless — that's the
    test seam.
    """
    if runner is not None:
        return DockerComposeController(runner=runner, registered_slugs=registered_slugs)
    if use_real is None:
        from pathlib import Path
        use_real = Path("/var/run/docker.sock").exists()
    if use_real:
        return DockerComposeController(registered_slugs=registered_slugs)
    return FakeContainerController(registered_slugs=registered_slugs)


__all__ = [
    "ALLOWED_VERBS",
    "BANNED_TOKENS",
    "CONTAINER_PREFIX",
    "FleetControlError",
    "ContainerStatus",
    "ActResult",
    "ContainerController",
    "FakeContainerController",
    "DockerComposeController",
    "validate_action",
    "get_fleet_controller",
]
