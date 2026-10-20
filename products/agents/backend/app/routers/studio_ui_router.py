"""Server-provided facts the Studio UI renders from (Julia v2 A-RT2 for FE-A). Every response is an explicit allowlist
and tiered (CONTRACT 0.4): the FE never infers a tier from roles and never receives a prompt, rule text or weight.

* ``GET /api/studio/agents/{key}/capacidades`` -- the caller's ``tier`` and the tab keys it may see (any org member).
* ``GET|PUT /api/studio/agents/{key}/conformidade/regras/{regra}`` -- a conformance rule's switches (platform admin;
  ``?org_id=`` selects another org's instance, default the caller's own row; every read audited).
* ``GET /api/studio/agents/{key}/conformidade/violacoes`` -- paged violation CODES (platform admin).
* ``GET /api/studio/agents/{key}/conformidade/resumo`` -- COUNTS only (org admin, own org).
* ``GET /api/studio/threads/{thread_id}`` -- participant states of a lead thread (org admin).
* ``GET /api/studio/textos/registro`` / ``GET /api/studio/ferramentas/registro`` -- registry STRUCTURE (platform admin):
  keys, categories, placeholders, applicability; tool names, parameter names and enum values. Not one word of text.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.channels.conformidade import SHINGLE_MAX, SHINGLE_MIN
from app.dependencies import get_conformidade_store_dep, get_conversation_store_dep, get_core_client, get_thread_store_dep, require_admin, require_member, require_platform_admin
from app.routers.studio_agents_router import (
    audit_definition_read,
    get_studio_definition_store_dep,
    http_error,
    resolve_agent,
)
from app.stores.conformidade import POLITICAS, REGRAS
from app.stores.errors import NotFound
from app.stores.threads import mapa_agentes
from app.studio.ferramentas_registry import FERRAMENTAS_CONHECIDAS
from app.studio.textos_registry import TEXTOS
from app.studio.vazamento import chamador_e_admin_da_plataforma
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import AuthContext, is_org_admin_for

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/studio", tags=["studio-ui"])

__all__ = ["router", "ABAS_POR_TIER", "tier_do_chamador"]

# ── 1. capabilities ─────────────────────────────────────────────────────────

#: Tab keys by tier (UI structure; the FE maps a key to its screen). A tab absent here does not exist for the tier.
ABAS_POR_TIER: dict[str, tuple[str, ...]] = {
    "plataforma": (
        "visao_geral", "secoes", "skills", "textos", "ferramentas", "decisoes", "especificacoes", "qualificacao",
        "conformidade", "conhecimento", "avaliacoes", "versoes", "compilado", "conversas", "controles",
    ),
    "org_admin": ("visao_geral", "especificacoes", "conversas", "resultados", "controles"),
    "org_member": ("visao_geral",),
}


def tier_do_chamador(ctx: AuthContext) -> str:
    """``plataforma`` (``noctus_users.role == 'admin'``) · ``org_admin`` (owner/admin of the org) · ``org_member``.
    Read from the trusted DB rows, never from token metadata."""
    if chamador_e_admin_da_plataforma(ctx):
        return "plataforma"
    try:
        if is_org_admin_for(get_core_client(), ctx):
            return "org_admin"
    except Exception:  # noqa: BLE001 -- unknown means the LOWER tier; logged
        logger.exception("agents.studio.tier_ilegivel")
    return "org_member"


class CapacidadesOut(BaseModel):
    agent_key: str
    tier: str
    abas: list[str]


@router.get("/agents/{key}/capacidades", response_model=CapacidadesOut)
async def capacidades(
    key: str, ctx: AuthContext = Depends(require_member), store=Depends(get_studio_definition_store_dep),
) -> CapacidadesOut:
    agent = resolve_agent(store, ctx.org_id, key, allow_instancia=True)
    tier = tier_do_chamador(ctx)
    return CapacidadesOut(agent_key=agent.key, tier=tier, abas=list(ABAS_POR_TIER[tier]))


# ── 2. conformance ──────────────────────────────────────────────────────────


class RegraOut(BaseModel):
    regra: str
    ativo: bool
    politica: str
    parametros: dict[str, Any]
    mensagem_correcao_texto_chave: str | None = None


class RegraIn(StrictHttpModel):
    ativo: bool | None = None
    politica: str | None = None
    parametros: dict[str, Any] | None = None


class ViolacaoItemOut(BaseModel):
    """Codes and ids only: ``detalhe`` carries counts/codes (the store never keeps reply text)."""

    id: UUID | None
    regra: str
    politica: str
    bloqueada: bool
    criada_em: datetime | None
    detalhe: dict[str, Any]


class ViolacoesOut(BaseModel):
    items: list[ViolacaoItemOut]
    pagina: int
    tamanho: int
    tem_mais: bool


class ResumoConformidadeOut(BaseModel):
    total: int
    bloqueadas: int
    por_regra: dict[str, int]


_MAX_PARAMETROS_BYTES = 8000
_MAX_VIOLACOES_LIDAS = 1000


def _agente_alvo(store, ctx: AuthContext, key: str, org_id: UUID | None):
    """The agent ROW the rules hang on: the caller's own (the platform org's definition) or, for a platform
    admin, the named org's instance."""
    alvo_org = org_id or ctx.org_id
    return alvo_org, resolve_agent(store, alvo_org, key, allow_instancia=True)


