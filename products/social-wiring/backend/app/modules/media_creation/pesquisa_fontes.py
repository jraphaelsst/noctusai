"""Pesquisa wave 2 — extraction sources (the ``FonteExtracao`` seam).

Three sources, all marca-scoped and read-only: Instagram media of the marca's
connected accounts, YouTube videos/shorts of its connected channels, and posts
created in Criação de mídia (``mc_posts``). Contract:
projects/core-studio/specs/pesquisa-wave2-contract.md sections 2.1 and 2.5.

Rules encoded here (each has a test):

* Marca scope goes through ``integration_accounts.marca_id`` /
  ``mc_brand_kits.marca_id`` — another marca's or org's data is absent.
* ``plays`` is ``None`` when the platform did not report views, never 0.
* Instagram paging REUSES ``IgInsightsRepository`` (keyset cursor included);
  the same cursor format serves the other two sources.
* An ``mc_post`` published to a connected Instagram account of the marca is
  left out of the ``mc_post`` list: it is the same real post, reachable through
  Instagram with real metrics, and its created-post text is appended there.
* A post whose assembled text is under :data:`MIN_TEXTO_CHARS` is
  ``analisavel=False`` (no LLM call is spent on it).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable, Optional, Protocol
from uuid import UUID

from noctusai_lib.integrations.persistence import iter_paged_rows

from app.modules.instagram.repository import (
    INSTAGRAM_PROVIDER,
    IgInsightsRepository,
    InvalidCursor,
    as_bigint,
    decode_cursor,
    encode_cursor,
    utc_iso,
)

logger = logging.getLogger(__name__)

MIN_TEXTO_CHARS = 20
#: Hard cap on one assembled post text (the config knob
#: ``pesquisa_extracao_texto_max_chars`` is passed in by the caller).
TEXTO_MAX_CHARS_DEFAULT = 6000
YT_DESCRIPTION_MAX_CHARS = 2000
YOUTUBE_PROVIDER = "youtube"
_IN_BATCH = 100
_PAGE = 500

Ref = tuple[Optional[str], str]


@dataclass(frozen=True)
class PostFonte:
    kind: str
    account_id: Optional[str]
    id: str
    url: Optional[str]
    thumbnail_url: Optional[str]
    published_at: Optional[str]
    texto: str
    analisavel: bool
    plays: Optional[int]
    likes: Optional[int]
    comments: Optional[int]
    extra: dict = field(default_factory=dict)


class FonteExtracao(Protocol):
    kind: str

    def contas(self, org_id: str, marca_id: str) -> list[dict]: ...

    def listar(
        self, org_id: str, marca_id: str, *, account_id: Optional[str],
        cursor: Optional[str], limit: int, busca: Optional[str],
    ) -> tuple[list[PostFonte], Optional[str]]: ...

    def obter(
        self, org_id: str, marca_id: str, refs: list[Ref],
    ) -> dict[Ref, PostFonte]: ...


# ── helpers ──────────────────────────────────────────────────────────────

def _batched(values: list[str], size: int = _IN_BATCH) -> Iterable[list[str]]:
    for i in range(0, len(values), size):
        yield values[i : i + size]


def _join_text(parts: Iterable[Optional[str]], max_chars: int) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        t = (p or "").strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return "\n\n".join(out)[:max_chars].strip()


def _analisavel(texto: str) -> bool:
    return len(texto.strip()) >= MIN_TEXTO_CHARS


def _iso(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, datetime):
        return utc_iso(value)
    try:
        return utc_iso(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        return str(value)


def _as_uuid(value: Optional[str]) -> Optional[UUID]:
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


def _matches(texto: str, busca: Optional[str]) -> bool:
    return not busca or busca.strip().casefold() in texto.casefold()


def _collect_page(
    fetch: Callable[[Optional[str], int], tuple[list[dict], Optional[str]]],
    to_post: Callable[[dict], Optional[PostFonte]],
    cursor_of: Callable[[dict], str],
    *, cursor: Optional[str], limit: int, busca: Optional[str],
) -> tuple[list[PostFonte], Optional[str]]:
    """Keyset page with post-filtering (overlap exclusion, ``busca``).

    Pulls raw pages until ``limit`` accepted posts plus one lookahead exist or
    the source is exhausted; ``next_cursor`` is the cursor of the last RETURNED
    row, so filtered-out rows never skip or repeat a post.
    """
    accepted: list[tuple[PostFonte, str]] = []
    cur = cursor
    while True:
        rows, nxt = fetch(cur, limit + 1)
        for row in rows:
            post = to_post(row)
            if post is not None and _matches(post.texto, busca):
                accepted.append((post, cursor_of(row)))
        if len(accepted) > limit or not nxt or not rows:
            break
        cur = cursor_of(rows[-1])
    if len(accepted) > limit:
        return [p for p, _ in accepted[:limit]], accepted[limit - 1][1]
    return [p for p, _ in accepted], None


# ── mc_posts shared lookups (used by Instagram AND mc_post sources) ──────

def _kit_ids(db, org_id: str, marca_id: str) -> list[str]:
    rows = (
        db.table("mc_brand_kits").select("id")
        .eq("org_id", org_id).eq("marca_id", marca_id).execute().data
    ) or []
    return [r["id"] for r in rows]


def _published_posts(db, org_id: str, marca_id: str) -> list[dict]:
    """The marca's mc_posts that were published to a platform media id."""
    kits = _kit_ids(db, org_id, marca_id)
    if not kits:
        return []
    out: list[dict] = []
    for chunk in _batched(kits):
        def page(start: int, end: int, _c=chunk):
            return (
                db.table("mc_posts").select("id, published_media_id")
                .eq("org_id", org_id).in_("brand_kit_id", _c)
                .not_.is_("published_media_id", "null")
                .order("id").range(start, end).execute().data
            )
        out.extend(iter_paged_rows(page, page_size=_PAGE, label="mc_posts published"))
    return out


