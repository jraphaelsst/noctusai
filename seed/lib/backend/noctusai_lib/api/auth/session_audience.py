"""Which product (if any) a Supabase session was minted for -- the S2 registry read side.

Design: ``project-history/plans/sso-session-lifecycle-2026-11.md`` section B (B1).

Core's ``/api/sso/session`` mints a FRESH session per product entry and registers
``session_id -> product_slug`` in ``public.sso_product_sessions`` (service-only table). Tokens
carry no product claim, so this module resolves it: the access token's ``session_id`` claim is read
(unverified -- the provider has ALREADY accepted the token by the time we ask) and looked up in the
registry. The answer rides the existing 30 s verified-token cache (``TokenCache``), so it is one
indexed PK read per token per process per 30 s.

Modes (``Settings.sso_product_session_mode`` / env ``SSO_PRODUCT_SESSION_MODE``):

* ``off``      -- nothing resolved, nothing logged.
* ``observe``  -- DEFAULT. Resolve ``AuthContext.session_product``; core logs
                  ``product_session_on_core_route`` once per request when a registered product
                  session reaches a route NOT tagged :func:`product_session_ok`. NEVER blocks. A
                  registry outage logs ``sso_registry_unavailable`` and continues as "unknown"
                  (never a 401, never a 403).
* ``enforce``  -- NOT IMPLEMENTED (slice S8). Starting with it is refused. When built, enforce
                  fails CLOSED with **503** (not 401: a 401 makes every seed SPA declare the session
                  dead and log the user out) when the registry cannot be read, and 403
                  ``sessao_de_produto`` on an untagged core route.
                  NOC-REMEDIATE[sso-session-enforce]: S8 -- implement enforce + the 503 branch in
                  :func:`resolve_session_product`. -- 2026-11-08
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Literal, Optional
from uuid import UUID

import jwt

from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.auth.token_cache import TokenCache

logger = logging.getLogger(__name__)

Mode = Literal["off", "observe", "enforce"]
REGISTRY_TABLE = "sso_product_sessions"

_mode: Mode = "off"  # unconfigured process (unit tests, tools): nothing happens
_is_core: bool = False


def parse_mode(value: Any, *, allow_enforce: bool = False) -> Mode:
    """Validate a mode string. Unknown values raise (a typo must not silently disable the control)."""
    mode = str(value or "observe").strip().lower()
    if mode not in ("off", "observe", "enforce"):
        raise ValueError(f"SSO_PRODUCT_SESSION_MODE must be off|observe|enforce, got {value!r}")
    if mode == "enforce" and not allow_enforce:
        # NOC-REMEDIATE[sso-session-enforce]: S8 lifts this guard together with the enforce branch. -- 2026-11-08
        raise RuntimeError(
            "SSO_PRODUCT_SESSION_MODE=enforce is not implemented yet (slice S8); use observe or off"
        )
    return mode  # type: ignore[return-value]


def configure_session_audience(*, mode: Any, is_core: bool) -> Mode:
    """Set the process mode once at app build (``create_product_app``). Raises on ``enforce``."""
    global _mode, _is_core
    _mode = parse_mode(mode)
    _is_core = bool(is_core)
    return _mode


def product_session_mode() -> Mode:
    return _mode


def product_session_ok(reason: str) -> Callable[[Callable], Callable]:
    """Tag a CORE route as legitimately callable with a product session. A no-op marker today
    (S7 tags routes, S8 enforces); it returns the function itself, so FastAPI sees the same signature."""
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("product_session_ok requires a non-empty reason")

    def _mark(fn: Callable) -> Callable:
        fn.__product_session_ok__ = reason  # type: ignore[attr-defined]
        return fn

    return _mark


def is_product_session_ok(endpoint: Any) -> bool:
    return bool(getattr(endpoint, "__product_session_ok__", None))


def session_id_of(token: str) -> Optional[str]:
    """The access token's ``session_id`` claim, UNVERIFIED -- only for a token the provider
    accepted (or one core just minted). ``None`` if absent / not a UUID."""
    try:
        claims = jwt.decode(token, options={"verify_signature": False, "verify_exp": False})
        return str(UUID(str(claims.get("session_id"))))
    except Exception:  # noqa: BLE001 - an unreadable claim means "no session id", handled by callers
        return None


class RegistryUnavailable(RuntimeError):
    """The registry could not be read (transport / schema / unexpected payload)."""


def lookup_session_product(get_core_client_fn: Callable[[], Any], session_id: str) -> Optional[str]:
    """Registry PK read: the product slug, or ``None`` when the session is not registered."""
    try:
        rows = (
            get_core_client_fn().table(REGISTRY_TABLE)
            .select("product_slug").eq("session_id", session_id).limit(1).execute().data
        )
    except Exception as exc:  # noqa: BLE001 - re-raised typed below, logged by the caller
        raise RegistryUnavailable(type(exc).__name__) from exc
    if not isinstance(rows, list):
        raise RegistryUnavailable("unexpected_payload")
    if not rows:
        return None
    slug = rows[0].get("product_slug") if isinstance(rows[0], dict) else None
    if not isinstance(slug, str) or not slug:
        raise RegistryUnavailable("unexpected_row")
    return slug


async def resolve_session_product(
    token: str, *, cache: TokenCache, get_core_client_fn: Callable[[], Any]
) -> Optional[str]:
    """``session_product(token)``: the product the session was minted for, else ``None``.

    Cached per token in ``cache`` (a registered session AND a "not registered" answer; an outage is
    never cached). Never raises in observe mode.
    """
    if _mode == "off":
        return None
    hit, cached = cache.get_session_product(token)
    if hit:
        return cached
    session_id = session_id_of(token)
    if session_id is None:
        return None
    try:
        slug = await run_blocking(lookup_session_product, get_core_client_fn, session_id)
    except RegistryUnavailable as exc:
        # Observe: log and continue as "unknown". Enforce (S8) will answer 503 here, never 401.
        logger.error("sso_registry_unavailable session_id=%s reason=%s mode=%s", session_id, exc, _mode)
        return None
    cache.put_session_product(token, slug)
    return slug


def observe_core_route(request: Any, session_product: Optional[str], user_id: Any = None) -> None:
    """Observe mode, core only: log ``product_session_on_core_route`` once per request when a
    registered product session reaches a route that did not declare :func:`product_session_ok`."""
    if _mode != "observe" or not _is_core or not session_product or request is None:
        return
    state = getattr(request, "state", None)
    if state is None or getattr(state, "product_session_logged", False):
        return
    endpoint = request.scope.get("endpoint") if hasattr(request, "scope") else None
    if is_product_session_ok(endpoint):
        return
    state.product_session_logged = True
    logger.warning(
        "product_session_on_core_route product=%s user_id=%s method=%s path=%s",
        session_product, user_id, getattr(request, "method", "-"),
        getattr(getattr(request, "url", None), "path", "-"),
    )


__all__ = [
    "Mode", "RegistryUnavailable", "configure_session_audience", "is_product_session_ok",
    "lookup_session_product", "observe_core_route", "parse_mode", "product_session_mode",
    "product_session_ok", "resolve_session_product", "session_id_of",
]
