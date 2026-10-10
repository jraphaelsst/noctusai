"""Biblioteca ingestion -- the three ``biblioteca.*`` job handlers (contract section 3.3, 9.2).

``biblioteca.sync_perfil`` reads a monitored profile through Business Discovery (the org's own
``provider='meta'`` Facebook-Login connection, official API only), upserts its posts, mirrors
thumbnails into the PRIVATE ``sw-biblioteca`` bucket and recomputes the viral metric.
``biblioteca.transcrever`` downloads a viral Reel (SSRF-safe) and hands it to the shared transcription
layer's LOW-PRIORITY library lane (``TranscricaoService.submit_sistema``). ``biblioteca.classificar``
asks an LLM for the structure of the post (hook, taxonomy, trigger, blueprint).

Every IO boundary is a port on :class:`IngestaoPorts` (Business Discovery adapter, safe fetcher, LLM,
transcription service, storage, queue), built from production seams by :func:`default_ports` and
replaced by Fakes in tests -- nothing here is monkeypatched. The handlers are plain functions of
``(ports, job)``.

Security (section 9): the post text is untrusted LLM input (see the prompt module); media is fetched
ONLY through ``safe_fetch`` with a CDN host allow-list and a byte cap; a Graph error text is never
stored for display -- the profile's ``erro_mensagem`` is our own pt-BR copy.

The ``biblioteca`` worker's claim gate (``geracao_jobs``) keeps all of this idle while
``biblioteca_ingestao_habilitada`` is off (default).
"""
from __future__ import annotations

import asyncio
import logging
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional, Sequence

from noctusai_lib.domain.jobs import DeadLetterError, Job, JobRepository
from noctusai_lib.domain.jobs.repo import RescheduleLater
from noctusai_lib.integrations.media.safe_fetch import (
    MAGIC_JPEG,
    MAGIC_MP4,
    MAGIC_PNG,
    MAGIC_WEBP,
    SafeFetchError,
    SafeFetcher,
    make_safe_fetcher,
)
from noctusai_lib.integrations.meta import (
    BUSINESS_DISCOVERY_MEDIA_FIELDS,
    BusinessDiscoveryNotFound,
    MetaGraphError,
)
from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.storage import StorageBackend

from app.modules.media_creation.prompts.biblioteca_classificador import (
    BIBLIOTECA_CLASSIFICADOR_SYSTEM_PROMPT,
    PROMPT_VERSAO,
    ClassificadorParseError,
    build_user_message,
    parse_classificador_output,
)
from app.modules.media_creation.services import geracao_jobs
from app.modules.media_creation.services.biblioteca_service import BUCKET, PERFIS, VIRAIS
from app.services.integration_account_service import IntegrationAccountNotFound

logger = logging.getLogger(__name__)

# ── tunables (contract 3.3; finite, named) ──────────────────────────────────
PAGE_LIMIT = 25
FIRST_SYNC_POSTS = 50
LATER_SYNC_MAX_POSTS = 100
REFRESH_WINDOW_DAYS = 30
METRIC_WINDOW_POSTS = 50
MIN_POSTS_FOR_MEDIAN = 10
VIEWS_COVERAGE = 0.8
VIRAL_MIN_AGE = timedelta(hours=48)
THUMB_MAX_BYTES = 2 * 1024 * 1024
VIDEO_MAX_BYTES = 15 * 1024 * 1024
RATE_LIMIT_DELAY_S = 900
SYNC_INTERVAL = timedelta(days=1)
THUMB_TYPES = ("image/jpeg", "image/png", "image/webp")
THUMB_MAGIC = (MAGIC_JPEG, MAGIC_PNG, MAGIC_WEBP)
VIDEO_TYPES = ("video/mp4",)
VIDEO_MAGIC = (MAGIC_MP4,)
_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
VIDEO_PRODUCT_TYPES = ("REELS",)