def _mc_text_parts(db, org_id: str, posts: list[dict]) -> dict[str, list[str]]:
    """``post_id -> [title, idea?, key_message?, caption, slide headline/body...]``."""
    parts: dict[str, list[str]] = {}
    ids = [p["id"] for p in posts]
    for p in posts:
        parts[p["id"]] = [p.get("title"), p.get("idea"), p.get("key_message"), p.get("copy_caption")]
    for chunk in _batched(ids):
        slides = (
            db.table("mc_post_slides").select("post_id, slide_n, headline, body")
            .eq("org_id", org_id).in_("post_id", chunk).order("slide_n").execute().data
        ) or []
        for s in sorted(slides, key=lambda r: (r.get("slide_n") or 0)):
            parts[s["post_id"]].extend([s.get("headline"), s.get("body")])
    return parts


_MC_COLUMNS = (
    "id, title, idea, key_message, copy_caption, published_media_id, "
    "published_permalink, published_at, created_at"
)


# ── Instagram ────────────────────────────────────────────────────────────

class InstagramFonte:
    kind = "instagram_media"

    def __init__(self, db, texto_max_chars: int = TEXTO_MAX_CHARS_DEFAULT) -> None:
        self._db = db
        self._repo = IgInsightsRepository(db)
        self._max = texto_max_chars

    def _accounts(self, org_id: str, marca_id: str) -> list[dict]:
        return (
            self._db.table("integration_accounts")
            .select("id, account_label, last_synced_at")
            .eq("org_id", org_id).eq("marca_id", marca_id)
            .eq("provider", INSTAGRAM_PROVIDER).eq("status", "validated")
            .execute().data
        ) or []

    def _account_ok(self, org_id: str, marca_id: str, account_id: Optional[str]) -> bool:
        return any(a["id"] == account_id for a in self._accounts(org_id, marca_id))

    def contas(self, org_id: str, marca_id: str) -> list[dict]:
        out = []
        for a in self._accounts(org_id, marca_id):
            resp = (
                self._db.table("ig_media").select("ig_media_id", count="exact")
                .eq("org_id", org_id).eq("account_id", a["id"]).limit(1).execute()
            )
            label = a.get("account_label") or ""
            out.append({
                "account_id": a["id"],
                "label": f"@{label.lstrip('@')}" if label else "Instagram",
                "total_posts": resp.count or 0,
                "last_synced_at": a.get("last_synced_at"),
            })
        return out

    def _linked_text(self, org_id: str, marca_id: str, media_ids: list[str]) -> dict[str, list[str]]:
        """``ig_media_id -> mc_post text parts`` for posts of THIS marca."""
        kits = _kit_ids(self._db, org_id, marca_id)
        if not kits or not media_ids:
            return {}
        posts: list[dict] = []
        for chunk in _batched(media_ids):
            for kit_chunk in _batched(kits):
                posts.extend(
                    self._db.table("mc_posts").select(_MC_COLUMNS)
                    .eq("org_id", org_id).in_("brand_kit_id", kit_chunk)
                    .in_("published_media_id", chunk).execute().data or []
                )
        parts = _mc_text_parts(self._db, org_id, posts)
        return {p["published_media_id"]: parts[p["id"]] for p in posts}

    def _to_post(self, row: dict, account_id: str, linked: dict[str, list[str]]) -> PostFonte:
        metrics = row.get("latest_metrics") or {}
        media_id = str(row["ig_media_id"])
        texto = _join_text([row.get("caption"), *linked.get(media_id, [])], self._max)
        mtype = row.get("media_type")
        return PostFonte(
            kind=self.kind, account_id=account_id, id=media_id,
            url=row.get("permalink"),
            thumbnail_url=row.get("thumbnail_url") or (row.get("media_url") if mtype == "IMAGE" else None),
            published_at=_iso(row.get("published_at")), texto=texto,
            analisavel=_analisavel(texto),
            plays=as_bigint(metrics.get("views")),  # NULL when Meta did not return it
            likes=as_bigint(row.get("like_count")),
            comments=as_bigint(row.get("comments_count")),
            extra={
                "media_product_type": row.get("media_product_type"),
                "media_type": mtype,
                "reach": as_bigint(metrics.get("reach")),
                "shares": as_bigint(metrics.get("shares")),
                "saved": as_bigint(metrics.get("saved")),
                "latest_snapshot_date": row.get("latest_snapshot_date"),
            },
        )

    def listar(self, org_id, marca_id, *, account_id, cursor, limit, busca):
        acc = _as_uuid(account_id)
        if acc is None or not self._account_ok(org_id, marca_id, account_id):
            return [], None
        org = UUID(str(org_id))
        linked_cache: dict[str, list[str]] = {}

        def fetch(cur, n):
            rows, nxt = self._repo.list_media_page(acc, org, limit=n, cursor=cur)
            linked_cache.update(self._linked_text(org_id, marca_id, [str(r["ig_media_id"]) for r in rows]))
            return rows, nxt

        return _collect_page(
            fetch, lambda r: self._to_post(r, account_id, linked_cache),
            lambda r: encode_cursor(_iso(r["published_at"]), str(r["ig_media_id"])),
            cursor=cursor, limit=limit, busca=busca,
        )

    def obter(self, org_id, marca_id, refs):
        out: dict[Ref, PostFonte] = {}
        valid = {a["id"] for a in self._accounts(org_id, marca_id)}
        rows: list[tuple[str, dict]] = []
        for account_id, media_id in refs:
            acc = _as_uuid(account_id)
            if acc is None or account_id not in valid:
                continue
            row = self._repo.get_media(acc, UUID(str(org_id)), str(media_id))
            if row:
                rows.append((account_id, row))
        linked = self._linked_text(org_id, marca_id, [str(r["ig_media_id"]) for _, r in rows])
        for account_id, row in rows:
            out[(account_id, str(row["ig_media_id"]))] = self._to_post(row, account_id, linked)
        return out


