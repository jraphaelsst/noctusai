"""
Standard routers that NoctusAI products can opt into.

Bundled routers live here:
  - "health"       → `/api/health`
  - "notificacoes" → `/api/notificacoes` (proxy to core `public.notifications`)
  - "team"         → `/api/team` (invitations, members)
  - "llm"          → `/api/llm/providers|models|preferences`
  - "ai_outputs"   → `/api/ai/outputs` (per-entity AI-output lookup; P1 pattern)
  - "ai_feedback"  → `/api/ai/feedback` (thumbs feedback on AI outputs; P1)
  - "scheduler"    → `/api/scheduler/jobs[/{job_id}]` (read-only APScheduler view)
  - "status_paginas" → `/api/status-paginas` (list + change page-visibility status; admin/dev-gated)

Products declare which ones they want via the `standard_routers=[...]` kwarg
on `create_product_app()`. `build_standard_routers()` resolves that list
against the `_STANDARD_ROUTERS` registry. Unknown names raise `ValueError`.

Usage::

    # Inside create_product_app — products never call this directly.
    for router in build_standard_routers(
        deps, settings, product_name="Mailing", version="0.1.0",
        names=["health", "notificacoes", "team"],
    ):
        app.include_router(router)
"""
import logging
from typing import Optional, Sequence

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from noctusai_lib.domain.invitations import (
    create_invitation,
    validate_invitation,
    accept_invitation,
    cancel_invitation,
    list_pending_invitations,
)
from noctusai_lib.domain.org import (
    attach_user_to_org,
    provision_invited_identity,
    sync_org_metadata,
)
from noctusai_lib.api.auth import make_get_current_user_org
from noctusai_lib.api.auth.platform import resolve_platform_admin_role
from noctusai_lib.api.auth.session.scopes import resolve_org_role
from noctusai_lib.integrations.email.templates import send_product_invitation_email
from noctusai_lib.domain.notifications import map_notification_to_pt
from noctusai_lib.primitives.roles import (
    ADMIN_ROLES,
    MANAGE_TEAM_ROLES,
    ORG_ROLE_LABELS,
    ORG_ROLES,
)

logger = logging.getLogger(__name__)

# PostgREST resolves table names RELATIVE to the schema already bound on the
# client (`deps.get_admin_client()` → `DatabaseModule.get_client(schema=...)`),
# so this name must stay BARE. Qualifying it (`f"{deps._db.schema}.invitations"`)
# asks PostgREST for `<schema>.<schema>.invitations` → 500 "Could not find the
# table ... in the schema cache". `noctusai_lib.domain.invitations` re-checks
# this at the call boundary. → KB § PATTERNS/backend/postgrest-schema-targeting.md
_INVITATIONS_TABLE = "invitations"


def _create_health_router(product_name: str, version: str = "0.1.0") -> APIRouter:
    router = APIRouter(tags=["Health"])

    @router.get("/api/health")
    async def health_check(request: Request):
        # `startup_hook_error` is the NAMED DESTINATION for a product
        # `lifespan_startup` hook that raised. The seed deliberately no longer
        # lets such a failure abort the boot (see the block comment in
        # `noctusai_seed.app.create_product_app`'s lifespan), so this field is
        # the thing that keeps it from being a silent fallback: `null` on a
        # clean boot, the exception's `Type: message` when the hook failed.
        #
        # The HTTP status stays 200 and `status` stays "ok" on purpose — the
        # container healthcheck + the deploy probe both read this endpoint, and
        # the API genuinely IS serving; a failed side-effect hook must not be
        # reported as "this product is down". Degradation is a FIELD, not a
        # status code. → KB § PATTERNS/backend/startup-hook-must-not-be-fatal.md
        return {
            "status": "ok",
            "version": version,
            "product": product_name,
            "startup_hook_error": getattr(
                request.app.state, "startup_hook_error", None
            ),
        }

    return router


