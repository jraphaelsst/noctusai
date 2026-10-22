"""AI-generated first drafts for agents (S3a).

NOC-REMEDIATE[ai-draft-generation-seed]: agents-only today (N=1). When a second product generates structured drafts
with a spend cap, lift the cap tracker + the per-area JSON pipeline into the seed — 2026-10-22.

A short creation form (the *briefing*) becomes a DRAFT starting point: context sections, system texts, tool
descriptions, decisions, org-spec declarations, recommended library skills and initial settings. Publishing stays
human. The generator is a platform agent like any other: the platform definition whose ``papel`` is ``gerador`` (found
by ROLE, never by key); its PUBLISHED version composes the prompt (sections -> system prompt; the per-area instructions
are its sections ``planejamento`` and ``area-<area>``) and fixes the model/provider. NO instruction text lives in this
module: what the model is told is data, written in the generator's sections; this module only supplies structured
context (briefing, plan, registry facts, the output JSON schema) and validates what comes back.

Pipeline: one planning call, then one call per area (<= 2 in parallel). Cost is capped per run: before EVERY call a
worst-case estimate (input chars / 2.5 per token + ``max_tokens`` x output price) must fit the remaining budget, else
the call is not made (area ``pulado``). An in-flight call of a cancelled run finishes but its output is discarded.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from dataclasses import dataclass, replace
from typing import Any, Awaitable, Callable
from uuid import UUID

from app.schemas.studio_geracao import (
    SAIDAS,
    AreaOut,
    Briefing,
    GeracaoOut,
    ItemGeradoOut,
    Plano,
)
from app.stores._util import utcnow
from app.stores.errors import NotFound
from app.stores.studio_definitions import PROVIDERS, EFFORTS, MODELS_BY_PROVIDER, StudioAgentRecord
from app.stores.studio_geracoes import ACTIVE_STATUSES, AREAS, GeracaoAreaRecord, GeracaoRecord
from app.studio.eval_pii import achar_pii
from app.studio.ferramentas_registry import FERRAMENTAS_CONHECIDAS, ferramenta_da_conversa
from app.studio.geracao_itens import ErroEscrita, escrever_area, estados_das_areas, hashes_atuais
from app.studio.models import SPEC_TIPOS
from app.studio.textos_registry import TEXTOS, chaves_exigidas

logger = logging.getLogger(__name__)

__all__ = [
    "Dependencias",
    "GeracaoErro",
    "Gerador",
    "MAX_TOKENS",
    "PARALELISMO",
    "ORFA_ERRO",
    "carregar_gerador",
    "iniciar",
    "repetir",
    "cancelar",
    "executar",
    "montar_saida",
    "registrar_aprendizado",
    "conteudo_status",
    "varrer_geracoes_orfas",
]

PARALELISMO = 2
ORFA_ERRO = "interrompida"
#: Output budget per call (the Anthropic SDK refuses a non-streaming call above ~21k output tokens).
MAX_TOKENS: dict[str, int] = {
    "planejamento": 4000, "secoes": 16000, "textos": 20000, "ferramentas": 12000, "decisoes": 8000,
    "specs": 6000, "skills": 4000, "configuracoes": 2000,
}
#: Worst-case chars per token used to estimate the INPUT of a call before it is made (pt-BR JSON is ~3.5-4).
_CHARS_POR_TOKEN = 2.5
_MAX_TEXTO_EXEMPLAR = 4000

ChatFn = Callable[..., Awaitable[Any]]


class GeracaoErro(Exception):
    """A refusal with the product's flat body ``{code, message, detail}``."""

    def __init__(self, status: int, code: str, message: str, detail: Any = None) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message
        self.detail = detail if detail is not None else message


@dataclass
class Dependencias:
    studio: Any
    geracoes: Any
    skills: Any
    catalog: Any
    #: ``chat_completion_with_usage``-shaped coroutine (the seed's); tests inject a wrapper over the seed Fake.
    chat: ChatFn


@dataclass(frozen=True)
class Gerador:
    agent: StudioAgentRecord
    version: Any
    sistema: str
    instrucoes: dict[str, str]
    preco_in: float
    preco_out: float


# ── the generator (found by role) ───────────────────────────────────────────


def _preco(provider: str, model: str) -> tuple[float, float] | None:
    from noctusai_lib.integrations.llm import is_priced, models_for

    entry = next((m for m in models_for(provider, "chat") if m.id == model), None)
    if entry is None or not is_priced(entry):
        return None
    return float(entry.cost_per_1m_input_tokens), float(entry.cost_per_1m_output_tokens)


