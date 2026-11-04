"""Biblioteca ingestion SOURCE: Apify (default) vs Business Discovery -- the pure/IO helpers.

Owner decision 2026-11-04 (transitional, until Meta verifies noc): ``biblioteca_fonte`` selects where the
ingestion handler reads a monitored public profile. ``apify`` scrapes the PUBLIC profile through the seed
``noctusai_lib.integrations.apify`` port (no connected Meta account needed); ``business_discovery`` is the
original Meta path, kept intact. Contract: ``projects/core-studio-build/specs/apify-biblioteca-contract.md`` 2.

This module holds what is NOT the sync loop: the source switch reader, the normalised post/header shape
both sources feed, the daily-cap accounting (``cs_apify_uso``) and the ``public.cost_ledger`` booking.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Optional

from noctusai_lib.integrations.apify import InstagramProfileScrape, InstagramPublicPost

logger = logging.getLogger(__name__)

FONTE_KEY = "biblioteca_fonte"
FONTE_APIFY = "apify"
FONTE_BUSINESS_DISCOVERY = "business_discovery"
FONTES = (FONTE_APIFY, FONTE_BUSINESS_DISCOVERY)
USO = "cs_apify_uso"
LEDGER_CATEGORY = "apify"
LEDGER_REFERENCE_TYPE = "biblioteca_perfil_sync"

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


def _midia(p: InstagramPublicPost) -> Midia:
    reel = (p.product_type or "").lower() == "clips"
    return Midia(
        id=p.id, permalink=p.permalink, media_type=p.media_type,
        media_product_type="REELS" if reel else "FEED",
        caption=p.caption, timestamp=p.timestamp, like_count=p.likes, comments_count=p.comments, views=p.views,
        thumbnail_url=p.display_url, media_url=p.video_url, duracao_s=p.duration_s,
    )


def normalizar(scrape: InstagramProfileScrape) -> tuple[Cabecalho, list[Midia]]:
    pr = scrape.profile
    head = Cabecalho(
        ig_user_id=pr.external_id, name=pr.full_name, followers_count=pr.followers_count,
        media_count=pr.posts_count, profile_picture_url=pr.profile_pic_url,
    )
    return head, [_midia(p) for p in scrape.posts]


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
    db: Any, ledger_db: Any, *, org_id: str, perfil_id: str, results: int, usd: Optional[Decimal],
    run_id: Optional[str], now: datetime,
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
            "org_id": org_id, "category": LEDGER_CATEGORY, "step": "biblioteca.sync_perfil",
            "reference_type": LEDGER_REFERENCE_TYPE, "reference_id": str(perfil_id),
            "amount_native": str(usd), "currency": "USD", "fx_pending": True,
        }).execute()
    except Exception as exc:  # noqa: BLE001 - booking a cost must never break the sync
        logger.warning("biblioteca: cost_ledger insert falhou perfil=%s (%s)", perfil_id, type(exc).__name__)
