"""Headline generation pipeline -- the ``headline.gerar`` job (Geração, BE-4).

Contract ``specs/geracao-contract.md`` section 5. For one batch (``cs_headline_lotes`` row):

1. **select structures** -- deterministic, no LLM (:func:`selecionar_estruturas`): the structures are the
   ``ativa`` Estruturas of the PLATFORM library (estruturas-contract 8.2: the brand's selected profiles, else the
   whole library; round-robin across profiles, seeded by the lote id), narrowed by ``estrutura_ids`` /
   ``referencia`` / a profile named in free text, the formato / gatilho filters going THROUGH the source video,
   the Metodo fallback when the pool is empty;
2. **assemble** one user message per structure (``prompts.headline_geracao.build_user_message``): the rendered
   Estrutura (formula + blocos) with the bio and the brains' elements that fill its ``[placeholders]``;
3. **one LLM call per structure** -> two headlines; a failure of one structure never stops the rest;
4. **verify** the research items the model claims (:func:`verificar_itens`: only a literal match the
   server can see survives); in SOMENTE_PESQUISA discard a headline that uses no kept item; ALWAYS discard a
   headline that still carries a ``[placeholder]``; write one ``cs_estrutura_usos`` row per headline;
5. settle the batch (``completo`` when at least one headline exists, else ``falha``).

LLM output is untrusted: it is parsed strictly, every claimed item id must have been offered, and
nothing from the reply is used as anything but text.

The handler is registered at import (:func:`register`) in the ``geracao_jobs`` registry, together
with the reconciler that moves a dead-lettered batch to ``falha``. A re-run of an interrupted batch
starts clean: the headlines of the aborted attempt are removed first, so a retry never duplicates.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Mapping, Optional

from noctusai_lib.domain.jobs import DeadLetterError, Job
from noctusai_lib.integrations.llm import LLMBudgetExceeded, LLMNotConfigured, chat_completion
from noctusai_lib.primitives.accents import fold_accents
from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.persistence.table_reads import PAGE_SIZE, batched

from app.modules.media_creation.geracao_scheduler import MSG_JOB_FAILED
from app.modules.media_creation.geracao_taxonomias import TONS
from app.modules.media_creation.pesquisa_variables import VARIABLES, VARIABLE_SLUGS
from app.modules.media_creation.prompts.cerebro_synthesis import ELEMENTOS_HEADING
from app.modules.media_creation.prompts.estruturas_contexto import renderizar_estrutura
from app.modules.media_creation.prompts.headline_geracao import (
    PROMPT_VERSAO,
    TEMPERATURA,
    TEMPLATES_METODO,
    TEMPLATES_POR_CRIATIVIDADE,
    HeadlineParseError,
    ItemOfertado,
    build_system_prompt,
    build_user_message,
    parse_output,
    tem_placeholder,
    template_blob,
    viral_blob,
)
from app.modules.media_creation.services import estruturas_retrieval as er
from app.modules.media_creation.services import geracao_jobs
from app.modules.media_creation.services.estruturas_service import EstruturasService

logger = logging.getLogger(__name__)

JOB_TYPE = "headline.gerar"

LOTES = "cs_headline_lotes"
HEADLINES = "cs_headlines"
VIRAIS = "cs_virais"
REFERENCIAS = "cs_biblioteca_referencias"
ITENS = "cs_research_items"
PERFIL = "cs_marca_perfil"
BRAINS = "cs_brains"
TOPICOS = "cs_viral_topics"
ESTRUTURAS = er.ESTRUTURAS
USOS = "cs_estrutura_usos"

GPT_SLOT = "GPT"
ELEMENTOS_MAX_CHARS = 4_000
ITENS_MAX = 40
LLM_MAX_TOKENS = 1_500

#: ``origem`` -> ``cs_headlines.modo`` (form batches leave it NULL).
MODO_POR_ORIGEM: dict[str, Optional[str]] = {"biblioteca": "manual", "sugestao_auto": "automatico"}

MSG_SEM_ESTRUTURA_FILTROS = "Nenhuma estrutura da biblioteca corresponde aos filtros escolhidos."
MSG_SEM_BIO = "Preencha a bio em Meu Perfil antes de gerar headlines."
MSG_SEM_ESTRUTURA_VIRAL = "A estrutura escolhida não está mais disponível."
MSG_IA_NAO_CONFIGURADA = "A IA não está configurada para esta organização."
MSG_ORCAMENTO = "O orçamento de IA da organização foi excedido."
MSG_NADA_GERADO = "Não foi possível gerar headlines — tente novamente."
MSG_DESCARTADAS = (
    "As headlines geradas não usaram literalmente os itens da sua pesquisa. "
    "Tente novamente ou desmarque «usar apenas os itens da minha pesquisa»."
)
#: Every generated headline kept a ``[placeholder]`` the bio / brains could not fill (counted with the discards).
MSG_DESCARTADAS_PLACEHOLDER = (
    "As headlines geradas ficaram com campos [entre colchetes] sem preencher. "
    "Complete a bio em Meu Perfil e os cérebros da marca e tente novamente."
)

#: ``(system, user, org_id, temperature) -> raw reply``. The DI seam of the LLM.
HeadlineLlm = Callable[[str, str, Optional[str], float], Awaitable[str]]

_LABELS = {v.slug: v.label for v in VARIABLES}
#: Tom ids 10..15 (the reference app) -> label, by position in ``TONS``.
TOM_LABELS = {10 + i: nome for i, (_, nome) in enumerate(TONS)}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat()


async def chat_headline_llm(system_prompt: str, user_message: str, org_id: Optional[str], temperature: float) -> str:
    """The real LLM: Anthropic pinned explicitly (never the process default), the model from config
    (a model the seed catalog prices -- an unpriced one disarms the org budget guard). Not cached:
    a creative generation must not be replayed."""
    from app.config import settings

    return await chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        provider="anthropic",
        model=settings.geracao_llm_model,
        org_id=org_id,
        temperature=temperature,
        max_tokens=LLM_MAX_TOKENS,
        cache=False,
    )


# ── reads ──────────────────────────────────────────────────────────────────────


def _all_rows(db: Any, table: str, cols: str, apply: Callable[[Any], Any], label: str) -> list[dict[str, Any]]:
    def page(start: int, end: int):
        return apply(db.table(table).select(cols)).order("id").range(start, end).execute().data

    return list(iter_paged_rows(page, page_size=PAGE_SIZE, label=label))


def carregar_perfil(db: Any, org_id: str, marca_id: str) -> Optional[dict[str, Any]]:
    rows = (
        db.table(PERFIL).select("marca_id,bio,nichos")
        .eq("marca_id", marca_id).eq("org_id", org_id).execute().data
    )
    return rows[0] if rows else None


def carregar_itens_aprovados(db: Any, org_id: str, marca_id: str) -> list[dict[str, Any]]:
    return _all_rows(
        db, ITENS, "id,variable_slug,content,plays",
        lambda q: q.eq("org_id", org_id).eq("marca_id", marca_id).eq("status", "approved"),
        "cs_research_items approved",
    )


def extrair_elementos(content: str) -> str:
    """The ``### Elementos para conteúdo`` section of a brain (up to the next heading)."""
    lines = (content or "").splitlines()
    out: list[str] = []
    on = False
    for ln in lines:
        if ln.strip().lower() == ELEMENTOS_HEADING.lower():
            on = True
            continue
        if on:
            if ln.startswith("#"):
                break
            out.append(ln)
    return "\n".join(out).strip()