def carregar_gerador(studio: Any) -> Gerador:
    """The published version of the platform definition whose ``papel`` is ``gerador``. 409 ``gerador_indisponivel``
    when there is none, it has no published version, or its model has no price (a cap that cannot be computed is no
    cap)."""
    indisponivel = GeracaoErro(409, "gerador_indisponivel", "O gerador de agentes não está disponível.")
    definicao = next((d for d in studio.list_platform_definitions() if d.papel == "gerador"), None)
    if definicao is None:
        raise indisponivel
    version = studio.get_active_version(definicao.org_id, definicao.id)
    if version is None:
        raise indisponivel
    preco = _preco(version.provider, version.model)
    if preco is None:
        logger.error("agents.geracao.gerador_sem_preco provider=%s model=%s", version.provider, version.model)
        raise indisponivel
    secoes = [s for s in studio.list_sections(definicao.org_id, version.id) if s.ativo]
    instrucoes = {s.chave: s.conteudo for s in secoes if s.chave == "planejamento" or s.chave.startswith("area-")}
    sistema = "\n\n".join(
        f"## {s.titulo}\n{s.conteudo}" for s in sorted(secoes, key=lambda s: s.ordem) if s.chave not in instrucoes
    )
    return Gerador(definicao, version, sistema, instrucoes, preco[0], preco[1])


# ── exemplar + registry facts (structured context, no prose) ────────────────


def estrutura_exemplar(studio: Any, skills: Any, *, verbatim: bool) -> tuple[list[dict[str, Any]], str, list[tuple[UUID, UUID]]]:
    """The structure of every ``papel='exemplar'`` platform definition's published version: which slots are filled,
    lengths, section layout. The verbatim text rides along only when ``verbatim`` (the target lives in the platform
    org). Also returns the exemplars' full text (the leak-check source) and their ``(org, version)`` ids."""
    saida: list[dict[str, Any]] = []
    fonte: list[str] = []
    versoes: list[tuple[UUID, UUID]] = []
    for d in studio.list_platform_definitions():
        if d.papel != "exemplar":
            continue
        v = studio.get_active_version(d.org_id, d.id)
        if v is None:
            continue
        versoes.append((d.org_id, v.id))
        secoes = studio.list_sections(d.org_id, v.id)
        textos = studio.list_textos(d.org_id, v.id)
        ferr = studio.list_ferramentas(d.org_id, v.id)
        fonte += [s.conteudo for s in secoes] + [t.conteudo for t in textos] + [f.descricao for f in ferr]
        item: dict[str, Any] = {
            "secoes": [
                {"chave": s.chave, "titulo": s.titulo, "ordem": s.ordem, "tamanho": len(s.conteudo)}
                | ({"conteudo": s.conteudo[:_MAX_TEXTO_EXEMPLAR]} if verbatim else {})
                for s in secoes
            ],
            "textos": [
                {"chave": t.chave, "tamanho": len(t.conteudo)}
                | ({"conteudo": t.conteudo[:_MAX_TEXTO_EXEMPLAR]} if verbatim else {})
                for t in textos if t.conteudo.strip()
            ],
            "ferramentas": [
                {"ferramenta": f.ferramenta, "ativo": f.ativo, "tamanho": len(f.descricao)}
                | ({"descricao": f.descricao[:_MAX_TEXTO_EXEMPLAR]} if verbatim else {})
                for f in ferr
            ],
            "decisoes": [{"chave": x.chave, "opcoes": len(x.opcoes)} for x in studio.list_decisoes(d.org_id, v.id)],
            "specs": [
                {"chave": x.chave, "tipo": x.tipo, "obrigatoria": x.obrigatoria}
                for x in studio.list_spec_defs(d.org_id, v.id)
            ],
            "skills": [r.skill_chave for r in skills.listar_refs(v.id)],
            "configuracoes": {"effort": v.effort, "max_turns": v.max_turns, "tool_policy": dict(v.tool_policy)},
        }
        saida.append(item)
    return saida, "\n".join(fonte), versoes


def textos_aplicaveis(
    agent: StudioAgentRecord, draft: Any, briefing: Briefing, *, tem_skills: bool,
) -> dict[str, bool]:
    """``{chave: obrigatoria}`` of the registry slots that apply to the agent: channel texts when the briefing says
    WhatsApp or the agent has a transport owner (the compiler's own ``canal`` rule), in-app texts otherwise."""
    canal = briefing.canal == "whatsapp" or agent.owner_product is not None
    todos = {k: replace(s, obrigatoria=True) for k, s in TEXTOS.items()}
    aplicaveis = chaves_exigidas(
        tool_policy=dict(draft.tool_policy), tem_skills=tem_skills, com_cliente=False, canal=canal,
        com_qualificacao=agent.padrao_qualificacao is not None, registro=todos,
    )
    return {k: TEXTOS[k].obrigatoria for k in sorted(aplicaveis)}


