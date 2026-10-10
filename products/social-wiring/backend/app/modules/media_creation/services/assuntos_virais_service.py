"""Assuntos Virais — per-marca viral topics with their source posts.

Pure data service over the PostgREST client. Every read/write is org-scoped
AND marca-scoped; ``rejected`` topics are soft (kept as dedupe memory) and
never returned. ``total_plays`` is the sum of the sources' plays (NULLs
skipped) and is recomputed whenever a source is added.

``salvar_extraidos`` is the entry point for the extraction handler (BE-3).
It takes ``PostFonte``-shaped inputs, typed here with the minimal local
:class:`PostLike` Protocol so this module does not depend on
``pesquisa_fontes.py`` (built in parallel by another slice).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Callable, Optional, Protocol, Sequence

from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.persistence.table_reads import PAGE_SIZE, batched

from app.modules.media_creation.pesquisa_wave2_constants import VIRAL_TOPIC_MAX_CHARS
from app.modules.media_creation.services.pesquisa_service import PesquisaError

logger = logging.getLogger(__name__)

TOPICS = "cs_viral_topics"
SOURCES = "cs_viral_topic_sources"
TOPIC_COLS = "id,marca_id,topic,status,origin,total_plays,created_at"
SOURCE_FIELDS = (
    "source_kind", "account_id", "source_id", "url", "thumbnail_url",
    "published_at", "plays", "likes", "comments", "excerpt",
)
SOURCE_COLS = ",".join(SOURCE_FIELDS)


class PostLike(Protocol):
    """The slice of ``pesquisa_fontes.PostFonte`` this service reads."""

    @property
    def kind(self) -> str: ...
    @property
    def account_id(self) -> Optional[str]: ...
    @property
    def id(self) -> str: ...
    @property
    def url(self) -> Optional[str]: ...
    @property
    def thumbnail_url(self) -> Optional[str]: ...
    @property
    def published_at(self) -> Optional[str]: ...
    @property
    def plays(self) -> Optional[int]: ...
    @property
    def likes(self) -> Optional[int]: ...
    @property
    def comments(self) -> Optional[int]: ...


#: Optional hook refreshing ``url``/``thumbnail_url`` of source rows from the
#: live source post (IG CDN URLs expire). ``rows -> rows``; wired by the
#: caller once the sources seam exists. ``None`` = return the snapshot as is.
SourceRefresher = Callable[[str, str, list[dict[str, Any]]], list[dict[str, Any]]]


class AssuntosViraisService:
    def __init__(
        self, db, org_id: str, user_id: Optional[str] = None,
        source_refresher: Optional[SourceRefresher] = None,
    ):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id
        self.source_refresher = source_refresher

    # ── guards ──────────────────────────────────────────────────────────

    def assert_marca(self, marca_id: str) -> None:
        rows = (
            self.db.table("marcas").select("id")
            .eq("id", marca_id).eq("org_id", self.org_id).execute().data
        )
        if not rows:
            raise PesquisaError(404, "Marca não encontrada")

    def _topics(self):
        return self.db.table(TOPICS)

    def _sources(self):
        return self.db.table(SOURCES)

    def _get_topic(self, topic_id: str) -> dict[str, Any]:
        rows = (
            self._topics().select(TOPIC_COLS)
            .eq("id", topic_id).eq("org_id", self.org_id).neq("status", "rejected")
            .execute().data
        )
        if not rows:
            raise PesquisaError(404, "Assunto não encontrado")
        return rows[0]

    # ── shaping ─────────────────────────────────────────────────────────

    def _with_counts(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for chunk in batched([r["id"] for r in rows]):
            def page(start: int, end: int, _chunk=chunk):
                return (
                    self._sources().select("id,topic_id")
                    .eq("org_id", self.org_id).in_("topic_id", _chunk)
                    .order("id").range(start, end).execute().data
                )
            for s in iter_paged_rows(page, page_size=PAGE_SIZE, label="cs_viral_topic_sources count"):
                counts[s["topic_id"]] = counts.get(s["topic_id"], 0) + 1
        return [{**r, "fontes_count": counts.get(r["id"], 0)} for r in rows]

    def _one(self, row: dict[str, Any]) -> dict[str, Any]:
        return self._with_counts([row])[0]

    # ── reads ───────────────────────────────────────────────────────────

    def list_topics(
        self, marca_id: str, *, status: str, sort: str, limit: int, offset: int,
    ) -> dict[str, Any]:
        self.assert_marca(marca_id)
        q = (
            self._topics().select(TOPIC_COLS, count="exact")
            .eq("org_id", self.org_id).eq("marca_id", marca_id).eq("status", status)
        )
        if sort == "plays":
            q = q.order("total_plays", desc=True, nullsfirst=False)
        q = q.order("created_at", desc=True).order("id").range(offset, offset + limit - 1)
        res = q.execute()
        rows = res.data or []
        total = res.count if getattr(res, "count", None) is not None else len(rows)
        return {"items": self._with_counts(rows), "total": total}

    def counts(self, marca_id: str) -> dict[str, int]:
        self.assert_marca(marca_id)

        def page(start: int, end: int):
            return (
                self._topics().select("id,status")
                .eq("org_id", self.org_id).eq("marca_id", marca_id)
                .neq("status", "rejected").order("id").range(start, end).execute().data
            )

        out = {"approved": 0, "pending": 0}
        for row in iter_paged_rows(page, page_size=PAGE_SIZE, label="cs_viral_topics counts"):
            out[row["status"]] += 1
        return out

    def list_sources(self, topic_id: str) -> list[dict[str, Any]]:
        topic = self._get_topic(topic_id)

        def page(start: int, end: int):
            return (
                self._sources().select(SOURCE_COLS)
                .eq("org_id", self.org_id).eq("topic_id", topic_id)
                .order("id").range(start, end).execute().data
            )

        rows = [
            {k: r.get(k) for k in SOURCE_FIELDS}
            for r in iter_paged_rows(page, page_size=PAGE_SIZE, label="cs_viral_topic_sources")
        ]
        rows.sort(key=lambda r: (r.get("plays") is None, -(r.get("plays") or 0)))
        if self.source_refresher is not None:
            try:
                rows = self.source_refresher(self.org_id, topic["marca_id"], rows)
            except Exception as exc:  # noqa: BLE001 - snapshot is still valid
                logger.warning("assuntos virais: source refresh failed, using snapshot: %s", exc)
        return rows

    # ── writes ──────────────────────────────────────────────────────────

    def _existing(self, marca_id: str) -> dict[str, dict[str, Any]]:
        def page(start: int, end: int):
            return (
                self._topics().select("id,topic,status,origin,total_plays")
                .eq("org_id", self.org_id).eq("marca_id", marca_id)
                .order("id").range(start, end).execute().data
            )

        return {
            r["topic"].lower(): r
            for r in iter_paged_rows(page, page_size=PAGE_SIZE, label="cs_viral_topics dedupe")
        }

    def add_manual(self, marca_id: str, topics: list[str]) -> dict[str, Any]:
        """Manual add: approved, ``total_plays`` NULL. A rejected duplicate
        flips back to approved; any other duplicate is skipped."""
        self.assert_marca(marca_id)
        existing = self._existing(marca_id)
        saved: list[dict[str, Any]] = []
        skipped = 0
        for topic in topics:
            key = topic.lower()
            prior = existing.get(key)
            if prior is not None:
                if prior["status"] == "rejected":
                    upd = (
                        self._topics().update({"status": "approved", "origin": "manual"})
                        .eq("id", prior["id"]).eq("org_id", self.org_id).execute().data
                    )
                    if upd:
                        existing[key] = {**prior, "status": "approved"}
                        saved.append(upd[0])
                        continue
                skipped += 1
                continue
            res = self._topics().insert({
                "id": str(uuid.uuid4()), "org_id": self.org_id, "marca_id": marca_id,
                "topic": topic, "status": "approved", "origin": "manual",
                "total_plays": None, "created_by": self.user_id,
            }).execute().data
            if res:
                existing[key] = res[0]
                saved.append(res[0])
        return {
            "saved": len(saved), "skipped": skipped,
            "items": self._with_counts(saved),
        }

    def _recompute_total_plays(self, topic_id: str) -> Optional[int]:
        def page(start: int, end: int):
            return (
                self._sources().select("id,plays")
                .eq("org_id", self.org_id).eq("topic_id", topic_id)
                .order("id").range(start, end).execute().data
            )

        plays = [
            r["plays"]
            for r in iter_paged_rows(page, page_size=PAGE_SIZE, label="cs_viral_topic_sources plays")
            if r.get("plays") is not None
        ]
        total = sum(plays) if plays else None
        self._topics().update({"total_plays": total}).eq("id", topic_id).eq(
            "org_id", self.org_id
        ).execute()
        return total

    def _add_source(
        self, topic_id: str, extracao_id: Optional[str], post: PostLike, excerpt: Optional[str],
    ) -> bool:
        """Insert the source unless the same post is already attached."""
        q = (
            self._sources().select("id")
            .eq("org_id", self.org_id).eq("topic_id", topic_id)
            .eq("source_kind", post.kind).eq("source_id", post.id)
        )
        q = q.is_("account_id", "null") if post.account_id is None else q.eq("account_id", post.account_id)
        if q.execute().data:
            return False
        self._sources().insert({
            "id": str(uuid.uuid4()), "org_id": self.org_id, "topic_id": topic_id,
            "source_kind": post.kind, "account_id": post.account_id, "source_id": post.id,
            "url": post.url, "thumbnail_url": post.thumbnail_url,
            "published_at": post.published_at,
            "plays": post.plays, "likes": post.likes, "comments": post.comments,
            "excerpt": excerpt, "extracao_id": extracao_id,
        }).execute()
        return True

    def salvar_extraidos(
        self, marca_id: str, extracao_id: Optional[str],
        topicos: Sequence[tuple[str, PostLike, Optional[str]]],
    ) -> dict[str, int]:
        """Persist extracted ``(topic, post, excerpt)`` triples as pending
        topics with their source. A duplicate topic (any status) is skipped
        but still gains the new source and a recomputed ``total_plays``."""
        self.assert_marca(marca_id)
        existing = self._existing(marca_id)
        saved = skipped = 0
        for raw, post, excerpt in topicos:
            topic = (raw or "").strip()
            if not topic or len(topic) > VIRAL_TOPIC_MAX_CHARS:
                skipped += 1
                continue
            key = topic.lower()
            prior = existing.get(key)
            if prior is not None:
                if self._add_source(prior["id"], extracao_id, post, excerpt):
                    self._recompute_total_plays(prior["id"])
                skipped += 1
                continue
            res = self._topics().insert({
                "id": str(uuid.uuid4()), "org_id": self.org_id, "marca_id": marca_id,
                "topic": topic, "status": "pending", "origin": "extraction",
                "total_plays": None, "created_by": self.user_id,
            }).execute().data
            if not res:
                skipped += 1
                continue
            existing[key] = res[0]
            self._add_source(res[0]["id"], extracao_id, post, excerpt)
            self._recompute_total_plays(res[0]["id"])
            saved += 1
        return {"saved": saved, "skipped": skipped}

    def _set_status(self, topic: dict[str, Any], status: str, allowed_from: tuple[str, ...]):
        if topic["status"] not in allowed_from:
            return self._one(topic)
        res = (
            self._topics().update({"status": status})
            .eq("id", topic["id"]).eq("org_id", self.org_id).execute().data
        )
        return self._one(res[0] if res else topic)

    def approve(self, topic_id: str) -> dict[str, Any]:
        return self._set_status(self._get_topic(topic_id), "approved", ("pending",))

    def reject(self, topic_id: str) -> dict[str, Any]:
        return self._set_status(self._get_topic(topic_id), "rejected", ("pending", "approved"))

    def delete(self, topic_id: str) -> None:
        rows = (
            self._topics().select("id").eq("id", topic_id).eq("org_id", self.org_id).execute().data
        )
        if not rows:
            raise PesquisaError(404, "Assunto não encontrado")
        self._topics().delete().eq("id", topic_id).eq("org_id", self.org_id).execute()

    def bulk(self, marca_id: str, action: str, ids: list[str]) -> int:
        self.assert_marca(marca_id)
        affected = 0
        for chunk in batched(sorted(set(ids))):
            base = lambda q: q.in_("id", chunk).eq("org_id", self.org_id).eq("marca_id", marca_id)  # noqa: E731
            if action == "delete":
                affected += len(base(self._topics().delete()).execute().data or [])
            elif action == "approve":
                affected += len(
                    base(self._topics().update({"status": "approved"})).eq("status", "pending")
                    .execute().data or []
                )
            else:
                affected += len(
                    base(self._topics().update({"status": "rejected"})).neq("status", "rejected")
                    .execute().data or []
                )
        return affected

    def empty(self, marca_id: str, status: str) -> int:
        """Hard-delete one status only; rejected rows stay as dedupe memory."""
        self.assert_marca(marca_id)
        res = (
            self._topics().delete()
            .eq("org_id", self.org_id).eq("marca_id", marca_id).eq("status", status)
            .execute().data
        )
        return len(res or [])
