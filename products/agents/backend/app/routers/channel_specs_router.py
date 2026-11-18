"""The org-specs surface of the channel API (Julia-line CONTRACT §E / §F): social-wiring edits ITS org's business
specifications for the agent -- as DATA -- through us.

* ``GET /api/channels/agents/{agent_key}/specs``  -- the declared specs (chave / tipo / rotulo / descricao), the
  org's values, ``faltando``, ``invalidas`` and ``modo_validacao``.
* ``PUT /api/channels/agents/{agent_key}/specs``  -- ``{"valores": {...}, "ator": {user_id, papel?, nome?, email?}}`` (``ator`` required,
  422 ``ator_obrigatorio``; PRODUCT-ATTESTED -- the channel token vouches for the person, recorded as ``updated_by`` + audit); the SAME write path as the studio PUT
  (:func:`app.routers.studio_conteudo_router.aplicar_org_specs`): 200 + ``invalidas`` in report mode, 422 +
  ``violacoes`` in block mode, 422 ``spec_nao_declarada`` for a key the definition does not declare.

Owner decision 2026-11-18: an org's business knowledge/contacts are org-owned data, edited by the org's own admins in
social-wiring (which forwards only for an org admin). Writable keys are the CLOSED allowlist
``especificacoes_service.CHAVES_EDITAVEIS_PELA_ORG`` (422 ``spec_nao_editavel_pela_org`` for any other key, whole request
refused); platform staff keep ``PUT /api/studio/plataforma/agents/{key}/products/{product}/orgs/{org_id}/specs`` for every key.

Auth: a channel token (``issuer=social-wiring``) holding ``agents:channel-specs`` -- minted ONLY by the platform
grant -- and bound to ``agent_key``. The org is the token's, never the body's. Only DECLARED keys are org-editable;
everything platform-fixed (the core prompt, fixed rules, tools) is not a spec and is unreachable from here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import SCOPE_CHANNEL_SPECS, _require_channel
from app.routers.channel_threads_router import _agente_do_token
from app.routers.studio_agents_router import get_studio_definition_store_dep, http_error
from app.routers.studio_conteudo_router import aplicar_org_specs, get_spec_validacao_dep, ler_org_specs
from app.schemas.studio_conteudo import OrgSpecsChannelUpdateRequest, OrgSpecsOut
from app.studio.especificacoes_service import ConfigValidacao, chave_editavel_pela_org
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
    payload: OrgSpecsChannelUpdateRequest,
    ctx: AuthContext = Depends(require_channel_specs),
    store=Depends(get_studio_definition_store_dep),
    config: ConfigValidacao = Depends(get_spec_validacao_dep),
) -> OrgSpecsOut:
    _agente_do_token(store, ctx, agent_key)
    if payload.ator is None:
        raise http_error(422, "ator_obrigatorio", "Informe o usuário que está alterando (ator): não há escrita anônima de produto.")
    # closed allowlist: only the org-owned business data is writable here; the rest is staff-only (platform route). The detail
    # never echoes the keys the caller sent.
    if any(not chave_editavel_pela_org(c) for c in payload.valores):
        raise http_error(
            422, "spec_nao_editavel_pela_org",
            "Uma ou mais especificações só podem ser alteradas pela equipe NoctusAI. Nada foi salvo.",
        )
    # The next turn compiles with the new values by construction (the compile cache key carries the org-specs hash).
    # NOC-REMEDIATE[org-specs-reeval]: no eval re-run is triggered when an org changes its knowledge; trigger a published-content re-eval of the org's agent after this write (agents evals) — 2026-11-18
    return aplicar_org_specs(store, ctx, agent_key, payload.valores, config, ator=payload.ator)