def _contexto_da_area(area: str, *, deps: Dependencias, agent: StudioAgentRecord, draft: Any, aplicaveis: dict[str, bool]) -> dict[str, Any]:
    """Structured facts the area's call needs (registry keys, allowed values, the skill library)."""
    org = agent.org_id
    if area == "secoes":
        return {"existentes": [{"chave": s.chave, "titulo": s.titulo} for s in deps.studio.list_sections(org, draft.id)]}
    if area == "textos":
        return {
            "slots": [
                {
                    "chave": k, "obrigatoria": obrig, "categoria": TEXTOS[k].categoria,
                    "placeholders_permitidos": list(TEXTOS[k].placeholders_permitidos),
                    "condicao": TEXTOS[k].condicao,
                }
                for k, obrig in aplicaveis.items()
            ],
            "preenchidos": [t.chave for t in deps.studio.list_textos(org, draft.id) if t.conteudo.strip()],
        }
    if area == "ferramentas":
        return {"ferramentas_disponiveis": sorted(n for n in FERRAMENTAS_CONHECIDAS if ferramenta_da_conversa(n))}
    if area == "decisoes":
        return {"existentes": [d.chave for d in deps.studio.list_decisoes(org, draft.id)]}
    if area == "specs":
        return {"tipos": list(SPEC_TIPOS), "existentes": [s.chave for s in deps.studio.list_spec_defs(org, draft.id)]}
    if area == "skills":
        biblioteca = []
        for s in deps.skills.listar_skills():
            try:
                v = deps.skills.obter_versao_publicada(s.chave)
            except NotFound:
                continue
            biblioteca.append({"chave": s.chave, "nome": s.nome, "descricao": v.descricao_modelo or s.descricao})
        return {"biblioteca": biblioteca, "fixadas": [r.skill_chave for r in deps.skills.listar_refs(draft.id)]}
    if area == "configuracoes":
        return {
            "providers": list(PROVIDERS), "modelos": {p: list(m) for p, m in MODELS_BY_PROVIDER.items()},
            "efforts": list(EFFORTS), "atual": {c: getattr(draft, c, None) for c in ("provider", "model", "effort", "max_turns", "idioma", "tool_policy")},
        }
    raise ValueError(area)


# ── cost cap ────────────────────────────────────────────────────────────────


class _Orcamento:
    """The run's spend. No ``await`` between a check and a reservation, so the two parallel workers can never both
    spend the same remainder (asyncio only switches tasks at an ``await``)."""

    def __init__(self, limite: float, gasto: float) -> None:
        self.limite = limite
        self.gasto = gasto
        self.reservado = 0.0

    def reservar(self, estimativa: float) -> bool:
        if self.gasto + self.reservado + estimativa > self.limite + 1e-9:
            return False
        self.reservado += estimativa
        return True

    def liquidar(self, estimativa: float, real: float) -> None:
        self.reservado = max(0.0, self.reservado - estimativa)
        self.gasto += real


def _estimar(mensagens: list[dict], max_tokens: int, g: Gerador) -> float:
    chars = sum(len(m["content"]) for m in mensagens)
    return (math.ceil(chars / _CHARS_POR_TOKEN) * g.preco_in + max_tokens * g.preco_out) / 1_000_000


# ── request-time operations (sync; the routes run them off the event loop) ──


def _hashes_do_agente(deps: Dependencias, agent: StudioAgentRecord, area: str, version: Any, cache: dict) -> dict[str, str]:
    chave = (version.id, area)
    if chave not in cache:
        cache[chave] = hashes_atuais(area, store=deps.studio, skills=deps.skills, org_id=agent.org_id, version=version)
    return cache[chave]


def _versao_de_leitura(deps: Dependencias, agent: StudioAgentRecord) -> Any | None:
    return deps.studio.get_draft(agent.org_id, agent.id) or deps.studio.get_active_version(agent.org_id, agent.id)


def _itens_anteriores(deps: Dependencias, agent: StudioAgentRecord, area: str) -> list[dict[str, str]]:
    """The items the most recent generation that wrote this area left (newest first; failed retries keep them)."""
    for g in deps.geracoes.list_geracoes(agent.org_id, agent.id, 20):
        for a in deps.geracoes.list_areas(agent.org_id, g.id):
            if a.area == area and a.itens:
                return a.itens
    return []


def _areas_editadas(deps: Dependencias, agent: StudioAgentRecord, areas: list[str]) -> list[str]:
    version = _versao_de_leitura(deps, agent)
    if version is None:
        return []
    cache: dict = {}
    editadas = []
    for area in areas:
        itens = _itens_anteriores(deps, agent, area)
        if not itens:
            continue
        estados = estados_das_areas(area, itens, _hashes_do_agente(deps, agent, area, version, cache))
        if any(e["estado"] == "editado" for e in estados):
            editadas.append(area)
    return editadas


