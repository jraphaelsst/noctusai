"""Biblioteca ingestion SOURCE: Apify (default) vs Business Discovery -- the pure/IO helpers.

Owner decision 2026-11-04 (transitional, until Meta verifies noc): ``biblioteca_fonte`` selects where the
ingestion handler reads a monitored public profile. ``apify`` scrapes the PUBLIC profile through the seed
``noctusai_lib.integrations.apify`` port (no connected Meta account needed); ``business_discovery`` is the
original Meta path, kept intact. Contract: ``projects/core-studio-build/specs/apify-biblioteca-contract.md`` 2.

This module holds what is NOT the sync loop: the source switch reader, the platform ingestion-org reader, the
normalised post/header shape both sources feed (and the ONE row builder the sync and the admin add-by-link share), the
single-post fetch of add-by-link, the thumbnail mirror, the daily-cap accounting (``cs_apify_uso``) and the
``public.cost_ledger`` booking.

Since migration 351 the library is platform-wide: ingestion (credentials, caps, cost ledger, transcription lane) is keyed on
ONE org -- the NoctusAI org -- read by :func:`read_ingestao_org` (platform_settings first, then env / settings). It is a
visible, coded failure (``ingestao_sem_org_plataforma``) when missing, never a silent skip.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Optional

from noctusai_lib.integrations.apify import (
    ActorRunner,
    InstagramProfileScrape,
    InstagramPublicPost,
)
from noctusai_lib.integrations.apify.mapping import map_post
from noctusai_lib.integrations.media.safe_fetch import (
    MAGIC_JPEG,
    MAGIC_PNG,
    MAGIC_WEBP,
    SafeFetcher,
    SafeFetchError,
)
from noctusai_lib.integrations.storage import StorageBackend

logger = logging.getLogger(__name__)

FONTE_KEY = "biblioteca_fonte"
FONTE_APIFY = "apify"
FONTE_BUSINESS_DISCOVERY = "business_discovery"
FONTES = (FONTE_APIFY, FONTE_BUSINESS_DISCOVERY)
USO = "cs_apify_uso"
LEDGER_CATEGORY = "apify"
LEDGER_REFERENCE_TYPE = "biblioteca_perfil_sync"

ORG_KEY = "corestudio_biblioteca_org_id"
USER_KEY = "corestudio_biblioteca_user_id"
#: Storage prefix of every platform profile's blobs: ``sw-biblioteca/platform/{perfil}/...`` (legacy rows keep ``{org}/...``).
PREFIXO_PLATAFORMA = "platform"
CODIGO_SEM_ORG = "ingestao_sem_org_plataforma"
MSG_SEM_ORG = "A organização de ingestão da biblioteca não está configurada. Fale com a equipe NoctusAI."
ACTOR_INSTAGRAM = "apify/instagram-scraper"
LEDGER_REFERENCE_POST = "biblioteca_post_link"

MSG_SEM_CREDENCIAL = "Configure a chave do Apify em Configurações → Chaves de API."
MSG_SEM_ORCAMENTO = "Limite diário de leituras do Apify atingido para a sua organização. A sincronização retoma amanhã."
MSG_PRIVADO = "Este perfil é privado. Só é possível monitorar perfis públicos."
MSG_NAO_ENCONTRADO_APIFY = "Perfil não encontrado. Confira o @ — só é possível monitorar perfis públicos."


def read_biblioteca_fonte(
    resolver: Optional[Callable[[str], Optional[str]]] = None, default: str = FONTE_APIFY
) -> str:
    """``biblioteca_fonte``: platform_settings first, then env, then ``settings`` (default ``apify``).

    An unknown value is refused loudly (logged) and falls back to the default -- never to a silent
    third source."""
    if resolver is None:
        from noctusai_lib.config.credentials import resolve_credential as resolver
    try:
        value = str(resolver(FONTE_KEY) or "").strip().lower()
    except Exception:  # noqa: BLE001 - an unreadable switch falls back to the configured default
        logger.exception("biblioteca: could not read %s; using %s", FONTE_KEY, default)
        return default
    if not value:
        return default
    if value not in FONTES:
        logger.error("biblioteca: %s=%r is not one of %s; using %s", FONTE_KEY, value, FONTES, default)
        return default
    return value


def _read_uuid_setting(
    key: str, default: str, resolver: Optional[Callable[[str], Optional[str]]]
) -> Optional[str]:
    if resolver is None:
        from noctusai_lib.config.credentials import resolve_credential as resolver
    try:
        value = str(resolver(key) or "").strip() or str(default or "").strip()
    except Exception:  # noqa: BLE001 - an unreadable setting is "not configured" (fail closed), logged
        logger.exception("biblioteca: could not read %s", key)
        return None
    if not value:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        logger.error("biblioteca: %s is not a UUID; treated as not configured", key)
        return None


def read_ingestao_org(
    resolver: Optional[Callable[[str], Optional[str]]] = None, default: str = ""
) -> Optional[str]:
    """The platform ingestion org (``corestudio_biblioteca_org_id``): platform_settings first, then env, then ``default``
    (``settings``). ``None`` = not configured or not a UUID -> the caller fails VISIBLY with :data:`CODIGO_SEM_ORG`."""
    return _read_uuid_setting(ORG_KEY, default, resolver)


def read_ingestao_user(
    resolver: Optional[Callable[[str], Optional[str]]] = None, default: str = ""
) -> Optional[str]:
    """The system user the library transcription lane (``origem='biblioteca'``) is attributed to
    (``corestudio_biblioteca_user_id``, same chain as :func:`read_ingestao_org`)."""
    return _read_uuid_setting(USER_KEY, default, resolver)


# ── normalised shapes (what the sync loop consumes, whichever the source) ───


@dataclass(frozen=True)
class Cabecalho:
    ig_user_id: Optional[str]
    name: Optional[str]
    followers_count: Optional[int]
    media_count: Optional[int]
    profile_picture_url: Optional[str]


@dataclass(frozen=True)
class Midia:
    """Same attribute names as ``BusinessDiscoveryMedia`` plus the Apify-only video/duration fields."""

    id: str
    permalink: Optional[str]
    media_type: Optional[str]
    media_product_type: Optional[str]
    caption: Optional[str]
    timestamp: Optional[datetime]
    like_count: Optional[int]
    comments_count: Optional[int]
    views: Optional[int]
    thumbnail_url: Optional[str]
    media_url: Optional[str]
    duracao_s: Optional[float] = None
    from_apify: bool = True
    shortcode: Optional[str] = None


def _midia(p: InstagramPublicPost) -> Midia:
    reel = (p.product_type or "").lower() == "clips"
    return Midia(
        id=p.id, permalink=p.permalink, media_type=p.media_type,
        media_product_type="REELS" if reel else "FEED",
        caption=p.caption, timestamp=p.timestamp, like_count=p.likes, comments_count=p.comments, views=p.views,
        thumbnail_url=p.display_url, media_url=p.video_url, duracao_s=p.duration_s, shortcode=p.shortcode,
    )


def normalizar(scrape: InstagramProfileScrape) -> tuple[Cabecalho, list[Midia]]:
    pr = scrape.profile
    head = Cabecalho(
        ig_user_id=pr.external_id, name=pr.full_name, followers_count=pr.followers_count,
        media_count=pr.posts_count, profile_picture_url=pr.profile_pic_url,
    )
    return head, [_midia(p) for p in scrape.posts]


# ── the ONE row builder (sync and admin add-by-link) ─────────────────────────


VIDEO_PRODUCT_TYPES = ("REELS",)


def e_video(m: Any) -> bool:
    return (m.media_product_type or "").upper() in VIDEO_PRODUCT_TYPES or (m.media_type or "").upper() == "VIDEO"


def campos_midia(m: Any, stamp: str) -> dict[str, Any]:
    """The ``cs_virais`` columns one fetched post fills -- shared by the profile sync and the admin add-by-link so a
    manually added video is normalised EXACTLY like a synced one."""
    base: dict[str, Any] = {
        "permalink": m.permalink, "media_type": m.media_type, "media_product_type": m.media_product_type,
        "caption": (m.caption or "")[:5000] or None,
        "publicado_em": m.timestamp.isoformat() if m.timestamp else None,
        "likes": m.like_count, "comments": m.comments_count, "views": m.views, "metricas_em": stamp,
    }
    if getattr(m, "shortcode", None):
        base["ig_shortcode"] = m.shortcode
    if getattr(m, "from_apify", False):
        base["duracao_s"] = m.duracao_s
        if m.media_url and e_video(m):
            base["video_url"], base["video_url_em"] = m.media_url, stamp
    return base


THUMB_MAX_BYTES = 2 * 1024 * 1024
THUMB_TYPES = ("image/jpeg", "image/png", "image/webp")
THUMB_MAGIC = (MAGIC_JPEG, MAGIC_PNG, MAGIC_WEBP)
_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


async def espelhar_imagem(
    fetcher: SafeFetcher, storage: StorageBackend, bucket: str, url: str, key_base: str
) -> Optional[str]:
    """Mirror an image into the private bucket (CDN host allow-list + byte cap via ``safe_fetch``). ``None`` (logged) on any
    fetch problem: a missing thumbnail never fails a sync or an add-by-link."""
    try:
        res = await asyncio.to_thread(
            fetcher.fetch, url, max_bytes=THUMB_MAX_BYTES, allowed_content_types=THUMB_TYPES, expect_magic=THUMB_MAGIC
        )
    except SafeFetchError as exc:
        logger.warning("biblioteca: imagem não baixada (%s)", exc.code)
        return None
    key = f"{key_base}.{_EXT.get(res.content_type, 'jpg')}"
    await storage.put(bucket=bucket, key=key, data=res.data, content_type=res.content_type)
    return key


# ── single post by link (admin add-by-link) ─────────────────────────────────


class PostNaoEncontrado(Exception):
    """The source returned no post for the link (deleted, private, or not served)."""


@dataclass(frozen=True)
class PostBuscado:
    midia: Midia
    owner: str
    results: int
    usd: Optional[Decimal]
    run_id: Optional[str]


def buscar_post(runner: ActorRunner, *, shortcode: str, url: str, timeout_s: float = 120) -> PostBuscado:
    """Fetch ONE public post through the generic Apify actor runner (the seed ``ActorRunner`` port: Fake + Real + factory).

    ``url`` is the RE-COMPOSED canonical link (never the pasted string). The actor is the same
    ``apify/instagram-scraper`` the profile sync uses, in ``directUrls`` mode with a post URL and ``resultsLimit=1``. Errors
    are the seed's (``ApifyNotConfigured`` / ``ApifyRateLimited`` / ``ApifyRunFailed``) and are mapped by the caller.
    An item whose ``shortCode`` is not the requested one is NOT accepted (the actor must answer for THIS post)."""
    res = runner.run_actor(
        ACTOR_INSTAGRAM,
        {"directUrls": [url], "resultsType": "posts", "resultsLimit": 1, "addParentData": False},
        timeout_s=timeout_s, max_items=1,
    )
    for raw in res.items:
        if raw.get("error") or str(raw.get("shortCode") or "") != shortcode:
            continue
        post = map_post(raw, str(raw.get("ownerUsername") or ""))  # a malformed item raises ApifyRunFailed
        if not post.owner_username:
            raise PostNaoEncontrado(shortcode)
        return PostBuscado(
            midia=_midia(post), owner=post.owner_username.strip().lower(), results=res.usage.results,
            usd=res.usage.usd, run_id=res.usage.run_id,
        )
    raise PostNaoEncontrado(shortcode)


# ── daily cap + cost ─────────────────────────────────────────────────────────


def resultados_hoje(db: Any, org_id: str, now: datetime) -> int:
    """Apify results billed to ``org_id`` since 00:00 UTC of ``now``'s day."""
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    from noctusai_lib.integrations.persistence import iter_paged_rows

    rows = iter_paged_rows(
        lambda s, e: db.table(USO).select("resultados").eq("org_id", org_id).gte("criado_em", start)
        .order("criado_em").range(s, e).execute().data
    )
    return sum(int(r.get("resultados") or 0) for r in rows)