# ── YouTube ──────────────────────────────────────────────────────────────

_YT_COLUMNS = (
    "youtube_video_id, title, description, tags, thumbnail_url, published_at, "
    "view_count, like_count, comment_count"
)


class YoutubeFonte:
    kind = "youtube_video"

    def __init__(self, db, texto_max_chars: int = TEXTO_MAX_CHARS_DEFAULT) -> None:
        self._db = db
        self._max = texto_max_chars

    def _accounts(self, org_id: str, marca_id: str) -> list[dict]:
        return (
            self._db.table("integration_accounts")
            .select("id, account_label, last_synced_at")
            .eq("org_id", org_id).eq("marca_id", marca_id)
            .eq("provider", YOUTUBE_PROVIDER).execute().data
        ) or []

    def _account_ok(self, org_id, marca_id, account_id) -> bool:
        return any(a["id"] == account_id for a in self._accounts(org_id, marca_id))

    def contas(self, org_id, marca_id):
        out = []
        for a in self._accounts(org_id, marca_id):
            ids: set[str] = set()
            for table in ("youtube_videos", "youtube_shorts"):
                def page(start, end, _t=table, _a=a["id"]):
                    return (
                        self._db.table(_t).select("youtube_video_id")
                        .eq("org_id", org_id).eq("account_id", _a)
                        .order("youtube_video_id").range(start, end).execute().data
                    )
                ids.update(
                    r["youtube_video_id"]
                    for r in iter_paged_rows(page, page_size=_PAGE, id_key="youtube_video_id",
                                             label=f"{table} ids")
                )
            out.append({
                "account_id": a["id"],
                "label": a.get("account_label") or "YouTube",
                "total_posts": len(ids),
                "last_synced_at": a.get("last_synced_at"),
            })
        return out

    def _to_post(self, row: dict, account_id: str, is_short: bool) -> PostFonte:
        vid = row["youtube_video_id"]
        tags = row.get("tags") or []
        texto = _join_text(
            [row.get("title"), (row.get("description") or "")[:YT_DESCRIPTION_MAX_CHARS],
             ("Tags: " + ", ".join(tags)) if tags else None],
            self._max,
        )
        return PostFonte(
            kind=self.kind, account_id=account_id, id=vid,
            url=f"https://youtube.com/shorts/{vid}" if is_short else f"https://youtube.com/watch?v={vid}",
            thumbnail_url=row.get("thumbnail_url"), published_at=_iso(row.get("published_at")),
            texto=texto, analisavel=_analisavel(texto),
            plays=as_bigint(row.get("view_count")), likes=as_bigint(row.get("like_count")),
            comments=as_bigint(row.get("comment_count")), extra={"is_short": is_short},
        )

    def _merge(self, videos: list[dict], shorts: list[dict], account_id: str) -> list[tuple[dict, bool]]:
        merged: dict[str, tuple[dict, bool]] = {r["youtube_video_id"]: (r, False) for r in videos}
        for r in shorts:  # the shorts row wins and sets is_short
            merged[r["youtube_video_id"]] = (r, True)
        return sorted(
            merged.values(),
            key=lambda t: (_iso(t[0].get("published_at")) or "", t[0]["youtube_video_id"]),
            reverse=True,
        )

    def listar(self, org_id, marca_id, *, account_id, cursor, limit, busca):
        if _as_uuid(account_id) is None or not self._account_ok(org_id, marca_id, account_id):
            return [], None

        def fetch(cur, n):
            per_table = []
            for table in ("youtube_videos", "youtube_shorts"):
                q = (
                    self._db.table(table).select(_YT_COLUMNS)
                    .eq("org_id", org_id).eq("account_id", account_id)
                )
                if cur:
                    ts, vid = decode_cursor(cur)
                    q = q.or_(
                        f'published_at.lt."{ts}",'
                        f'and(published_at.eq."{ts}",youtube_video_id.lt."{vid}")'
                    )
                per_table.append(
                    q.order("published_at", desc=True).order("youtube_video_id", desc=True)
                    .limit(n).execute().data or []
                )
            merged = self._merge(per_table[0], per_table[1], account_id)
            rows = [dict(r, _is_short=s) for r, s in merged[:n]]
            nxt = encode_cursor(_iso(rows[-1]["published_at"]), rows[-1]["youtube_video_id"]) if len(merged) >= n and rows else None
            return rows, nxt

        return _collect_page(
            fetch, lambda r: self._to_post(r, account_id, r["_is_short"]),
            lambda r: encode_cursor(_iso(r["published_at"]), r["youtube_video_id"]),
            cursor=cursor, limit=limit, busca=busca,
        )

    def obter(self, org_id, marca_id, refs):
        out: dict[Ref, PostFonte] = {}
        valid = {a["id"] for a in self._accounts(org_id, marca_id)}
        by_account: dict[str, list[str]] = {}
        for account_id, vid in refs:
            if account_id in valid:
                by_account.setdefault(account_id, []).append(str(vid))
        for account_id, vids in by_account.items():
            videos: list[dict] = []
            shorts: list[dict] = []
            for chunk in _batched(vids):
                for table, bucket in (("youtube_videos", videos), ("youtube_shorts", shorts)):
                    bucket.extend(
                        self._db.table(table).select(_YT_COLUMNS)
                        .eq("org_id", org_id).eq("account_id", account_id)
                        .in_("youtube_video_id", chunk).execute().data or []
                    )
            for row, is_short in self._merge(videos, shorts, account_id):
                out[(account_id, row["youtube_video_id"])] = self._to_post(row, account_id, is_short)
        return out