def _resolver_alvo(deps: Dependencias, org_id: UUID, key: str) -> StudioAgentRecord:
    try:
        agent = deps.studio.get_agent(org_id, key)
    except NotFound as exc:
        raise GeracaoErro(404, "agente_nao_encontrado", "Agente não encontrado.") from exc
    if agent.definition_scope == "instancia":
        raise GeracaoErro(
            409, "definicao_na_plataforma", "A definição deste agente é da plataforma; a organização edita as suas especificações.")
    if agent.definition_mode != "studio" or agent.conteudo_modo != "linhas":
        raise GeracaoErro(
            409, "conteudo_modo_legado",
            "Este agente ainda usa os textos do compilador no código; a geração por IA não se aplica.")
    return agent


def garantir_rascunho(deps: Dependencias, agent: StudioAgentRecord, ator: UUID) -> Any:
    """The agent's draft; created from the active version when absent (a published agent has none)."""
    draft = deps.studio.get_draft(agent.org_id, agent.id)
    if draft is not None:
        return draft
    active = deps.studio.get_active_version(agent.org_id, agent.id)
    draft = deps.studio.create_draft(agent.org_id, agent.id, active.id if active else None, ator)
    _refresh_hash(deps, agent, draft.id)
    return deps.studio.get_version(agent.org_id, draft.id)


def _refresh_hash(deps: Dependencias, agent: StudioAgentRecord, draft_id: UUID) -> None:
    """Re-stamp the draft's ``compiled_hash`` (every content table is hash-covered). Best effort: a miss is logged and
    the next save path re-stamps."""
    try:
        from app.routers.studio_agents_router import _refresh_draft_hash

        _refresh_draft_hash(deps.studio, deps.catalog, agent.org_id, agent, draft_id)
    except Exception:  # noqa: BLE001 -- HTTPException from the shared helper or a compile failure; logged
        logger.warning("agents.geracao.hash_nao_atualizado agent_id=%s", agent.id, exc_info=True)


def _pii_no_briefing(briefing: Briefing) -> None:
    if briefing.exemplos:
        tipos = achar_pii(briefing.exemplos)
        if tipos:
            raise GeracaoErro(
                422, "exemplos_com_pii", "Os exemplos contêm dados pessoais; use exemplos sintéticos.", detail=tipos)


def iniciar(
    deps: Dependencias, *, org_id: UUID, key: str, briefing: Briefing, areas: list[str] | None, forcar: bool,
    limite_usd: float, ator: UUID,
) -> tuple[GeracaoRecord, StudioAgentRecord, list[str]]:
    """Validate + book a run (``pendente``) and return it with the target and the areas to execute. Nothing is
    called on the LLM here."""
    agent = _resolver_alvo(deps, org_id, key)
    _pii_no_briefing(briefing)
    pedidas = [a for a in AREAS if a in set(areas or AREAS)]
    if any(g.status in ACTIVE_STATUSES for g in deps.geracoes.list_geracoes(org_id, agent.id, 20)):
        raise GeracaoErro(409, "geracao_em_andamento", "Já existe uma geração em andamento para este agente.")
    gerador = carregar_gerador(deps.studio)
    if not forcar:
        editadas = _areas_editadas(deps, agent, pedidas)
        if editadas:
            raise GeracaoErro(
                409, "conteudo_editado", "Há conteúdo gerado antes que foi editado; use forcar para sobrescrever.",
                detail=editadas)
    garantir_rascunho(deps, agent, ator)
    try:
        rec = deps.geracoes.create_geracao(
            org_id, agent.id, briefing=briefing.model_dump(mode="json"), areas=pedidas, forcar=forcar,
            modelo=gerador.version.model, provider=gerador.version.provider, limite_usd=limite_usd,
            versao_gerador=gerador.version.versao, criado_por=ator,
        )
    except Exception as exc:
        if getattr(exc, "code", None) == "geracao_em_andamento":
            raise GeracaoErro(409, "geracao_em_andamento", "Já existe uma geração em andamento para este agente.") from exc
        raise
    deps.studio.append_audit(
        org_id, agent.id, ator, "agente_gerado", None,
        {"geracao_id": str(rec.id), "areas": pedidas, "modelo": rec.modelo, "versao_gerador": rec.versao_gerador,
         "limite_usd": limite_usd},
    )
    return rec, agent, pedidas


