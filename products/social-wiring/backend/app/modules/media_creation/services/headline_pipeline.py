"""Headline generation pipeline -- the ``headline.gerar`` job (Geração, BE-4).

Contract ``specs/geracao-contract.md`` section 5. For one batch (``cs_headline_lotes`` row):

1. **select structures** -- deterministic, no LLM (:func:`selecionar_estruturas`): the pool order,
   the filters, the variable compatibility, the ``somente_pesquisa`` exclusion, the Metodo Audience
   fallback when the library has nothing;
2. **assemble** one user message per structure (``prompts.headline_geracao.build_user_message``);
3. **one LLM call per structure** -> two headlines; a failure of one structure never stops the rest;
4. **verify** the research items the model claims (:func:`verificar_itens`: only a literal match the
   server can see survives) and, in SOMENTE_PESQUISA, discard a headline a slot of which is not
   backed by a kept item;
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
    template_blob,
    viral_blob,
)
from app.modules.media_creation.services import geracao_jobs

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

#: ``(system, user, org_id, temperature) -> raw reply``. The DI seam of the LLM.
HeadlineLlm = Callable[[str, str, Optional[str], float], Awaitable[str]]

_LABELS = {v.slug: v.label for v in VARIABLES}
#: Tom ids 10..15 (CoreStudio) -> label, by position in ``TONS``.
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


_VIRAL_COLS = "id,codigo,perfil_id,blueprint,blueprint_slots,formato_ids,nicho_ids,gatilho,score_viral,e_viral,publicado_em"


def carregar_candidatos(db: Any, org_id: str) -> list[dict[str, Any]]:
    """Every classified viral of the org with a blueprint (the structure candidates)."""
    rows = _all_rows(
        db, VIRAIS, _VIRAL_COLS,
        lambda q: q.eq("org_id", org_id).eq("classificacao_status", "concluida"),
        "cs_virais candidatos",
    )
    return [r for r in rows if (r.get("blueprint") or "").strip()]


def carregar_virais_por_id(db: Any, org_id: str, ids: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for chunk in batched(ids):
        out.extend(
            db.table(VIRAIS).select(_VIRAL_COLS)
            .eq("org_id", org_id).eq("classificacao_status", "concluida").in_("id", chunk)
            .execute().data or []
        )
    return [r for r in out if (r.get("blueprint") or "").strip()]


def referencias_da_marca(db: Any, org_id: str, marca_id: str) -> list[dict[str, Any]]:
    return _all_rows(
        db, REFERENCIAS, "id,modo,perfil_id,viral_id,posts_ate",
        lambda q: q.eq("org_id", org_id).eq("marca_id", marca_id), "cs_biblioteca_referencias",
    )


# ── selection ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Estrutura:
    """One structure to generate from: a library viral or a Metodo Audience template."""

    viral_id: Optional[str] = None
    template_metodo: Optional[int] = None
    blueprint: Optional[str] = None
    slots: tuple[str, ...] = ()
    compativel: bool = True

    @property
    def obrigatorios(self) -> frozenset[str]:
        return frozenset(self.slots) - {GPT_SLOT}

    def blob(self) -> str:
        if self.template_metodo is not None:
            return template_blob(self.template_metodo)
        return viral_blob(self.blueprint or "")


@dataclass
class Selecao:
    estruturas: list[Estrutura] = field(default_factory=list)
    fallback_metodo: bool = False
    aviso_poucas: bool = False
    erro: Optional[str] = None


def _estrutura(row: Mapping[str, Any], compativel: bool = True) -> Estrutura:
    return Estrutura(
        viral_id=str(row["id"]), blueprint=row.get("blueprint"),
        slots=tuple(row.get("blueprint_slots") or ()), compativel=compativel,
    )


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def pool_da_biblioteca(
    candidatos: list[dict[str, Any]], referencias: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Tier 1: what the marca's Minha Biblioteca allows -- the virals of the profile references newer
    than their ``posts_ate`` plus the video references (CoreStudio did the same, mechanisms 7.3.1)."""
    by_perfil: dict[str, Optional[datetime]] = {}
    videos: set[str] = set()
    for ref in referencias:
        if ref.get("modo") == "perfil" and ref.get("perfil_id"):
            by_perfil[str(ref["perfil_id"])] = _parse_ts(ref.get("posts_ate"))
        elif ref.get("modo") == "video" and ref.get("viral_id"):
            videos.add(str(ref["viral_id"]))
    out = []
    for c in candidatos:
        if str(c["id"]) in videos:
            out.append(c)
        elif str(c["perfil_id"]) in by_perfil:
            cutoff = by_perfil[str(c["perfil_id"])]
            pub = _parse_ts(c.get("publicado_em"))
            if cutoff is None or (pub is not None and pub >= cutoff):
                out.append(c)
    return out


