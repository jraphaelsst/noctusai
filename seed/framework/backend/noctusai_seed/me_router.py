"""``create_me_router(deps)`` -- ``/api/me/access`` + the platform org picker endpoints.

Auto-mounted on EVERY product by ``create_product_app`` (registry key ``"me"``):

* ``GET /api/me/access`` -- auth required, deliberately NOT license-gated: how the SPA
  asks "may I be here?" (answers ``has_access=false`` instead of 403). Carries the
  ``org_selection`` block (picker state) and the EFFECTIVE ``org_role`` -- the SPA's
  role labels come from here, never from ``user_metadata``.
* ``GET /api/me/org-choices`` / ``PUT`` / ``DELETE /api/me/org-choice`` -- the org picker
  (owner decision 2026-10-08). PLATFORM STAFF only (``noctus_users.role='admin'`` AND home
  org ``is_platform``): everyone else gets strict ``403 not_platform_staff``; staff
  without an aal2 session get ``403 mfa_required``; a product that is not
  ``org_picker_ready`` answers ``409 product_not_ready``. The listed orgs are those with
  an ACTIVE, non-expired license for this product, the home org always first.

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

logger = logging.getLogger(__name__)

NOT_PLATFORM_STAFF = "not_platform_staff"
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
    available = bool(eff is not None and eff.is_staff)
    return {
        "available": available,
        "required": available and eff.selection_id is None,
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
            eff = resolve_effective_org_for_request(core, user_id, token=token)
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

    def _staff_gate(core: Any, user_id: Any) -> None:
        try:
            staff = is_platform_staff(core, user_id)
        except Exception:
            logger.error("org_picker_staff_lookup_error user_id=%s", user_id, exc_info=True)
            raise HTTPException(status_code=503, detail="Falha ao resolver organizacao do usuario")
        if not staff:
            raise _err(403, "Acesso restrito à equipe da plataforma.", NOT_PLATFORM_STAFF)

    def _picker_ctx(core: Any, user, token: str, *, need_aal2: bool = True):
        """Staff gate -> aal2 -> product ready. Returns ``(slug, store, session_id)``."""
        _staff_gate(core, user.id)
        session_id, aal = read_session_claims(token, user_id=user.id)
        if need_aal2 and aal != "aal2":
            raise _err(403, "Verificação em duas etapas (MFA) obrigatória.", MFA_REQUIRED)
        gate = get_license_gate()
        store = gate.selection_store if gate else None
        slug = gate.product_slug if gate and not gate.exempt else None
        try:
            ready = bool(store and slug and store.product_ready(slug))
        except Exception:
            logger.error("org_picker_ready_lookup_error product=%s", slug, exc_info=True)
            raise HTTPException(status_code=503, detail="Falha ao consultar o produto")
        if not ready:
            raise _err(409, "Este produto ainda não permite escolher a organização.", PRODUCT_NOT_READY)
        return slug, store, session_id

    @router.get("/access")
    async def me_access(auth=Depends(deps.get_current_user_ungated)) -> dict:
        user, token = auth
        return _access_body(deps.get_core_client(), user.id, token)

    @router.get("/org-choices")
    async def org_choices(response: Response, auth=Depends(deps.get_current_user_ungated)) -> dict:
        user, token = auth
        core = deps.get_core_client()
        slug, store, _sid = _picker_ctx(core, user, token)
        response.headers["Cache-Control"] = "no-store"
        try:
            eff = resolve_effective_org_for_request(core, user.id)  # home (no token)
            licensed = store.licensed_orgs(slug)
        except Exception:
            logger.error("org_choices_error user_id=%s", user.id, exc_info=True)
            raise HTTPException(status_code=503, detail="Falha ao listar organizações")
        home_id = str(eff.org_id) if eff is not None and eff.org_id else None
        orgs = []
        if home_id:
            home = _org_dto(core, home_id)
            orgs.append({**home, "is_home": True})
        others = sorted(
            (o for o in licensed if str(o["id"]) != home_id),
            key=lambda o: (o.get("nome") or "").lower(),
        )
        orgs.extend({**o, "is_home": False} for o in others)
        return {"orgs": orgs}

    @router.put("/org-choice")
    async def put_org_choice(body: OrgChoiceBody, auth=Depends(deps.get_current_user_ungated)) -> dict:
        user, token = auth
        core = deps.get_core_client()
        slug, store, session_id = _picker_ctx(core, user, token)
        if not session_id:
            raise _err(403, "Sessão sem identificador.", MFA_REQUIRED)
        try:
            store.set(user.id, slug, str(body.org_id), session_id)
        except OrgSelectionError as exc:
            if exc.code == "not_platform_staff":
                raise _err(403, "Acesso restrito à equipe da plataforma.", NOT_PLATFORM_STAFF)
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
        core = deps.get_core_client()
        _staff_gate(core, user.id)
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