def _regra_out(c) -> RegraOut:
    return RegraOut(
        regra=c.regra, ativo=c.ativo, politica=c.politica, parametros=dict(c.parametros),
        mensagem_correcao_texto_chave=c.mensagem_correcao_texto_chave,
    )


def _regra_valida(regra: str) -> None:
    if regra not in REGRAS:
        raise http_error(404, "regra_not_found", "Regra não encontrada.")


@router.get("/agents/{key}/conformidade/regras/{regra}", response_model=RegraOut)
async def ler_regra(
    key: str, regra: str, org_id: UUID | None = Query(default=None),
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep), conformidade=Depends(get_conformidade_store_dep),
) -> RegraOut:
    _regra_valida(regra)
    alvo_org, agent = _agente_alvo(store, ctx, key, org_id)
    audit_definition_read(store, ctx, resolve_agent(store, ctx.org_id, key, allow_instancia=True), f"regra:{regra}")
    return _regra_out(conformidade.regras(alvo_org, agent.id)[regra])


@router.put("/agents/{key}/conformidade/regras/{regra}", response_model=RegraOut)
async def definir_regra(
    key: str, regra: str, payload: RegraIn, org_id: UUID | None = Query(default=None),
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep), conformidade=Depends(get_conformidade_store_dep),
) -> RegraOut:
    _regra_valida(regra)
    if payload.politica is not None and payload.politica not in POLITICAS:
        raise http_error(422, "invalid_field", "Campo inválido: politica")
    if payload.parametros is not None:
        if len(json.dumps(payload.parametros, ensure_ascii=False, default=str)) > _MAX_PARAMETROS_BYTES:
            raise http_error(422, "invalid_field", "Campo inválido: parametros")
        st = payload.parametros.get("shingle_tokens")
        if st is not None and (isinstance(st, bool) or not isinstance(st, int) or not SHINGLE_MIN <= st <= SHINGLE_MAX):
            raise http_error(422, "invalid_field", "Campo inválido: parametros.shingle_tokens")
    alvo_org, agent = _agente_alvo(store, ctx, key, org_id)
    antes = conformidade.regras(alvo_org, agent.id)[regra]
    novo = conformidade.definir_regra(
        alvo_org, agent.id, regra, ativo=payload.ativo, politica=payload.politica, parametros=payload.parametros)
    store.append_audit(
        agent.org_id, agent.id, ctx.user_id, "conteudo_editado_mcp",
        {"o_que": "conformidade_regra", "regra": regra, "ativo": antes.ativo, "politica": antes.politica},
        {"o_que": "conformidade_regra", "regra": regra, "ativo": novo.ativo, "politica": novo.politica},
    )
    return _regra_out(novo)


