"""Onboarding staff channel -- agents writes a client org's Julia settings as the NoctusAI team (service tier).

  GET /api/julia/onboarding/whoami   the harmless read-only check the channel's holder (agents) makes to prove the credential
                                     works: answers only {"ok": true, "escopo": <the onboarding scope>} -- no org, no data
  PUT /api/julia/onboarding/orgs/{org_id}/configuracoes/{setting}   body {"corpo": {...}, "ator": {"user_id": uuid}, "grant_id"?: uuid}

Auth (every layer is a refusal, none a hint):
  - no / invalid / expired credential  -> 401 (the auth dependency, before anything here)
  - a human session                    -> 403 `product_required`   (an org admin never reaches another org through here)
  - missing scope                      -> 403 `scope_missing`      (`social-wiring:onboarding-settings`)
  - issuer != `noctus-platform`        -> 403 `issuer_not_allowed` (the platform-minted service token, never an org's token)
  - org not found                      -> 404 `org_nao_encontrada`
  - setting outside the allow-list     -> 422 `setting_nao_permitida` (`julia_onboarding_service.SETTINGS`)

The target org is the PATH's, which is why the credential is the platform's, not an org's: agents holds it only to act
for a platform admin with a live `plataforma` grant, and passes that staff user as `ator` (product-attested, the same
trust the channel-specs PUT puts in `ator`). The actor and `via=onboarding` land in the `configuracao_alterada` event.
"""
from typing import Any, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.access_tiers import access_tier, make_router
from noctusai_lib.api.auth.session import AuthContext, require_scopes
from noctusai_lib.primitives.exceptions import AppException

from app.dependencies import get_auth_context, get_core_client, get_scoped_admin_client
from app.services import julia_onboarding_service as svc

ONBOARDING_SCOPE = "social-wiring:onboarding-settings"
ONBOARDING_ISSUER = "noctus-platform"


def _require_onboarding(
    ctx: AuthContext = Depends(require_scopes(ONBOARDING_SCOPE, get_auth_context=get_auth_context, restrict="product_only")),
) -> AuthContext:
    if ctx.issuer != ONBOARDING_ISSUER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"detail": "Token issuer not allowed for this route", "code": "issuer_not_allowed"},
        )
    return ctx


router = make_router(tier="service", guard=_require_onboarding, tags=["julia-onboarding"])


def get_onboarding_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


def get_onboarding_core() -> Any:
    """DI seam: the ``public``-schema client (organizations)."""
    return get_core_client()


class Ator(StrictHttpModel):
    user_id: UUID


class ConfiguracaoIn(StrictHttpModel):
    corpo: dict[str, Any] = Field(max_length=20)
    ator: Ator
    grant_id: Optional[UUID] = None


@router.get("/api/julia/onboarding/whoami")
@access_tier("service")
def get_whoami() -> dict[str, Any]:
    """Reached only with a valid, unexpired platform-issued token carrying the onboarding scope (the guard refuses
    everything else, 401 / 403): so a 200 proves credential, scope and issuer end to end. Answers no org and no data."""
    return {"data": {"ok": True, "escopo": ONBOARDING_SCOPE}}


@router.put("/api/julia/onboarding/orgs/{org_id}/configuracoes/{setting}")
@access_tier("service")
def put_configuracao(
    org_id: UUID, setting: str, payload: ConfiguracaoIn,
    client: Any = Depends(get_onboarding_client),
    core: Any = Depends(get_onboarding_core),
) -> dict[str, Any]:
    try:
        existe = svc.org_existe(core, org_id)
    except Exception as exc:
        raise AppException("org_indisponivel", "Não foi possível consultar a organização.", 503) from exc
    if not existe:
        raise AppException("org_nao_encontrada", "Organização não encontrada.", 404)
    return {"data": svc.aplicar(
        client, org_id, setting, payload.corpo, ator_id=str(payload.ator.user_id),
        grant_id=str(payload.grant_id) if payload.grant_id else None,
    )}
