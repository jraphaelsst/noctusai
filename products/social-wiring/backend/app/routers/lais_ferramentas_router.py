"""Lais read tools -- agents calls these back during a turn (contract A3 / 2.2).

  POST /api/lais/ferramentas/{nome}     product token, scope `social-wiring:lais-tools`, issuer `agents`

Auth is the agents-bridge pattern (`agents_bridge_router`): `get_auth_context` composed with the
seed's `require_scopes(..., restrict="product_only")`, then an ISSUER check in the body of the
dependency (a scope string says what a token may do, never who holds it):

  - no / invalid / expired credential      -> 401 (the underlying auth dep, before anything here)
  - a human session                        -> 403 `product_required`
  - missing scope                          -> 403 `scope_missing`
  - issuer != agents                       -> 403 `issuer_not_allowed`
  - unknown tool                           -> 404 `ferramenta_desconhecida`
  - body does not fit the tool's model     -> 422 `invalid_field`

Success is the SW envelope `{"data": ...}`; errors are `AppException` (`{"error": {...}}`). The
org is the TOKEN's org (`ctx.org_id`) -- never a body field -- so one org's token cannot read
another org's catalogue. The response never contains owner/proprietario personal data
(`lais_ferramentas_service` reads an explicit column allow-list).
"""
import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import ValidationError

from noctusai_lib.api.auth.session import AuthContext, require_scopes
from noctusai_lib.primitives.exceptions import AppException

from app.dependencies import coerce_org_uuid, get_auth_context, get_scoped_admin_client
from app.services import lais_ferramentas_service as svc
from app.services.lais_contexto_service import TOOLS_TOKEN_ISSUER, TOOLS_TOKEN_SCOPE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lais/ferramentas", tags=["lais-ferramentas"])


def _require_tools(
    ctx: AuthContext = Depends(
        require_scopes(TOOLS_TOKEN_SCOPE, get_auth_context=get_auth_context, restrict="product_only")
    ),
) -> AuthContext:
    if ctx.issuer != TOOLS_TOKEN_ISSUER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"detail": "Token issuer not allowed for this route", "code": "issuer_not_allowed"},
        )
    return ctx


def get_ferramentas_client() -> Any:
    """DI seam: the schema-scoped service-role client the tools read through (tests override)."""
    return get_scoped_admin_client("social_wiring")


@router.post("/{nome}")
def post_ferramenta(
    nome: str,
    corpo: dict[str, Any] = Body(default_factory=dict),
    ctx: AuthContext = Depends(_require_tools),
    client: Any = Depends(get_ferramentas_client),
) -> dict[str, Any]:
    if nome not in svc.FERRAMENTAS:
        raise AppException("ferramenta_desconhecida", "Ferramenta desconhecida.", status_code=404)
    try:
        args = svc.ARGS[nome](**corpo).model_dump()
    except ValidationError as exc:
        campos = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        raise AppException(
            "invalid_field", "Argumentos inválidos.", status_code=422, details={"campos": campos},
        ) from exc
    org_id = coerce_org_uuid(ctx.org_id)
    data = svc.FERRAMENTAS[nome](client, org_id, args)
    svc.registrar_consulta(client, org_id, nome, args, data)  # feeds Relatorios "top imoveis"; never raises
    return {"data": data}


__all__ = ["router"]