@router.get("/agents/{key}/conformidade/violacoes", response_model=ViolacoesOut)
async def listar_violacoes(
    key: str, pagina: int = Query(default=1, ge=1, le=200), tamanho: int = Query(default=50, ge=1, le=200),
    thread_id: UUID | None = Query(default=None), org_id: UUID | None = Query(default=None),
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep), conformidade=Depends(get_conformidade_store_dep),
) -> ViolacoesOut:
    alvo_org, agent = _agente_alvo(store, ctx, key, org_id)
    ate = min(pagina * tamanho + 1, _MAX_VIOLACOES_LIDAS)
    # the store lists oldest-first within the newest ``limite``: newest-first for the UI
    todas = list(reversed(conformidade.listar_violacoes(alvo_org, agent.id, thread_id=thread_id, limite=ate)))
    ini = (pagina - 1) * tamanho
    fatia = todas[ini:ini + tamanho]
    return ViolacoesOut(
        items=[
            ViolacaoItemOut(
                id=v.id, regra=v.regra, politica=v.politica, bloqueada=v.bloqueada, criada_em=v.created_at,
                detalhe=dict(v.detalhe))
            for v in fatia
        ],
        pagina=pagina, tamanho=tamanho, tem_mais=len(todas) > ini + tamanho,
    )


@router.get("/agents/{key}/conformidade/resumo", response_model=ResumoConformidadeOut)
async def resumo_conformidade(
    key: str, ctx: AuthContext = Depends(require_admin),
    store=Depends(get_studio_definition_store_dep), conformidade=Depends(get_conformidade_store_dep),
) -> ResumoConformidadeOut:
    """Org admin: COUNTS over its own org's violations -- no detail, no thread, no rule parameters."""
    agent = resolve_agent(store, ctx.org_id, key, allow_instancia=True)
    todas = conformidade.listar_violacoes(ctx.org_id, agent.id, limite=_MAX_VIOLACOES_LIDAS)
    por_regra: dict[str, int] = {}
    for v in todas:
        por_regra[v.regra] = por_regra.get(v.regra, 0) + 1
    return ResumoConformidadeOut(
        total=len(todas), bloqueadas=sum(1 for v in todas if v.bloqueada), por_regra=por_regra)


# ── 3. a lead thread's participant states ───────────────────────────────────


class ParticipanteEstadoOut(BaseModel):
    agent_key: str
    agent_nome: str
    estado: str
    pausado_ate: datetime | None = None
    ultimo_turno_em: datetime | None = None


class StudioThreadOut(BaseModel):
    thread_id: UUID
    channel: str
    participantes: list[ParticipanteEstadoOut]
    ultimo_turno_em: datetime | None
    ultima_mensagem_lead_em: datetime | None
    criado_em: datetime


@router.get("/threads/{thread_id}", response_model=StudioThreadOut)
async def studio_thread(
    thread_id: UUID, ctx: AuthContext = Depends(require_admin),
    studio_store=Depends(get_studio_definition_store_dep), conv_store=Depends(get_conversation_store_dep),
    threads=Depends(get_thread_store_dep),
) -> StudioThreadOut:
    try:
        thread = conv_store.get(ctx.org_id, thread_id)
    except NotFound as exc:
        raise http_error(404, "thread_not_found", "Conversa não encontrada.") from exc
    if thread.tipo != "thread_lead":
        raise http_error(404, "thread_not_found", "Conversa não encontrada.")
    agentes = mapa_agentes(studio_store, ctx.org_id)
    parts = threads.list_participantes(ctx.org_id, thread.id)
    turnos = [p.ultimo_turno_em for p in parts if p.ultimo_turno_em is not None]
    return StudioThreadOut(
        thread_id=thread.id, channel=thread.channel or "",
        participantes=[
            ParticipanteEstadoOut(
                agent_key=agentes.get(p.agent_id, ("", ""))[0], agent_nome=agentes.get(p.agent_id, ("", ""))[1],
                estado=p.estado, pausado_ate=p.pausado_ate, ultimo_turno_em=p.ultimo_turno_em)
            for p in parts
        ],
        ultimo_turno_em=max(turnos) if turnos else None,
        ultima_mensagem_lead_em=thread.ultima_mensagem_lead_em, criado_em=thread.created_at,
    )


# ── 4. registries (structure only) ──────────────────────────────────────────


