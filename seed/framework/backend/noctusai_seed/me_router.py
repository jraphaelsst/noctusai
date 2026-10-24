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
  user with an ACTIVE membership (``public.org_memberships``): only their ELIGIBLE orgs --
  active, non-customer, licensed for the product, not blocked from it (owner D5, 2026-10-14) --
  never ``aal2`` (Q1), their last-active org first. A PUT for an org that is neither is
  ``403 not_a_member``; a blocked one ``403 product_blocked``; a product that is not
  ``org_picker_ready`` answers ``409 product_not_ready``.

``/api/me/access`` (contract: roadmap multi-org-membership-2026-10 § S4b API contract) also
carries, for the S5 picker/switcher: ``org_selection.eligible_orgs`` (this product's eligible
orgs, D1 -- a choice is required iff >=2 and no valid selection), ``org_selection.platform_role``
(``owner``|``admin``|``null``) and ``org_selection.manageable_orgs`` (orgs whose team the caller
may manage: ACTIVE owner/admin memberships; platform staff manage ANY org, D2).

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
    PROFILE_COLUMNS,
    EffectiveOrg,
    is_platform_staff,
    resolve_effective_org_for_request,
    staff_role_of,
)
from noctusai_lib.api.auth._blocking import run_blocking, run_parallel
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
PRODUCT_BLOCKED = "product_blocked"
#: Org roles that may manage an org's team / moves / product blocks (D3, D5).
MANAGER_ORG_ROLES = ("owner", "admin")


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


def _org_names(core_client: Any, org_ids: list[str]) -> dict[str, Optional[str]]:
    """``{org_id: nome}`` for a handful of org ids (one query)."""
    ids = sorted({str(o) for o in org_ids if o})
    if not ids:
        return {}
    rows = core_client.table("organizations").select("id, nome").in_("id", ids).execute().data or []
    return {str(r["id"]): r.get("nome") for r in rows}


def _named_profile(core_client: Any, user_id: Any) -> Optional[dict]:
    """The caller's profile row with the home org's ``nome`` + ``is_platform`` embedded (one
    query: the staff rule AND the home org's name, no follow-up lookup)."""
    cols = PROFILE_COLUMNS.replace("organizations(is_platform)", "organizations(is_platform, nome)")
    rows = (
        core_client.table("noctus_users").select(cols)
        .eq("id", str(user_id)).limit(1).execute().data or []
    )
    return rows[0] if rows else None


def _named_memberships(core_client: Any, user_id: Any) -> list[dict]:
    """The caller's ACTIVE memberships with each org's ``nome`` embedded,
    ``[{org_id, org_role, organizations: {nome}}]`` (one query). Names every org the picker can
    list (eligible orgs are a subset) and the manageable ones are filtered from it."""
    return (
        core_client.table("org_memberships").select("org_id, org_role, organizations(nome)")
        .eq("user_id", str(user_id)).eq("status", "active").execute().data or []
    )


def _embedded_names(profile: Optional[dict], memberships: list[dict]) -> dict[str, Optional[str]]:
    """``{org_id: nome}`` from the embeds the two reads above already carry."""
    named = [(profile.get("org_id"), profile.get("organizations"))] if profile else []
    named += [(m.get("org_id"), m.get("organizations")) for m in memberships]
    return {str(org): emb.get("nome") for org, emb in named if org and isinstance(emb, dict)}


def _manageable_orgs(rows: list[dict], names: dict[str, Optional[str]]) -> list[dict]:
    """``[{id, nome, org_role}]`` by name, from the membership rows + the shared name map."""
    out = [{"id": str(r["org_id"]), "nome": names.get(str(r["org_id"])), "org_role": r.get("org_role")}
           for r in rows]
    return sorted(out, key=lambda o: (o.get("nome") or "").lower())


class OrgChoiceBody(StrictHttpModel):
    org_id: UUID