def carregar_elementos(db: Any, org_id: str, marca_id: str, max_chars: int = ELEMENTOS_MAX_CHARS) -> str:
    """The "Elementos para conteúdo" of each non-empty Sistema brain, <= ``max_chars`` in total."""
    rows = (
        db.table(BRAINS).select("name,content,created_at")
        .eq("org_id", org_id).eq("marca_id", marca_id).eq("kind", "sistema")
        .order("created_at").execute().data
        or []
    )
    parts: list[str] = []
    used = 0
    for r in rows:
        el = extrair_elementos(r.get("content") or "")
        if not el:
            continue
        block = f"[{r['name']}]\n{el}"
        room = max_chars - used
        if room <= 0:
            break
        block = block[:room]
        parts.append(block)
        used += len(block) + 2
    return "\n\n".join(parts)


def carregar_assunto(db: Any, org_id: str, marca_id: str, params: Mapping[str, Any]) -> str:
    """The subject line: a typed ``assunto``, or the approved viral topics joined by ``; ``."""
    pieces: list[str] = []
    ids = [str(i) for i in (params.get("assunto_ids") or [])]
    if ids:
        for chunk in batched(ids):
            rows = (
                db.table(TOPICOS).select("id,topic")
                .eq("org_id", org_id).eq("marca_id", marca_id).eq("status", "approved")
                .in_("id", chunk).execute().data
                or []
            )
            pieces.extend(r["topic"] for r in rows)
    for key in ("assunto_livre", "assunto"):
        v = (params.get(key) or "").strip()
        if v:
            pieces.append(v)
    return "; ".join(p for p in pieces if p)


