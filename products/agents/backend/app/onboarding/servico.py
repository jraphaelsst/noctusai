"""The ONE onboarding apply entry point shared by the staff route and the interviewer's tool.

``aplicar_na_org`` re-resolves the live grant (so a grant revoked mid-interview stops the write), reads the org's stored
specs, runs :func:`app.onboarding.aplicar.aplicar` and writes the valid spec values through the one org-spec write path
(``aplicar_org_specs``: validation + audit). Raises the same typed HTTP errors as the route; the interviewer tool turns
them into a refusal the model can read.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from noctusai_lib.api.auth.session import AuthContext

from app.grants.store import GrantStore
from app.onboarding import aplicar as ap
from app.onboarding.sw_settings import SwSettingsPort
from app.routers.plataforma_org_specs_router import _alvo
from app.routers.studio_agents_router import http_error
from app.routers.studio_conteudo_router import aplicar_org_specs, ler_org_specs
from app.studio.especificacoes_service import ConfigValidacao

__all__ = ["aplicar_na_org", "valores_armazenados"]


def valores_armazenados(out) -> dict[str, str]:
    return {v.chave: v.valor for v in out.valores}


def aplicar_na_org(
    *, store, grants: GrantStore, ctx: AuthContext, key: str, product: str, org_id: UUID, respostas: Mapping[int, Any],
    importados: frozenset[int] = frozenset(), confirmados: frozenset[int] = frozenset(), config: ConfigValidacao,
    sw: SwSettingsPort, origem_extra: Mapping[str, Any] | None = None,
) -> ap.Relatorio:
    alvo, grant = _alvo(store, grants, ctx, key, product, org_id)
    atual = ler_org_specs(store, alvo, key, config)
    if not atual.declaradas:
        raise http_error(409, "definicao_sem_especificacoes", "A definição ainda não declara especificações da organização.")
    origem = {
        "origem": "plataforma_onboarding", "produto": product, "grant_id": str(grant.id), "org_alvo": str(org_id),
        "ator_plataforma": str(ctx.user_id), **(origem_extra or {}),
    }
    return ap.aplicar(
        respostas, org_id=org_id, declaradas={d.chave: d.tipo for d in atual.declaradas}, armazenados=valores_armazenados(atual),
        nao_confirmados=importados - confirmados,
        config=config, gravar_specs=lambda v: aplicar_org_specs(store, alvo, key, v, config, origem=origem), sw=sw,
    )
