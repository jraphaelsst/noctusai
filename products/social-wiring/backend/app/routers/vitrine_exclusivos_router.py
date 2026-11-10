"""`GET /api/vitrine/exclusivos` -- the org's exclusive listings for the exclusividades showcase (owner 2026-11-09).

NOT public: key-authenticated, 1 key = 1 consumer. The caller is a `noc_` product token minted by an org admin through the
platform's existing `POST /api/settings/api-tokens` (name e.g. `exclusividades`, scope `vitrine:exclusivos:read`); the seed
stores it hashed, supports revoke and `last_used_at`. The org comes from the token, never from the URL. No key / wrong key /
revoked key: strict 401; a key without the scope: 403 `scope_missing`; a user session: 403 `product_required`. An org that
has not opted in (`vitrine_exclusivos_orgs`) is a 404. Read-only; the response carries public listing fields only
(`app.services.vitrine_exclusivos_service.CAMPOS_SAIDA`).
"""
# No `from __future__ import annotations`: slowapi resolves the `Request` parameter from the signature.
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from noctusai_lib.api.auth.session import TOKEN_SCOPES, AuthContext, require_scopes

from app.config import settings
from app.dependencies import coerce_org_uuid, get_admin_client, get_auth_context
from app.rate_limit import limiter
from app.services.vitrine_exclusivos_service import VitrineExclusivosService

SCOPE = "vitrine:exclusivos:read"
TOKEN_SCOPES.register(SCOPE)  # listed by GET /api/settings/api-tokens/scopes (the mint UI)

router = APIRouter(prefix="/api/vitrine", tags=["vitrine-exclusivos"])


def get_vitrine_service() -> VitrineExclusivosService:
    """DI seam (tests override with a Fake-backed client)."""
    return VitrineExclusivosService(get_admin_client())


@router.get("/exclusivos")
@limiter.limit(settings.webhook_rate_limit)
def listar_exclusivos(
    request: Request,
    response: Response,
    ctx: AuthContext = Depends(require_scopes(SCOPE, get_auth_context=get_auth_context, restrict="product_only")),
    svc: VitrineExclusivosService = Depends(get_vitrine_service),
) -> dict:
    org_id = coerce_org_uuid(ctx.org_id)
    site = svc.site_url(org_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Vitrine de exclusivos não habilitada para esta organização")
    response.headers["Cache-Control"] = "private, max-age=300"
    return {"atualizado_em": svc.atualizado_em(org_id), "imoveis": svc.exclusivos(org_id, site)}