# ── Posts criados (mc_posts) ─────────────────────────────────────────────

class McPostFonte:
    kind = "mc_post"

    def __init__(self, db, texto_max_chars: int = TEXTO_MAX_CHARS_DEFAULT) -> None:
        self._db = db
        self._max = texto_max_chars

    def _overlap_ids(self, org_id: str, marca_id: str) -> set[str]:
        """mc_post ids already reachable through a connected Instagram account."""
        published = _published_posts(self._db, org_id, marca_id)
        if not published:
            return set()
        accounts = [
            a["id"] for a in (
                self._db.table("integration_accounts").select("id")
                .eq("org_id", org_id).eq("marca_id", marca_id)
                .eq("provider", INSTAGRAM_PROVIDER).eq("status", "validated").execute().data
            ) or []
        ]
        if not accounts:
            return set()
        media_ids = [p["published_media_id"] for p in published]
        present: set[str] = set()
        for acc_chunk in _batched(accounts):
            for chunk in _batched(media_ids):
                present.update(
                    str(r["ig_media_id"]) for r in (
                        self._db.table("ig_media").select("ig_media_id")
                        .eq("org_id", org_id).in_("account_id", acc_chunk)
                        .in_("ig_media_id", chunk).execute().data
                    ) or []
                )
        return {p["id"] for p in published if p["published_media_id"] in present}

    def contas(self, org_id, marca_id):
        kits = _kit_ids(self._db, org_id, marca_id)
        total = 0
        for chunk in _batched(kits):
            total += self._db.table("mc_posts").select("id", count="exact") \
                .eq("org_id", org_id).in_("brand_kit_id", chunk).limit(1).execute().count or 0
        total -= len(self._overlap_ids(org_id, marca_id))
        return [{"account_id": None, "label": "Posts criados", "total_posts": max(total, 0),
                 "last_synced_at": None}]

    def _to_posts(self, org_id: str, rows: list[dict]) -> list[PostFonte]:
        parts = _mc_text_parts(self._db, org_id, rows)
        out = []
        for r in rows:
            texto = _join_text(parts[r["id"]], self._max)
            out.append(PostFonte(
                kind=self.kind, account_id=None, id=r["id"], url=r.get("published_permalink"),
                thumbnail_url=None, published_at=_iso(r.get("published_at") or r.get("created_at")),
                texto=texto, analisavel=_analisavel(texto), plays=None, likes=None, comments=None,
                extra={"published": bool(r.get("published_media_id"))},
            ))
        return out

    def listar(self, org_id, marca_id, *, account_id, cursor, limit, busca):
        kits = _kit_ids(self._db, org_id, marca_id)
        if not kits:
            return [], None
        overlap = self._overlap_ids(org_id, marca_id)
        cache: dict[str, PostFonte] = {}

        def fetch(cur, n):
            q = self._db.table("mc_posts").select(_MC_COLUMNS).eq("org_id", org_id).in_("brand_kit_id", kits)
            if cur:
                ts, pid = decode_cursor(cur)
                q = q.or_(f'created_at.lt."{ts}",and(created_at.eq."{ts}",id.lt."{pid}")')
            rows = (q.order("created_at", desc=True).order("id", desc=True).limit(n).execute().data) or []
            keep = [r for r in rows if r["id"] not in overlap]
            cache.update({p.id: p for p in self._to_posts(org_id, keep)})
            nxt = "more" if len(rows) >= n else None
            return rows, nxt

        return _collect_page(
            fetch, lambda r: cache.get(r["id"]),
            lambda r: encode_cursor(_iso(r["created_at"]), r["id"]),
            cursor=cursor, limit=limit, busca=busca,
        )

    def obter(self, org_id, marca_id, refs):
        kits = _kit_ids(self._db, org_id, marca_id)
        ids = [str(i) for _, i in refs]
        if not kits or not ids:
            return {}
        overlap = self._overlap_ids(org_id, marca_id)
        rows: list[dict] = []
        for chunk in _batched(ids):
            rows.extend(
                self._db.table("mc_posts").select(_MC_COLUMNS).eq("org_id", org_id)
                .in_("brand_kit_id", kits).in_("id", chunk).execute().data or []
            )
        return {(None, p.id): p for p in self._to_posts(org_id, [r for r in rows if r["id"] not in overlap])}


FONTES: dict[str, Callable[[Any], FonteExtracao]] = {
    "instagram_media": InstagramFonte,
    "youtube_video": YoutubeFonte,
    "mc_post": McPostFonte,
}


__all__ = [
    "FONTES", "FonteExtracao", "InvalidCursor", "MIN_TEXTO_CHARS", "PostFonte",
    "InstagramFonte", "YoutubeFonte", "McPostFonte",
]
