"""Supabase-backed VectorStore via REST/RPC (httpx).

Written but NOT exercised in automated tests — the supervisor applies the
migration to live Supabase and exercises this adapter manually.

Schema assumed (see backend/migrations/001_knowledge_extractor.sql):
  - Table : ``knowledge_extractor.kb_chunk``
  - RPC   : ``knowledge_extractor.match_kb(query_embedding, match_count)``

Auth: Supabase service-role key passed as ``SUPABASE_SERVICE_ROLE_KEY``
(settings). Uses ``httpx.AsyncClient`` — no additional SDKs.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.integrations.vectors.types import KBChunk, KBHit


class SupabaseVectorStore:
    """Real VectorStore backed by Supabase pgvector via REST + RPC.

    Parameters
    ----------
    url:
        Supabase project URL, e.g. ``https://<ref>.supabase.co``.
    service_role_key:
        Supabase service-role key (bypasses RLS — never expose client-side).
    """

    def __init__(self, *, url: str, service_role_key: str) -> None:
        self._url = url.rstrip("/")
        self._headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }

    # ── VectorStore protocol ──────────────────────────────────────────────────

    async def upsert(
        self,
        chunks: list[tuple[KBChunk, list[float]]],
    ) -> int:
        """Upsert (chunk, embedding) pairs into ``knowledge_extractor.kb_chunk``.

        Uses Supabase's ``POST /rest/v1/knowledge_extractor.kb_chunk`` with
        ``Prefer: resolution=merge-duplicates`` to perform an ON CONFLICT DO UPDATE
        on the primary key (``id``).
        """
        if not chunks:
            return 0

        # Store embedding as part of the row.  The table column is vector(1536)
        # so Supabase accepts a JSON array of floats.
        rows: list[dict[str, Any]] = [
            {
                "id": chunk.id,
                "document_id": chunk.document_id,
                "content": chunk.content,
                "module": chunk.module,
                "confidence": chunk.confidence,
                "embedding": emb,
            }
            for chunk, emb in chunks
        ]

        upsert_headers = {
            **self._headers,
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._url}/rest/v1/kb_chunk",
                headers=upsert_headers,
                content=json.dumps(rows),
                params={"schema": "knowledge_extractor"},
            )
            resp.raise_for_status()

        return len(rows)

    async def query(
        self,
        embedding: list[float],
        k: int = 5,
    ) -> list[KBHit]:
        """Call the ``match_kb`` RPC and return ranked KBHit objects.

        The RPC is defined in the migration as:
            match_kb(query_embedding vector(1536), match_count int)
            → TABLE(id, document_id, content, module, confidence, similarity)
        """
        payload = {
            "query_embedding": embedding,
            "match_count": k,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._url}/rest/v1/rpc/match_kb",
                headers={**self._headers, "Prefer": "return=representation"},
                content=json.dumps(payload),
            )
            resp.raise_for_status()
            rows: list[dict[str, Any]] = resp.json()

        hits: list[KBHit] = []
        for row in rows:
            chunk = KBChunk(
                id=row["id"],
                document_id=row["document_id"],
                content=row["content"],
                module=row["module"],
                confidence=float(row.get("confidence", 1.0)),
            )
            hits.append(KBHit(chunk=chunk, score=float(row["similarity"])))

        return hits


__all__ = ["SupabaseVectorStore"]
