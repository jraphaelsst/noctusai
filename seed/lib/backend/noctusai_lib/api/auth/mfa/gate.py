"""``require_admin_assurance`` — the admin-MFA gate (project ``platform-admin-mfa``, slice M2).

Composed INSIDE the seed's admin gate factories (``require_platform_admin``,
``require_org_admin``, ``require_scopes``, ``make_require_role``) so a
product cannot forget it. The config rides ``app.state.mfa_gate`` — set by
``create_product_app`` — and is read at REQUEST time (no import-time
singleton). No config on the app ⇒ the gate is a no-op: behaviour is
byte-for-byte what it was before M2.

Modes (``MfaPolicy``, product override > fleet default > ``off``):

* ``off``     — nothing happens.
* ``warn``    — passes; sets ``X-Noctus-MFA: required``; one audit row
  (``method="MFA_WARN"``) through the app's audit sink when audit is
  enabled, else a WARNING log (route + actor id; never a token/secret).
* ``enforce`` — an ``aal1`` user ⇒ ``403 {"code": "mfa_required",
  "enrolled": bool|None}``; ``aal2`` passes.

Assurance semantics:

* ``caller_kind == "product"`` (``pk_*`` tokens, ``aal=None``) pass —
  PROJECT §5 point 1: a product token is a bearer capability minted by an
  aal2 caller (admin-scoped minting is gated at the mint site), it has no
  second factor of its own to challenge.
* A USER whose ``aal`` is ``None`` (a resolver that does not fill it yet)
  is treated as ``aal1`` — unknown is never ``aal2``; under ``enforce`` an
  unconverted resolver therefore fails closed, which is visible, not silent.
* ``enrolled`` is read from the CALLER's bearer token via
  ``MfaClient.list_factors``. A cookie session's tokens live server-side
  and are not reachable from the gate, so ``enrolled`` is ``None``
  (unknown) there — the SPA reads ``/api/auth/mfa/status`` (M3) for it.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request, Response

from noctusai_lib.api.audit.types import AuditActor, AuditEntry
from noctusai_lib.api.auth.mfa.client import MfaClient
from noctusai_lib.api.auth.mfa.policy import MfaMode, MfaPolicy

logger = logging.getLogger(__name__)

MFA_WARN_HEADER = "X-Noctus-MFA"
MFA_WARN_METHOD = "MFA_WARN"
#: Roles (org_role / platform role strings) the gate treats as "admin" in
#: factories where the role set is caller-defined (``require_scopes``,
#: ``make_require_role``). Owner decision Q2 (recommended): platform admins +
#: org owners/admins.
ADMIN_TIER_ROLES: frozenset[str] = frozenset({"admin", "owner", "platform_admin"})


@dataclass
class MfaGateConfig:
    product: str
    policy: MfaPolicy
    client: Optional[MfaClient] = None
    audit_sink: Any = None
    audit_enabled: bool = False
    #: Seconds a resolved mode is reused. Short on purpose: the policy row is
    #: the instant off-switch. ``0`` disables caching (tests).
    cache_ttl: float = 5.0
    _cached: Optional[tuple[float, MfaMode]] = field(default=None, repr=False)

    async def mode(self) -> MfaMode:
        now = time.monotonic()
        if self._cached is not None and self.cache_ttl > 0 and now - self._cached[0] < self.cache_ttl:
            return self._cached[1]
        mode = await self.policy.resolve(self.product)
        self._cached = (now, mode)
        return mode


def _bearer(request: Request) -> Optional[str]:
    h = request.headers.get("authorization") or ""
    return h[7:].strip() if h.lower().startswith("bearer ") and h[7:].strip() else None


async def _enrolled(cfg: MfaGateConfig, request: Request) -> Optional[bool]:
    token = _bearer(request)
    if cfg.client is None or token is None:
        return None
    try:
        factors = await cfg.client.list_factors(token)
    except Exception as exc:  # noqa: BLE001 — logged; unknown enrolment must not mask the 403
        logger.warning("mfa.gate: list_factors failed (%s) — enrolled unknown", type(exc).__name__)
        return None
    return any(f.status == "verified" for f in factors)


async def _audit_warn(cfg: MfaGateConfig, request: Request, user_id: Any, org_id: Any, role: Optional[str]) -> None:
    route = getattr(request.scope.get("route"), "path", None) or request.url.path
    logger.warning("mfa.gate: warn — admin aal1 on %s %s (actor=%s)", request.method, route, user_id)
    if not (cfg.audit_enabled and cfg.audit_sink is not None):
        return
    entry = AuditEntry(
        product_slug=cfg.product, method=MFA_WARN_METHOD, route_template=route,
        path_params=dict(request.path_params), status=0, actor_kind="user",
        client_hint="mfa-gate",
        actor=AuditActor(
            user_id=str(user_id) if user_id else None,
            org_id=str(org_id) if org_id else None, role=role,
        ),
    )
    await cfg.audit_sink.record(entry)


async def require_admin_assurance(
    request: Optional[Request],
    response: Optional[Response],
    *,
    caller_kind: str,
    aal: Optional[str],
    user_id: Any = None,
    org_id: Any = None,
    role: Optional[str] = None,
) -> None:
    """Gate an ALREADY-authorized admin call on its assurance level. See module docstring."""
    if request is None:  # direct (non-HTTP) call of a dependency — nothing to gate
        return
    cfg: Optional[MfaGateConfig] = getattr(request.app.state, "mfa_gate", None)
    if cfg is None or caller_kind != "user":
        return
    mode = await cfg.mode()
    if mode == "off" or aal == "aal2":
        return
    if mode == "warn":
        if response is not None:
            response.headers[MFA_WARN_HEADER] = "required"
        await _audit_warn(cfg, request, user_id, org_id, role)
        return
    raise HTTPException(
        status_code=403,
        detail={
            "detail": "Verificação em duas etapas (MFA) obrigatória para esta ação",
            "code": "mfa_required",
            "enrolled": await _enrolled(cfg, request),
        },
    )


class _LazyCoreClient:
    """Defers ``get_core_client()`` to first use (the client may not be
    buildable at app-construction time — same late-binding as
    ``ProductDependencies``)."""

    def __init__(self, factory: Callable[[], Any]) -> None:
        self._factory = factory

    def from_(self, name: str) -> Any:
        return self._factory().from_(name)


def build_mfa_gate_config(
    *, product: str, settings: Any, core_client_factory: Callable[[], Any],
    audit_sink: Any = None, audit_enabled: bool = False,
) -> MfaGateConfig:
    """The config ``create_product_app`` parks on ``app.state.mfa_gate``.

    Real policy (``public.mfa_policy``) + real GoTrue client when Supabase is
    configured; the Fake (all ``off``) under pytest or with no Supabase
    settings — so no unit test of a product ever reads a table it didn't
    declare. Tests that exercise the gate assign their own
    ``MfaGateConfig(policy=FakeMfaPolicy(...), client=FakeMfaClient())`` to
    ``app.state.mfa_gate`` (a DI seam, not a patch).
    """
    from noctusai_lib.api.audit.sink import running_under_pytest
    from noctusai_lib.api.auth.mfa.client import make_mfa_client
    from noctusai_lib.api.auth.mfa.policy import make_mfa_policy

    url = getattr(settings, "supabase_url", None)
    anon = getattr(settings, "supabase_anon_key", None)
    if running_under_pytest() or not url or not anon:
        return MfaGateConfig(product=product, policy=make_mfa_policy(use_fake=True))
    return MfaGateConfig(
        product=product,
        policy=make_mfa_policy(core_client=_LazyCoreClient(core_client_factory)),
        client=make_mfa_client(
            supabase_url=url, anon_key=anon,
            service_role_key=getattr(settings, "supabase_service_role_key", None),
        ),
        audit_sink=audit_sink, audit_enabled=audit_enabled,
    )


__all__ = [
    "ADMIN_TIER_ROLES", "MFA_WARN_HEADER", "MFA_WARN_METHOD", "MfaGateConfig",
    "build_mfa_gate_config", "require_admin_assurance",
]
