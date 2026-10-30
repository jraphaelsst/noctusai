"""Who / which product / which feature an LLM call is billed to (roadmap D25).

Every `UsageEvent` is stamped at record time from three layers, innermost wins:

1. **Explicit scope** — ``with llm_usage_context(feature="julia.reply", agent_key="julia"):``
   (nests; an inner scope overrides only the fields it names).
2. **The HTTP request** — `UsageAttributionMiddleware` (mounted by
   ``noctusai_lib.api.app_factory.configure_app``) exposes the request's ASGI
   ``scope`` so the stamp can read, lazily at record time, the caller the seed
   auth dependency already resolved (``request.state.audit_actor`` — the SAME
   trusted identity the audit trail records, never ``user_metadata``), the
   matched route template (the default ``feature``) and the correlation id
   (``request_id``).
3. **The process** — `set_default_product(slug)`, called once by
   ``create_product_app`` with the product's catalog slug. A background job
   with no request still lands under its product.

No product writes attribution plumbing: the seed fills product + user + route
by construction; a product only names ``feature`` / ``purpose`` / ``agent_key``
/ ``conversation_id`` where the route template is not specific enough.

LGPD: identifiers only (uuids, slugs, route templates) — never prompt text.
"""
from __future__ import annotations

import contextlib
import contextvars
from dataclasses import dataclass, fields, replace
from typing import Any, Iterator, Optional

__all__ = [
    "UsageAttribution",
    "UsageAttributionMiddleware",
    "current_attribution",
    "get_default_product",
    "llm_usage_context",
    "set_default_product",
]


@dataclass(frozen=True)
class UsageAttribution:
    """The billing dimensions of one LLM call. Every field is optional."""

    product: Optional[str] = None
    feature: Optional[str] = None
    purpose: Optional[str] = None
    org_id: Optional[str] = None
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    agent_key: Optional[str] = None
    request_id: Optional[str] = None

    def merged_over(self, base: "UsageAttribution") -> "UsageAttribution":
        """``self``'s non-None fields over ``base``."""
        changes = {f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name) is not None}
        return replace(base, **changes)


_EMPTY = UsageAttribution()

_EXPLICIT: contextvars.ContextVar[UsageAttribution] = contextvars.ContextVar(
    "noctusai_llm_usage_attribution", default=_EMPTY
)
#: The current request's ASGI scope (set by `UsageAttributionMiddleware`).
_REQUEST_SCOPE: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "noctusai_llm_usage_request_scope", default=None
)
_DEFAULT_PRODUCT: Optional[str] = None


def set_default_product(product: Optional[str]) -> None:
    """Process-wide fallback ``product`` (one process == one product)."""
    global _DEFAULT_PRODUCT
    _DEFAULT_PRODUCT = product or None


def get_default_product() -> Optional[str]:
    return _DEFAULT_PRODUCT


@contextlib.contextmanager
def llm_usage_context(
    *,
    product: Optional[str] = None,
    feature: Optional[str] = None,
    purpose: Optional[str] = None,
    org_id: Optional[str] = None,
    user_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    agent_key: Optional[str] = None,
) -> Iterator[UsageAttribution]:
    """Attribute every LLM call made inside this block (this task and the
    tasks / threads it spawns — contextvars are copied into both)."""
    scoped = UsageAttribution(
        product=product, feature=feature, purpose=purpose, org_id=org_id,
        user_id=user_id, conversation_id=conversation_id, agent_key=agent_key,
    ).merged_over(_EXPLICIT.get())
    token = _EXPLICIT.set(scoped)
    try:
        yield scoped
    finally:
        _EXPLICIT.reset(token)


def _from_request(scope: Optional[dict]) -> UsageAttribution:
    if not scope:
        return _EMPTY
    state = scope.get("state") or {}
    actor = state.get("audit_actor") if isinstance(state, dict) else None
    route = scope.get("route")
    template = getattr(route, "path", None)
    feature = f"{scope.get('method', '')} {template}".strip() if template else None
    return UsageAttribution(
        feature=feature,
        org_id=_str_or_none(getattr(actor, "org_id", None)),
        user_id=_str_or_none(getattr(actor, "user_id", None)),
    )


def _str_or_none(value: Any) -> Optional[str]:
    return str(value) if value else None


def current_attribution() -> UsageAttribution:
    """The fully-resolved attribution for an event recorded right now."""
    from noctusai_lib.primitives._correlation import get_correlation_id

    base = UsageAttribution(product=_DEFAULT_PRODUCT)
    scope = _REQUEST_SCOPE.get()
    if scope is not None:
        req = _from_request(scope)
        rid = get_correlation_id()
        base = replace(req, request_id=rid if rid and rid != "-" else None).merged_over(base)
    return _EXPLICIT.get().merged_over(base)


class UsageAttributionMiddleware:
    """Pure ASGI: exposes the request scope to `current_attribution()`.

    Reads nothing at request entry (the auth dependency has not run yet) —
    the scope dict is read lazily when an event is recorded, by which point
    ``scope["state"]["audit_actor"]`` and ``scope["route"]`` are filled.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        scope.setdefault("state", {})
        token = _REQUEST_SCOPE.set(scope)
        try:
            await self.app(scope, receive, send)
        finally:
            _REQUEST_SCOPE.reset(token)
