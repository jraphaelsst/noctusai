"""Persistent local VectorStore — offline dev backend (no Supabase, no network).

Embeds once (via the LLM seam at ingest time), caches each (chunk, embedding) to a
JSON file on disk, loads it on init, and answers queries with in-memory cosine
similarity. Same ``VectorStore`` protocol as Fake/Supabase, so moving to the live
Supabase KB later is a factory swap — the callers (agents) never change.

The cache file is gitignored (generated artifact); rebuild it with ``cli kb-build``.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.integrations.vectors.fake import _cosine
from app.integrations.vectors.types import KBChunk, KBHit


class LocalVectorStore:
    """File-backed VectorStore. Persists on upsert, loads on construction."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._store: dict[str, tuple[KBChunk, list[float]]] = {}
        self._load()

    # ── persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.exists():
            return
        data = json.loads(self._path.read_text(encoding="utf-8"))
        for row in data.get("chunks", []):
            chunk = KBChunk(
                id=row["id"],
                document_id=row["document_id"],
                content=row["content"],
                module=row["module"],
                confidence=float(row.get("confidence", 1.0)),
            )
            self._store[chunk.id] = (chunk, row["embedding"])

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "id": c.id,
                "document_id": c.document_id,
                "content": c.content,
                "module": c.module,
                "confidence": c.confidence,
                "embedding": emb,
            }
            for c, emb in self._store.values()
        ]
        self._path.write_text(json.dumps({"chunks": rows}, ensure_ascii=False), encoding="utf-8")

    # ── VectorStore protocol ──────────────────────────────────────────────────

    async def upsert(self, chunks: list[tuple[KBChunk, list[float]]]) -> int:
        await asyncio.sleep(0)
        for chunk, embedding in chunks:
            self._store[chunk.id] = (chunk, embedding)
        self._save()
        return len(chunks)

    async def query(self, embedding: list[float], k: int = 5) -> list[KBHit]:
        await asyncio.sleep(0)
        scored = [
            KBHit(chunk=chunk, score=_cosine(embedding, stored_emb))
            for chunk, stored_emb in self._store.values()
        ]
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:k]

    # ── introspection ─────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._store)


__all__ = ["LocalVectorStore"]