_LINHA_COLS = "id,perfil_id,viral_id,formato,objetivos"
_VIRAL_COLS = "id,classificacao_status,formato_ids,nicho_ids,gatilho,score_viral,e_viral"


def referencias_da_marca(db: Any, org_id: str, marca_id: str) -> list[dict[str, Any]]:
    return _all_rows(
        db, REFERENCIAS, "id,modo,perfil_id,viral_id,posts_ate",
        lambda q: q.eq("org_id", org_id).eq("marca_id", marca_id), "cs_biblioteca_referencias",
    )


def escopo_da_marca(db: Any, org_id: str, marca_id: str) -> Optional[set[str]]:
    """The brand's selected profiles (estruturas-contract 8.2 step 1); ``None`` = it selected nothing = the
    WHOLE library. The one org-scoped input of the pool."""
    perfis = EstruturasService(db, org_id=org_id, user_id="", is_admin=False).perfis_selecionados(marca_id)
    return perfis or None


def carregar_linhas(
    db: Any, *, perfil_ids: Optional[set[str]] = None, estrutura_ids: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """The ``ativa`` Estruturas (``id, perfil_id, viral_id, formato, objetivos``) of the PLATFORM library -- no
    ``org_id`` (migration 351). ``estrutura_ids`` wins over ``perfil_ids``; neither = the whole library. An empty
    ``perfil_ids`` set is nothing, never "everything"."""
    def query(filtro: Callable[[Any], Any]):
        def pagina(a: int, b: int):
            q = db.table(ESTRUTURAS).select(_LINHA_COLS).eq("status", "ativa")
            return filtro(q).order("id").range(a, b).execute().data
        return pagina

    if estrutura_ids is not None:
        coluna, valores = "id", estrutura_ids
    elif perfil_ids is not None:
        coluna, valores = "perfil_id", sorted(perfil_ids)
    else:
        return list(iter_paged_rows(query(lambda q: q), label="cs_estruturas (biblioteca)", page_size=1000, max_pages=200))
    rows: list[dict[str, Any]] = []
    for lote in batched(sorted({str(v) for v in valores})):
        rows += list(iter_paged_rows(query(lambda q, lote=lote: q.in_(coluna, lote)), label=f"cs_estruturas ({coluna})", page_size=500))
    return rows


def carregar_virais_fonte(db: Any, viral_ids: Any) -> dict[str, dict[str, Any]]:
    """The source videos' classification (platform-wide, no org filter), ``{viral_id: row}``."""
    out: dict[str, dict[str, Any]] = {}
    for lote in batched(sorted({str(v) for v in viral_ids if v})):
        for r in db.table(VIRAIS).select(_VIRAL_COLS).in_("id", lote).execute().data or []:
            out[str(r["id"])] = r
    return out


# ── selection ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Estrutura:
    """One structure to generate from: an Estrutura of the library or a Metodo template."""

    pool: Optional[er.EstruturaPool] = None
    viral_id: Optional[str] = None  # the source video (legacy ``Headline.viral``)
    template_metodo: Optional[int] = None

    @property
    def estrutura_id(self) -> Optional[str]:
        return self.pool.id if self.pool is not None else None

    @property
    def obrigatorios(self) -> frozenset[str]:
        """Research slots the structure demands: none -- an Estrutura has ``[placeholders]``, not ``{{SLUG}}`` slots."""
        return frozenset()

    def blob(self) -> str:
        if self.template_metodo is not None:
            return template_blob(self.template_metodo)
        if self.pool is None:
            raise ValueError("Estrutura sem template nem linha da biblioteca")
        return viral_blob(renderizar_estrutura(self.pool))


@dataclass
class Selecao:
    estruturas: list[Estrutura] = field(default_factory=list)
    fallback_metodo: bool = False
    aviso_poucas: bool = False
    #: Estruturas a formato / gatilho filter excluded because their source video is missing or unclassified.
    aviso_sem_classificacao: int = 0
    erro: Optional[str] = None


def estruturas_de(db: Any, linhas: list[dict[str, Any]], ids: list[str]) -> list[Estrutura]:
    """The full :class:`Estrutura` objects of ``ids`` (in that order), taking ``viral_id`` from ``linhas``."""
    viral_de = {str(r["id"]): (str(r["viral_id"]) if r.get("viral_id") else None) for r in linhas}
    return [Estrutura(pool=p, viral_id=viral_de.get(p.id)) for p in er.carregar_estruturas(db, ids)]


def _passa_filtros(viral: Mapping[str, Any], referencia: Mapping[str, Any]) -> bool:
    """The formato / gatilho filter, judged on the SOURCE VIDEO's classification."""
    if referencia.get("tipo") == "formato":
        return bool(set(referencia.get("formato_ids") or []) & set(viral.get("formato_ids") or []))
    if referencia.get("tipo") == "gatilho":
        return viral.get("gatilho") in set(referencia.get("gatilhos") or [])
    return True


def rank_score(c: Mapping[str, Any]) -> float:
    return -float(c.get("score_viral") or 0.0)


def itens_por_slug(itens: list[dict[str, Any]], valores: Optional[Mapping[str, Any]] = None) -> dict[str, list[dict[str, Any]]]:
    """Approved items grouped by variable slug; a slug the user narrowed with ``valores`` keeps only
    the picked ids."""
    picked = {slug: {str(i) for i in ids} for slug, ids in (valores or {}).items()}
    out: dict[str, list[dict[str, Any]]] = {}
    for it in itens:
        slug = it["variable_slug"]
        if slug in picked and str(it["id"]) not in picked[slug]:
            continue
        out.setdefault(slug, []).append(it)
    return out


def _sem_itens_para_somente(params: Mapping[str, Any], por_slug: Mapping[str, list[dict[str, Any]]]) -> Optional[str]:
    """SOMENTE_PESQUISA needs at least one approved item among the selected variables; else the honest error."""
    variaveis = set(params.get("variaveis") or [])
    if "*" in variaveis:
        variaveis = set(VARIABLE_SLUGS)
    variaveis.discard(GPT_SLOT)
    if any(por_slug.get(s) for s in variaveis):
        return None
    nomes = [_LABELS.get(s, s) for s in sorted(variaveis)]
    extra = f" (faltam: {'; '.join(nomes[:5])})" if nomes else ""
    return (
        "Nenhuma estrutura pode ser preenchida só com os itens da sua pesquisa. "
        f"Aprove itens em Minha Pesquisa{extra} ou desmarque «usar apenas os itens da minha pesquisa»."
    )


def selecionar_estruturas(
    db: Any,
    *,
    org_id: str,
    marca_id: str,
    origem: str,
    params: Mapping[str, Any],
    por_slug: Mapping[str, list[dict[str, Any]]],
    limite: int,
    semente: str,
) -> Selecao:
    """Contract 5.1 steps 1-2 over the Estruturas pool (estruturas-contract 8.2), deterministic. ``biblioteca`` /
    ``sugestao_auto`` batches are handled by :func:`estruturas_dadas` (their structures are chosen by id).

    Scope: ``estrutura_ids`` (those ``ativa`` rows) > ``referencia: perfil`` / a profile named in free text
    (``perfis_resolvidos``) > the brand's selected profiles > the whole library. The formato / gatilho filters go
    through the source video; Estruturas whose video is missing or unclassified are excluded and COUNTED."""
    criatividade = params.get("criatividade") or "equilibrado"
    referencia = params.get("referencia") or None
    ids_pedidos = [str(i) for i in params.get("estrutura_ids") or []]
    perfis_pedidos: Optional[set[str]] = None
    if referencia and referencia.get("tipo") == "perfil":
        perfis_pedidos = {str(p) for p in referencia.get("perfil_ids") or []}
    elif params.get("perfis_resolvidos"):
        perfis_pedidos = {str(p) for p in params["perfis_resolvidos"]}

    if ids_pedidos:
        linhas = carregar_linhas(db, estrutura_ids=ids_pedidos)
    elif perfis_pedidos is not None:
        linhas = carregar_linhas(db, perfil_ids=perfis_pedidos)
    else:
        linhas = carregar_linhas(db, perfil_ids=escopo_da_marca(db, org_id, marca_id))
    estreitado = bool(ids_pedidos) or perfis_pedidos is not None
    if not linhas:
        if estreitado:
            return Selecao(erro=MSG_SEM_ESTRUTURA_FILTROS)
        nums = TEMPLATES_POR_CRIATIVIDADE[criatividade][:limite]  # never silently empty: the Metodo templates
        return Selecao([Estrutura(template_metodo=n) for n in nums if n in TEMPLATES_METODO], fallback_metodo=True)

    sem_class = 0
    if referencia and referencia.get("tipo") in ("formato", "gatilho"):
        virais = carregar_virais_fonte(db, (r.get("viral_id") for r in linhas))
        mantidas = []
        for r in linhas:
            v = virais.get(str(r["viral_id"])) if r.get("viral_id") else None
            if v is None or v.get("classificacao_status") != "concluida":
                sem_class += 1
            elif _passa_filtros(v, referencia):
                mantidas.append(r)
        linhas = mantidas
    if not linhas:
        return Selecao(erro=MSG_SEM_ESTRUTURA_FILTROS, aviso_sem_classificacao=sem_class)

    formulario = origem in ("form_me", "form_public")
    if formulario and params.get("somente_pesquisa"):
        erro = _sem_itens_para_somente(params, por_slug)
        if erro:
            return Selecao(erro=erro, aviso_sem_classificacao=sem_class)

    ids = er.selecionar_ids(linhas, semente=semente, limite=limite)
    escolhidas = estruturas_de(db, linhas, ids)
    if not escolhidas:  # the rows vanished between the two reads
        return Selecao(erro=MSG_SEM_ESTRUTURA_FILTROS, aviso_sem_classificacao=sem_class)
    return Selecao(escolhidas, aviso_poucas=len(escolhidas) < 3, aviso_sem_classificacao=sem_class)


def estruturas_dadas(db: Any, ids: list[str]) -> list[Estrutura]:
    """Structures chosen by id (the Biblioteca wizard / the daily suggestions): ``ativa`` rows only, in the order given."""
    ordem = list(dict.fromkeys(str(i) for i in ids))
    linhas = carregar_linhas(db, estrutura_ids=ordem)
    por_id = {e.estrutura_id: e for e in estruturas_de(db, linhas, [str(r["id"]) for r in linhas])}
    return [por_id[i] for i in ordem if i in por_id]


def estruturas_do_viral(db: Any, viral_id: str) -> list[str]:
    """The ``ativa`` Estruturas of one source video (the Biblioteca wizard's ``viral_id``), by id."""
    rows = db.table(ESTRUTURAS).select("id").eq("viral_id", viral_id).eq("status", "ativa").order("id").execute().data or []
    return [str(r["id"]) for r in rows]


# ── item offering + verification ───────────────────────────────────────────────


def itens_oferecidos(
    estrutura: Estrutura,
    por_slug: Mapping[str, list[dict[str, Any]]],
    params: Mapping[str, Any],
) -> list[ItemOfertado]:
    """The approved items offered for ONE structure: slugs present in its blueprint or selected in
    ``variaveis``; the user's picked values first, then by plays; at most :data:`ITENS_MAX`."""
    slugs = set(estrutura.obrigatorios)
    variaveis = set(params.get("variaveis") or [])
    if "*" in variaveis:
        variaveis = set(por_slug)
    slugs |= variaveis - {GPT_SLOT}
    picked = {str(i) for ids in (params.get("valores") or {}).values() for i in ids}
    pool = [it for s in sorted(slugs) for it in por_slug.get(s, [])]
    pool.sort(key=lambda it: (str(it["id"]) not in picked, -(it.get("plays") or 0), str(it["id"])))
    return [ItemOfertado(str(it["id"]), it["variable_slug"], it["content"]) for it in pool[:ITENS_MAX]]


_WS = re.compile(r"\s+")


def normalizar(text: str) -> str:
    """Case- and accent-insensitive form used to compare an item with the headline text."""
    return _WS.sub(" ", fold_accents(text).casefold()).strip()


def verificar_itens(
    texto: str, itens_declarados: list[str], oferecidos: Mapping[str, ItemOfertado],
) -> list[dict[str, str]]:
    """Keep a declared item only when it was OFFERED and its content occurs in ``texto``
    (case/accent-insensitive). Returns ``itens_usados`` rows ``{slot, item_id, conteudo}``."""
    alvo = normalizar(texto)
    kept: list[dict[str, str]] = []
    seen: set[str] = set()
    for item_id in itens_declarados:
        it = oferecidos.get(item_id)
        if it is None or item_id in seen:
            continue
        conteudo = normalizar(it.conteudo)
        if conteudo and conteudo in alvo:
            seen.add(item_id)
            kept.append({"slot": it.slug, "item_id": it.id, "conteudo": it.conteudo})
    return kept


def montar_mensagem(
    *,
    estrutura: Estrutura,
    bio: str,
    elementos: str,
    itens: list[ItemOfertado],
    assunto: str,
    params: Mapping[str, Any],
    origem: str,
) -> str:
    tom = TOM_LABELS.get(params.get("tom") or 0, "") if origem == "form_viral" else ""
    somente = bool(params.get("somente_pesquisa")) and origem in ("form_me", "form_public")
    return build_user_message(
        bio=bio, elementos=elementos, itens=itens, assunto=assunto, tom=tom,
        modo="SOMENTE_PESQUISA" if somente else "PESQUISA_PREFERENCIAL",
        criatividade=params.get("criatividade") or "equilibrado",
        estrutura=estrutura.blob(),
    )


# ── the job ────────────────────────────────────────────────────────────────────


def _params_com_aviso(params: Mapping[str, Any], sel: Selecao) -> dict[str, Any]:
    """``parametros`` with this run's ``aviso_sem_classificacao`` (the lote has no column for it; it is derived
    afresh on every (re)run and read back by ``HeadlineService.present_lote``)."""
    return {"parametros": {**params, "aviso_sem_classificacao": sel.aviso_sem_classificacao}}


def _registrar_usos(
    db: Any, est: Estrutura, headlines: list[dict[str, Any]], *, org_id: str, marca_id: str, user_id: Optional[str],
) -> None:
    """One ``cs_estrutura_usos`` row per generated headline (``contexto='lote_headlines'``, ``papel='principal'``).
    A Metodo-template headline has no Estrutura and writes nothing."""
    if est.estrutura_id is None:
        return
    db.table(USOS).insert([
        {
            "id": str(uuid.uuid4()), "org_id": org_id, "marca_id": marca_id, "estrutura_id": est.estrutura_id,
            "contexto": "lote_headlines", "papel": "principal", "ordem": 1, "bloco_ids": [],
            "headline_id": h["id"], "created_by": user_id, "created_at": _iso(),
        }
        for h in headlines
    ]).execute()


_TERMINAL = frozenset({"completo", "falha"})

#: `(org_id, lote_id, state)` — pushes a batch's live state to the SSE job-progress stream. Optional.
ProgressPublisher = Callable[[str, str, dict[str, Any]], Awaitable[None]]


def _patch(db: Any, lote_id: str, patch: dict[str, Any]) -> None:
    db.table(LOTES).update({**patch, "updated_at": _iso()}).eq("id", lote_id).execute()


def _falhar(db: Any, lote_id: str, erro: str, extra: Optional[dict[str, Any]] = None) -> None:
    _patch(db, lote_id, {"status": "falha", "erro": erro, "etapa": None, "finished_at": _iso(), **(extra or {})})


async def executar_lote(
    db: Any, llm: HeadlineLlm, lote_id: str, *, cfg: Any = None, progress: Optional[ProgressPublisher] = None,
) -> None:
    """Run (or re-run) one batch. Never leaves the row in a non-terminal state on its own failure:
    every path ends ``completo`` or ``falha``; only a missing row raises (``DeadLetterError``)."""
    if cfg is None:
        from app.config import settings as cfg
    rows = db.table(LOTES).select("*").eq("id", lote_id).execute().data
    if not rows:
        raise DeadLetterError(f"lote {lote_id} não existe mais")
    lote = rows[0]
    if lote["status"] in _TERMINAL:
        return
    org_id, marca_id, origem = lote["org_id"], lote["marca_id"], lote["origem"]
    params: dict[str, Any] = lote.get("parametros") or {}

    async def _push(**state: Any) -> None:
        """Push the batch's new state to the live stream (best-effort: the row stays the truth)."""
        if progress is not None:
            await progress(str(org_id), lote_id, {"status": "processando", "estruturas_total": total_est, **state})

    total_est = 0
    _patch(db, lote_id, {
        "status": "processando", "etapa": "Selecionando estruturas",
        "started_at": lote.get("started_at") or _iso(),
        "modelo": cfg.geracao_llm_model, "prompt_versao": PROMPT_VERSAO,
        "estruturas_processadas": 0, "estruturas_com_erro": 0,
    })
    await _push(etapa="Selecionando estruturas", estruturas_processadas=0)
    # an interrupted earlier attempt left partial headlines: start clean, never duplicate
    db.table(HEADLINES).delete().eq("lote_id", lote_id).eq("org_id", org_id).execute()

    perfil = carregar_perfil(db, org_id, marca_id)
    bio = ((perfil or {}).get("bio") or "").strip()
    if not bio:
        _falhar(db, lote_id, MSG_SEM_BIO)
        return
    aprovados = carregar_itens_aprovados(db, org_id, marca_id)
    por_slug = itens_por_slug(aprovados, params.get("valores"))
    elementos = carregar_elementos(db, org_id, marca_id)
    assunto = carregar_assunto(db, org_id, marca_id, params)
    limite = int(cfg.headline_estruturas_por_lote)

    if origem == "biblioteca":
        if params.get("estrutura_id"):
            ids = [str(params["estrutura_id"])]
        else:  # the chosen video = all its ``ativa`` Estruturas
            ids = estruturas_do_viral(db, str(params.get("viral_id")))
        sel = Selecao(estruturas_dadas(db, ids[:limite]))
        if not sel.estruturas:
            sel.erro = MSG_SEM_ESTRUTURA_VIRAL
    elif origem == "sugestao_auto":
        ids = [str(i) for i in params.get("estrutura_ids") or []]
        for viral_id in params.get("viral_ids") or []:  # a batch queued before Estruturas: its videos' Estruturas
            ids += estruturas_do_viral(db, str(viral_id))
        sel = Selecao(estruturas_dadas(db, ids[:limite]))
        if not sel.estruturas:
            sel.erro = MSG_SEM_ESTRUTURA_VIRAL
    else:
        sel = selecionar_estruturas(
            db, org_id=org_id, marca_id=marca_id, origem=origem, params=params, por_slug=por_slug,
            limite=limite, semente=lote_id,
        )
    if sel.erro:
        _falhar(db, lote_id, sel.erro, _params_com_aviso(params, sel))
        await _push(status="falha", erro=sel.erro, etapa=None)
        return
    total_est = len(sel.estruturas)

    _patch(db, lote_id, {
        "estruturas_total": len(sel.estruturas), "aviso_poucas_estruturas": sel.aviso_poucas,
        "fallback_metodo": sel.fallback_metodo, **_params_com_aviso(params, sel),
    })

    somente = bool(params.get("somente_pesquisa")) and origem in ("form_me", "form_public")
    criatividade = params.get("criatividade") or "equilibrado"
    system = build_system_prompt()
    modo = MODO_POR_ORIGEM.get(origem)
    n_ok = n_erro = n_descartadas = n_colchetes = 0
    fatal: Optional[str] = None

    for idx, est in enumerate(sel.estruturas, start=1):
        _patch(db, lote_id, {"etapa": f"Gerando headlines — estrutura {idx} de {len(sel.estruturas)}"})
        await _push(etapa=f"Gerando headlines — estrutura {idx} de {len(sel.estruturas)}", estruturas_processadas=idx - 1)
        itens = itens_oferecidos(est, por_slug, params)
        oferecidos = {it.id: it for it in itens}
        msg = montar_mensagem(
            estrutura=est, bio=bio, elementos=elementos, itens=itens, assunto=assunto,
            params=params, origem=origem,
        )
        try:
            reply = await llm(system, msg, org_id, TEMPERATURA[criatividade])
        except LLMNotConfigured:
            fatal = MSG_IA_NAO_CONFIGURADA
            break
        except LLMBudgetExceeded:
            fatal = MSG_ORCAMENTO
            break
        except Exception as exc:  # noqa: BLE001 - one structure's failure never stops the batch
            logger.warning("headline.gerar %s: LLM falhou na estrutura %d: %s", lote_id, idx, exc)
            n_erro += 1
            _patch(db, lote_id, {"estruturas_processadas": idx, "estruturas_com_erro": n_erro})
            continue
        try:
            saidas = parse_output(reply)
        except HeadlineParseError as exc:
            logger.warning("headline.gerar %s: resposta inválida na estrutura %d: %s", lote_id, idx, exc)
            n_erro += 1
            _patch(db, lote_id, {"estruturas_processadas": idx, "estruturas_com_erro": n_erro})
            continue

        novas = []
        for s in saidas:
            if tem_placeholder(s.texto):  # a [placeholder] the bio / brains did not fill: never shown, but counted
                n_colchetes += 1
                continue
            usados = verificar_itens(s.texto, list(s.itens), oferecidos)
            if somente and not usados:
                n_descartadas += 1
                continue
            novas.append({
                "id": str(uuid.uuid4()), "org_id": org_id, "marca_id": marca_id, "lote_id": lote_id,
                "viral_id": est.viral_id, "template_metodo": est.template_metodo,
                "texto": s.texto, "texto_original": s.texto, "angulo": s.angulo,
                "itens_usados": usados, "favorita": False, "modo": modo,
                "created_by": lote.get("created_by"), "created_at": _iso(),
            })
        if novas:
            db.table(HEADLINES).insert(novas).execute()
            _registrar_usos(db, est, novas, org_id=org_id, marca_id=marca_id, user_id=lote.get("created_by"))
            n_ok += len(novas)
        else:
            n_erro += 1
        _patch(db, lote_id, {"estruturas_processadas": idx, "estruturas_com_erro": n_erro})

    finished = {"etapa": None, "finished_at": _iso()}
    if n_ok:
        _patch(db, lote_id, {**finished, "status": "completo", "erro": fatal})
        await _push(status="completo", etapa=None, estruturas_processadas=total_est)
    else:
        if fatal:
            erro = fatal
        elif n_colchetes and not n_descartadas:
            erro = MSG_DESCARTADAS_PLACEHOLDER
        elif somente and n_descartadas:
            erro = MSG_DESCARTADAS
        else:
            erro = MSG_NADA_GERADO
        _falhar(db, lote_id, erro)
        await _push(status="falha", erro=erro, etapa=None)


def reconciliar_dead_letter(db: Any, job: Job) -> None:
    """``on_dead_letter`` reconciler: a dead-lettered queue row moves its batch to ``falha``
    (terminal batches are left alone)."""
    lote_id = (job.payload or {}).get("lote_id")
    if not lote_id:
        return
    db.table(LOTES).update({
        "status": "falha", "erro": MSG_JOB_FAILED, "etapa": None, "finished_at": _iso(), "updated_at": _iso(),
    }).eq("id", str(lote_id)).in_("status", ["criando", "processando"]).execute()


def make_handler(
    get_db: Callable[[], Any], llm: HeadlineLlm, cfg: Any = None, progress: Optional[ProgressPublisher] = None,
) -> Callable[[Job], Awaitable[None]]:
    async def handle(job: Job) -> None:
        lote_id = (job.payload or {}).get("lote_id")
        if not lote_id:
            raise DeadLetterError("payload sem lote_id")
        db = get_db()
        if db is None:
            raise RuntimeError("sem cliente admin do Supabase")  # retried by the worker policy
        await executar_lote(db, llm, str(lote_id), cfg=cfg, progress=progress)

    return handle


def _admin_db() -> Any:
    from app.dependencies import get_admin_client

    return get_admin_client()


async def _publish_progress(org_id: str, lote_id: str, state: dict[str, Any]) -> None:
    from app.modules.media_creation.services.headline_progress import publish_lote_progress

    await publish_lote_progress(org_id, lote_id, state)


handle_headline_gerar = make_handler(_admin_db, chat_headline_llm, progress=_publish_progress)


def register() -> None:
    """Register the ``headline.gerar`` handler + dead-letter reconciler (idempotent)."""
    geracao_jobs.register_handler(JOB_TYPE, handle_headline_gerar, on_dead_letter=reconciliar_dead_letter)


register()

__all__ = [
    "Estrutura",
    "HeadlineLlm",
    "JOB_TYPE",
    "Selecao",
    "carregar_linhas",
    "chat_headline_llm",
    "escopo_da_marca",
    "estruturas_dadas",
    "estruturas_do_viral",
    "executar_lote",
    "extrair_elementos",
    "handle_headline_gerar",
    "itens_oferecidos",
    "itens_por_slug",
    "make_handler",
    "montar_mensagem",
    "normalizar",
    "reconciliar_dead_letter",
    "register",
    "selecionar_estruturas",
    "verificar_itens",
]
