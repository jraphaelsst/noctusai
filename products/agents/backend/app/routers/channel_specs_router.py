"""The org-specs surface of the channel API (Julia-line CONTRACT §E / §F): social-wiring edits ITS org's business
specifications for the agent -- as DATA -- through us.

* ``GET /api/channels/agents/{agent_key}/specs``  -- the declared specs (chave / tipo / rotulo / descricao), the
  org's values, ``faltando``, ``invalidas`` and ``modo_validacao``.
* ``PUT /api/channels/agents/{agent_key}/specs``  -- ``{"valores": {...}}``; the SAME write path as the studio PUT
  (:func:`app.routers.studio_conteudo_router.aplicar_org_specs`): 200 + ``invalidas`` in report mode, 422 +
  ``violacoes`` in block mode, 422 ``spec_nao_declarada`` for a key the definition does not declare.

Auth: a channel token (``issuer=social-wiring``) holding ``agents:channel-specs`` -- minted ONLY by the platform
grant -- and bound to ``agent_key``. The org is the token's, never the body's. Only DECLARED keys are org-editable;
everything platform-fixed (the core prompt, fixed rules, tools) is not a spec and is unreachable from here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import SCOPE_CHANNEL_SPECS, _require_channel
from app.routers.channel_threads_router import _agente_do_token
from app.routers.studio_agents_router import get_studio_definition_store_dep
from app.routers.studio_conteudo_router import aplicar_org_specs, get_spec_validacao_dep, ler_org_specs
from app.schemas.studio_conteudo import OrgSpecsOut, OrgSpecsUpdateRequest
from app.studio.especificacoes_service import ConfigValidacao
from noctusai_lib.api.auth.session import AuthContext

__all__ = ["router", "require_channel_specs"]

require_channel_specs = _require_channel(SCOPE_CHANNEL_SPECS)

router = APIRouter(tags=["channel-specs"])


@router.get("/api/channels/agents/{agent_key}/specs", response_model=OrgSpecsOut)
def channel_get_specs(
    agent_key: str,
    ctx: AuthContext = Depends(require_channel_specs),
    store=Depends(get_studio_definition_store_dep),
    config: ConfigValidacao = Depends(get_spec_validacao_dep),
) -> OrgSpecsOut:
    _agente_do_token(store, ctx, agent_key)
    return ler_org_specs(store, ctx, agent_key, config)


@router.put("/api/channels/agents/{agent_key}/specs", response_model=OrgSpecsOut)
def channel_put_specs(
    agent_key: str,
    payload: OrgSpecsUpdateRequest,
    ctx: AuthContext = Depends(require_channel_specs),
    store=Depends(get_studio_definition_store_dep),
    config: ConfigValidacao = Depends(get_spec_validacao_dep),
) -> OrgSpecsOut:
    _agente_do_token(store, ctx, agent_key)
    return aplicar_org_specs(store, ctx, agent_key, payload.valores, config)