def repetir(
    deps: Dependencias, *, org_id: UUID, key: str, geracao_id: UUID, area: str, forcar: bool, ator: UUID,
) -> tuple[GeracaoRecord, StudioAgentRecord]:
    agent = _resolver_alvo(deps, org_id, key)
    ger = _obter(deps, org_id, agent, geracao_id)
    area_rec = next((a for a in deps.geracoes.list_areas(org_id, geracao_id) if a.area == area), None)
    if area_rec is None:
        raise GeracaoErro(404, "geracao_nao_encontrada", "Área não encontrada nesta geração.")
    if any(g.status in ACTIVE_STATUSES for g in deps.geracoes.list_geracoes(org_id, agent.id, 20)):
        raise GeracaoErro(409, "geracao_em_andamento", "Já existe uma geração em andamento para este agente.")
    if area_rec.status == "concluida" and not forcar:
        raise GeracaoErro(409, "area_concluida", "A área já foi concluída; use forcar para gerar de novo.")
    gerador = carregar_gerador(deps.studio)
    if not forcar:
        editadas = _areas_editadas(deps, agent, [area])
        if editadas:
            raise GeracaoErro(
                409, "conteudo_editado", "Há conteúdo gerado antes que foi editado; use forcar para sobrescrever.",
                detail=editadas)
    garantir_rascunho(deps, agent, ator)
    deps.geracoes.update_area(org_id, geracao_id, area, {"status": "pendente", "erro": None, "concluido_em": None})
    try:
        ger = deps.geracoes.update_geracao(
            org_id, geracao_id, {"status": "executando", "erro": None, "concluido_em": None, "versao_gerador": gerador.version.versao},
        )
    except Exception as exc:
        if getattr(exc, "code", None) == "geracao_em_andamento":
            raise GeracaoErro(409, "geracao_em_andamento", "Já existe uma geração em andamento para este agente.") from exc
        raise
    deps.studio.append_audit(
        org_id, agent.id, ator, "agente_gerado", {"geracao_id": str(geracao_id)},
        {"geracao_id": str(geracao_id), "repetir": area, "forcar": forcar},
    )
    return ger, agent


def cancelar(deps: Dependencias, *, org_id: UUID, key: str, geracao_id: UUID) -> GeracaoRecord:
    agent = _resolver_alvo(deps, org_id, key)
    ger = _obter(deps, org_id, agent, geracao_id)
    if ger.status not in ACTIVE_STATUSES:
        raise GeracaoErro(409, "geracao_finalizada", "A geração já foi finalizada.")
    novo = deps.geracoes.update_geracao(
        org_id, geracao_id, {"status": "cancelada", "concluido_em": utcnow()}, only_if_status=ACTIVE_STATUSES)
    if novo is None:
        raise GeracaoErro(409, "geracao_finalizada", "A geração já foi finalizada.")
    for a in deps.geracoes.list_areas(org_id, geracao_id):
        deps.geracoes.update_area(
            org_id, geracao_id, a.area, {"status": "cancelada", "concluido_em": utcnow()},
            only_if_status=("pendente", "executando"))
    return novo


def _obter(deps: Dependencias, org_id: UUID, agent: StudioAgentRecord, geracao_id: UUID) -> GeracaoRecord:
    try:
        ger = deps.geracoes.get_geracao(org_id, geracao_id)
    except NotFound as exc:
        raise GeracaoErro(404, "geracao_nao_encontrada", "Geração não encontrada.") from exc
    if ger.agent_id != agent.id:
        raise GeracaoErro(404, "geracao_nao_encontrada", "Geração não encontrada.")
    return ger


# ── the background job ──────────────────────────────────────────────────────


async def _t(fn: Callable[..., Any], *a: Any, **kw: Any) -> Any:
    return await asyncio.to_thread(lambda: fn(*a, **kw))


def _json(texto: str) -> Any:
    t = (texto or "").strip()
    if t.startswith("```"):
        nl = t.find("\n")
        t = t[nl + 1:] if nl >= 0 else ""
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return json.loads(t.strip())


async def executar(deps: Dependencias, *, org_id: UUID, geracao_id: UUID, agent_id: UUID, areas: list[str]) -> None:
    """Run (or re-run) ``areas`` of the booked run. Never raises: an unexpected failure marks the run ``falhou``."""
    try:
        await _executar(deps, org_id=org_id, geracao_id=geracao_id, agent_id=agent_id, areas=areas)
    except Exception:  # noqa: BLE001 -- the run is marked failed with a fixed code; the traceback is logged
        logger.exception("agents.geracao.erro_interno geracao_id=%s", geracao_id)
        try:
            await _t(deps.geracoes.update_geracao, org_id, geracao_id,
                     {"status": "falhou", "erro": "erro_interno", "concluido_em": utcnow()},
                     only_if_status=ACTIVE_STATUSES)
        except Exception:  # noqa: BLE001
            logger.exception("agents.geracao.erro_interno_nao_registrado geracao_id=%s", geracao_id)