class TextoRegistroOut(BaseModel):
    chave: str
    categoria: str
    obrigatoria: bool
    placeholders_permitidos: list[str]
    aplica_a: str
    condicao: str | None
    fixo_plataforma: bool
    #: ``<aplica_a>`` or ``<aplica_a>:<condicao>`` -- when the key is needed (a code, not a sentence).
    aparece_quando: str


@router.get("/textos/registro", response_model=list[TextoRegistroOut])
async def registro_textos(ctx: AuthContext = Depends(require_platform_admin)) -> list[TextoRegistroOut]:
    return [
        TextoRegistroOut(
            chave=k, categoria=s.categoria, obrigatoria=s.obrigatoria,
            placeholders_permitidos=list(s.placeholders_permitidos), aplica_a=s.aplica_a, condicao=s.condicao,
            fixo_plataforma=s.fixo_plataforma,
            aparece_quando=s.aplica_a + (f":{s.condicao}" if s.condicao else ""),
        )
        for k, s in sorted(TEXTOS.items())
    ]


class ParametroRegistroOut(BaseModel):
    nome: str
    tipo: str | None
    obrigatorio: bool
    valores: list[str] = Field(default_factory=list)


class FerramentaRegistroOut(BaseModel):
    ferramenta: str
    #: Capabilities a turn needs for the tool to be offered at all.
    exige: list[str]
    parametros: list[ParametroRegistroOut]
    #: Keys the row's ``parametros`` may carry to label each enum value (``<parametro>.<valor>``).
    chaves_rotulo_enum: list[str]


def _resolver(schema: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if ref:
        return _resolver(defs.get(ref.rsplit("/", 1)[-1], {}), defs)
    for alt in schema.get("anyOf") or schema.get("oneOf") or ():
        if alt.get("type") != "null":
            return _resolver(alt, defs)
    return schema


def _percorrer(schema: dict[str, Any], defs: dict[str, Any], prefixo: str, obrigatorios: set[str]) -> list[ParametroRegistroOut]:
    out: list[ParametroRegistroOut] = []
    for nome, sub in (schema.get("properties") or {}).items():
        s = _resolver(sub, defs)
        caminho = f"{prefixo}{nome}"
        if s.get("type") == "array":
            item = _resolver(s.get("items") or {}, defs)
            if item.get("properties"):
                out.append(ParametroRegistroOut(nome=caminho, tipo="array", obrigatorio=nome in obrigatorios))
                out.extend(_percorrer(item, defs, f"{caminho}.", set(item.get("required") or ())))
                continue
            enum_item = item.get("enum")
            out.append(ParametroRegistroOut(
                nome=caminho, tipo="array", obrigatorio=nome in obrigatorios,
                valores=[str(v) for v in enum_item] if enum_item else []))
            continue
        if s.get("properties"):
            out.append(ParametroRegistroOut(nome=caminho, tipo="object", obrigatorio=nome in obrigatorios))
            out.extend(_percorrer(s, defs, f"{caminho}.", set(s.get("required") or ())))
            continue
        out.append(ParametroRegistroOut(
            nome=caminho, tipo=s.get("type"), obrigatorio=nome in obrigatorios,
            valores=[str(v) for v in s["enum"]] if s.get("enum") else []))
    return out


@router.get("/ferramentas/registro", response_model=list[FerramentaRegistroOut])
async def registro_ferramentas(ctx: AuthContext = Depends(require_platform_admin)) -> list[FerramentaRegistroOut]:
    from app.channels.tool_registry import TOOLS

    out: list[FerramentaRegistroOut] = []
    for nome in sorted(FERRAMENTAS_CONHECIDAS):
        t = TOOLS.get(nome)
        if t is None:  # knowledge / extraction tools: named, no channel-argument schema
            out.append(FerramentaRegistroOut(ferramenta=nome, exige=[], parametros=[], chaves_rotulo_enum=[]))
            continue
        schema = t.args.model_json_schema()
        params = _percorrer(schema, schema.get("$defs") or {}, "", set(schema.get("required") or ()))
        out.append(FerramentaRegistroOut(
            ferramenta=nome, exige=sorted(t.exige), parametros=params,
            chaves_rotulo_enum=[f"{p.nome}.{v}" for p in params for v in p.valores],
        ))
    return out