MSG_NAO_ENCONTRADO = (
    "Perfil não encontrado. Só é possível monitorar contas profissionais (comercial ou criador) e públicas."
)
MSG_SEM_CONTA = "Conecte uma conta do Instagram pelo login do Facebook (Meta) para monitorar perfis."
MSG_SEM_PERMISSAO = (
    "A conta Meta conectada não tem permissão para consultar outros perfis. Reconecte e autorize o acesso."
)
MSG_ERRO = "Não foi possível atualizar este perfil agora. Tente novamente mais tarde."

#: ``submit_sistema`` error codes -> the viral's terminal transcription state (contract 3.3 step 5).
_COD_GRANDE = {"arquivo_grande"}
_COD_LONGO = {"duracao_excedida", "reel_longo"}
_COD_SEM_ORCAMENTO = {
    "cota_diaria_org", "cota_diaria_usuario", "capacidade_diaria", "fila_cheia", "limite_usuario",
    # BE-3's library lane (reservar_transcricao_biblioteca)
    "fila_biblioteca_cheia", "cota_diaria_biblioteca_org", "capacidade_diaria_biblioteca",
}
_COD_ADIAR = {"transcricao_desativada", "transcricao_indisponivel"}

LlmCall = Callable[[str, str, Optional[str]], Awaitable[str]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── viral math (pure) ───────────────────────────────────────────────────────


def metrica(row: dict[str, Any], base: str) -> Optional[float]:
    """The profile metric of one post. ``engajamento`` is NULL when both counts are unknown
    (never 0 -- unknown is not zero)."""
    if base == "views":
        v = row.get("views")
        return float(v) if v is not None else None
    likes, comments = row.get("likes"), row.get("comments")
    if likes is None and comments is None:
        return None
    return float((likes or 0) + (comments or 0))


def escolher_base(window: Sequence[dict[str, Any]]) -> str:
    """``views`` when >= 80 % of the window serves them, else ``engajamento``."""
    if window and sum(1 for r in window if r.get("views") is not None) / len(window) >= VIEWS_COVERAGE:
        return "views"
    return "engajamento"


def calcular_virais(
    rows: Sequence[dict[str, Any]], *, ratio: float, now: datetime
) -> tuple[str, Optional[float], dict[str, tuple[Optional[float], bool]]]:
    """``(metrica_base, mediana, {row_id: (score_viral, e_viral)})`` for a profile.

    ``rows`` are every stored post of the profile. The window is the newest 50 by ``publicado_em``;
    the median needs >= 10 posts with a non-null metric (else it is None and nothing is viral).
    ``score = metric / max(median, 1)``; ``e_viral = score >= ratio`` and the post is >= 48 h old
    (metrics settle). Recomputed from scratch on every call."""
    ordered = sorted(rows, key=lambda r: _parse_dt(r.get("publicado_em")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    window = ordered[:METRIC_WINDOW_POSTS]
    base = escolher_base(window)
    values = [m for m in (metrica(r, base) for r in window) if m is not None]
    mediana = float(statistics.median(values)) if len(values) >= MIN_POSTS_FOR_MEDIAN else None
    out: dict[str, tuple[Optional[float], bool]] = {}
    for r in rows:
        m = metrica(r, base)
        if mediana is None or m is None:
            out[str(r["id"])] = (None, False)
            continue
        score = m / max(mediana, 1.0)
        published = _parse_dt(r.get("publicado_em"))
        old_enough = published is not None and now - published >= VIRAL_MIN_AGE
        out[str(r["id"])] = (round(score, 4), bool(score >= ratio and old_enough))
    return base, mediana, out


# ── ports ───────────────────────────────────────────────────────────────────


@dataclass
class IngestaoPorts:
    db: Any
    jobs: JobRepository
    storage: StorageBackend
    fetcher: SafeFetcher
    llm: LlmCall
    #: ``(account_id, org_id) -> MetaAdapter`` (raises IntegrationAccountNotFound / ValueError).
    adapter_factory: Callable[[str, str], Any]
    #: ``(org_id, user_id) -> object with async submit_sistema(data, contexto_ref, *, user_id)``.
    transcricao_factory: Callable[[Any, str, str], Any]
    cfg: Any
    clock: Callable[[], datetime] = _now


async def _chat_llm(system: str, user: str, org_id: Optional[str]) -> str:
    from noctusai_lib.integrations.llm import chat_completion

    from app.config import settings

    return await chat_completion(
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        provider="anthropic",
        model=settings.biblioteca_llm_model,
        org_id=org_id,
        temperature=0.0,
        cache=False,
    )


def _transcricao_service(db: Any, org_id: str, user_id: str) -> Any:
    from app.modules.transcricoes.deps import (
        get_kill_switch,
        get_transcricao_jobs,
        get_transcricao_storage,
        get_transcriber_factory,
    )
    from app.modules.transcricoes.service import TranscricaoService

    return TranscricaoService(
        db, org_id, user_id,
        storage=get_transcricao_storage(), jobs=get_transcricao_jobs(),
        transcriber_factory=get_transcriber_factory(), kill_switch=get_kill_switch(),
    )


def default_ports() -> IngestaoPorts:
    """Production wiring. Imported lazily so this module stays importable without a Supabase client."""
    from app.config import settings
    from app.dependencies import get_admin_client
    from app.modules.media_creation.deps import get_branding_storage
    from app.services.meta import get_meta_adapter_for_account

    db = get_admin_client()
    if db is None:
        raise RuntimeError("biblioteca: sem cliente admin do Supabase")
    return IngestaoPorts(
        db=db,
        jobs=geracao_jobs.make_jobs_repository(db),
        storage=get_branding_storage(),
        fetcher=make_safe_fetcher(real=True),
        llm=_chat_llm,
        adapter_factory=lambda account_id, org_id: get_meta_adapter_for_account(account_id, org_id),
        transcricao_factory=lambda org_id, user_id: _transcricao_service(db, org_id, user_id),
        cfg=settings,
    )


# ── small helpers ───────────────────────────────────────────────────────────


def _load_perfil(ports: IngestaoPorts, perfil_id: Optional[str]) -> dict[str, Any]:
    if not perfil_id:
        raise DeadLetterError("payload sem perfil_id")
    rows = ports.db.table(PERFIS).select("*").eq("id", str(perfil_id)).execute().data
    if not rows:
        raise DeadLetterError(f"perfil {perfil_id} inexistente")
    return rows[0]


def _load_viral(ports: IngestaoPorts, viral_id: Optional[str]) -> dict[str, Any]:
    if not viral_id:
        raise DeadLetterError("payload sem viral_id")
    rows = ports.db.table(VIRAIS).select("*").eq("id", str(viral_id)).execute().data
    if not rows:
        raise DeadLetterError(f"viral {viral_id} inexistente")
    return rows[0]


def _set_perfil(ports: IngestaoPorts, perfil_id: str, **fields: Any) -> None:
    fields["updated_at"] = _iso(ports.clock())
    ports.db.table(PERFIS).update(fields).eq("id", str(perfil_id)).execute()


def _set_viral(ports: IngestaoPorts, viral_id: str, **fields: Any) -> None:
    fields["updated_at"] = _iso(ports.clock())
    ports.db.table(VIRAIS).update(fields).eq("id", str(viral_id)).execute()


async def _fetch(ports: IngestaoPorts, url: str, **kw: Any):
    """``safe_fetch`` off the event loop (the fetcher is synchronous)."""
    return await asyncio.to_thread(ports.fetcher.fetch, url, **kw)


async def _put_image(ports: IngestaoPorts, url: str, key_base: str) -> Optional[str]:
    """Mirror an image into the private bucket. ``None`` (logged) on any fetch problem: a missing
    thumbnail never fails a sync."""
    try:
        res = await _fetch(
            ports, url, max_bytes=THUMB_MAX_BYTES, allowed_content_types=THUMB_TYPES, expect_magic=THUMB_MAGIC
        )
    except SafeFetchError as exc:
        logger.warning("biblioteca: imagem não baixada (%s)", exc.code)
        return None
    key = f"{key_base}.{_EXT.get(res.content_type, 'jpg')}"
    await ports.storage.put(bucket=BUCKET, key=key, data=res.data, content_type=res.content_type)
    return key


async def _enqueue(ports: IngestaoPorts, type_: str, payload: dict[str, Any], key: str) -> None:
    await ports.jobs.enqueue(type=type_, payload=payload, max_retries=2, dedupe_key=key)


def _day(ports: IngestaoPorts) -> str:
    return ports.clock().strftime("%Y%m%d")


# ── biblioteca.sync_perfil ──────────────────────────────────────────────────


def _is_video(m: Any) -> bool:
    return (m.media_product_type or "").upper() in VIDEO_PRODUCT_TYPES or (m.media_type or "").upper() == "VIDEO"


async def sync_perfil(ports: IngestaoPorts, job: Job) -> None:
    perfil = _load_perfil(ports, (job.payload or {}).get("perfil_id"))
    pid, org_id = str(perfil["id"]), str(perfil["org_id"])
    if perfil["status"] == "pausado":
        return
    now = ports.clock()

    conta = perfil.get("conta_descoberta_id") or _default_conta(ports, org_id)
    if not conta:
        _set_perfil(ports, pid, status="sem_conta", erro_codigo="sem_conta", erro_mensagem=MSG_SEM_CONTA)
        return
    try:
        adapter = ports.adapter_factory(str(conta), org_id)
        contas_ig = await asyncio.to_thread(adapter.list_instagram_accounts)
    except (IntegrationAccountNotFound, ValueError) as exc:  # gone, or not a provider='meta' row
        logger.info("biblioteca: conta de descoberta inválida perfil=%s (%s)", pid, type(exc).__name__)
        _set_perfil(ports, pid, status="sem_conta", erro_codigo="sem_conta", erro_mensagem=MSG_SEM_CONTA)
        return
    except MetaGraphError as exc:
        if _meta_blocked(ports, pid, exc):
            return
        raise
    if not contas_ig:
        _set_perfil(ports, pid, status="sem_conta", erro_codigo="sem_conta", erro_mensagem=MSG_SEM_CONTA)
        return
    caller_ig = contas_ig[0].id

    stored = list(
        iter_paged_rows(
            lambda s, e: ports.db.table(VIRAIS)
            .select("id,ig_media_id,thumbnail_path,publicado_em,likes,comments,views,score_viral,e_viral,"
                    "transcricao_status,classificacao_status")
            .eq("perfil_id", pid).order("id").range(s, e).execute().data
        )
    )
    by_media = {str(r["ig_media_id"]): r for r in stored}
    first = not stored
    cap = FIRST_SYNC_POSTS if first else LATER_SYNC_MAX_POSTS
    cutoff = now - timedelta(days=REFRESH_WINDOW_DAYS)

    header = None
    media: list[Any] = []
    after: Optional[str] = None
    try:
        while True:
            page = await asyncio.to_thread(
                adapter.get_business_discovery, caller_ig, perfil["handle"],
                fields=BUSINESS_DISCOVERY_MEDIA_FIELDS, after=after, limit=PAGE_LIMIT,
            )
            header = header or page
            media.extend(page.media)
            if len(media) >= cap or not page.next_cursor:
                break
            if not first and page.media:
                times = [t for t in (_parse_dt(m.timestamp) for m in page.media) if t]
                if any(str(m.id) in by_media for m in page.media) and times and min(times) < cutoff:
                    break
            after = page.next_cursor
    except BusinessDiscoveryNotFound:
        _set_perfil(ports, pid, status="nao_encontrado", erro_codigo="nao_encontrado", erro_mensagem=MSG_NAO_ENCONTRADO)
        return
    except MetaGraphError as exc:
        if _meta_blocked(ports, pid, exc):
            return
        logger.error("biblioteca: Business Discovery falhou perfil=%s code=%s", pid, exc.code)
        raise
    media = media[:cap]

    header_patch: dict[str, Any] = {}
    if header is not None:
        header_patch = {
            "ig_user_id": header.ig_user_id, "nome": header.name, "seguidores": header.followers_count,
            "media_count": header.media_count,
        }
        if header.profile_picture_url and not perfil.get("foto_path"):
            foto = await _put_image(ports, header.profile_picture_url, f"{org_id}/{pid}/foto")
            if foto:
                header_patch["foto_path"] = foto

    stamp = _iso(now)
    for m in media:
        base = {
            "permalink": m.permalink, "media_type": m.media_type, "media_product_type": m.media_product_type,
            "caption": (m.caption or "")[:5000] or None,
            "publicado_em": _iso(m.timestamp) if m.timestamp else None,
            "likes": m.like_count, "comments": m.comments_count, "views": m.views, "metricas_em": stamp,
        }
        existing = by_media.get(str(m.id))
        if existing is None:
            row = ports.db.table(VIRAIS).insert({
                **base, "org_id": org_id, "perfil_id": pid, "ig_media_id": str(m.id),
                "transcricao_status": "nao_aplicavel", "classificacao_status": "pendente", "e_viral": False,
            }).execute().data[0]
            thumb = m.thumbnail_url or (m.media_url if not _is_video(m) else None)
            if thumb:
                path = await _put_image(ports, thumb, f"{org_id}/{pid}/{row['id']}")
                if path:
                    _set_viral(ports, row["id"], thumbnail_path=path)
        else:
            _set_viral(ports, existing["id"], **base)
    media_urls = {str(m.id): m.media_url for m in media if _is_video(m)}

    # Recompute the viral metric over EVERYTHING stored for the profile.
    rows = list(
        iter_paged_rows(
            lambda s, e: ports.db.table(VIRAIS)
            .select("id,ig_media_id,publicado_em,likes,comments,views,score_viral,e_viral,"
                    "transcricao_status,classificacao_status")
            .eq("perfil_id", pid).order("id").range(s, e).execute().data
        )
    )
    base_metric, mediana, scores = calcular_virais(rows, ratio=float(ports.cfg.biblioteca_viral_ratio), now=now)
    day = _day(ports)
    for r in rows:
        score, viral = scores[str(r["id"])]
        was_viral = bool(r.get("e_viral"))
        prev_score = float(r["score_viral"]) if r.get("score_viral") is not None else None
        if score != prev_score or viral != was_viral:
            _set_viral(ports, r["id"], score_viral=score, e_viral=viral)
        if not viral:
            continue
        rid = str(r["id"])
        status_t, classif = r.get("transcricao_status"), r.get("classificacao_status")
        url = media_urls.get(str(r["ig_media_id"]))
        if status_t == "sem_orcamento":
            # Out of library budget earlier: retry with a fresh URL when this sync saw the post.
            if url:
                _set_viral(ports, rid, transcricao_status="pendente")
                await _enqueue(ports, "biblioteca.transcrever", {"viral_id": rid, "media_url": url},
                               f"transcrever:{rid}:{day}")
        elif not was_viral and classif == "pendente" and status_t not in ("pendente", "na_fila"):
            if url and status_t == "nao_aplicavel":
                _set_viral(ports, rid, transcricao_status="pendente")
                await _enqueue(ports, "biblioteca.transcrever", {"viral_id": rid, "media_url": url},
                               f"transcrever:{rid}:{day}")
            else:
                await _enqueue(ports, "biblioteca.classificar", {"viral_id": rid}, f"classificar:{rid}:{day}")
        elif classif == "falhou":
            await _enqueue(ports, "biblioteca.classificar", {"viral_id": rid}, f"classificar:{rid}:{day}")

    _set_perfil(
        ports, pid, status="ativo", erro_codigo=None, erro_mensagem=None, ultima_sync_em=stamp,
        proxima_sync_em=_iso(now + SYNC_INTERVAL), metrica_base=base_metric, mediana_metrica=mediana,
        conta_descoberta_id=str(conta), **header_patch,
    )


def _meta_blocked(ports: IngestaoPorts, pid: str, exc: MetaGraphError) -> bool:
    """Map a Graph refusal to the profile's state. True = handled (stop); rate limits reschedule
    (no retry spent); anything else is left to the caller (transient: retried)."""
    if exc.is_rate_limited:
        raise RescheduleLater(RATE_LIMIT_DELAY_S, "meta rate limit") from None
    if exc.is_auth_error or exc.is_permission or exc.requires_app_review:
        logger.warning("biblioteca: Meta recusou perfil=%s code=%s", pid, exc.code)
        _set_perfil(ports, pid, status="sem_conta", erro_codigo="sem_permissao", erro_mensagem=MSG_SEM_PERMISSAO)
        return True
    return False


def _default_conta(ports: IngestaoPorts, org_id: str) -> Optional[str]:
    rows = (
        ports.db.table("integration_accounts").select("id,is_default").eq("org_id", org_id)
        .eq("provider", "meta").eq("status", "validated").execute().data or []
    )
    rows.sort(key=lambda r: not r.get("is_default"))
    return str(rows[0]["id"]) if rows else None


# ── biblioteca.transcrever ──────────────────────────────────────────────────


async def transcrever(ports: IngestaoPorts, job: Job) -> None:
    payload = job.payload or {}
    viral = _load_viral(ports, payload.get("viral_id"))
    vid, org_id = str(viral["id"]), str(viral["org_id"])
    if viral["transcricao_status"] != "pendente":
        return  # already settled (a retried / duplicated job)
    day = _day(ports)

    async def terminal(status: str) -> None:
        _set_viral(ports, vid, transcricao_status=status)
        await _enqueue(ports, "biblioteca.classificar", {"viral_id": vid}, f"classificar:{vid}:{day}")

    url = payload.get("media_url")
    perfil = _load_perfil(ports, str(viral["perfil_id"]))
    user_id = perfil.get("created_by")
    if not url or not user_id:
        logger.warning("biblioteca: transcrição sem url/usuário viral=%s", vid)
        await terminal("falhou")
        return
    try:
        res = await _fetch(
            ports, str(url), max_bytes=VIDEO_MAX_BYTES, allowed_content_types=VIDEO_TYPES, expect_magic=VIDEO_MAGIC
        )
    except SafeFetchError as exc:
        if exc.code == "too_large":
            await terminal("grande_demais")
            return
        if exc.code in ("timeout", "network", "dns"):
            raise  # transient: the queue retries (2x) and the dead-letter reconciler settles it
        logger.warning("biblioteca: vídeo recusado viral=%s code=%s", vid, exc.code)
        await terminal("falhou")
        return

    from app.modules.transcricoes.errors import TranscricaoErro

    service = ports.transcricao_factory(org_id, str(user_id))
    try:
        out = await service.submit_sistema(res.data, vid, user_id=str(user_id))
    except TranscricaoErro as exc:
        codigo = str(getattr(exc, "codigo", "") or "")
        if codigo in _COD_GRANDE:
            await terminal("grande_demais")
        elif codigo in _COD_LONGO:
            await terminal("longa_demais")
        elif codigo in _COD_SEM_ORCAMENTO:
            await terminal("sem_orcamento")
        elif codigo in _COD_ADIAR:
            raise RescheduleLater(float(getattr(exc, "retry_after_s", None) or 900), codigo) from None
        else:
            logger.warning("biblioteca: transcrição recusada viral=%s codigo=%s", vid, codigo)
            await terminal("falhou")
        return
    patch: dict[str, Any] = {"transcricao_status": "na_fila", "transcricao_id": str(out["id"])}
    if out.get("duracao_s") is not None:
        patch["duracao_s"] = float(out["duracao_s"])
    _set_viral(ports, vid, **patch)


# ── biblioteca.classificar ──────────────────────────────────────────────────


async def classificar(ports: IngestaoPorts, job: Job) -> None:
    viral = _load_viral(ports, (job.payload or {}).get("viral_id"))
    vid, org_id = str(viral["id"]), str(viral["org_id"])
    if viral["classificacao_status"] == "concluida":
        return
    if viral.get("transcricao_status") in ("pendente", "na_fila"):
        raise RescheduleLater(300, "aguardando a transcrição")
    start_of_day = ports.clock().replace(hour=0, minute=0, second=0, microsecond=0)
    done_today = (
        ports.db.table(VIRAIS).select("id", count="exact").eq("org_id", org_id)
        .gte("classificado_em", _iso(start_of_day)).limit(1).execute()
    )
    count = done_today.count if getattr(done_today, "count", None) is not None else len(done_today.data or [])
    if count >= int(ports.cfg.biblioteca_classificacoes_dia_org):
        raise RescheduleLater(3600, "limite diário de classificações da organização")
    _set_viral(ports, vid, classificacao_status="processando")

    reply = await ports.llm(
        BIBLIOTECA_CLASSIFICADOR_SYSTEM_PROMPT,
        build_user_message(viral.get("caption"), viral.get("transcricao_texto")),
        org_id,
    )
    try:
        parsed = parse_classificador_output(reply)
    except ClassificadorParseError as exc:
        _set_viral(ports, vid, classificacao_status="falhou", classificacao_erro=str(exc)[:300])
        return
    _set_viral(
        ports, vid,
        classificacao_status="concluida", classificado_em=_iso(ports.clock()),
        classificacao_modelo=f"{ports.cfg.biblioteca_llm_model}|{PROMPT_VERSAO}",
        classificacao_erro=parsed.blueprint_erro, gancho=parsed.gancho, blueprint=parsed.blueprint,
        blueprint_slots=parsed.blueprint_slots, formato_ids=parsed.formato_ids, nicho_ids=parsed.nicho_ids,
        profissao_ids=parsed.profissao_ids, gatilho=parsed.gatilho,
    )


# ── dead-letter reconcilers (sync: the sweep calls them with the service-role client) ───


def reconcile_sync(db: Any, job: Job) -> None:
    pid = (job.payload or {}).get("perfil_id")
    if pid:
        db.table(PERFIS).update({"status": "erro", "erro_codigo": "falha_sync", "erro_mensagem": MSG_ERRO}).eq(
            "id", str(pid)).in_("status", ["aguardando", "ativo"]).execute()


def reconcile_classificar(db: Any, job: Job) -> None:
    vid = (job.payload or {}).get("viral_id")
    if vid:
        db.table(VIRAIS).update({"classificacao_status": "falhou", "classificacao_erro": "Falha ao classificar."}).eq(
            "id", str(vid)).in_("classificacao_status", ["pendente", "processando"]).execute()


def reconcile_transcrever(db: Any, job: Job) -> None:
    vid = (job.payload or {}).get("viral_id")
    if vid:
        db.table(VIRAIS).update({"transcricao_status": "falhou"}).eq("id", str(vid)).eq(
            "transcricao_status", "pendente").execute()


# ── registry wiring ─────────────────────────────────────────────────────────


async def handle_sync_perfil(job: Job) -> None:
    await sync_perfil(default_ports(), job)


async def handle_transcrever(job: Job) -> None:
    await transcrever(default_ports(), job)


async def handle_classificar(job: Job) -> None:
    await classificar(default_ports(), job)


def register_handlers() -> None:
    """Idempotent; called at import and again from ``media_creation.register()`` (the registry is
    process-global and a test may have cleared it)."""
    geracao_jobs.register_handler("biblioteca.sync_perfil", handle_sync_perfil, on_dead_letter=reconcile_sync)
    geracao_jobs.register_handler("biblioteca.transcrever", handle_transcrever, on_dead_letter=reconcile_transcrever)
    geracao_jobs.register_handler("biblioteca.classificar", handle_classificar, on_dead_letter=reconcile_classificar)


register_handlers()

__all__ = [
    "IngestaoPorts",
    "calcular_virais",
    "classificar",
    "default_ports",
    "escolher_base",
    "metrica",
    "reconcile_classificar",
    "reconcile_sync",
    "reconcile_transcrever",
    "register_handlers",
    "sync_perfil",
    "transcrever",
]
