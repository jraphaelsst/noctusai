"""The ONE ``ViralCard`` presenter for Geração (dashboard, headlines, roteiros).

Thumbnails live in the PRIVATE ``sw-biblioteca`` bucket (``deps.BIBLIOTECA_BUCKET``) and are only ever
served as short-TTL signed URLs. A missing / unsignable thumbnail (or no storage injected) yields
``thumbnail_url=None`` and never fails the page. Library endpoints build their richer card in
``biblioteca_service`` (filter-aware ``trecho``); this is the compact shape the Geração surfaces share.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from noctusai_lib.integrations.persistence.table_reads import batched
from noctusai_lib.integrations.storage import StorageBackend

from app.modules.media_creation.deps import BIBLIOTECA_BUCKET, SIGNED_URL_TTL_SECONDS

logger = logging.getLogger(__name__)

VIRAIS = "cs_virais"
PERFIS = "cs_perfis_monitorados"
TRECHO_CHARS = 140
VIRAL_CARD_COLS = (
    "id,codigo,perfil_id,permalink,publicado_em,views,likes,comments,duracao_s,score_viral,e_viral,"
    "gancho,caption,thumbnail_path"
)


async def sign_thumbnail(storage: Optional[StorageBackend], path: Optional[str]) -> Optional[str]:
    if not path or storage is None:
        return None
    try:
        return await storage.signed_url(
            bucket=BIBLIOTECA_BUCKET, key=path, expires_in_seconds=SIGNED_URL_TTL_SECONDS
        )
    except Exception as exc:  # noqa: BLE001 - a missing thumbnail never fails a page
        logger.warning("viral_card: thumbnail %s não assinada: %s", path, exc)
        return None


async def present_viral_card(
    row: dict[str, Any], handle: Optional[str], storage: Optional[StorageBackend]
) -> dict[str, Any]:
    trecho = " ".join((row.get("gancho") or row.get("caption") or "").split())
    return {
        "id": str(row["id"]),
        "codigo": row.get("codigo"),
        "perfil": {"id": str(row.get("perfil_id")), "handle": handle or ""},
        "thumbnail_url": await sign_thumbnail(storage, row.get("thumbnail_path")),
        "permalink": row.get("permalink") or "",
        "publicado_em": row.get("publicado_em"),
        "views": row.get("views"),
        "likes": row.get("likes"),
        "comments": row.get("comments"),
        "duracao_s": row.get("duracao_s"),
        "score_viral": row.get("score_viral"),
        "e_viral": bool(row.get("e_viral")),
        "trecho": trecho[:TRECHO_CHARS] or None,
    }


async def viral_cards(
    db: Any, org_id: str, storage: Optional[StorageBackend], viral_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """``{viral_id: ViralCard}`` for the org's virais (unknown / foreign ids are simply absent)."""
    ids = sorted({str(i) for i in viral_ids if i})
    if not ids:
        return {}
    rows: list[dict[str, Any]] = []
    for chunk in batched(ids):
        rows.extend(
            db.table(VIRAIS).select(VIRAL_CARD_COLS).eq("org_id", org_id).in_("id", chunk).execute().data or []
        )
    handles: dict[str, str] = {}
    for chunk in batched(sorted({str(r["perfil_id"]) for r in rows})):
        for p in db.table(PERFIS).select("id,handle").eq("org_id", org_id).in_("id", chunk).execute().data or []:
            handles[str(p["id"])] = p["handle"]
    return {str(r["id"]): await present_viral_card(r, handles.get(str(r["perfil_id"])), storage) for r in rows}
