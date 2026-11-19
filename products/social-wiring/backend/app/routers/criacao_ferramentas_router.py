"""CoreStudio criacao read tools -- the Diretor de Criacao (agents) calls these back during a turn.

  POST /api/criacao/ferramentas/{nome}     product token, scope `social-wiring:criacao-tools`, issuer `agents`

Same gate and error envelope as Julia's tools (`noctusai_lib.api.agent_tools.make_agent_tools_router`). READ-ONLY;
the org is the token's. Contract: `core-studio-build/specs/criacao-pipeline-contract.md` section 4.
"""
from typing import Any

from app.dependencies import coerce_org_uuid, get_auth_context, get_scoped_admin_client
from app.services.criacao_ferramentas_service import CRIACAO_TOOLS_ISSUER, CRIACAO_TOOLS_SCOPE, REGISTRY
from noctusai_lib.api.agent_tools import make_agent_tools_router


def get_criacao_client() -> Any:
    """DI seam: the schema-scoped service-role client the tools read through (tests override)."""
    return get_scoped_admin_client("social_wiring")


router = make_agent_tools_router(
    "/api/criacao/ferramentas",
    CRIACAO_TOOLS_SCOPE,
    REGISTRY,
    get_auth_context=get_auth_context,
    get_client=get_criacao_client,
    coerce_org=coerce_org_uuid,
    issuer=CRIACAO_TOOLS_ISSUER,
    tags=["criacao-ferramentas"],
)

__all__ = ["router"]