async def _executar(deps: Dependencias, *, org_id: UUID, geracao_id: UUID, agent_id: UUID, areas: list[str]) -> None:
    ger = await _t(deps.geracoes.update_geracao, org_id, geracao_id,
                   {"status": "executando"},
                   only_if_status=ACTIVE_STATUSES)
    if ger is None:
        return  # cancelled before it started
    if ger.iniciado_em is None:
        await _t(deps.geracoes.update_geracao, org_id, geracao_id, {"iniciado_em": utcnow()})
    agent = await _t(deps.studio.get_agent_by_id, agent_id)
    briefing = Briefing(**ger.briefing)
    try:
        gerador = await _t(carregar_gerador, deps.studio)
    except GeracaoErro as exc:
        await _falhar_tudo(deps, org_id, geracao_id, areas, exc.code)
        return
    draft = await _t(garantir_rascunho, deps, agent, ger.criado_por)
    platform = await _t(deps.studio.is_platform_org, agent.org_id)
    exemplar, fonte_vazamento, _versoes = await _t(estrutura_exemplar, deps.studio, deps.skills, verbatim=platform)
    guarda = None
    if not platform and fonte_vazamento.strip():
        from app.channels.conformidade import GuardaVazamento

        # The fingerprint check only: the honeytoken (046) is pinned to the channel turn + publish and is never read by a
        # Studio route (tests/channels/test_julia_v2_proveniencia.py).
        guarda = GuardaVazamento(fonte_vazamento)
    orc = _Orcamento(ger.limite_usd, ger.custo_usd)

    async def _chamar(etapa: str, entrada: dict[str, Any]) -> tuple[str | None, str | None, float, int | None, int | None]:
        """One LLM call under the cap. Returns ``(text, erro, custo, tokens_in, tokens_out)``."""
        instrucao = gerador.instrucoes.get(etapa if etapa == "planejamento" else f"area-{etapa}")
        if instrucao is None:
            return None, "instrucao_ausente", 0.0, None, None
        mensagens = []
        if gerador.sistema.strip():
            mensagens.append({"role": "system", "content": gerador.sistema})
        mensagens.append({"role": "user", "content": json.dumps({"instrucao": instrucao, **entrada}, ensure_ascii=False, default=str)})
        max_tokens = MAX_TOKENS[etapa]
        estimativa = _estimar(mensagens, max_tokens, gerador)
        if not orc.reservar(estimativa):
            return None, "limite_de_custo", 0.0, None, None
        try:
            r = await deps.chat(
                mensagens, provider=gerador.version.provider, model=gerador.version.model, org_id=str(agent.org_id),
                max_tokens=max_tokens, response_format={"type": "json_object"}, cache=False,
            )
        except Exception:  # noqa: BLE001 -- provider/key failure: logged, fixed code to the caller
            logger.warning("agents.geracao.llm_falhou etapa=%s geracao_id=%s", etapa, geracao_id, exc_info=True)
            orc.liquidar(estimativa, 0.0)
            return None, "llm_erro", 0.0, None, None
        if r.usage is None:
            # unmeasured != free: charge the worst-case estimate so the cap stays honest
            logger.warning("agents.geracao.uso_ausente etapa=%s geracao_id=%s", etapa, geracao_id)
            custo, tin, tout = estimativa, None, None
        else:
            custo, tin, tout = r.usage.cost_usd, r.usage.prompt_tokens, r.usage.completion_tokens
        orc.liquidar(estimativa, custo)
        await _t(deps.geracoes.update_geracao, org_id, geracao_id, {"custo_usd": round(orc.gasto, 4)})
        return r.text, None, custo, tin, tout

    # ── planning
    plano = ger.plano
    if plano is None:
        entrada = {
            "briefing": briefing.model_dump(mode="json"), "exemplar": exemplar, "areas": areas,
            "schema_saida": Plano.model_json_schema(),
        }
        texto, erro, _c, _i, _o = await _chamar("planejamento", entrada)
        if erro is None:
            try:
                plano = Plano.model_validate(_json(texto)).model_dump(mode="json")
            except Exception:  # noqa: BLE001 -- invalid JSON / schema: fixed code
                erro = "plano_invalido"
        if erro is not None:
            status_area = "pulado" if erro == "limite_de_custo" else "falhou"
            await _falhar_tudo(deps, org_id, geracao_id, areas, erro, status_area=status_area)
            return
        await _t(deps.geracoes.update_geracao, org_id, geracao_id, {"plano": plano})

    # ── areas (<= 2 in parallel)
    sem = asyncio.Semaphore(PARALELISMO)
    aplicaveis_cache: dict[str, bool] = {}

    async def _area(area: str) -> None:
        async with sem:
            await _rodar_area(area)

    async def _rodar_area(area: str) -> None:
        marcada = await _t(deps.geracoes.update_area, org_id, geracao_id, area, {"status": "executando"},
                           only_if_status=("pendente",))
        if marcada is None:
            return  # cancelled (or already running)
        draft_atual = await _t(garantir_rascunho, deps, agent, ger.criado_por)
        aplicaveis: dict[str, bool] = {}
        if area == "textos":
            tem_skills = bool(await _t(deps.skills.listar_refs, draft_atual.id)) or bool(
                [s for s in await _t(deps.studio.list_skills, agent.org_id, draft_atual.id) if s.ativo])
            aplicaveis = await _t(textos_aplicaveis, agent, draft_atual, briefing, tem_skills=tem_skills)
            aplicaveis_cache.update(aplicaveis)
        contexto = await _t(_contexto_da_area, area, deps=deps, agent=agent, draft=draft_atual, aplicaveis=aplicaveis)
        entrada = {
            "briefing": briefing.model_dump(mode="json"), "plano": plano, "diretriz": (plano or {}).get("diretrizes", {}).get(area),
            "contexto": contexto, "exemplar": exemplar, "schema_saida": SAIDAS[area].model_json_schema(),
        }
        texto, erro, custo, tin, tout = await _chamar(area, entrada)
        base = {"custo_usd": round(custo, 4), "tokens_entrada": tin, "tokens_saida": tout}
        # the run may have been cancelled while the call was in flight: pay for it, discard its output
        if not await _run_ativa(deps, org_id, geracao_id):
            await _t(deps.geracoes.update_area, org_id, geracao_id, area, {**base, "concluido_em": utcnow()},
                     only_if_status=("executando",))
            return
        if erro is not None:
            st = "pulado" if erro == "limite_de_custo" else "falhou"
            await _fechar_area(deps, org_id, geracao_id, area, {**base, "status": st, "erro": erro})
            return
        try:
            saida = SAIDAS[area].model_validate(_json(texto))
        except Exception:  # noqa: BLE001 -- invalid JSON / schema
            await _fechar_area(deps, org_id, geracao_id, area, {**base, "status": "falhou", "erro": "saida_invalida"})
            return
        if guarda is not None and guarda.verificar(json.dumps(saida.model_dump(mode="json"), ensure_ascii=False)):
            logger.warning("agents.geracao.vazamento_bloqueado geracao_id=%s area=%s", geracao_id, area)
            await _fechar_area(deps, org_id, geracao_id, area, {**base, "status": "falhou", "erro": "vazamento_detectado"})
            return
        try:
            anteriores = {i["chave"] for i in await _t(_itens_anteriores, deps, agent, area)}
            version = await _t(garantir_rascunho, deps, agent, ger.criado_por)
            escritas, lacunas = await _t(
                escrever_area, area, saida, store=deps.studio, skills=deps.skills, org_id=agent.org_id,
                draft=version, anteriores=anteriores, textos_aplicaveis=aplicaveis,
            )
            version = await _t(deps.studio.get_version, agent.org_id, version.id)
            atuais = await _t(hashes_atuais, area, store=deps.studio, skills=deps.skills, org_id=agent.org_id, version=version)
            itens = [{"chave": k, "hash": atuais[k]} for k in escritas if k in atuais]
        except ErroEscrita as exc:
            await _fechar_area(deps, org_id, geracao_id, area, {**base, "status": "falhou", "erro": exc.codigo})
            return
        await _t(_refresh_hash, deps, agent, version.id)
        await _fechar_area(deps, org_id, geracao_id, area, {
            **base, "status": "concluida", "erro": None, "saida": saida.model_dump(mode="json"),
            "itens": itens, "lacunas": lacunas, "concluido_em": utcnow(),
        })

    await asyncio.gather(*(_area(a) for a in areas))
    await _t(_finalizar, deps, org_id, geracao_id, round(orc.gasto, 4))