def _create_notificacoes_router(deps) -> APIRouter:
    router = APIRouter(prefix="/api/notificacoes", tags=["Notificacoes"])

    @router.get("")
    async def listar(
        authorization: Optional[str] = Header(None),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ):
        user, token = await deps.get_current_user(authorization)
        core = deps.get_core_client()
        offset = (page - 1) * page_size
        result = (
            core.table("notifications")
            .select("*", count="exact")
            .eq("user_id", str(user.id))
            .order("created_at", desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        items = [map_notification_to_pt(n) for n in (result.data or [])]
        return {"data": items, "total": result.count or 0, "page": page, "page_size": page_size}

    @router.get("/contagem")
    async def contagem(authorization: Optional[str] = Header(None)):
        user, token = await deps.get_current_user(authorization)
        core = deps.get_core_client()
        result = (
            core.table("notifications")
            .select("id", count="exact")
            .eq("user_id", str(user.id))
            .eq("read", False)
            .execute()
        )
        return {"nao_lidas": result.count or 0}

    @router.patch("/{notificacao_id}/ler")
    async def marcar_lida(notificacao_id: str, authorization: Optional[str] = Header(None)):
        user, _ = await deps.get_current_user(authorization)
        core = deps.get_core_client()
        core.table("notifications").update({"read": True}).eq("id", notificacao_id).eq("user_id", str(user.id)).execute()
        return {"ok": True}

    @router.post("/ler-todas")
    async def marcar_todas_lidas(authorization: Optional[str] = Header(None)):
        user, _ = await deps.get_current_user(authorization)
        core = deps.get_core_client()
        core.table("notifications").update({"read": True}).eq("user_id", str(user.id)).eq("read", False).execute()
        return {"ok": True}

    return router


#: Pseudo-role returned by `_trusted_team_role` for a NoctusAI platform
#: operator (`public.noctus_users.role == 'admin'`). It grants team management
#: ONLY inside the operator's OWN trusted org — every team query is scoped by
#: the trusted `org_id`, so it never reaches another tenant.
_PLATFORM_ADMIN = "platform_admin"

#: Who may grant which org role through `/api/team/invite`. A role absent from
#: this map is grantable by anyone who may invite at all (MANAGE_TEAM_ROLES).
#: Without it any inviter could mint an `owner` — i.e. a manager could invite a
#: sock-puppet owner and take the org over.
_GRANT_REQUIRES = {
    "owner": frozenset({"owner", _PLATFORM_ADMIN}),
    "admin": frozenset({"owner", "admin", _PLATFORM_ADMIN}),
}


def _no_untrusted_org_fallback(_user) -> None:
    """The team router NEVER falls back to `user_metadata.org_id`.

    `make_get_current_user_org` consults its `get_org_id_fn` only when the
    caller has no `public.noctus_users` row. Every team route lists, invites
    into, or deletes from an org using the SERVICE-ROLE client, so a
    metadata fallback (which the user can rewrite via `auth.updateUser({data})`)
    would hand a row-less caller another tenant's roster. No row ⇒ no org ⇒ 403.
    """
    return None


def _trusted_team_role(core, user) -> Optional[str]:
    """The caller's role for team management, from `public.noctus_users` only.

    `org_role` (owner/admin/manager/...) via `resolve_org_role`; a NoctusAI
    platform operator (`role == 'admin'`, via `resolve_platform_admin_role`)
    maps to `_PLATFORM_ADMIN`. NEVER `user_metadata` — that is user-writable.
    """
    user_id = getattr(user, "id", None)
    if resolve_platform_admin_role(core, user_id) == "admin":
        return _PLATFORM_ADMIN
    return resolve_org_role(core, user_id)


def _require_team_role(role: Optional[str], allowed, detail: str) -> None:
    if role != _PLATFORM_ADMIN and role not in allowed:
        raise HTTPException(status_code=403, detail=detail)


def _org_display_name(core, org_id: str) -> str:
    """`organizations.nome` for the invitation email — read from the DB by the
    TRUSTED org_id, never `user_metadata.org_name` (user-writable: a spoofed
    name would let a member send an invite email impersonating another org)."""
    try:
        res = (
            core.table("organizations").select("nome").eq("id", org_id)
            .limit(1).execute()
        )
    except Exception as exc:  # display-only; the invite itself must not fail
        logger.warning(
            "team.invite: could not read organizations.nome for org=%s (%s) — "
            "using the generic label in the email", org_id, exc,
        )
        return "sua organizacao"
    rows = res.data or []
    return (rows[0].get("nome") if rows else None) or "sua organizacao"


def _create_team_router(deps, settings, product_name: str) -> APIRouter:
    """`/api/team` — members + invitations.

    🔴 Trust model (SEC-1, 2026-09-28): every authenticated route resolves the
    caller's org AND role from `public.noctus_users` (the row RLS trusts) —
    NEVER from `user_metadata`, which any user can rewrite via
    `auth.updateUser({data})`. These routes act through the service-role client
    (RLS bypassed), so the app-layer org scope IS the tenant boundary: every
    read, invite and delete is filtered by the trusted `org_id`.
    """
    router = APIRouter(prefix="/api/team", tags=["Team"])

    _get_current_user_org = make_get_current_user_org(
        # Late-bound: resolve `deps.get_current_user` per request, exactly as
        # the pre-SEC-1 imperative calls did (a product/test rebinding it after
        # mount must still take effect).
        lambda authorization: deps.get_current_user(authorization),
        _no_untrusted_org_fallback,
        get_admin_client_fn=lambda: deps.get_core_client(),
    )

    async def _member_context(authorization: Optional[str]):
        """(user, trusted org_id, trusted team role) — 401 unauthenticated,
        403 when the caller has no org membership row."""
        user, _token, org_id = await _get_current_user_org(authorization)
        role = _trusted_team_role(deps.get_core_client(), user)
        return user, org_id, role

    @router.get("")
    async def list_members(authorization: Optional[str] = Header(None)):
        _user, org_id, _role = await _member_context(authorization)
        core = deps.get_core_client()
        result = core.table("noctus_users").select("*").eq("org_id", org_id).execute()
        return {"data": result.data or []}

    @router.post("/invite")
    async def invite_member(
        body: dict,
        authorization: Optional[str] = Header(None),
    ):
        user, org_id, inviter_role = await _member_context(authorization)
        _require_team_role(inviter_role, MANAGE_TEAM_ROLES, "Sem permissao para convidar")

        email = (body.get("email") or "").strip()
        if not email:
            raise HTTPException(status_code=400, detail="Email e obrigatorio")
        role = body.get("role") or "member"
        if role not in ORG_ROLES:
            raise HTTPException(status_code=400, detail=f"Papel invalido: {role}")
        grantors = _GRANT_REQUIRES.get(role)
        if grantors is not None and inviter_role not in grantors:
            raise HTTPException(
                status_code=403,
                detail=f"Sem permissao para convidar como {ORG_ROLE_LABELS[role]}",
            )

        admin = deps.get_admin_client()
        invite = create_invitation(
            admin,
            _INVITATIONS_TABLE,
            email=email,
            org_id=org_id,
            role=role,
            invited_by=str(user.id),
        )
        inviter_name = (user.user_metadata or {}).get("name", "Um administrador")
        org_name = _org_display_name(deps.get_core_client(), org_id)
        base_url = settings.cors_origins.split(",")[0] if settings.cors_origins else "http://localhost:3000"
        send_product_invitation_email(
            to=email,
            product_name=product_name,
            org_name=org_name,
            role_label=ORG_ROLE_LABELS[role],
            invite_token=invite["token"],
            invited_by=inviter_name,
            base_url=base_url,
        )
        return {"data": invite}

    @router.get("/accept/validate")
    async def validate_invite(token: str = Query(...)):
        admin = deps.get_admin_client()
        result = validate_invitation(admin, _INVITATIONS_TABLE, token)
        if not result:
            raise HTTPException(status_code=400, detail="Convite invalido ou expirado")
        return {"data": result}

    @router.post("/accept")
    async def accept_invite(
        body: dict,
        authorization: Optional[str] = Header(None),
    ):
        """Accept an invitation — and actually make the invitee a member.

        Until 2026-08-07 this only flipped the invitation row to `accepted`.
        It created no identity, no `noctus_users` profile and no org
        membership, and silently discarded the `nome`/`password` the
        `AcceptInvitePage` organ submits — so the invitee saw a success screen
        and then could not log in anywhere. Core's `/api/sso/launch/{slug}`
        404s "Perfil não encontrado" without that profile row, so the account
        could not open ANY product.

        Two paths:

        - **Authenticated** (a Bearer token) — the caller already has an
          identity; they are joined to the org as-is and any submitted
          password is ignored. Someone who is signed in is accepting for
          themselves, not creating an account.
        - **Anonymous** — `nome` + `password` are required, and the identity is
          created (or an existing one for that email is linked, without
          touching its password).

        The invitation's `email` is the source of truth for the address; the
        body cannot override it, so a leaked token cannot enroll a different
        address than the one that was invited.
        """
        token = body.get("token")
        if not token:
            raise HTTPException(status_code=400, detail="Token do convite ausente")

        admin = deps.get_admin_client()
        # `noctus_users` + `auth.users` are PLATFORM tables in `public` — the
        # product-schema client cannot see them.
        core = deps.get_core_client()

        inv = validate_invitation(admin, _INVITATIONS_TABLE, token)
        email = inv["email"]
        org_id = inv["org_id"]
        org_role = inv.get("role", "member")

        # ── Identity ──────────────────────────────────────────────────────
        current_user = None
        if authorization:
            try:
                current_user, _ = await deps.get_current_user(authorization)
            except HTTPException as exc:
                # A stale/invalid token must not block the anonymous path —
                # fall through and treat this as a fresh acceptance.
                logger.info(
                    "team.accept: ignoring unusable Authorization header (%s)",
                    getattr(exc, "detail", exc),
                )

        created_identity = False
        if current_user is not None:
            # The invitation names ONE address. A signed-in caller accepts for
            # THEMSELVES, so they must BE that address — otherwise anyone holding
            # a leaked token joins the org under their own account.
            caller_email = (getattr(current_user, "email", None) or "").strip().lower()
            if caller_email != (email or "").strip().lower():
                raise HTTPException(
                    status_code=403,
                    detail="Este convite foi enviado para outro email",
                )
            user_id = str(current_user.id)
            nome = (
                body.get("nome")
                or (current_user.user_metadata or {}).get("nome")
                or (current_user.email or email).split("@", 1)[0]
            )
        else:
            nome = (body.get("nome") or "").strip()
            password = body.get("password") or ""
            if not nome:
                raise HTTPException(status_code=400, detail="Nome e obrigatorio")
            if len(password) < 6:
                raise HTTPException(
                    status_code=400,
                    detail="Senha deve ter no minimo 6 caracteres",
                )
            user_id, created_identity = provision_invited_identity(
                core, email=email, password=password, nome=nome,
            )

        # ── Membership ────────────────────────────────────────────────────
        try:
            attach_user_to_org(
                core,
                user_id,
                org_id=org_id,
                email=email,
                nome=nome,
                org_role=org_role,
            )
        except Exception as exc:
            # Compensating delete: an identity we JUST created, with no
            # membership, is unreachable AND blocks the retry (its email is
            # now taken). Leaving it behind converts a transient failure into
            # a permanent one. An identity that already existed is never
            # touched — it is not ours to delete.
            if created_identity:
                try:
                    core.auth.admin.delete_user(user_id)
                    logger.info(
                        "team.accept: rolled back orphan identity %s after membership failure",
                        user_id,
                    )
                except Exception as cleanup_exc:
                    logger.error(
                        "team.accept: could not roll back orphan identity %s (%s) — "
                        "a retry for %s will report the email as already registered",
                        user_id, cleanup_exc, email,
                    )
            # An HTTPException is a decision (the 409 for "already in another
            # org") and travels as-is. Anything else is an infrastructure
            # failure: convert it rather than letting a bare exception escape
            # the handler, which would surface as an unhandled crash instead
            # of an answer the frontend can render.
            if isinstance(exc, HTTPException):
                raise
            logger.error(
                "team.accept: could not attach %s to org %s (%s)", user_id, org_id, exc,
            )
            raise HTTPException(
                status_code=500, detail="Erro ao vincular usuario a organizacao",
            ) from exc

        # Mirror into user_metadata so the member works BEFORE their first SSO
        # launch (which re-syncs from noctus_users anyway). Best-effort.
        sync_org_metadata(core, user_id, org_id=org_id, org_role=org_role, nome=nome)

        accept_invitation(
            admin, _INVITATIONS_TABLE, inv["id"], accepted_by=user_id,
        )
        logger.info(
            "team.accept: invitation=%s email=%s joined org=%s as %s (identity %s)",
            inv["id"], email, org_id, org_role,
            "created" if created_identity else "existing",
        )
        return {
            "data": {
                **inv,
                "user_id": user_id,
                "org_role": org_role,
                "created_identity": created_identity,
            }
        }

    @router.get("/invitations")
    async def list_invitations(authorization: Optional[str] = Header(None)):
        _user, org_id, role = await _member_context(authorization)
        _require_team_role(role, ADMIN_ROLES, "Sem permissao")
        admin = deps.get_admin_client()
        result = list_pending_invitations(admin, _INVITATIONS_TABLE, org_id)
        return {"data": result}

    @router.delete("/invitations/{invitation_id}")
    async def cancel_invite(invitation_id: str, authorization: Optional[str] = Header(None)):
        _user, org_id, role = await _member_context(authorization)
        _require_team_role(role, ADMIN_ROLES, "Sem permissao")
        admin = deps.get_admin_client()
        # `cancel_invitation` takes org_id as its 4th positional arg — it scopes the
        # cancel to the caller's TRUSTED org (an admin of org A must not cancel
        # org B's invite).
        cancel_invitation(admin, _INVITATIONS_TABLE, invitation_id, org_id)
        return {"ok": True}

    @router.delete("/{user_id}")
    async def remove_member(user_id: str, authorization: Optional[str] = Header(None)):
        user, org_id, role = await _member_context(authorization)
        _require_team_role(role, ADMIN_ROLES, "Sem permissao")
        if str(user.id) == user_id:
            raise HTTPException(status_code=400, detail="Nao pode remover a si mesmo")
        core = deps.get_core_client()
        # The target must be a member of the caller's OWN org — this is a
        # service-role delete, so the org filter IS the tenant boundary.
        target = (
            core.table("noctus_users").select("id, org_role")
            .eq("id", user_id).eq("org_id", org_id).limit(1).execute()
        )
        rows = target.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="Membro nao encontrado")
        if rows[0].get("org_role") == "owner" and role not in ("owner", _PLATFORM_ADMIN):
            raise HTTPException(
                status_code=403, detail="Somente o proprietario pode remover um proprietario",
            )
        core.table("noctus_users").delete().eq("id", user_id).eq("org_id", org_id).execute()
        return {"ok": True}

    return router


def _build_llm_router(deps, settings, product_name: str, version: str) -> APIRouter:
    # Deferred import: llm_router imports `noctusai_lib.llm` and a few catalog
    # modules at collection time; keeping it inside the factory avoids pulling
    # that cost for products that opt out of "llm".
    from noctusai_seed.llm_router import create_llm_router
    return create_llm_router(deps)


def _build_ai_outputs_router(deps, settings, product_name: str, version: str) -> APIRouter:
    # Deferred import for the same reason as `_build_llm_router`.
    from noctusai_seed.ai_router import create_ai_outputs_router
    return create_ai_outputs_router(deps)


def _build_ai_feedback_router(deps, settings, product_name: str, version: str) -> APIRouter:
    # Deferred import — keeps Pydantic model collection cost out of the
    # hot path for products that don't opt in.
    from noctusai_seed.ai_feedback_router import create_ai_feedback_router
    return create_ai_feedback_router(deps)


def _build_scheduler_router(deps, settings, product_name: str, version: str) -> APIRouter:
    # Deferred import — keeps `noctusai_lib.api.scheduler` (which pulls
    # APScheduler at module import time) out of the hot path for
    # products that don't run background jobs.
    from noctusai_seed.scheduler_router import create_scheduler_router
    return create_scheduler_router(deps)


def _build_status_paginas_router(deps, settings, product_name: str, version: str) -> APIRouter:
    # Deferred import — mirrors the other `_build_*` factories; keeps the
    # module import off the hot path for products that opt out.
    from noctusai_seed.status_pagina_router import _create_status_pagina_router
    return _create_status_pagina_router(deps, settings, product_name)


def _build_auth_router(deps, settings, product_name: str, version: str) -> APIRouter:
    # Deferred import — keeps the noctusai_lib.api.auth.session chain
    # (Redis/GoTrue adapters) out of the hot path for products that opt
    # out. Wraps /api/auth/{login,me,logout} + api-token management —
    # promoted from the social-wiring fork, erp-httponly-cookie-session
    # roadmap Slice 1b.
    from noctusai_seed.auth_router import create_auth_router
    return create_auth_router(deps, settings)


# Maintenance contract for _STANDARD_ROUTERS:
# Adding a new standard router requires all three of:
#   (a) adding an entry to this registry,
#   (b) updating `seed/framework/backend/tests/test_build_standard_routers.py
#       ::test_registry_keys_match_documented_set` (drift guard),
#   (c) documenting the new capability in `KNOWLEDGE-BASE/CONTEXT/
#       03-SEED-ARCHITECTURE.md § Standard routers`.
# Miss any of (a)-(c) and the drift-guard test will fail opaquely.
_STANDARD_ROUTERS = {
    "health":       lambda deps, s, n, v: _create_health_router(n, v),
    "notificacoes": lambda deps, s, n, v: _create_notificacoes_router(deps),
    "team":         lambda deps, s, n, v: _create_team_router(deps, s, n),
    "llm":          _build_llm_router,
    "ai_outputs":   _build_ai_outputs_router,
    "ai_feedback":  _build_ai_feedback_router,
    "scheduler":    _build_scheduler_router,
    "status_paginas": _build_status_paginas_router,
    "auth":           _build_auth_router,
}


def build_standard_routers(
    deps,
    settings,
    product_name: str,
    version: str,
    names: Sequence[str],
) -> list:
    """Return the subset of standard routers named by `names`.

    Order is preserved: `build_standard_routers(..., names=["llm", "health"])`
    returns `[llm_router, health_router]` in that order. FastAPI's
    `include_router` registration is order-sensitive for overlapping routes —
    products that care can enforce ordering by ordering their opt-in list.

    Raises:
        ValueError: if any name is not in the registry. Error message names
            every unknown key and lists the valid keys for quick fixing.
    """
    unknown = [n for n in names if n not in _STANDARD_ROUTERS]
    if unknown:
        raise ValueError(
            f"Unknown standard router(s): {unknown}. "
            f"Valid: {sorted(_STANDARD_ROUTERS)}"
        )
    return [_STANDARD_ROUTERS[n](deps, settings, product_name, version) for n in names]
