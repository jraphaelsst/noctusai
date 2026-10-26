"""TEST-ONLY fixture: a complete Julia v2 world (platform definition + org instance + published standard).

Not one model-visible word is real here: every text is ``txt:<chave>`` (plus its placeholders) and every tool
description ``desc:<tool>`` -- the suites assert on MECHANISM, and on the fact that the words come from rows.
The qualification standard is the CONTRACT §4.3 ``imob-lead`` v1 fixture, extended with the identity criteria
(nome / email / cpf / rg) the owner requires before the visit.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from app.channels.tool_registry import TOOLS
from app.qualificacao.models import CriterioDef
from app.stores.studio_definitions import SectionInput
from app.stores.studio_definitions_conteudo import DecisaoInput, FerramentaInput, TextoInput
from app.studio.textos_registry import TEXTOS, chaves_exigidas
from tests.qualificacao.fixture_v1 import versao_v1
from tests.qualificacao.harness import ADMIN

PLAT_ORG = UUID(int=2)

#: TEST DATA (not a code registry): the key + first-draft settings + qualification attributes of the world's agent.
JULIA_KEY = "julia"
JULIA_RASCUNHO = {
    "provider": "openai", "model": "gpt-5.6-terra", "effort": "medium", "max_turns": 8,
    "tool_policy": {"web_search": False, "knowledge": False},
}

#: ``parametros`` of the tools whose enums carry labels (the rows hold every word of them).
_PARAMETROS: dict[str, dict[str, str]] = {
    "handoff": {
        "motivo_codigo": "reason code", "motivo_codigo.pedido_humano": "asks for a person",
        "motivo_codigo.reclamacao": "complains", "motivo": "short reason",
    },
    "registrar_perfil": {"itens": "answers", "itens.criterio": "criterion key", "itens.trecho": "lead's words"},
    "oferecer_imoveis": {"modo": "mode", "modo.campanha": "the campaign one", "modo.similares": "similar ones"},
}


def texto_de(chave: str) -> str:
    spec = TEXTOS[chave]
    return " ".join([f"txt:{chave}", *(("{" + p + "}") for p in spec.placeholders_permitidos)])


def textos_completos() -> list[TextoInput]:
    """A row for every REQUIRED key of a channel agent with a standard (the optional ones stay empty)."""
    chaves = chaves_exigidas(
        tool_policy={"web_search": False, "knowledge": False}, tem_skills=True, com_cliente=False, canal=True,
        com_qualificacao=True,
    )
    return [TextoInput(c, texto_de(c)) for c in sorted(chaves)]


def versao_com_identidade():
    """imob-lead v1 + the identity criteria; ``pronto_para_corretor`` also needs the identity complete, and the
    identity is asked only once a visit intent exists."""
    v = versao_v1()
    base = tuple(c for c in v.criterios if c.chave not in ("nome", "email"))
    ident = tuple(
        CriterioDef(chave=k, grupo="contato", rotulo=k.upper(), descricao_modelo=f"identity {k}", tipo="identificacao",
                    ordem=900 + i)
        for i, k in enumerate(("nome", "email", "cpf", "rg"))
    )
    estagios = tuple(
        replace(e, regra={"todos": [e.regra, {"identificacao": "completa"}]}) if e.chave == "pronto_para_corretor" else e
        for e in v.estagios
    )
    parametros = replace(v.parametros, pedir_identificacao_quando={"evento": "quer_visitar"})
    return replace(v, criterios=base + ident, estagios=estagios, parametros=parametros)


def publicar_padrao(padroes, *, versao=None) -> UUID:
    v = versao or versao_com_identidade()
    padrao = padroes.criar_padrao("imob-lead", "Imobiliaria: lead", None)
    vid = padroes.criar_rascunho(padrao.id, "v1", None)
    for c in v.criterios:
        padroes.salvar_criterio(vid, c)
    for e in v.estagios:
        padroes.salvar_estagio(vid, e)
    padroes.salvar_parametros(vid, v.parametros)
    padroes.publicar(vid, ADMIN)
    return vid


@dataclass
class MundoJulia:
    definicao: Any
    instancia: Any
    versao: Any
    padrao_versao_id: UUID


def montar_julia_v2(
    studio, catalog, org_id: UUID, user_id: UUID, *, ativo_modo: str = "ligado", controles=None,
    obrigatoria: dict[str, str] | None = None, textos_extra: list[TextoInput] | None = None,
    sem_ferramentas: tuple[str, ...] = (), com_decisao: bool | str = False, publicar: bool = True,
) -> MundoJulia:
    """Platform definition (published) + the org's instance. ``obrigatoria`` maps tool -> skill that gates it."""
    from tests.studio.rt.fakes import publish

    studio.mark_platform_org(PLAT_ORG)
    d = studio.create_studio_agent(
        PLAT_ORG, JULIA_KEY, "Julia", None, runtime="llm", owner_product="social-wiring",
        definition_scope="plataforma", escopo_qualificacao="sdr", padrao_qualificacao="imob-lead",
        rascunho_padrao=JULIA_RASCUNHO, instanciavel=False,
    )
    draft = studio.create_draft(PLAT_ORG, d.id, None, d.id)
    studio.update_draft(PLAT_ORG, draft.id, dict(JULIA_RASCUNHO))
    studio.replace_sections(PLAT_ORG, draft.id, [SectionInput("persona", "Persona", 10, "Persona do teste.")])
    for nome in ("qualificar-lead", "ofertar-imoveis"):
        studio.create_skill(PLAT_ORG, draft.id, nome=nome, descricao=f"skill {nome}", corpo=f"corpo de {nome}")
    studio.replace_textos(PLAT_ORG, draft.id, textos_completos() + list(textos_extra or []))
    obrig = obrigatoria or {}
    studio.replace_ferramentas(PLAT_ORG, draft.id, [
        FerramentaInput(n, f"desc:{n}", parametros=dict(_PARAMETROS.get(n, {})), obrigatoria_skill=obrig.get(n))
        for n in [*TOOLS, "registrar_resumo", "registrar_escolha"] if n not in sem_ferramentas
    ])
    if com_decisao:
        studio.replace_decisoes(PLAT_ORG, draft.id, [DecisaoInput(
            "abordagem-meta", "Abordagem", "" if com_decisao == "sem_regra" else "regra: escolha por origem",
            [{"valor": "template_a", "rotulo": "A", "padrao": True}, {"valor": "template_b", "rotulo": "B", "padrao": False}],
        )])
    version = draft
    if publicar:
        version = publish(studio, PLAT_ORG, d, draft.id, user_id, catalog=catalog)
    studio.grant_definition_org(d.id, org_id)  # 050: a product-owned definition reaches an org only by grant
    inst = studio.create_studio_agent(
        org_id, JULIA_KEY, "Julia", None, runtime="llm", owner_product="social-wiring",
        definition_scope="instancia", definition_agent_id=d.id,
    )
    inst = studio.update_agent(org_id, JULIA_KEY, {"ativo": ativo_modo != "desligado"})
    if controles is not None:
        controles.set(org_id, inst.id, modo=ativo_modo)
    return MundoJulia(d, inst, version, UUID(int=0))