def registrar_uso(
    db: Any, ledger_db: Any, *, org_id: str, perfil_id: Optional[str], results: int, usd: Optional[Decimal],
    run_id: Optional[str], now: datetime, step: str = "biblioteca.sync_perfil",
    reference_type: str = LEDGER_REFERENCE_TYPE,
) -> None:
    """Record one scrape: the cap row (always) and a ``public.cost_ledger`` row (USD, ``fx_pending``)
    when the run exposed its cost. Cost booking is best-effort -- it never fails a sync -- and an
    unknown cost is logged, never invented."""
    db.table(USO).insert({
        "org_id": org_id, "perfil_id": perfil_id, "resultados": int(results),
        "usd": str(usd) if usd is not None else None, "run_id": run_id, "criado_em": now.isoformat(),
    }).execute()
    if usd is None:
        logger.warning("biblioteca: apify run sem custo exposto perfil=%s results=%s; cost_ledger não gravado",
                       perfil_id, results)
        return
    if ledger_db is None:
        logger.warning("biblioteca: cost_ledger indisponível perfil=%s; custo apify não gravado", perfil_id)
        return
    try:
        ledger_db.table("cost_ledger").insert({
            "org_id": org_id, "category": LEDGER_CATEGORY, "step": step,
            "reference_type": reference_type, "reference_id": str(perfil_id) if perfil_id else None,
            "amount_native": str(usd), "currency": "USD", "fx_pending": True,
        }).execute()
    except Exception as exc:  # noqa: BLE001 - booking a cost must never break the sync
        logger.warning("biblioteca: cost_ledger insert falhou perfil=%s (%s)", perfil_id, type(exc).__name__)
