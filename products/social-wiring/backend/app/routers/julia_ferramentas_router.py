"""Julia read tools -- agents calls these back during a turn (contract A3 / 2.2).

  POST /api/julia/ferramentas/{nome}     product token, scope `social-wiring:lais-tools`, issuer `agents`

Auth is the product-token pattern: `get_auth_context` composed with the
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
(`julia_ferramentas_service` reads an explicit column allow-list).
"""
import logging
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.access_tiers import access_tier
from noctusai_lib.api.agent_tools import AgentTool, make_agent_tools_router
from noctusai_lib.api.auth.session import AuthContext

from app.dependencies import coerce_org_uuid, get_auth_context, get_core_client, get_scoped_admin_client
from app.services import julia_ferramentas_service as svc
from app.services import julia_solicitacoes_titular_service as solicitacoes
from app.services.julia_contexto_service import TOOLS_TOKEN_ISSUER, TOOLS_TOKEN_SCOPE

logger = logging.getLogger(__name__)


def get_ferramentas_client() -> Any:
    """DI seam: the schema-scoped service-role client the tools read through (tests override)."""
    return get_scoped_admin_client("social_wiring")


class SolicitacaoTitularIn(StrictHttpModel):
    lead_ref: str = Field(min_length=1, max_length=64)
    chat_id: Optional[str] = Field(default=None, max_length=200)
    tipo: Literal[
        "confirmacao", "acesso", "correcao", "eliminacao", "portabilidade", "revogacao_consentimento", "oposicao",
        "info_compartilhamento", "outro",
    ]
    trecho: str = Field(min_length=1, max_length=2000)


def _extra_routes(router: APIRouter, require_tools: Any) -> None:
    @router.post("/solicitacao-titular")
    @access_tier("service")  # machine-to-machine: product token + scope + issuer via `require_tools`
    def post_solicitacao_titular(
        corpo: SolicitacaoTitularIn,
        ctx: AuthContext = Depends(require_tools),
        client: Any = Depends(get_ferramentas_client),
    ) -> dict[str, Any]:
        """Julia (the model) registers a lead's data-subject request (LGPD art. 18). It only RECORDS it and tells the
        org's admins; nothing is deleted or changed here -- an admin decides, and an erasure is the admin's act.
        Declared BEFORE `/{nome}`. Same auth as every tool: product token, scope `lais-tools`, issuer `agents`; the
        org is the token's."""
        org_id = coerce_org_uuid(ctx.org_id)
        linha = solicitacoes.registrar(
            client, get_core_client(), org_id=org_id, lead_ref=corpo.lead_ref, tipo=corpo.tipo, trecho=corpo.trecho,
            chat_id=corpo.chat_id,
        )
        return {"data": {"id": str(linha["id"]), "prazo_em": linha["prazo_em"]}}


def _registrar_consulta(client: Any, org_id: Any, nome: str, args: dict[str, Any], data: Any) -> None:
    svc.registrar_consulta(client, org_id, nome, args, data)  # feeds Relatorios "top imoveis"; never raises


router = make_agent_tools_router(
    "/api/julia/ferramentas",
    TOOLS_TOKEN_SCOPE,
    {nome: AgentTool(svc.ARGS[nome], fn) for nome, fn in svc.FERRAMENTAS.items()},
    get_auth_context=get_auth_context,
    get_client=get_ferramentas_client,
    coerce_org=coerce_org_uuid,
    issuer=TOOLS_TOKEN_ISSUER,
    tags=["julia-ferramentas"],
    extra_routes=_extra_routes,
    after_call=_registrar_consulta,
)

__all__ = ["router"]