def tiers_de_pool(candidatos: list[dict[str, Any]], referencias: list[dict[str, Any]], nichos: list[int]) -> list[list[dict[str, Any]]]:
    nich = set(nichos or [])
    t1 = pool_da_biblioteca(candidatos, referencias)
    t2 = [c for c in candidatos if nich & set(c.get("nicho_ids") or [])]
    return [t1, t2, list(candidatos)]


def pool_de_estruturas(
    candidatos: list[dict[str, Any]], referencias: list[dict[str, Any]], nichos: list[int],
) -> list[dict[str, Any]]:
    """THE canonical structure pool (contract 5.1 step 1): the first non-empty tier of
    Minha Biblioteca -> niche overlap -> whole org, over ``candidatos`` (classified virals with a
    blueprint, see :func:`carregar_candidatos`). Filters / ranking are applied by the caller."""
    return next((t for t in tiers_de_pool(candidatos, referencias, nichos) if t), [])


def _passa_filtros(c: Mapping[str, Any], referencia: Optional[Mapping[str, Any]]) -> bool:
    if not referencia:
        return True
    tipo = referencia.get("tipo")
    if tipo == "perfil":
        return str(c["perfil_id"]) in {str(p) for p in referencia.get("perfil_ids") or []}
    if tipo == "formato":
        return bool(set(referencia.get("formato_ids") or []) & set(c.get("formato_ids") or []))
    if tipo == "gatilho":
        return c.get("gatilho") in set(referencia.get("gatilhos") or [])
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


def selecionar_estruturas(
    *,
    origem: str,
    params: Mapping[str, Any],
    candidatos: list[dict[str, Any]],
    referencias: list[dict[str, Any]],
    nichos: list[int],
    por_slug: Mapping[str, list[dict[str, Any]]],
    limite: int,
) -> Selecao:
    """Contract 5.1 steps 1-2, deterministic. ``biblioteca`` / ``sugestao_auto`` batches are handled
    by :func:`estruturas_dadas` (their structures are chosen by id)."""
    criatividade = params.get("criatividade") or "equilibrado"
    if not candidatos:
        nums = TEMPLATES_POR_CRIATIVIDADE[criatividade][:limite]
        return Selecao([Estrutura(template_metodo=n, compativel=True) for n in nums if n in TEMPLATES_METODO],
                       fallback_metodo=True)

    formulario = origem in ("form_me", "form_public")
    somente = bool(params.get("somente_pesquisa")) and formulario
    variaveis = set(params.get("variaveis") or [])
    if "*" in variaveis:
        variaveis = set(VARIABLE_SLUGS)
    variaveis.discard(GPT_SLOT)

    filtrou_algo = False
    faltantes: list[str] = []
    for tier in tiers_de_pool(candidatos, referencias, nichos):
        filtrados = [c for c in tier if _passa_filtros(c, params.get("referencia"))]
        if not filtrados:
            continue
        filtrou_algo = True
        elegiveis: list[Estrutura] = []
        for c in sorted(filtrados, key=rank_score):
            slots = frozenset(c.get("blueprint_slots") or ()) - {GPT_SLOT}
            compat = (not formulario) or bool(slots & variaveis)
            if somente:
                lacunas = [s for s in sorted(slots) if not por_slug.get(s)]
                if not compat or lacunas:
                    faltantes.extend(lacunas)
                    continue
            elegiveis.append(_estrutura(c, compat))
        if not elegiveis:
            continue
        elegiveis.sort(key=lambda e: not e.compativel)  # stable: compatible first, score order kept
        escolhidas = elegiveis[:limite]
        if formulario:
            aviso = sum(1 for e in escolhidas if e.compativel) < 3
        else:
            aviso = origem == "form_viral" and len(escolhidas) < 3
        return Selecao(escolhidas, aviso_poucas=aviso)

    if somente and filtrou_algo:
        nomes = []
        for s in faltantes:
            lab = _LABELS.get(s, s)
            if lab not in nomes:
                nomes.append(lab)
        extra = f" (faltam: {'; '.join(nomes[:5])})" if nomes else ""
        return Selecao(erro=(
            "Nenhuma estrutura pode ser preenchida só com os itens da sua pesquisa. "
            f"Aprove itens em Minha Pesquisa{extra} ou desmarque «usar apenas os itens da minha pesquisa»."
        ))
    return Selecao(erro=MSG_SEM_ESTRUTURA_FILTROS)


def estruturas_dadas(rows: list[dict[str, Any]], ordem: list[str]) -> list[Estrutura]:
    """Structures chosen by id (the Biblioteca wizard / the daily suggestions), in the order given."""
    by_id = {str(r["id"]): r for r in rows}
    return [_estrutura(by_id[i]) for i in ordem if i in by_id]


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

_TERMINAL = frozenset({"completo", "falha"})


