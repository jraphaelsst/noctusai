"""TEST-ONLY fixture: a published ``diretor-de-criacao`` (platform definition + the org's instance) for the ``app`` channel.

Every text is ``txt:<chave>`` and every tool description ``desc:<tool>`` (mechanism suites, no real wording). The definition
declares NO qualification standard: an ``app`` turn must run without one."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.criacao.ferramentas import CRIACAO_TOOLS
from app.stores.studio_definitions import SectionInput
from app.stores.studio_definitions_conteudo import FerramentaInput, TextoInput
from app.studio.textos_registry import chaves_exigidas
from tests.channels.julia_v2 import PLAT_ORG, texto_de

DIRETOR_KEY = "diretor-de-criacao"
RASCUNHO = {
    "provider": "openai", "model": "gpt-5.6-terra", "effort": "medium", "max_turns": 8,
    "tool_policy": {"web_search": False, "knowledge": False},
}
MARCA = UUID(int=0xB1)
OUTRA_MARCA = UUID(int=0xB2)


def montar_diretor(studio, catalog, org_id: UUID, user_id: UUID, controles: Any, *, key: str = DIRETOR_KEY,
                   modo: str = "ligado") -> Any:
    """Publish the platform definition and create the org's instance; returns the instance (the token's principal)."""
    from tests.studio.rt.fakes import publish

    studio.mark_platform_org(PLAT_ORG)
    d = studio.create_studio_agent(
        PLAT_ORG, key, "Diretor de Criação", None, runtime="llm", owner_product="social-wiring",
        definition_scope="plataforma", rascunho_padrao=RASCUNHO, instanciavel=False,
    )
    draft = studio.create_draft(PLAT_ORG, d.id, None, d.id)
    studio.update_draft(PLAT_ORG, draft.id, dict(RASCUNHO))
    studio.replace_sections(PLAT_ORG, draft.id, [SectionInput("persona", "Persona", 10, "Persona do teste.")])
    chaves = chaves_exigidas(
        tool_policy=RASCUNHO["tool_policy"], tem_skills=False, com_cliente=False, canal=True,
        ferramentas_ativas=frozenset(CRIACAO_TOOLS))
    studio.replace_textos(PLAT_ORG, draft.id, [TextoInput(c, texto_de(c)) for c in sorted(chaves)])
    studio.replace_ferramentas(PLAT_ORG, draft.id, [FerramentaInput(n, f"desc:{n}") for n in CRIACAO_TOOLS])
    publish(studio, PLAT_ORG, d, draft.id, user_id, catalog=catalog)
    studio.grant_definition_org(d.id, org_id)
    inst = studio.create_studio_agent(
        org_id, key, "Diretor de Criação", None, runtime="llm", owner_product="social-wiring",
        definition_scope="instancia", definition_agent_id=d.id,
    )
    inst = studio.update_agent(org_id, key, {"ativo": modo != "desligado"})
    controles.set(org_id, inst.id, modo=modo)
    return inst