def _selection_block(names: dict[str, Optional[str]], eff: Optional[EffectiveOrg]) -> dict:
    """The picker block. ``names`` is the ONE ``{org_id: nome}`` map the caller fetched for every
    org the response mentions (home, effective, eligible, manageable) -- no per-org lookups."""

    def _dto(org_id: Optional[str]) -> Optional[dict]:
        return {"id": str(org_id), "nome": names.get(str(org_id))} if org_id else None

    home = _dto(eff.home_org_id) if eff is not None else None
    effective = _dto(eff.org_id) if eff is not None else None
    is_staff = bool(eff is not None and eff.is_staff)
    can_select = bool(eff is not None and eff.member_can_select)
    eligible = list(eff.eligible) if eff is not None else []
    home_id = str(eff.home_org_id) if eff is not None and eff.home_org_id else None
    eligible_orgs = sorted(
        ({"id": org, "nome": names.get(org), "org_role": role, "is_home": org == home_id}
         for org, role in eligible),
        key=lambda o: (not o["is_home"], (o.get("nome") or "").lower()),
    )
    return {
        "available": is_staff or can_select,
        # Staff: every entry is a choice. A member (D1): >=2 eligible orgs and no valid selection.
        "required": (is_staff and eff.selection_id is None)
        or bool(eff is not None and eff.member_choice_required),
        "eligible_orgs": eligible_orgs,
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
        """SYNC (worker thread). ONE round trip of wall time in the common case: the effective-org
        resolve (its reads issued together), the named profile (staff rule + home org name) and
        the named memberships run CONCURRENTLY, and the org names ride along as embeds. An org
        neither read names (staff acting in a customer org) costs one lookup after them (was
        ~11 sequential calls, then 3 serial hops)."""

        def _resolve():
            try:
                # Ungated picker bootstrap: staff without a selection get the home
                # snapshot + `required`, never the gated 409 org_selection_required.
                return resolve_effective_org_for_request(
                    core, user_id, token=token, require_selection=False
                )
            except HTTPException:
                raise
            except LicenseCheckUnavailable:
                raise HTTPException(status_code=503, detail="Falha ao verificar a licença da organização")
            except Exception:
                logger.error("me_access_lookup_error user_id=%s", user_id, exc_info=True)
                raise HTTPException(status_code=503, detail="Falha ao resolver organizacao do usuario")

        def _guarded(fn):
            def run():
                try:
                    return fn()
                except Exception:
                    logger.error("me_access_manageable_lookup_error user_id=%s", user_id, exc_info=True)
                    raise HTTPException(status_code=503, detail="Falha ao resolver organizacao do usuario")
            return run

        eff, profile, memberships = run_parallel(
            _resolve,
            _guarded(lambda: _named_profile(core, user_id)),
            _guarded(lambda: _named_memberships(core, user_id)),
        )
        platform_role = staff_role_of(profile)
        manage_rows = [m for m in memberships if m.get("org_role") in MANAGER_ORG_ROLES]
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
        wanted = [o for o in (eff.home_org_id, eff.org_id) if o] if eff is not None else []
        wanted += [org for org, _role in (eff.eligible if eff is not None else ())]
        wanted += [str(r["org_id"]) for r in manage_rows]
        names = _embedded_names(profile, memberships)
        # Only an org neither read named (staff acting in a customer org) costs a lookup.
        missing = [o for o in wanted if str(o) not in names]
        if missing:
            names.update(_org_names(core, missing))
        block = _selection_block(names, eff)
        block["platform_role"] = platform_role
        block["manage_any_org"] = platform_role is not None
        block["manageable_orgs"] = _manageable_orgs(manage_rows, names)
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
        return await run_blocking(_access_body, deps.get_core_client(), user.id, token)

    @router.get("/org-choices")
    async def org_choices(response: Response, auth=Depends(deps.get_current_user_ungated)) -> dict:
        user, token = auth
        response.headers["Cache-Control"] = "no-store"
        return await run_blocking(_org_choices, deps.get_core_client(), user, token)

    def _org_choices(core: Any, user, token: str) -> dict:
        slug, store, _sid, is_staff = _picker_ctx(core, user, token)
        try:
            eff = resolve_effective_org_for_request(core, user.id)  # home (no token)
            licensed = store.licensed_orgs(slug)
            blocked = set() if is_staff else store.blocked_orgs(user.id, slug)
            roles = {} if is_staff else {
                m.org_id: m.org_role for m in store.memberships(user.id)
                if not is_customer_role(m.org_role) and str(m.org_id) not in blocked
            }
        except Exception:
            logger.error("org_choices_error user_id=%s", user.id, exc_info=True)
            raise HTTPException(status_code=503, detail="Falha ao listar organizações")
        home_id = str(eff.org_id) if eff is not None and eff.org_id else None
        if not is_staff:
            # A member sees only their ELIGIBLE orgs: ACTIVE, non-customer, licensed for this
            # product and not blocked from it (D5); their last-active org (profile home) leads.
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
        return await run_blocking(_put_org_choice, core, user, token, body)

    def _put_org_choice(core: Any, user, token: str, body: OrgChoiceBody) -> dict:
        slug, store, session_id, _is_staff_caller = _picker_ctx(core, user, token)
        if not session_id:
            raise _err(403, "Sessão sem identificador.", MFA_REQUIRED)
        try:
            store.set(user.id, slug, str(body.org_id), session_id)
        except OrgSelectionError as exc:
            if exc.code == "not_a_member":
                raise _err(403, "Você não é membro desta organização.", NOT_A_MEMBER)
            if exc.code == "product_blocked":
                raise _err(403, "Seu acesso a este produto nesta organização está bloqueado.", PRODUCT_BLOCKED)
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