def _patch(db: Any, lote_id: str, patch: dict[str, Any]) -> None:
    db.table(LOTES).update({**patch, "updated_at": _iso()}).eq("id", lote_id).execute()


def _falhar(db: Any, lote_id: str, erro: str, extra: Optional[dict[str, Any]] = None) -> None:
    _patch(db, lote_id, {"status": "falha", "erro": erro, "etapa": None, "finished_at": _iso(), **(extra or {})})


async def executar_lote(db: Any, llm: HeadlineLlm, lote_id: str, *, cfg: Any = None) -> None:
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
    _patch(db, lote_id, {
        "status": "processando", "etapa": "Selecionando estruturas",
        "started_at": lote.get("started_at") or _iso(),
        "modelo": cfg.geracao_llm_model, "prompt_versao": PROMPT_VERSAO,
        "estruturas_processadas": 0, "estruturas_com_erro": 0,
    })
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
        sel = Selecao(estruturas_dadas(carregar_virais_por_id(db, org_id, [str(params.get("viral_id"))]),
                                      [str(params.get("viral_id"))]))
        if not sel.estruturas:
            sel.erro = MSG_SEM_ESTRUTURA_VIRAL
    elif origem == "sugestao_auto":
        ids = [str(i) for i in params.get("viral_ids") or []][:limite]
        sel = Selecao(estruturas_dadas(carregar_virais_por_id(db, org_id, ids), ids))
        if not sel.estruturas:
            sel.erro = MSG_SEM_ESTRUTURA_VIRAL
    else:
        sel = selecionar_estruturas(
            origem=origem, params=params, candidatos=carregar_candidatos(db, org_id),
            referencias=referencias_da_marca(db, org_id, marca_id),
            nichos=list((perfil or {}).get("nichos") or []), por_slug=por_slug, limite=limite,
        )
    if sel.erro:
        _falhar(db, lote_id, sel.erro)
        return

    _patch(db, lote_id, {
        "estruturas_total": len(sel.estruturas), "aviso_poucas_estruturas": sel.aviso_poucas,
        "fallback_metodo": sel.fallback_metodo,
    })

    somente = bool(params.get("somente_pesquisa")) and origem in ("form_me", "form_public")
    criatividade = params.get("criatividade") or "equilibrado"
    system = build_system_prompt()
    modo = MODO_POR_ORIGEM.get(origem)
    n_ok = n_erro = n_descartadas = 0
    fatal: Optional[str] = None

    for idx, est in enumerate(sel.estruturas, start=1):
        _patch(db, lote_id, {"etapa": f"Gerando headlines — estrutura {idx} de {len(sel.estruturas)}"})
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
            usados = verificar_itens(s.texto, list(s.itens), oferecidos)
            if somente and est.obrigatorios - {u["slot"] for u in usados}:
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
            n_ok += len(novas)
        else:
            n_erro += 1
        _patch(db, lote_id, {"estruturas_processadas": idx, "estruturas_com_erro": n_erro})

    finished = {"etapa": None, "finished_at": _iso()}
    if n_ok:
        _patch(db, lote_id, {**finished, "status": "completo", "erro": fatal})
    elif fatal:
        _falhar(db, lote_id, fatal)
    else:
        _falhar(db, lote_id, MSG_DESCARTADAS if somente and n_descartadas else MSG_NADA_GERADO)


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
    get_db: Callable[[], Any], llm: HeadlineLlm, cfg: Any = None,
) -> Callable[[Job], Awaitable[None]]:
    async def handle(job: Job) -> None:
        lote_id = (job.payload or {}).get("lote_id")
        if not lote_id:
            raise DeadLetterError("payload sem lote_id")
        db = get_db()
        if db is None:
            raise RuntimeError("sem cliente admin do Supabase")  # retried by the worker policy
        await executar_lote(db, llm, str(lote_id), cfg=cfg)

    return handle


def _admin_db() -> Any:
    from app.dependencies import get_admin_client

    return get_admin_client()


handle_headline_gerar = make_handler(_admin_db, chat_headline_llm)


def register() -> None:
    """Register the ``headline.gerar`` handler + dead-letter reconciler (idempotent)."""
    geracao_jobs.register_handler(JOB_TYPE, handle_headline_gerar, on_dead_letter=reconciliar_dead_letter)


register()

__all__ = [
    "Estrutura",
    "HeadlineLlm",
    "JOB_TYPE",
    "Selecao",
    "chat_headline_llm",
    "executar_lote",
    "extrair_elementos",
    "handle_headline_gerar",
    "itens_oferecidos",
    "itens_por_slug",
    "make_handler",
    "montar_mensagem",
    "pool_de_estruturas",
    "normalizar",
    "pool_da_biblioteca",
    "reconciliar_dead_letter",
    "register",
    "selecionar_estruturas",
    "verificar_itens",
]