async def _run_ativa(deps: Dependencias, org_id: UUID, geracao_id: UUID) -> bool:
    return (await _t(deps.geracoes.get_geracao, org_id, geracao_id)).status == "executando"


async def _fechar_area(deps: Dependencias, org_id: UUID, geracao_id: UUID, area: str, campos: dict[str, Any]) -> None:
    campos = {"concluido_em": utcnow(), **campos}
    await _t(deps.geracoes.update_area, org_id, geracao_id, area, campos, only_if_status=("executando",))


async def _falhar_tudo(
    deps: Dependencias, org_id: UUID, geracao_id: UUID, areas: list[str], erro: str, *, status_area: str = "falhou",
) -> None:
    for a in areas:
        await _t(deps.geracoes.update_area, org_id, geracao_id, a,
                 {"status": status_area, "erro": erro, "concluido_em": utcnow()},
                 only_if_status=("pendente", "executando"))
    await _t(_finalizar, deps, org_id, geracao_id, None, erro)


def status_final(areas: list[GeracaoAreaRecord]) -> str:
    """The run-status rule: all requested areas concluded -> ``concluida``; >= 1 concluded and >= 1 failed/skipped
    -> ``parcial``; none concluded -> ``falhou``."""
    concluidas = [a for a in areas if a.status == "concluida"]
    if len(concluidas) == len(areas):
        return "concluida"
    if concluidas:
        return "parcial"
    return "falhou"


def _finalizar(deps: Dependencias, org_id: UUID, geracao_id: UUID, custo: float | None, erro: str | None = None) -> None:
    areas = deps.geracoes.list_areas(org_id, geracao_id)
    campos: dict[str, Any] = {"status": status_final(areas), "concluido_em": utcnow()}
    if custo is not None:
        campos["custo_usd"] = custo
    if erro is not None:
        campos["erro"] = erro
    # conditional: a cancelled run is never flipped back
    deps.geracoes.update_geracao(org_id, geracao_id, campos, only_if_status=ACTIVE_STATUSES)


