"""``create_mfa_router(deps, settings)`` — the seed TOTP step-up router (``/api/auth/mfa``).

Project ``platform-admin-mfa``, slice M3. Mounted for EVERY product by
``create_product_app`` (registry key ``"mfa"``, appended automatically) so a
product cannot forget the step-up half of the M2 gate.

Endpoints (contract: ``projects/platform-admin-mfa/PROJECT.md`` §5):
``GET /status`` · ``POST /enroll`` · ``POST /verify`` ·
``DELETE /factors/{factor_id}`` · ``POST /admin/reset/{user_id}``.

Identity: a cookie session (``nai_session``) wins, else a Supabase Bearer
(validated by ``auth.get_user``; ``aal`` read only afterwards). A cookie
session's tokens live server-side: the access token is fetched through the
``TokenExchanger`` and, after a successful verify, the stored tokens are
REWRITTEN to the aal2 session — the body carries no tokens. A Bearer caller
gets the new tokens in the body (the SPA swaps them).

Never logs or returns codes, secrets, QR data or tokens. Setting a policy to
``enforce`` is NOT an API (SQL only — break-glass by design).
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.audit.types import AuditActor, AuditEntry
from noctusai_lib.api.auth import validate_bearer_token_with_aal
from noctusai_lib.api.auth.mfa.client import MfaClient, MfaError, make_mfa_client
from noctusai_lib.api.auth.platform import resolve_platform_admin_role
from noctusai_lib.api.auth.session import SessionStore, make_token_exchanger_from_settings
from noctusai_lib.api.rate_limit import client_ip_key

logger = logging.getLogger(__name__)

_SESSION_COOKIE = "nai_session"
MAX_VERIFIED_FACTORS = 2
VERIFY_LIMIT = 5
VERIFY_WINDOW_SECONDS = 60.0
MFA_RESET_METHOD = "MFA_RESET"


def _err(code_http: int, message: str, code: str, **headers: str) -> HTTPException:
    """Seed error shape ``{"detail", "code"}`` (flat via the seed exception handler)."""
    return HTTPException(status_code=code_http, detail={"detail": message, "code": code},
                         headers=headers or None)


class SlidingWindowLimiter:
    """Per-key sliding window (in-process). ``allow(key)`` records + answers.

    Process-local on purpose: the verify limit is a brute-force brake on a
    6-digit code (GoTrue also rate-limits upstream), not a quota.
    """

    def __init__(self, limit: int = VERIFY_LIMIT, window_seconds: float = VERIFY_WINDOW_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._limit, self._window, self._clock = limit, window_seconds, clock
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < self._window]
            if len(hits) >= self._limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > 10_000:  # bound memory under key churn
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < self._window}
            return True

    @property
    def window_seconds(self) -> float:
        return self._window


# ─── Schemas ────────────────────────────────────────────────────────────


class EnrollRequest(StrictHttpModel):
    friendly_name: str = Field(min_length=1, max_length=40)


class VerifyRequest(StrictHttpModel):
    factor_id: str = Field(min_length=1, max_length=128)
    code: str = Field(pattern=r"^\d{6}$")


@dataclass(frozen=True)
class _Caller:
    user_id: str
    aal: Optional[str]
    org_id: Optional[str]
    bearer: Optional[str]
    session_id: Optional[str]


_exchanger: Any = None
_exchanger_settings_id: Optional[int] = None


def _get_token_exchanger(settings, store: SessionStore):
    """Process-local ``TokenExchanger`` keyed by ``id(settings)`` (Real with a Redis
    lock when ``redis_url`` is set; the Fake otherwise — dev/tests)."""
    global _exchanger, _exchanger_settings_id
    if _exchanger is None or _exchanger_settings_id != id(settings):
        _exchanger = make_token_exchanger_from_settings(
            store,
            redis_url=getattr(settings, "redis_url", None) or None,
            supabase_url=getattr(settings, "supabase_url", None) or None,
            supabase_anon_key=getattr(settings, "supabase_anon_key", None) or None,
        )
        _exchanger_settings_id = id(settings)
    return _exchanger


def _build_default_client(settings) -> MfaClient:
    from noctusai_lib.api.audit.sink import running_under_pytest

    url = getattr(settings, "supabase_url", None)
    anon = getattr(settings, "supabase_anon_key", None)
    if not url or not anon:
        if not running_under_pytest():
            logger.warning("mfa.router: no Supabase settings — using the Fake MFA client")
        return make_mfa_client(use_fake=True)
    return make_mfa_client(supabase_url=url, anon_key=anon,
                           service_role_key=getattr(settings, "supabase_service_role_key", None))


def create_mfa_router(
    deps,
    settings,
    *,
    client: Optional[MfaClient] = None,
    session_store: Optional[SessionStore] = None,
    token_exchanger: Any = None,
    bearer_validator: Optional[Callable[[str], tuple[Any, Optional[str]]]] = None,
    verify_limiter: Optional[SlidingWindowLimiter] = None,
) -> APIRouter:
    """Build the ``/api/auth/mfa`` router. Every kwarg is a DI seam (tests / advanced wiring)."""
    from noctusai_seed.auth_router import get_session_store

    store = session_store or get_session_store(settings)
    mfa_client = client or _build_default_client(settings)
    limiter = verify_limiter or SlidingWindowLimiter()
    router = APIRouter(prefix="/api/auth/mfa", tags=["auth", "mfa"])

    def _exchanger():
        return token_exchanger or _get_token_exchanger(settings, store)

    def _validate(token: str) -> tuple[Any, Optional[str]]:
        if bearer_validator is not None:
            return bearer_validator(token)
        # ProductDependencies exposes get_core_client (service role); auth.get_user(token) verifies
        # the JWT with any key. There is no deps.get_client -- calling it 500'd every bearer call.
        return validate_bearer_token_with_aal(deps.get_core_client(), token)

    async def get_caller(request: Request) -> _Caller:
        cookie = request.cookies.get(_SESSION_COOKIE)
        if cookie:
            ctx = await store.lookup(cookie)
            if ctx is not None and ctx.caller_kind == "user" and ctx.user_id is not None:
                return _Caller(str(ctx.user_id), ctx.aal, str(ctx.org_id), None, cookie)
        header = request.headers.get("authorization") or ""
        if header.lower().startswith("bearer ") and header[7:].strip():
            token = header[7:].strip()
            user, aal = await asyncio.to_thread(_validate, token)
            uid = getattr(user, "id", None)
            if uid is None:
                raise HTTPException(status_code=401, detail="Token inválido")
            meta = getattr(user, "user_metadata", None) or {}
            org = meta.get("org_id") if isinstance(meta, dict) else None
            return _Caller(str(uid), aal, str(org) if org else None, token, None)
        raise HTTPException(status_code=401, detail="Token ausente")

    async def _access_token(caller: _Caller) -> str:
        if caller.bearer:
            return caller.bearer
        try:
            return await _exchanger().access_token_for(caller.session_id)
        except Exception as exc:  # noqa: BLE001 — typed to a 401, class logged only
            logger.warning("mfa.router: session token exchange failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=401, detail="Sessão expirada") from exc

    def _map(exc: MfaError) -> HTTPException:
        if exc.code == "invalid_code" or exc.code == "challenge_invalid":
            return _err(400, "Código inválido", "mfa_invalid_code")
        if exc.code == "factor_not_found":
            return _err(404, "Fator não encontrado", "mfa_factor_not_found")
        if exc.code == "unauthorized":
            return HTTPException(status_code=401, detail="Token inválido")
        logger.error("mfa.router: provider failure code=%s", exc.code)
        return _err(502, "Provedor de autenticação indisponível", "mfa_provider_error")

    def _factor_dto(f) -> dict[str, Any]:
        return {"id": f.id, "friendly_name": f.friendly_name,
                "status": "verified" if f.status == "verified" else "unverified",
                "created_at": str(f.created_at or "")}

    @router.get("/status")
    async def mfa_status(caller: _Caller = Depends(get_caller)) -> dict[str, Any]:
        token = await _access_token(caller)
        try:
            factors = [f for f in await mfa_client.list_factors(token) if f.factor_type in ("totp", "")]
        except MfaError as exc:
            raise _map(exc) from exc
        return {
            "enrolled": any(f.status == "verified" for f in factors),
            "aal": caller.aal if caller.aal in ("aal1", "aal2") else None,
            "factors": [_factor_dto(f) for f in factors],
        }

    @router.post("/enroll")
    async def mfa_enroll(body: EnrollRequest, caller: _Caller = Depends(get_caller)) -> dict[str, Any]:
        token = await _access_token(caller)
        try:
            factors = await mfa_client.list_factors(token)
            verified = sum(1 for f in factors if f.status == "verified")
            # Adding a factor to an account that already has one is itself a second-factor action: otherwise a
            # password alone could enroll an attacker's device, verify it and reach aal2 (review 2026-10-04).
            if verified and caller.aal != "aal2":
                raise _err(403, "Verificação em duas etapas (MFA) obrigatória para esta ação", "mfa_required")
            if verified >= MAX_VERIFIED_FACTORS:
                raise _err(409, "Limite de fatores atingido", "mfa_factor_limit")
            enrollment = await mfa_client.enroll_totp(token, friendly_name=body.friendly_name)
        except MfaError as exc:
            raise _map(exc) from exc
        return {"factor_id": enrollment.factor_id, "qr_code": enrollment.qr_svg, "uri": enrollment.uri}

    @router.post("/verify")
    async def mfa_verify(body: VerifyRequest, request: Request,
                         caller: _Caller = Depends(get_caller)) -> dict[str, Any]:
        if not limiter.allow(f"{caller.user_id}|{client_ip_key(request)}"):
            raise _err(429, "Muitas tentativas — aguarde um minuto", "mfa_rate_limited",
                       **{"Retry-After": str(int(limiter.window_seconds))})
        token = await _access_token(caller)
        try:
            challenge = await mfa_client.challenge(token, body.factor_id)
            session = await mfa_client.verify(token, body.factor_id, challenge.id, body.code)
        except MfaError as exc:
            raise _map(exc) from exc
        if caller.session_id:
            await store.write_tokens(
                caller.session_id, refresh_token=session.refresh_token,
                access_token=session.access_token, access_expires_at=session.expires_at,
                aal=session.aal,
            )
            return {"aal": "aal2"}
        return {"aal": "aal2", "access_token": session.access_token,
                "refresh_token": session.refresh_token,
                "expires_in": max(int(session.expires_at - time.time()), 0)}

    @router.delete("/factors/{factor_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def mfa_delete_factor(factor_id: str, caller: _Caller = Depends(get_caller)) -> Response:
        token = await _access_token(caller)
        try:
            factors = await mfa_client.list_factors(token)
            if not any(f.id == factor_id for f in factors):
                raise _err(404, "Fator não encontrado", "mfa_factor_not_found")
            if any(f.status == "verified" for f in factors) and caller.aal != "aal2":
                raise _err(403, "Verificação em duas etapas (MFA) obrigatória para esta ação", "mfa_required")
            await mfa_client.delete_factor(caller.user_id, factor_id)
        except MfaError as exc:
            raise _map(exc) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    async def _audit_reset(request: Request, caller: _Caller, target: str, deleted: int) -> None:
        logger.warning("mfa.router: admin reset actor=%s target=%s deleted=%d", caller.user_id, target, deleted)
        sink = getattr(request.app.state, "audit_sink", None)
        if sink is None or not getattr(request.app.state, "audit_enabled", False):
            return
        gate = getattr(request.app.state, "mfa_gate", None)
        await sink.record(AuditEntry(
            product_slug=getattr(gate, "product", "") or "", method=MFA_RESET_METHOD,
            route_template="/api/auth/mfa/admin/reset/{user_id}", path_params={"user_id": target},
            status=200, actor_kind="user", client_hint="mfa-router",
            actor=AuditActor(user_id=caller.user_id, org_id=caller.org_id, role="admin"),
        ))

    @router.post("/admin/reset/{user_id}")
    async def mfa_admin_reset(user_id: str, request: Request,
                              caller: _Caller = Depends(get_caller)) -> dict[str, int]:
        role = await asyncio.to_thread(resolve_platform_admin_role, deps.get_core_client(), caller.user_id)
        if role != "admin":
            raise _err(403, "Restrito a administradores da plataforma NoctusAI", "platform_admin_required")
        if caller.aal != "aal2":
            raise _err(403, "Verificação em duas etapas (MFA) obrigatória para esta ação", "mfa_required")
        try:
            factors = await mfa_client.admin_list_factors(user_id)
            for f in factors:
                await mfa_client.delete_factor(user_id, f.id)
        except MfaError as exc:
            raise _map(exc) from exc
        await _audit_reset(request, caller, user_id, len(factors))
        return {"deleted": len(factors)}

    return router


__all__ = ["MAX_VERIFIED_FACTORS", "SlidingWindowLimiter", "create_mfa_router"]
