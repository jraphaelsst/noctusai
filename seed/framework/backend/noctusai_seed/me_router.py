"""``create_me_router(deps)`` -- ``/api/me/access`` + the platform org picker endpoints.

Auto-mounted on EVERY product by ``create_product_app`` (registry key ``"me"``):

* ``GET /api/me/access`` -- auth required, deliberately NOT license-gated: how the SPA
  asks "may I be here?" (answers ``has_access=false`` instead of 403). Carries the
  ``org_selection`` block (picker state) and the EFFECTIVE ``org_role`` -- the SPA's
  role labels come from here, never from ``user_metadata``.
* ``GET /api/me/org-choices`` / ``PUT`` / ``DELETE /api/me/org-choice`` -- the org picker
  (owner decisions 2026-10-08, widened to members 2026-10-13). WHO may choose: PLATFORM
  STAFF (``noctus_users.role='admin'`` AND home org ``is_platform``) -- any org licensed for
  the product, ``aal2`` required when the product asks for it (``403 mfa_required``), the home
  org ("Entrar como NoctusAI (minha org)") always LAST (owner decision 2026-10-12) -- OR any
  user with an ACTIVE membership (``public.org_memberships``): only the orgs they are an
  active member of AND that are licensed for the product, never ``aal2`` (Q1), their last-active
  org first. A PUT for an org that is neither is ``403 not_a_member``; a product that is not
  ``org_picker_ready`` answers ``409 product_not_ready``.

Identity resolves through the ONE effective-org resolver
(:mod:`noctusai_lib.api.auth.effective_org`); the selection itself is written only by
the SECURITY DEFINER RPCs (:mod:`noctusai_lib.api.auth.org_selection`).

KB § PATTERNS/backend/tenancy-license-gate.md § Platform org picker
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.effective_org import (
    EffectiveOrg,
    is_platform_staff,
    resolve_effective_org_for_request,
)
from noctusai_lib.api.auth.mfa.aal import read_session_claims
from noctusai_lib.api.auth.org_selection import OrgSelectionError
from noctusai_lib.domain.licensing import (
    LicenseCheckUnavailable,
    enforce_license,
    get_license_gate,
    org_sem_licenca,
)
from noctusai_lib.primitives.roles import is_customer_role

logger = logging.getLogger(__name__)

NOT_A_MEMBER = "not_a_member"
MFA_REQUIRED = "mfa_required"
PRODUCT_NOT_READY = "product_not_ready"


def _err(status: int, detail: str, code: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"detail": detail, "code": code})


def _org_dto(core_client: Any, org_id: Optional[str]) -> Optional[dict]:
    """``{"id", "nome"}`` for an org id (``None`` when no id / no row)."""
    if not org_id:
        return None
    result = (
        core_client.table("organizations").select("id, nome")
        .eq("id", str(org_id)).limit(1).execute()
    )
    rows = result.data or []
    nome = rows[0].get("nome") if rows else None
    return {"id": str(org_id), "nome": nome}


class OrgChoiceBody(StrictHttpModel):
    org_id: UUID


def _selection_block(core: Any, eff: Optional[EffectiveOrg]) -> dict:
    home = _org_dto(core, eff.home_org_id) if eff is not None else None
    effective = _org_dto(core, eff.org_id) if eff is not None else None
    is_staff = bool(eff is not None and eff.is_staff)
    can_select = bool(eff is not None and eff.member_can_select)
    return {
        "available": is_staff or can_select,
        # Staff: every entry is a choice. A member: only when the last-active org cannot be
        # served (not licensed for this product / no longer an active membership) -- Q2.
        "required": (is_staff and eff.selection_id is None)
        or bool(eff is not None and eff.member_choice_required),
        "mfa_required": bool(eff is not None and eff.mfa_required),
        "acting": bool(eff is not None and eff.acting),
        "org": effective,
        "home_org": home,
        "selection_id": eff.selection_id if eff is not None else None,
        "org_role": eff.org_role if eff is not None else None,
    }


def create_me_router(deps) -> APIRouter:
    router = APIRouter(prefix="/api/me", tags=["me"])

    def _access_body(core: Any, user_id: Any, token: str) -> dict:
        try:
            # Ungated picker bootstrap: staff without a selection get the home
            # snapshot + `required`, never the gated 409 org_selection_required.
            eff = resolve_effective_org_for_request(
                core, user_id, token=token, require_selection=False
            )
        except HTTPException:
            raise
        except LicenseCheckUnavailable:
            raise HTTPException(status_code=503, detail="Falha ao verificar a licença da organização")
        except Exception:
            logger.error("me_access_lookup_error user_id=%s", user_id, exc_info=True)
            raise HTTPException(status_code=503, detail="Falha ao resolver organizacao do usuario")
        gate = get_license_gate()
        slug = gate.product_slug if gate else None
        has_access = False
        if eff is not None and eff.org_id:
            try:
                enforce_license(eff.org_id, eff.org_role, allow_customer=True)
                has_access = True
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
        block = _selection_block(core, eff)
        return {
            "has_access": has_access,
            "product_slug": slug,
            "org": block["org"],
            "org_selection": block,
        }

    def _is_staff(core: Any, user_id: Any) -> bool:
        try:
            return is_platform_staff(core, user_id)
        except Exception:
            logger.error("org_picker_staff_lookup_error user_id=%s", user_id, exc_info=True)
            raise HTTPException(status_code=503, detail="Falha ao resolver organizacao do usuario")

    def _picker_ctx(core: Any, user, token: str, *, need_aal2: bool = True):
        """aal2 (STAFF only, when the product requires it) -> product ready. Members never
        need aal2 (owner decision Q1). Returns ``(slug, store, session_id, is_staff)``."""
        is_staff = _is_staff(core, user.id)
        session_id, aal = read_session_claims(token, user_id=user.id)
        gate = get_license_gate()
        store = gate.selection_store if gate else None
        slug = gate.product_slug if gate and not gate.exempt else None
        try:
            requires_mfa = not (store and slug) or store.requires_mfa(slug)
        except Exception:
            logger.error("org_picker_mfa_lookup_error product=%s", slug, exc_info=True)
            raise HTTPException(status_code=503, detail="Falha ao consultar o produto")
        if is_staff and need_aal2 and requires_mfa and aal != "aal2":
            raise _err(403, "Verificação em duas etapas (MFA) obrigatória.", MFA_REQUIRED)
        try:
            ready = bool(store and slug and store.product_ready(slug))
        except Exception:
            logger.error("org_picker_ready_lookup_error product=%s", slug, exc_info=True)
            raise HTTPException(status_code=503, detail="Falha ao consultar o produto")
        if not ready:
            raise _err(409, "Este produto ainda não permite escolher a organização.", PRODUCT_NOT_READY)
        return slug, store, session_id, is_staff

    @router.get("/access")
    async def me_access(auth=Depends(deps.get_current_user_ungated)) -> dict:
        user, token = auth
        return _access_body(deps.get_core_client(), user.id, token)

    @router.get("/org-choices")
    async def org_choices(response: Response, auth=Depends(deps.get_current_user_ungated)) -> dict:
        user, token = auth
        core = deps.get_core_client()
        slug, store, _sid, is_staff = _picker_ctx(core, user, token)
        response.headers["Cache-Control"] = "no-store"
        try:
            eff = resolve_effective_org_for_request(core, user.id)  # home (no token)
            licensed = store.licensed_orgs(slug)
            roles = {} if is_staff else {
                m.org_id: m.org_role for m in store.memberships(user.id)
                if not is_customer_role(m.org_role)
            }
        except Exception:
            logger.error("org_choices_error user_id=%s", user.id, exc_info=True)
            raise HTTPException(status_code=503, detail="Falha ao listar organizações")
        home_id = str(eff.org_id) if eff is not None and eff.org_id else None
        if not is_staff:
            # A member sees only the orgs they are an ACTIVE member of AND that are licensed
            # for this product; their last-active org (profile home) leads.
            mine = sorted(
                ({**o, "is_home": str(o["id"]) == home_id, "org_role": roles[str(o["id"])]}
                 for o in licensed if str(o["id"]) in roles),
                key=lambda o: (not o["is_home"], (o.get("nome") or "").lower()),
            )
            return {"orgs": mine}
        others = sorted(
            (o for o in licensed if str(o["id"]) != home_id),
            key=lambda o: (o.get("nome") or "").lower(),
        )
        orgs = [{**o, "is_home": False} for o in others]
        if home_id:
            # Home LAST: a client org is the usual destination; home is the explicit opt-in.
            orgs.append({**_org_dto(core, home_id), "is_home": True})
        return {"orgs": orgs}

    @router.put("/org-choice")
    async def put_org_choice(body: OrgChoiceBody, auth=Depends(deps.get_current_user_ungated)) -> dict:
        user, token = auth
        core = deps.get_core_client()
        slug, store, session_id, _is_staff_caller = _picker_ctx(core, user, token)
        if not session_id:
            raise _err(403, "Sessão sem identificador.", MFA_REQUIRED)
        try:
            store.set(user.id, slug, str(body.org_id), session_id)
        except OrgSelectionError as exc:
            if exc.code == "not_a_member":
                raise _err(403, "Você não é membro desta organização.", NOT_A_MEMBER)
            if exc.code == "product_not_ready":
                raise _err(409, "Este produto ainda não permite escolher a organização.", PRODUCT_NOT_READY)
            raise org_sem_licenca()
        except Exception:
            logger.error("org_choice_set_error user_id=%s product=%s", user.id, slug, exc_info=True)
            raise HTTPException(status_code=503, detail="Falha ao registrar a organização")
        return _access_body(core, user.id, token)

    @router.delete("/org-choice", status_code=204)
    async def delete_org_choice(
        all_products: bool = Query(False, alias="all"),
        auth=Depends(deps.get_current_user_ungated),
    ) -> Response:
        """End this product's selection (``exit``); ``?all=true`` ends EVERY product's
        selection of the caller (``logout`` -- the SPA calls it before signing out)."""
        user, _token = auth
        # Ends only the CALLER's own selections (staff or member alike): no role gate needed.
        if all_products:
            gate = get_license_gate()
            store = gate.selection_store if gate else None
            if store is not None:
                try:
                    store.end(user.id, None, "logout")
                except Exception:
                    logger.error("org_choice_end_all_error user_id=%s", user.id, exc_info=True)
                    raise HTTPException(status_code=503, detail="Falha ao encerrar as seleções")
            return Response(status_code=204)
        gate = get_license_gate()
        store = gate.selection_store if gate else None
        slug = gate.product_slug if gate and not gate.exempt else None
        if store is not None and slug:
            try:
                store.end(user.id, slug, "exit")
            except Exception:
                logger.error("org_choice_end_error user_id=%s product=%s", user.id, slug, exc_info=True)
                raise HTTPException(status_code=503, detail="Falha ao encerrar a seleção")
        return Response(status_code=204)

    return router


__all__ = ["create_me_router"]