def varrer_geracoes_orfas(store: Any) -> int:
    """Startup: fail every run a previous life of the process left ``pendente|executando``."""
    n = store.fail_orphans(erro=ORFA_ERRO)
    if n:
        logger.warning("agents.geracao.orfas_falhadas count=%s", n)
    return n


# ── read model ──────────────────────────────────────────────────────────────


def montar_saida(deps: Dependencias, agent: StudioAgentRecord, geracoes: list[GeracaoRecord]) -> list[GeracaoOut]:
    version = _versao_de_leitura(deps, agent)
    cache: dict = {}
    out: list[GeracaoOut] = []
    for g in geracoes:
        areas = []
        for a in deps.geracoes.list_areas(agent.org_id, g.id):
            itens = []
            if a.status == "concluida" and a.itens and version is not None:
                itens = estados_das_areas(a.area, a.itens, _hashes_do_agente(deps, agent, a.area, version, cache))
            areas.append(AreaOut(
                area=a.area, status=a.status, erro=a.erro, custo_usd=a.custo_usd, itens_escritos=len(a.itens),
                itens=[ItemGeradoOut(**i) for i in itens], lacunas=list(a.lacunas), concluido_em=a.concluido_em,
            ))
        out.append(GeracaoOut(
            id=g.id, agent_key=agent.key, status=g.status, versao_gerador=g.versao_gerador, modelo=g.modelo,
            briefing=Briefing(**g.briefing), custo_usd=g.custo_usd, limite_usd=g.limite_usd, criado_em=g.created_at,
            iniciado_em=g.iniciado_em, concluido_em=g.concluido_em, erro=g.erro, areas=areas,
        ))
    return out


# ── learning: generated vs published ────────────────────────────────────────


def registrar_aprendizado(deps: Dependencias, agent: StudioAgentRecord, publicada: Any) -> int:
    """On the FIRST publish after a generation, store per-area generated-vs-published (what the author kept, edited,
    removed, added) in ``geracoes.aprendizado``. Returns the runs updated."""
    n = 0
    cache: dict = {}
    for g in deps.geracoes.list_sem_aprendizado(agent.org_id, agent.id):
        por_area: dict[str, Any] = {}
        for a in deps.geracoes.list_areas(agent.org_id, g.id):
            if a.status != "concluida" or not a.itens:
                continue
            atuais = _hashes_do_agente(deps, agent, a.area, publicada, cache)
            gerados = {i["chave"]: i["hash"] for i in a.itens}
            por_area[a.area] = {
                "gerados": sorted(gerados),
                "mantidos": sorted(k for k, h in gerados.items() if atuais.get(k) == h),
                "editados": sorted(k for k, h in gerados.items() if k in atuais and atuais[k] != h),
                "removidos": sorted(k for k in gerados if k not in atuais),
                "adicionados_pelo_autor": sorted(k for k in atuais if k not in gerados),
            }
        deps.geracoes.update_geracao(
            agent.org_id, g.id, {"aprendizado": {"versao_publicada": publicada.versao, "areas": por_area}})
        n += 1
    return n


# ── completeness signal (agent page) ────────────────────────────────────────


def conteudo_status(deps_studio: Any, skills: Any, agent: StudioAgentRecord) -> dict[str, Any] | None:
    """``{textos_preenchidos, textos_total, obrigatorios_faltando}`` against the registry slots that apply to the
    agent, read from its draft (else its active version); ``None`` for a ``legado`` agent or an instance."""
    if agent.conteudo_modo != "linhas" or agent.definition_scope == "instancia":
        return None
    version = deps_studio.get_draft(agent.org_id, agent.id) or deps_studio.get_active_version(agent.org_id, agent.id)
    if version is None:
        return None
    tem_skills = bool(skills.listar_refs(version.id)) or any(s.ativo for s in deps_studio.list_skills(agent.org_id, version.id))
    canal = agent.owner_product is not None
    todos = {k: replace(s, obrigatoria=True) for k, s in TEXTOS.items()}
    kw = dict(
        tool_policy=dict(version.tool_policy), tem_skills=tem_skills, com_cliente=False, canal=canal,
        com_qualificacao=agent.padrao_qualificacao is not None,
    )
    aplicaveis = chaves_exigidas(registro=todos, **kw)
    exigidos = chaves_exigidas(**kw)
    preenchidos = {t.chave for t in deps_studio.list_textos(agent.org_id, version.id) if t.conteudo.strip()}
    return {
        "textos_preenchidos": len(aplicaveis & preenchidos),
        "textos_total": len(aplicaveis),
        "obrigatorios_faltando": sorted(exigidos - preenchidos),
    }
